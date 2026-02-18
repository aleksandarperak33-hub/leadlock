"""
Stripe billing service — subscription management for LeadLock clients.

Handles: customer creation, checkout sessions, billing portal, webhook processing.
All Stripe calls are synchronous and run via run_in_executor to avoid blocking
the asyncio event loop.
"""
import asyncio
import logging
from typing import Optional

from src.config import get_settings

logger = logging.getLogger(__name__)

# Plan name mapping
PLAN_NAMES = {
    "starter": "Starter",
    "pro": "Professional",
    "business": "Business",
}

PLAN_AMOUNTS = {
    "starter": "$297",
    "pro": "$597",
    "business": "$1,497",
}

# Stripe API timeout (seconds)
STRIPE_API_TIMEOUT = 10


def _get_stripe():
    """Get configured Stripe module with per-request API key. Raises if not configured."""
    import stripe
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise ValueError("Stripe secret key not configured")
    stripe.api_key = settings.stripe_secret_key
    stripe.max_network_retries = 1
    return stripe


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous Stripe SDK call in the default thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _price_id_to_plan(price_id: str) -> str:
    """Map a Stripe price ID to a plan slug."""
    settings = get_settings()
    mapping = {
        settings.stripe_price_starter: "starter",
        settings.stripe_price_pro: "pro",
        settings.stripe_price_business: "business",
    }
    return mapping.get(price_id, "unknown")


async def create_customer(
    client_id: str,
    email: str,
    business_name: str,
) -> dict:
    """
    Create a Stripe customer for a LeadLock client.

    Returns: {"customer_id": str, "error": str|None}
    """
    try:
        stripe = _get_stripe()
        customer = await _run_sync(
            stripe.Customer.create,
            email=email,
            name=business_name,
            metadata={"leadlock_client_id": client_id},
        )
        logger.info(
            "Stripe customer created: %s for client %s",
            customer.id, client_id[:8],
        )
        return {"customer_id": customer.id, "error": None}
    except Exception as e:
        logger.error("Stripe customer creation failed: %s", str(e))
        return {"customer_id": None, "error": str(e)}


async def create_checkout_session(
    client_id: str,
    stripe_customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    """
    Create a Stripe Checkout session for subscription.

    Returns: {"session_url": str, "session_id": str, "error": str|None}
    """
    try:
        stripe = _get_stripe()
        session = await _run_sync(
            stripe.checkout.Session.create,
            customer=stripe_customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"leadlock_client_id": client_id},
            subscription_data={
                "metadata": {"leadlock_client_id": client_id},
            },
        )
        logger.info(
            "Stripe checkout session created: %s for client %s",
            session.id, client_id[:8],
        )
        return {"session_url": session.url, "session_id": session.id, "error": None}
    except Exception as e:
        logger.error("Stripe checkout creation failed: %s", str(e))
        return {"session_url": None, "session_id": None, "error": str(e)}


async def create_billing_portal_session(
    stripe_customer_id: str,
    return_url: str,
) -> dict:
    """
    Create a Stripe Billing Portal session for managing subscription.

    Returns: {"portal_url": str, "error": str|None}
    """
    try:
        stripe = _get_stripe()
        session = await _run_sync(
            stripe.billing_portal.Session.create,
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return {"portal_url": session.url, "error": None}
    except Exception as e:
        logger.error("Stripe portal session failed: %s", str(e))
        return {"portal_url": None, "error": str(e)}


async def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Process a Stripe webhook event.
    Verifies signature, then dispatches to the appropriate handler.

    Returns: {"event_type": str, "handled": bool, "error": str|None}
    """
    try:
        stripe = _get_stripe()
    except ValueError as e:
        logger.error("Stripe not configured: %s", str(e))
        return {"event_type": None, "handled": False, "error": str(e)}

    settings = get_settings()
    try:
        event = await _run_sync(
            stripe.Webhook.construct_event,
            payload, sig_header, settings.stripe_webhook_secret,
        )
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook signature verification failed")
        return {"event_type": None, "handled": False, "error": "Invalid signature"}
    except Exception as e:
        logger.error("Stripe webhook parsing failed: %s", str(e))
        return {"event_type": None, "handled": False, "error": str(e)}

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)
    elif event_type == "invoice.paid":
        await _handle_invoice_paid(data)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)
    else:
        logger.info("Unhandled Stripe event type: %s", event_type)
        return {"event_type": event_type, "handled": False, "error": None}

    return {"event_type": event_type, "handled": True, "error": None}


async def _handle_checkout_completed(session: dict) -> None:
    """Handle successful checkout — activate subscription."""
    client_id = session.get("metadata", {}).get("leadlock_client_id")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    if not client_id:
        logger.warning("Checkout completed without client_id in metadata")
        return

    from src.database import async_session_factory
    from src.models.client import Client
    from sqlalchemy import select
    import uuid

    dashboard_email = None
    plan_slug = "unknown"

    # Fetch subscription from Stripe BEFORE acquiring DB session to avoid
    # holding the connection open during a network call
    try:
        stripe = _get_stripe()
        sub = await _run_sync(stripe.Subscription.retrieve, subscription_id)
        price_id = sub["items"]["data"][0]["price"]["id"] if sub["items"]["data"] else ""
        plan_slug = _price_id_to_plan(price_id)
    except Exception as e:
        logger.warning(
            "Failed to retrieve Stripe subscription %s: %s. "
            "Proceeding without tier sync.", subscription_id, str(e),
        )

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(Client.id == uuid.UUID(client_id))
        )
        client = result.scalar_one_or_none()
        if not client:
            logger.error("Checkout completed for unknown client: %s", client_id[:8])
            return

        client.stripe_customer_id = customer_id
        client.stripe_subscription_id = subscription_id
        client.billing_status = "active"

        if plan_slug != "unknown":
            client.tier = plan_slug
            logger.info("Client %s tier set to %s", client_id[:8], plan_slug)

        # Capture values before session closes to avoid DetachedInstanceError
        dashboard_email = client.dashboard_email

        await db.commit()

    logger.info("Subscription activated for client %s", client_id[:8])

    # Send confirmation email (using captured values, session is closed)
    if dashboard_email and plan_slug != "unknown":
        plan_name = PLAN_NAMES.get(plan_slug, "Unknown")
        amount = PLAN_AMOUNTS.get(plan_slug, "N/A")

        from src.services.transactional_email import send_subscription_confirmation
        await send_subscription_confirmation(dashboard_email, plan_name, amount)


async def _handle_invoice_paid(invoice: dict) -> None:
    """Handle successful recurring payment."""
    customer_id = invoice.get("customer")
    if not customer_id:
        return

    from src.database import async_session_factory
    from src.models.client import Client
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(Client.stripe_customer_id == customer_id)
        )
        client = result.scalar_one_or_none()
        if client and client.billing_status != "active":
            client.billing_status = "active"
            await db.commit()
            logger.info("Payment received, billing status set to active for %s", client.business_name)


async def _handle_payment_failed(invoice: dict) -> None:
    """Handle failed payment — notify client."""
    customer_id = invoice.get("customer")
    if not customer_id:
        return

    from src.database import async_session_factory
    from src.models.client import Client
    from sqlalchemy import select

    dashboard_email = None
    business_name = None
    client_id = None

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(Client.stripe_customer_id == customer_id)
        )
        client = result.scalar_one_or_none()
        if not client:
            return

        client.billing_status = "past_due"

        # Capture values before session closes to avoid DetachedInstanceError
        dashboard_email = client.dashboard_email
        business_name = client.business_name
        client_id = str(client.id)

        await db.commit()

    logger.warning("Payment failed for client %s", business_name)

    # Send failure notification (using captured values, session is closed)
    if dashboard_email:
        from src.services.transactional_email import send_payment_failed
        await send_payment_failed(dashboard_email, business_name)

    # Alert ops team
    from src.utils.alerting import send_alert, AlertType
    await send_alert(
        "payment_failed",
        f"Payment failed for {business_name}",
        severity="warning",
        extra={"client_id": client_id},
    )


async def _handle_subscription_updated(subscription: dict) -> None:
    """Handle subscription changes (upgrade, downgrade, cancel at period end)."""
    customer_id = subscription.get("customer")
    status = subscription.get("status")

    if not customer_id:
        return

    from src.database import async_session_factory
    from src.models.client import Client
    from sqlalchemy import select

    status_mapping = {
        "active": "active",
        "past_due": "past_due",
        "trialing": "trial",
        "canceled": "canceled",
        "unpaid": "past_due",
    }

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(Client.stripe_customer_id == customer_id)
        )
        client = result.scalar_one_or_none()
        if client:
            new_status = status_mapping.get(status, client.billing_status)
            client.billing_status = new_status
            client.stripe_subscription_id = subscription.get("id")

            # Sync tier from subscription price (handles upgrades/downgrades)
            items = subscription.get("items", {}).get("data", [])
            if items:
                price_id = items[0].get("price", {}).get("id", "")
                plan_slug = _price_id_to_plan(price_id)
                if plan_slug != "unknown":
                    old_tier = client.tier
                    client.tier = plan_slug
                    if old_tier != plan_slug:
                        logger.info(
                            "Client %s tier changed: %s -> %s",
                            client.business_name, old_tier, plan_slug,
                        )

            await db.commit()
            logger.info(
                "Subscription updated for %s: %s", client.business_name, new_status,
            )


async def _handle_subscription_deleted(subscription: dict) -> None:
    """Handle subscription cancellation."""
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    from src.database import async_session_factory
    from src.models.client import Client
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(Client).where(Client.stripe_customer_id == customer_id)
        )
        client = result.scalar_one_or_none()
        if client:
            client.billing_status = "canceled"
            client.stripe_subscription_id = None
            await db.commit()
            logger.info("Subscription canceled for %s", client.business_name)
