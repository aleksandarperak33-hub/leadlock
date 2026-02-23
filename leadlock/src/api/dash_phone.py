"""
Dashboard phone provisioning and business registration endpoints.
Handles Twilio number search/provision, 10DLC/toll-free registration.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.api.dash_auth import get_current_client
from src.models.client import Client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])


# === PHONE PROVISIONING ===

@router.get("/api/v1/settings/available-numbers")
async def search_available_numbers(
    area_code: str = Query(default="", min_length=3, max_length=3),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Search for available phone numbers by area code."""
    if not area_code or not area_code.isdigit():
        raise HTTPException(status_code=400, detail="Valid 3-digit area code is required")

    try:
        from src.services.sms import search_available_numbers
        numbers = await search_available_numbers(area_code)
        return {"numbers": numbers, "area_code": area_code}
    except Exception as e:
        logger.error("Number search failed: %s", str(e))
        raise HTTPException(status_code=502, detail="Number search failed. Please try again.")


@router.post("/api/v1/settings/provision-number")
async def provision_number(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Provision a phone number for the client."""
    if client.twilio_phone:
        raise HTTPException(status_code=400, detail="A phone number is already provisioned")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    phone_number = (payload.get("phone_number") or "").strip()
    if not phone_number:
        raise HTTPException(status_code=400, detail="phone_number is required")

    try:
        from src.services.sms import provision_phone_number
        result = await provision_phone_number(
            phone_number, str(client.id), client.business_name,
        )

        if result.get("error"):
            raise HTTPException(status_code=502, detail=result["error"])

        client.twilio_phone = result["phone_number"]
        client.twilio_phone_sid = result["phone_sid"]
        client.twilio_messaging_service_sid = result.get("messaging_service_sid")
        client.ten_dlc_status = "collecting_info"

        # Auto-trigger toll-free verification if toll-free number
        if result.get("is_tollfree"):
            from src.services.twilio_registration import submit_tollfree_verification
            tf_result = await submit_tollfree_verification(
                phone_sid=result["phone_sid"],
                business_name=client.business_name,
                email=client.owner_email or client.dashboard_email or "",
                website=client.business_website,
            )
            if not tf_result["error"]:
                client.ten_dlc_status = "tf_verification_pending"
                client.ten_dlc_verification_sid = tf_result["result"]["verification_sid"]
                logger.info(
                    "Auto-triggered TF verification for %s",
                    client.business_name,
                )
            else:
                logger.warning(
                    "TF verification auto-trigger failed: %s",
                    tf_result["error"],
                )

        # Auto-trigger 10DLC if business info was pre-saved during onboarding
        elif client.business_type and not result.get("is_tollfree"):
            try:
                from src.services.twilio_registration import (
                    create_customer_profile,
                    submit_customer_profile,
                )
                email = client.owner_email or client.dashboard_email or ""
                address = client.business_address or {}
                profile_result = await create_customer_profile(
                    business_name=client.business_name,
                    email=email,
                    business_info={
                        "business_type": client.business_type,
                        "ein": client.business_ein or "",
                        "website": client.business_website or "",
                        "phone": client.owner_phone or "",
                        "street": address.get("street", ""),
                        "city": address.get("city", ""),
                        "state": address.get("state", ""),
                        "zip": address.get("zip", ""),
                    },
                )
                if not profile_result["error"]:
                    client.ten_dlc_profile_sid = profile_result["result"]["profile_sid"]
                    submit_result = await submit_customer_profile(
                        profile_result["result"]["profile_sid"],
                    )
                    client.ten_dlc_status = (
                        "profile_pending" if not submit_result["error"]
                        else "collecting_info"
                    )
                    logger.info(
                        "Auto-triggered 10DLC for %s (pre-saved business info)",
                        client.business_name,
                    )
            except Exception as e:
                logger.warning(
                    "Auto 10DLC trigger failed (non-blocking): %s", str(e),
                )

        await db.flush()

        logger.info("Phone provisioned for %s: %s", client.business_name, phone_number[:6] + "***")
        return {
            "status": "provisioned",
            "phone_number": result["phone_number"],
            "phone_sid": result["phone_sid"],
            "messaging_service_sid": result.get("messaging_service_sid"),
            "is_tollfree": result.get("is_tollfree", False),
            "ten_dlc_status": client.ten_dlc_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Phone provisioning failed: %s", str(e))
        raise HTTPException(status_code=502, detail="Phone provisioning failed. Please try again.")


# === BUSINESS REGISTRATION ===

@router.post("/api/v1/settings/business-registration")
async def submit_business_registration(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """
    Submit business information for 10DLC registration.
    Triggers the customer profile creation pipeline.
    """
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Validate required fields
    business_website = (payload.get("business_website") or "").strip()
    business_type = (payload.get("business_type") or "").strip()
    business_ein = (payload.get("business_ein") or "").strip()
    business_address = payload.get("business_address") or {}

    valid_types = {"sole_proprietorship", "llc", "corporation", "partnership"}
    if business_type and business_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"business_type must be one of: {', '.join(valid_types)}",
        )

    if not business_type:
        raise HTTPException(status_code=400, detail="business_type is required")

    if not client.twilio_phone:
        raise HTTPException(status_code=400, detail="Provision a phone number first")

    # Idempotency guard - don't re-create profile if already submitted
    if (
        client.ten_dlc_profile_sid
        and client.ten_dlc_status not in ("collecting_info", "profile_rejected")
    ):
        raise HTTPException(
            status_code=409,
            detail="Registration already in progress or completed",
        )

    # Save business info
    client.business_website = business_website or client.business_website
    client.business_type = business_type
    client.business_ein = business_ein or client.business_ein
    client.business_address = business_address or client.business_address

    # Trigger 10DLC profile creation
    from src.services.twilio_registration import create_customer_profile, submit_customer_profile

    email = client.owner_email or client.dashboard_email or ""
    address = business_address or {}

    profile_result = await create_customer_profile(
        business_name=client.business_name,
        email=email,
        business_info={
            "business_type": business_type,
            "ein": business_ein,
            "website": business_website,
            "phone": client.owner_phone or "",
            "street": address.get("street", ""),
            "city": address.get("city", ""),
            "state": address.get("state", ""),
            "zip": address.get("zip", ""),
        },
    )

    if profile_result["error"]:
        logger.error("Profile creation failed: %s", profile_result["error"])
        raise HTTPException(
            status_code=502,
            detail="Registration failed. Please verify your business information and try again.",
        )

    client.ten_dlc_profile_sid = profile_result["result"]["profile_sid"]

    # Submit profile for review
    submit_result = await submit_customer_profile(
        profile_result["result"]["profile_sid"],
    )
    if submit_result["error"]:
        logger.warning("Profile submission failed: %s", submit_result["error"])
        # Profile created but not submitted - poller can retry
        client.ten_dlc_status = "collecting_info"
    else:
        client.ten_dlc_status = "profile_pending"

    await db.flush()

    logger.info(
        "Business registration submitted for %s (status: %s)",
        client.business_name, client.ten_dlc_status,
    )
    return {
        "status": client.ten_dlc_status,
        "profile_sid": client.ten_dlc_profile_sid,
    }


@router.get("/api/v1/settings/registration-status")
async def get_registration_status(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get current 10DLC / toll-free registration status and guidance."""
    status = client.ten_dlc_status or "pending"

    # Map internal states to user-friendly status and next steps
    status_info = _get_registration_status_info(status, client)

    return {
        "ten_dlc_status": status,
        "display_status": status_info["display"],
        "description": status_info["description"],
        "next_step": status_info["next_step"],
        "estimated_time": status_info["estimated_time"],
        "has_phone": client.twilio_phone is not None,
        "has_business_info": client.business_type is not None,
        "is_tollfree": _check_is_tollfree(client.twilio_phone),
    }


# === HELPERS ===

def _mask_ein(ein: str | None) -> str | None:
    """Mask EIN for display - show only last 4 digits."""
    if not ein:
        return ein
    cleaned = ein.replace("-", "").replace(" ", "")
    if len(cleaned) <= 4:
        return ein
    return "***-**-" + cleaned[-4:]


def _check_is_tollfree(phone: str | None) -> bool:
    """Check if the client's phone is toll-free."""
    if not phone:
        return False
    from src.services.twilio_registration import is_tollfree
    return is_tollfree(phone)


def _get_registration_status_info(status: str, client) -> dict:
    """Map internal registration status to user-facing info."""
    info_map = {
        "pending": {
            "display": "Not Started",
            "description": "Provision a phone number to begin registration.",
            "next_step": "provision_number",
            "estimated_time": None,
        },
        "collecting_info": {
            "display": "Info Needed",
            "description": "We need your business details to register your number for SMS.",
            "next_step": "submit_business_info",
            "estimated_time": None,
        },
        "profile_pending": {
            "display": "In Review",
            "description": "Your business profile is being reviewed by Twilio.",
            "next_step": "wait",
            "estimated_time": "1-3 business days",
        },
        "profile_approved": {
            "display": "In Review",
            "description": "Profile approved. Brand registration in progress.",
            "next_step": "wait",
            "estimated_time": "1-2 business days",
        },
        "profile_rejected": {
            "display": "Action Required",
            "description": "Your business profile was rejected. Please update your information and resubmit.",
            "next_step": "resubmit_profile",
            "estimated_time": None,
        },
        "brand_pending": {
            "display": "In Review",
            "description": "Your brand is being registered with carriers.",
            "next_step": "wait",
            "estimated_time": "1-5 business days",
        },
        "brand_approved": {
            "display": "Almost Ready",
            "description": "Brand approved. Campaign registration in progress.",
            "next_step": "wait",
            "estimated_time": "1-2 business days",
        },
        "brand_rejected": {
            "display": "Action Required",
            "description": "Brand registration was rejected. Please contact support.",
            "next_step": "contact_support",
            "estimated_time": None,
        },
        "campaign_pending": {
            "display": "Almost Ready",
            "description": "Your messaging campaign is being reviewed.",
            "next_step": "wait",
            "estimated_time": "1-3 business days",
        },
        "campaign_rejected": {
            "display": "Action Required",
            "description": "Campaign registration was rejected. Please contact support.",
            "next_step": "contact_support",
            "estimated_time": None,
        },
        "tf_verification_pending": {
            "display": "In Review",
            "description": "Your toll-free number is being verified.",
            "next_step": "wait",
            "estimated_time": "1-3 business days",
        },
        "tf_rejected": {
            "display": "Action Required",
            "description": "Toll-free verification was rejected. Please contact support.",
            "next_step": "contact_support",
            "estimated_time": None,
        },
        "active": {
            "display": "Active",
            "description": "Your number is fully registered and ready to send SMS.",
            "next_step": None,
            "estimated_time": None,
        },
    }
    return info_map.get(status, info_map["pending"])
