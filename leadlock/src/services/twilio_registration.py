"""
Twilio A2P registration service - handles 10DLC and toll-free verification.

Registration state machine:
  collecting_info -> profile_pending -> profile_approved -> brand_pending -> brand_approved
    -> campaign_pending -> active

  Toll-free shortcut:
    collecting_info -> tf_verification_pending -> active

  Error states: profile_rejected, brand_rejected, campaign_rejected, tf_rejected

Each function returns {"result": ..., "error": str|None}.

All Twilio SDK calls are synchronous and run via run_in_executor to avoid
blocking the asyncio event loop.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Toll-free area codes
TOLLFREE_PREFIXES = {"800", "833", "844", "855", "866", "877", "888"}

# Registration states
TERMINAL_STATES = {
    "active", "profile_rejected", "brand_rejected",
    "campaign_rejected", "tf_rejected",
}
PENDING_STATES = {
    "collecting_info", "profile_pending", "profile_approved",
    "brand_pending", "brand_approved", "campaign_pending",
    "tf_verification_pending",
}

# Twilio SDK timeout (seconds)
TWILIO_API_TIMEOUT = 10


def is_tollfree(phone_number: str) -> bool:
    """Check if a phone number is toll-free based on area code."""
    digits = phone_number.lstrip("+")
    # US numbers: +1NXXNXXXXXX - area code starts at index 1
    if digits.startswith("1") and len(digits) >= 4:
        area_code = digits[1:4]
        return area_code in TOLLFREE_PREFIXES
    return False


def _get_twilio_client():
    """Create a Twilio REST client with configured timeout."""
    from twilio.rest import Client as TwilioClient
    from twilio.http.http_client import TwilioHttpClient
    from src.config import get_settings
    settings = get_settings()
    http_client = TwilioHttpClient(timeout=TWILIO_API_TIMEOUT)
    return TwilioClient(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        http_client=http_client,
    )


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in the default thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def create_messaging_service(
    client_id: str,
    business_name: str,
) -> dict:
    """
    Create a per-client Twilio Messaging Service.

    Returns: {"result": {"messaging_service_sid": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        service = await _run_sync(
            twilio.messaging.v1.services.create,
            friendly_name=f"LeadLock-{business_name[:30]}-{client_id[:8]}",
            inbound_request_url=None,
            use_inbound_webhook_on_number=True,
        )
        logger.info(
            "Messaging Service created: %s for client %s",
            service.sid, client_id[:8],
        )
        return {"result": {"messaging_service_sid": service.sid}, "error": None}
    except Exception as e:
        logger.error("Failed to create Messaging Service: %s", str(e))
        return {"result": None, "error": str(e)}


async def add_phone_to_messaging_service(
    messaging_service_sid: str,
    phone_sid: str,
) -> dict:
    """
    Attach a phone number to a Messaging Service.

    Returns: {"result": {"phone_sid": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        phone_number = await _run_sync(
            twilio.messaging.v1.services(
                messaging_service_sid
            ).phone_numbers.create,
            phone_number_sid=phone_sid,
        )
        logger.info(
            "Phone %s added to Messaging Service %s",
            phone_sid, messaging_service_sid,
        )
        return {"result": {"phone_sid": phone_number.sid}, "error": None}
    except Exception as e:
        logger.error(
            "Failed to add phone to Messaging Service: %s", str(e),
        )
        return {"result": None, "error": str(e)}


async def create_customer_profile(
    business_name: str,
    email: str,
    business_info: dict,
) -> dict:
    """
    Create a Secondary Customer Profile for 10DLC registration.
    business_info keys: business_type, ein, address, website, phone.

    Returns: {"result": {"profile_sid": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()

        # A2P Trust Hub Secondary Customer Profile
        profile = await _run_sync(
            twilio.trusthub.v1.customer_profiles.create,
            friendly_name=f"LeadLock-{business_name[:40]}",
            email=email,
            policy_sid="RNdfbf3fae0e1107f8abad0571f9b0e3a7",
        )
        logger.info("Customer profile created: %s", profile.sid)

        # Add business information as end-user
        end_user = await _run_sync(
            twilio.trusthub.v1.end_users.create,
            friendly_name=business_name,
            type="authorized_representative_1",
            attributes={
                "business_name": business_name,
                "business_type": business_info.get("business_type", "llc"),
                "ein": business_info.get("ein", ""),
                "email": email,
                "phone_number": business_info.get("phone", ""),
                "website": business_info.get("website", ""),
                "street_address": business_info.get("street", ""),
                "city": business_info.get("city", ""),
                "state": business_info.get("state", ""),
                "zip_code": business_info.get("zip", ""),
            },
        )

        # Attach end-user to profile
        await _run_sync(
            twilio.trusthub.v1.customer_profiles(
                profile.sid
            ).customer_profiles_entity_assignments.create,
            object_sid=end_user.sid,
        )

        return {"result": {"profile_sid": profile.sid}, "error": None}
    except Exception as e:
        logger.error("Failed to create customer profile: %s", str(e))
        return {"result": None, "error": str(e)}


async def submit_customer_profile(profile_sid: str) -> dict:
    """
    Submit a customer profile for Twilio review.

    Returns: {"result": {"status": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        evaluation = await _run_sync(
            twilio.trusthub.v1.customer_profiles(
                profile_sid
            ).customer_profiles_evaluations.create,
            policy_sid="RNdfbf3fae0e1107f8abad0571f9b0e3a7",
        )
        logger.info(
            "Customer profile %s submitted, status: %s",
            profile_sid, evaluation.status,
        )
        return {"result": {"status": evaluation.status}, "error": None}
    except Exception as e:
        logger.error("Failed to submit customer profile: %s", str(e))
        return {"result": None, "error": str(e)}


async def check_customer_profile_status(profile_sid: str) -> dict:
    """
    Poll the status of a customer profile.

    Returns: {"result": {"status": str}, "error": str|None}
    Status: "draft", "pending-review", "in-review", "twilio-approved", "twilio-rejected"
    """
    try:
        twilio = _get_twilio_client()
        profile = await _run_sync(
            twilio.trusthub.v1.customer_profiles(profile_sid).fetch,
        )
        logger.debug("Profile %s status: %s", profile_sid, profile.status)
        return {"result": {"status": profile.status}, "error": None}
    except Exception as e:
        logger.error("Failed to check profile status: %s", str(e))
        return {"result": None, "error": str(e)}


async def create_brand_registration(
    customer_profile_sid: str,
) -> dict:
    """
    Register an A2P brand with The Campaign Registry (TCR) via Twilio.

    Returns: {"result": {"brand_sid": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        brand = await _run_sync(
            twilio.messaging.v1.brand_registrations.create,
            customer_profile_bundle_sid=customer_profile_sid,
            a2p_profile_bundle_sid=customer_profile_sid,
        )
        logger.info("Brand registration created: %s", brand.sid)
        return {"result": {"brand_sid": brand.sid}, "error": None}
    except Exception as e:
        logger.error("Failed to create brand registration: %s", str(e))
        return {"result": None, "error": str(e)}


async def check_brand_status(brand_sid: str) -> dict:
    """
    Poll the status of a brand registration.

    Returns: {"result": {"status": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        brand = await _run_sync(
            twilio.messaging.v1.brand_registrations(brand_sid).fetch,
        )
        logger.debug("Brand %s status: %s", brand_sid, brand.status)
        return {"result": {"status": brand.status}, "error": None}
    except Exception as e:
        logger.error("Failed to check brand status: %s", str(e))
        return {"result": None, "error": str(e)}


async def create_campaign(
    brand_sid: str,
    messaging_service_sid: str,
    business_name: str,
) -> dict:
    """
    Register an A2P messaging campaign (use case) with TCR via Twilio.

    Returns: {"result": {"campaign_sid": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        campaign = await _run_sync(
            twilio.messaging.v1.services(
                messaging_service_sid
            ).us_app_to_person.create,
            brand_registration_sid=brand_sid,
            description=f"Lead response and appointment booking for {business_name}",
            message_flow=(
                "Homeowners submit service requests through web forms, ads, or phone calls. "
                "Our automated system sends an initial SMS response, qualifies the request "
                "through a brief conversation, and books an appointment."
            ),
            message_samples=[
                f"Hi! This is Sarah from {business_name}. We received your service request. "
                "What time works best for a technician visit?",
                f"Thanks for choosing {business_name}! Your appointment is confirmed for "
                "Thursday, March 6th between 9-11 AM. Reply STOP to opt out.",
            ],
            has_embedded_links=False,
            has_embedded_phone=False,
            opt_in_type="WEB_FORM",
        )
        logger.info("Campaign created: %s", campaign.sid)
        return {"result": {"campaign_sid": campaign.sid}, "error": None}
    except Exception as e:
        logger.error("Failed to create campaign: %s", str(e))
        return {"result": None, "error": str(e)}


async def check_campaign_status(
    campaign_sid: str,
    messaging_service_sid: str,
) -> dict:
    """
    Poll the status of a campaign registration.

    Returns: {"result": {"status": str}, "error": str|None}
    """
    try:
        twilio = _get_twilio_client()
        campaign = await _run_sync(
            twilio.messaging.v1.services(
                messaging_service_sid
            ).us_app_to_person(campaign_sid).fetch,
        )
        logger.debug(
            "Campaign %s status: %s",
            campaign_sid, campaign.campaign_status,
        )
        return {"result": {"status": campaign.campaign_status}, "error": None}
    except Exception as e:
        logger.error("Failed to check campaign status: %s", str(e))
        return {"result": None, "error": str(e)}


async def submit_tollfree_verification(
    phone_sid: str,
    business_name: str,
    email: str,
    website: Optional[str] = None,
    opt_in_image_urls: Optional[list[str]] = None,
) -> dict:
    """
    Submit a toll-free number for verification.

    Args:
        phone_sid: The Twilio phone number SID (PNxxxx).
        business_name: Business display name.
        email: Contact/notification email.
        website: Business website URL.
        opt_in_image_urls: URLs to screenshots showing SMS opt-in mechanism.

    Returns: {"result": {"verification_sid": str}, "error": str|None}
    """
    default_opt_in_urls = ["https://leadlock.org/sms-consent.svg"]

    try:
        twilio = _get_twilio_client()
        verification = await _run_sync(
            twilio.messaging.v1.tollfree_verifications.create,
            tollfree_phone_number_sid=phone_sid,
            business_name=business_name,
            business_contact_email=email,
            business_website=website or "",
            notification_email=email,
            use_case_categories=["CUSTOMER_CARE"],
            use_case_summary=(
                "Automated lead response and appointment booking for home services. "
                "Homeowners submit a service request through our web form at "
                "leadlock.org. The form includes a separate SMS consent checkbox "
                "with clear disclosure language. After opting in, they receive an "
                "initial SMS confirming their request, followed by up to 3 messages "
                "to qualify their needs and book an appointment. All messages include "
                "the business name and STOP opt-out instructions."
            ),
            production_message_sample=(
                f"Hi! This is Sarah from {business_name}. "
                "We got your request for service. "
                "Are you available Thursday between 9-11 AM? "
                "Reply STOP to opt out."
            ),
            opt_in_type="WEB_FORM",
            opt_in_image_urls=opt_in_image_urls or default_opt_in_urls,
            message_volume="1,000",
            additional_information=(
                "Consent flow: Homeowner fills out a service request form on our "
                "website (leadlock.org). The form has a SEPARATE checkbox (not "
                "pre-checked) that reads: 'I agree to receive SMS/text messages "
                "about my service request. Message frequency varies. Message and "
                "data rates may apply. Reply STOP to cancel at any time. Reply "
                "HELP for help.' The checkbox is visually highlighted and not "
                "bundled with other terms. Opt-in screenshot attached shows the "
                "exact form. After consent, the consumer receives: (1) an initial "
                "confirmation SMS with business name and STOP instructions, (2) up "
                "to 3 follow-up messages to qualify and book an appointment. No "
                "marketing messages are sent. AI disclosure included per CA SB 1001."
            ),
        )
        logger.info("Toll-free verification submitted: %s", verification.sid)
        return {"result": {"verification_sid": verification.sid}, "error": None}
    except Exception as e:
        logger.error("Failed to submit toll-free verification: %s", str(e))
        return {"result": None, "error": str(e)}


async def check_tollfree_status(verification_sid: str) -> dict:
    """
    Poll the status of a toll-free verification.

    Returns: {"result": {"status": str}, "error": str|None}
    Status: "PENDING_REVIEW", "IN_REVIEW", "TWILIO_APPROVED", "TWILIO_REJECTED"
    """
    try:
        twilio = _get_twilio_client()
        verification = await _run_sync(
            twilio.messaging.v1.tollfree_verifications(
                verification_sid
            ).fetch,
        )
        logger.debug(
            "TF verification %s status: %s",
            verification_sid, verification.status,
        )
        return {"result": {"status": verification.status}, "error": None}
    except Exception as e:
        logger.error("Failed to check toll-free status: %s", str(e))
        return {"result": None, "error": str(e)}
