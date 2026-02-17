"""
Billing API — Stripe checkout, billing portal, subscription status, and webhook.

The webhook endpoint has NO auth (Stripe signature verification only).
All other endpoints require JWT authentication.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.api.dashboard import get_current_client
from src.models.client import Client
from src.config import get_settings
from src.services import billing as billing_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["billing"])


@router.get("/api/v1/billing/plans")
async def get_plans():
    """Return available subscription plans with their Stripe price IDs."""
    settings = get_settings()
    return {
        "plans": [
            {"slug": "starter", "name": "Starter", "price": "$297", "price_id": settings.stripe_price_starter},
            {"slug": "pro", "name": "Professional", "price": "$597", "price_id": settings.stripe_price_pro, "popular": True},
            {"slug": "business", "name": "Business", "price": "$1,497", "price_id": settings.stripe_price_business},
        ]
    }


@router.post("/api/v1/billing/create-checkout")
async def create_checkout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Create a Stripe Checkout session for subscription."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    price_id = (payload.get("price_id") or "").strip()
    if not price_id:
        raise HTTPException(status_code=400, detail="price_id is required")

    settings = get_settings()
    valid_prices = {
        settings.stripe_price_starter,
        settings.stripe_price_pro,
        settings.stripe_price_business,
    }
    if price_id not in valid_prices:
        raise HTTPException(status_code=400, detail="Invalid price_id")

    # Ensure Stripe customer exists
    if not client.stripe_customer_id:
        result = await billing_service.create_customer(
            client_id=str(client.id),
            email=client.dashboard_email or client.owner_email or "",
            business_name=client.business_name,
        )
        if result["error"]:
            raise HTTPException(status_code=502, detail="Failed to create billing customer")
        client.stripe_customer_id = result["customer_id"]
        await db.flush()

    base_url = settings.app_base_url.rstrip("/")
    result = await billing_service.create_checkout_session(
        client_id=str(client.id),
        stripe_customer_id=client.stripe_customer_id,
        price_id=price_id,
        success_url=f"{base_url}/billing?success=true",
        cancel_url=f"{base_url}/billing?canceled=true",
    )

    if result["error"]:
        raise HTTPException(status_code=502, detail="Failed to create checkout session")

    return {"url": result["session_url"], "session_id": result["session_id"]}


@router.post("/api/v1/billing/portal")
async def billing_portal(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Create a Stripe Billing Portal session to manage subscription."""
    if not client.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Please subscribe first.")

    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")

    result = await billing_service.create_billing_portal_session(
        stripe_customer_id=client.stripe_customer_id,
        return_url=f"{base_url}/billing",
    )

    if result["error"]:
        raise HTTPException(status_code=502, detail="Failed to create billing portal session")

    return {"url": result["portal_url"]}


@router.get("/api/v1/billing/status")
async def billing_status(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get current billing/subscription status."""
    plan = "none"
    current_period_end = None

    if client.stripe_subscription_id:
        try:
            import stripe
            settings = get_settings()
            stripe.api_key = settings.stripe_secret_key
            sub = stripe.Subscription.retrieve(client.stripe_subscription_id)
            price_id = sub["items"]["data"][0]["price"]["id"] if sub["items"]["data"] else ""
            plan = billing_service._price_id_to_plan(price_id)
            current_period_end = sub.get("current_period_end")
        except Exception as e:
            logger.warning("Failed to fetch subscription details: %s", str(e))

    return {
        "billing_status": client.billing_status,
        "plan": plan,
        "stripe_customer_id": client.stripe_customer_id,
        "current_period_end": current_period_end,
        "trial_ends_at": client.trial_ends_at.isoformat() if hasattr(client, 'trial_ends_at') and client.trial_ends_at else None,
    }


@router.post("/api/v1/billing/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint. No JWT auth — uses Stripe signature verification.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    result = await billing_service.handle_webhook(payload, sig_header)

    if result["error"] == "Invalid signature":
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if result["error"]:
        logger.error("Webhook processing error: %s", result["error"])
        # Return 200 to prevent Stripe retries for processing errors
        return {"received": True, "error": result["error"]}

    return {"received": True, "event_type": result["event_type"]}
