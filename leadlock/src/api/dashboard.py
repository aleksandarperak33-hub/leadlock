"""
Dashboard API — all endpoints for the React client dashboard.
All endpoints require JWT authentication via Bearer token.
Includes lead actions, bookings, compliance, CSV export, auth flows, and phone provisioning.
"""
import csv
import io
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from src.database import get_db
from src.models.lead import Lead
from src.models.client import Client
from src.models.conversation import Conversation
from src.models.booking import Booking
from src.models.consent import ConsentRecord
from src.models.event_log import EventLog
from src.models.followup import FollowupTask
from src.schemas.api_responses import (
    LoginRequest,
    LoginResponse,
    LeadSummary,
    LeadListResponse,
    MessageSummary,
    LeadDetailResponse,
    BookingDetail,
    ConsentDetail,
    EventSummary,
    DashboardMetrics,
    ActivityEvent,
    ComplianceSummary,
)
from src.services.reporting import get_dashboard_metrics

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dashboard"])
bearer_scheme = HTTPBearer()


# === RATE LIMITING ===

async def _check_auth_rate_limit(
    action: str,
    identifier: str,
    max_attempts: int = 5,
    window_seconds: int = 900,
) -> None:
    """Redis-based rate limiter for auth endpoints."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        key = f"leadlock:rate:{action}:{identifier}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        if count > max_attempts:
            raise HTTPException(
                status_code=429,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(window_seconds)},
            )
    except HTTPException:
        raise
    except Exception as e:
        # Fail open — don't block auth if Redis is down, but log it
        logger.warning("Rate limiting unavailable (Redis error): %s", str(e))


# === AUTH ===

@router.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate dashboard user and return JWT token."""
    # Rate limit: 5 attempts per email per 15 minutes
    await _check_auth_rate_limit("login", payload.email)

    result = await db.execute(
        select(Client).where(Client.dashboard_email == payload.email)
    )
    client = result.scalar_one_or_none()

    if not client or not client.dashboard_password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    import bcrypt
    if not bcrypt.checkpw(payload.password.encode(), client.dashboard_password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate JWT
    import jwt
    from src.config import get_settings
    settings = get_settings()

    token = jwt.encode(
        {
            "client_id": str(client.id),
            "is_admin": client.is_admin,
            "exp": datetime.now(timezone.utc) + timedelta(hours=settings.dashboard_jwt_expiry_hours),
        },
        settings.dashboard_jwt_secret or settings.app_secret_key,
        algorithm="HS256",
    )

    return LoginResponse(
        token=token,
        client_id=str(client.id),
        business_name=client.business_name,
        is_admin=client.is_admin,
    )


@router.post("/api/v1/auth/signup")
async def signup(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new client account and return JWT token."""
    # Rate limit: 3 signups per IP per hour
    client_ip = request.client.host if request.client else "unknown"
    await _check_auth_rate_limit("signup", client_ip, max_attempts=3, window_seconds=3600)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    business_name = (payload.get("business_name") or "").strip()
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    phone = (payload.get("phone") or "").strip()
    trade_type = (payload.get("trade_type") or "general").strip().lower()
    password = payload.get("password") or ""

    if not business_name:
        raise HTTPException(status_code=400, detail="Business name is required")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Check if email already registered
    existing = await db.execute(
        select(Client).where(Client.dashboard_email == email).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    import bcrypt
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    client = Client(
        business_name=business_name,
        trade_type=trade_type,
        dashboard_email=email,
        dashboard_password_hash=password_hash,
        owner_name=name,
        owner_email=email,
        owner_phone=phone,
        is_admin=False,
        billing_status="trial",
        onboarding_status="pending",
    )
    db.add(client)
    await db.flush()

    # Generate JWT
    import jwt
    from src.config import get_settings
    settings = get_settings()

    token = jwt.encode(
        {
            "client_id": str(client.id),
            "is_admin": False,
            "exp": datetime.now(timezone.utc) + timedelta(hours=settings.dashboard_jwt_expiry_hours),
        },
        settings.dashboard_jwt_secret or settings.app_secret_key,
        algorithm="HS256",
    )

    logger.info("New signup: %s (%s)", business_name, email[:20] + "***")

    # Send verification email (fire-and-forget, don't block signup)
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        verify_token = secrets.token_urlsafe(32)
        await redis.setex(f"email_verify:{verify_token}", 86400, str(client.id))  # 24hr TTL

        from src.services.transactional_email import send_email_verification
        from src.config import get_settings as _get_settings
        s = _get_settings()
        verify_url = f"{s.app_base_url.rstrip('/')}/verify-email"
        await send_email_verification(email, verify_token, verify_url)
    except Exception as ve:
        logger.warning("Failed to send verification email on signup: %s", str(ve))

    return {
        "token": token,
        "client_id": str(client.id),
        "business_name": business_name,
        "is_admin": False,
    }


# === AUTH DEPENDENCIES ===

async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Client:
    """Dependency to extract and verify client from JWT Bearer token."""
    import jwt as pyjwt
    from src.config import get_settings
    settings = get_settings()

    try:
        payload = pyjwt.decode(
            credentials.credentials,
            settings.dashboard_jwt_secret or settings.app_secret_key,
            algorithms=["HS256"],
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    client_id = payload.get("client_id")
    if not client_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(
        select(Client).where(and_(Client.id == client_uuid, Client.is_active == True))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=401, detail="Client not found")
    return client


async def get_current_admin(
    client: Client = Depends(get_current_client),
) -> Client:
    """Dependency that requires the authenticated client to be an admin."""
    if not client.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return client


# === PASSWORD RESET ===

@router.post("/api/v1/auth/forgot-password")
async def forgot_password(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate password reset token and send reset email."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    # Always return success to prevent email enumeration
    result = await db.execute(
        select(Client).where(Client.dashboard_email == email)
    )
    client = result.scalar_one_or_none()

    if client:
        token = secrets.token_urlsafe(32)
        try:
            from src.utils.dedup import get_redis
            redis = await get_redis()
            await redis.setex(f"pw_reset:{token}", 3600, str(client.id))  # 1hr TTL

            from src.services.transactional_email import send_password_reset
            from src.config import get_settings as _get_settings
            s = _get_settings()
            reset_url = f"{s.app_base_url.rstrip('/')}/reset-password"
            await send_password_reset(email, token, reset_url)
            logger.info("Password reset email sent to %s", email[:20] + "***")
        except Exception as e:
            logger.error("Failed to send reset email: %s", str(e))

    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/api/v1/auth/reset-password")
async def reset_password(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Validate reset token and update password."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    token = (payload.get("token") or "").strip()
    new_password = payload.get("password") or ""

    if not token:
        raise HTTPException(status_code=400, detail="Reset token is required")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        client_id_raw = await redis.get(f"pw_reset:{token}")
    except Exception as e:
        logger.error("Redis error during password reset: %s", str(e))
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")

    if not client_id_raw:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    client_id = client_id_raw if isinstance(client_id_raw, str) else client_id_raw.decode()

    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    result = await db.execute(
        select(Client).where(Client.id == client_uuid)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="Invalid reset token")

    import bcrypt
    client.dashboard_password_hash = bcrypt.hashpw(
        new_password.encode(), bcrypt.gensalt()
    ).decode()

    # Delete the used token
    try:
        await redis.delete(f"pw_reset:{token}")
    except Exception:
        pass

    logger.info("Password reset completed for %s", client.dashboard_email[:20] + "***")
    return {"message": "Password has been reset successfully. You can now sign in."}


# === EMAIL VERIFICATION ===

@router.get("/api/v1/auth/verify-email/{token}")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Validate email verification token and mark client as verified."""
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        client_id_raw = await redis.get(f"email_verify:{token}")
    except Exception as e:
        logger.error("Redis error during email verification: %s", str(e))
        raise HTTPException(status_code=500, detail="Service temporarily unavailable")

    if not client_id_raw:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    client_id = client_id_raw if isinstance(client_id_raw, str) else client_id_raw.decode()

    result = await db.execute(
        select(Client).where(Client.id == uuid.UUID(client_id))
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    client.email_verified = True

    # Delete the used token
    try:
        await redis.delete(f"email_verify:{token}")
    except Exception:
        pass

    logger.info("Email verified for %s", client.dashboard_email[:20] + "***")

    # Send welcome email
    try:
        from src.services.transactional_email import send_welcome_email
        await send_welcome_email(client.dashboard_email, client.business_name)
    except Exception as e:
        logger.warning("Failed to send welcome email: %s", str(e))

    return {"message": "Email verified successfully!", "verified": True}


@router.post("/api/v1/auth/resend-verification")
async def resend_verification(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Resend email verification link. Rate limited to 1 per 2 minutes."""
    if getattr(client, 'email_verified', False):
        return {"message": "Email is already verified"}

    # Rate limit check
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        rate_key = f"verify_rate:{client.id}"
        if await redis.exists(rate_key):
            raise HTTPException(
                status_code=429,
                detail="Please wait 2 minutes before requesting another verification email",
            )

        verify_token = secrets.token_urlsafe(32)
        await redis.setex(f"email_verify:{verify_token}", 86400, str(client.id))
        await redis.setex(rate_key, 120, "1")  # 2-minute cooldown

        from src.services.transactional_email import send_email_verification
        from src.config import get_settings as _get_settings
        s = _get_settings()
        verify_url = f"{s.app_base_url.rstrip('/')}/verify-email"
        await send_email_verification(client.dashboard_email, verify_token, verify_url)

        return {"message": "Verification email sent"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to resend verification: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to send verification email")


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
    except Exception:
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
    except Exception:
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

    # Idempotency guard — don't re-create profile if already submitted
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
        # Profile created but not submitted — poller can retry
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


def _mask_ein(ein: str | None) -> str | None:
    """Mask EIN for display — show only last 4 digits."""
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


# === METRICS ===

@router.get("/api/v1/dashboard/metrics", response_model=DashboardMetrics)
async def get_metrics(
    period: str = Query(default="7d", pattern="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get aggregated KPI metrics for the dashboard."""
    return await get_dashboard_metrics(db, str(client.id), period)


# === LEADS ===

@router.get("/api/v1/dashboard/leads", response_model=LeadListResponse)
async def get_leads(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    state: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get paginated lead list with filters."""
    query = select(Lead).where(Lead.client_id == client.id)

    if state:
        query = query.where(Lead.state == state)
    if source:
        query = query.where(Lead.source == source)
    if search:
        # Escape SQL LIKE wildcards in user input
        escaped = search.replace("%", r"\%").replace("_", r"\_")
        search_pattern = f"%{escaped}%"
        query = query.where(
            Lead.first_name.ilike(search_pattern)
            | Lead.last_name.ilike(search_pattern)
            | Lead.phone.ilike(search_pattern)
            | Lead.service_type.ilike(search_pattern)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(desc(Lead.created_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    leads = result.scalars().all()

    return LeadListResponse(
        leads=[
            LeadSummary(
                id=str(l.id),
                first_name=l.first_name,
                last_name=l.last_name,
                phone_masked=l.phone[:6] + "***" if l.phone else "",
                source=l.source,
                state=l.state,
                score=l.score,
                service_type=l.service_type,
                urgency=l.urgency,
                first_response_ms=l.first_response_ms,
                total_messages=l.total_messages_sent + l.total_messages_received,
                created_at=l.created_at,
            )
            for l in leads
        ],
        total=total,
        page=page,
        pages=max(1, (total + per_page - 1) // per_page),
    )


@router.get("/api/v1/dashboard/leads/export")
async def export_leads_csv(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Export leads as CSV (capped at 10,000 rows for safety)."""
    MAX_EXPORT_ROWS = 10000
    result = await db.execute(
        select(Lead)
        .where(Lead.client_id == client.id)
        .order_by(desc(Lead.created_at))
        .limit(MAX_EXPORT_ROWS)
    )
    leads = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "first_name", "last_name", "phone", "source", "state",
        "score", "service_type", "urgency", "first_response_ms",
        "total_messages", "created_at",
    ])

    for lead in leads:
        writer.writerow([
            str(lead.id),
            lead.first_name,
            lead.last_name,
            lead.phone[:6] + "***" if lead.phone else "",
            lead.source,
            lead.state,
            lead.score,
            lead.service_type,
            lead.urgency,
            lead.first_response_ms,
            (lead.total_messages_sent or 0) + (lead.total_messages_received or 0),
            lead.created_at.isoformat() if lead.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"},
    )


@router.get("/api/v1/dashboard/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get full lead detail with conversation history."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get conversations
    conv_result = await db.execute(
        select(Conversation)
        .where(Conversation.lead_id == lead.id)
        .order_by(Conversation.created_at)
    )
    conversations = conv_result.scalars().all()

    # Get booking
    booking_result = await db.execute(
        select(Booking).where(Booking.lead_id == lead.id)
    )
    booking = booking_result.scalar_one_or_none()

    # Get consent
    consent = None
    if lead.consent_id:
        consent = await db.get(ConsentRecord, lead.consent_id)

    # Get events
    event_result = await db.execute(
        select(EventLog)
        .where(EventLog.lead_id == lead.id)
        .order_by(EventLog.created_at)
    )
    events = event_result.scalars().all()

    return LeadDetailResponse(
        lead=LeadSummary(
            id=str(lead.id),
            first_name=lead.first_name,
            last_name=lead.last_name,
            phone_masked=lead.phone[:6] + "***" if lead.phone else "",
            source=lead.source,
            state=lead.state,
            score=lead.score,
            service_type=lead.service_type,
            urgency=lead.urgency,
            first_response_ms=lead.first_response_ms,
            total_messages=lead.total_messages_sent + lead.total_messages_received,
            created_at=lead.created_at,
        ),
        conversations=[
            MessageSummary(
                id=str(c.id),
                direction=c.direction,
                agent_id=c.agent_id,
                content=c.content,
                delivery_status=c.delivery_status,
                created_at=c.created_at,
            )
            for c in conversations
        ],
        booking=BookingDetail(
            id=str(booking.id),
            appointment_date=str(booking.appointment_date),
            time_window_start=str(booking.time_window_start) if booking.time_window_start else None,
            time_window_end=str(booking.time_window_end) if booking.time_window_end else None,
            service_type=booking.service_type,
            tech_name=booking.tech_name,
            status=booking.status,
            crm_sync_status=booking.crm_sync_status,
        ) if booking else None,
        consent=ConsentDetail(
            id=str(consent.id),
            consent_type=consent.consent_type,
            consent_method=consent.consent_method,
            is_active=consent.is_active,
            opted_out=consent.opted_out,
            created_at=consent.created_at,
        ) if consent else None,
        events=[
            EventSummary(
                id=str(e.id),
                action=e.action,
                status=e.status,
                message=e.message,
                duration_ms=e.duration_ms,
                created_at=e.created_at,
            )
            for e in events
        ],
    )


@router.get("/api/v1/dashboard/leads/{lead_id}/conversations")
async def get_conversations(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get full conversation thread for a lead."""
    try:
        lid = uuid.UUID(lead_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lead ID")
    result = await db.execute(
        select(Conversation)
        .where(
            and_(Conversation.lead_id == lid, Conversation.client_id == client.id)
        )
        .order_by(Conversation.created_at)
    )
    conversations = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "direction": c.direction,
            "agent_id": c.agent_id,
            "content": c.content,
            "delivery_status": c.delivery_status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in conversations
    ]


# === ACTIVITY ===

@router.get("/api/v1/dashboard/activity")
async def get_activity(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get recent activity feed."""
    result = await db.execute(
        select(EventLog)
        .where(EventLog.client_id == client.id)
        .order_by(desc(EventLog.created_at))
        .limit(limit)
    )
    events = result.scalars().all()

    activity = []
    for e in events:
        event_type = "lead_created"
        if "sms_sent" in (e.action or ""):
            event_type = "sms_sent"
        elif "sms_received" in (e.action or ""):
            event_type = "sms_received"
        elif "booking" in (e.action or ""):
            event_type = "booking_confirmed"
        elif "opt_out" in (e.action or ""):
            event_type = "opt_out"
        elif "intake" in (e.action or ""):
            event_type = "sms_sent"

        activity.append(ActivityEvent(
            type=event_type,
            lead_id=str(e.lead_id) if e.lead_id else None,
            message=e.message or e.action,
            timestamp=e.created_at,
        ))

    return activity


# === REPORTS ===

@router.get("/api/v1/dashboard/reports/weekly")
async def get_weekly_report(
    week: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get weekly report data."""
    # Default to current week
    metrics = await get_dashboard_metrics(db, str(client.id), "7d")
    return metrics


# === SETTINGS ===

@router.get("/api/v1/dashboard/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get current client configuration."""
    return {
        "business_name": client.business_name,
        "trade_type": client.trade_type,
        "tier": client.tier,
        "twilio_phone": client.twilio_phone,
        "ten_dlc_status": client.ten_dlc_status,
        "crm_type": client.crm_type,
        "config": client.config,
        "email_verified": getattr(client, 'email_verified', True),
        "billing_status": client.billing_status,
        "twilio_messaging_service_sid": client.twilio_messaging_service_sid,
        "business_website": client.business_website,
        "business_type": client.business_type,
        "business_ein": _mask_ein(client.business_ein),
        "business_address": client.business_address,
    }


@router.put("/api/v1/dashboard/settings")
async def update_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Update client configuration."""
    try:
        body = await request.body()
        if len(body) > 51200:  # 50KB max
            raise HTTPException(status_code=413, detail="Payload too large (max 50KB)")
        import json
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    except HTTPException:
        raise

    if "config" in payload:
        if not isinstance(payload["config"], dict):
            raise HTTPException(status_code=400, detail="config must be a JSON object")
        # Merge with existing config instead of overwriting to prevent data loss
        existing = client.config or {}
        client.config = {**existing, **payload["config"]}
    await db.commit()
    return {"status": "updated"}


@router.post("/api/v1/dashboard/onboarding")
async def complete_onboarding(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Save onboarding configuration and mark client as onboarded."""
    if "config" in payload:
        existing = client.config or {}
        merged = {**existing, **payload["config"]}
        client.config = merged

    if "crm_type" in payload and payload["crm_type"]:
        client.crm_type = payload["crm_type"]

    if "crm_tenant_id" in payload and payload["crm_tenant_id"]:
        client.crm_tenant_id = payload["crm_tenant_id"]

    if "crm_api_key" in payload and payload["crm_api_key"]:
        from src.utils.encryption import encrypt_value
        client.crm_api_key_encrypted = encrypt_value(payload["crm_api_key"])

    # Save business registration info if provided (for later 10DLC submission)
    _valid_business_types = {"sole_proprietorship", "llc", "corporation", "partnership"}
    if payload.get("business_type"):
        if payload["business_type"] not in _valid_business_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid business_type. Must be one of: {', '.join(sorted(_valid_business_types))}",
            )
        client.business_type = payload["business_type"]
    if payload.get("business_ein"):
        client.business_ein = payload["business_ein"]
    if payload.get("business_website"):
        client.business_website = payload["business_website"]
    if payload.get("business_address"):
        client.business_address = payload["business_address"]

    client.onboarding_status = "live"

    await db.commit()
    logger.info("Onboarding completed for client %s", client.business_name)
    return {"status": "onboarded", "client_id": str(client.id)}


# === COMPLIANCE ===

@router.get("/api/v1/dashboard/compliance/summary", response_model=ComplianceSummary)
async def get_compliance_summary(
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get compliance health check summary."""
    # Total consent records
    consent_count = (await db.execute(
        select(func.count(ConsentRecord.id)).where(ConsentRecord.client_id == client.id)
    )).scalar() or 0

    # Opted out count
    opted_out_count = (await db.execute(
        select(func.count(ConsentRecord.id)).where(
            and_(ConsentRecord.client_id == client.id, ConsentRecord.opted_out == True)
        )
    )).scalar() or 0

    # Pending followups
    pending_followups = (await db.execute(
        select(func.count(FollowupTask.id)).where(
            and_(FollowupTask.client_id == client.id, FollowupTask.status == "pending")
        )
    )).scalar() or 0

    return ComplianceSummary(
        total_consent_records=consent_count,
        opted_out_count=opted_out_count,
        messages_in_quiet_hours=0,
        cold_outreach_violations=0,
        pending_followups=pending_followups,
        last_audit=datetime.now(timezone.utc),
    )


# === LEAD ACTIONS (Phase 2) ===

@router.put("/api/v1/dashboard/leads/{lead_id}/status")
async def update_lead_status(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Change lead status (close, re-engage, etc)."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    new_status = payload.get("status", "").strip()
    # opted_out excluded — must go through SMS pipeline for compliance
    valid_statuses = {"new", "qualifying", "qualified", "booking", "booked", "completed", "cold", "dead"}
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    lead.state = new_status
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated", "new_state": new_status}


@router.put("/api/v1/dashboard/leads/{lead_id}/archive")
async def archive_lead(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Archive or unarchive a lead."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    archived = payload.get("archived", True)
    if hasattr(lead, "archived"):
        lead.archived = archived
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated", "archived": archived}


@router.put("/api/v1/dashboard/leads/{lead_id}/tags")
async def update_lead_tags(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Add or remove tags from a lead."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list")

    if hasattr(lead, "tags"):
        lead.tags = tags
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated", "tags": tags}


@router.put("/api/v1/dashboard/leads/{lead_id}/notes")
async def update_lead_notes(
    lead_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Add internal notes to a lead."""
    try:
        lead_uuid = uuid.UUID(lead_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    lead = await db.get(Lead, lead_uuid)
    if not lead or lead.client_id != client.id:
        raise HTTPException(status_code=404, detail="Lead not found")

    notes = payload.get("notes", "")
    if hasattr(lead, "notes"):
        lead.notes = notes
    lead.updated_at = datetime.now(timezone.utc)
    return {"status": "updated"}


# === BOOKINGS (Phase 2) ===

@router.get("/api/v1/dashboard/bookings")
async def get_bookings(
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get bookings filtered by date range."""
    conditions = [Booking.client_id == client.id]

    if start:
        try:
            start_date = datetime.fromisoformat(start)
            conditions.append(Booking.appointment_date >= start_date.date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date format. Use ISO 8601.")

    if end:
        try:
            end_date = datetime.fromisoformat(end)
            conditions.append(Booking.appointment_date <= end_date.date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end date format. Use ISO 8601.")

    result = await db.execute(
        select(Booking)
        .where(and_(*conditions))
        .order_by(desc(Booking.appointment_date))
    )
    bookings = result.scalars().all()

    return {
        "bookings": [
            {
                "id": str(b.id),
                "lead_id": str(b.lead_id) if b.lead_id else None,
                "appointment_date": str(b.appointment_date),
                "time_window_start": str(b.time_window_start) if b.time_window_start else None,
                "time_window_end": str(b.time_window_end) if b.time_window_end else None,
                "service_type": b.service_type,
                "tech_name": b.tech_name,
                "status": b.status,
                "crm_sync_status": b.crm_sync_status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bookings
        ],
        "total": len(bookings),
    }


# === CUSTOM REPORTS & CSV EXPORT (Phase 2) ===

@router.get("/api/v1/dashboard/reports/custom")
async def get_custom_report(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
    client: Client = Depends(get_current_client),
):
    """Get custom date range report data."""
    try:
        start_date = datetime.fromisoformat(start)
        end_date = datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

    # Total leads in range
    lead_count = (await db.execute(
        select(func.count(Lead.id)).where(
            and_(Lead.client_id == client.id, Lead.created_at >= start_date, Lead.created_at <= end_date)
        )
    )).scalar() or 0

    # Leads by state
    state_result = await db.execute(
        select(Lead.state, func.count()).where(
            and_(Lead.client_id == client.id, Lead.created_at >= start_date, Lead.created_at <= end_date)
        ).group_by(Lead.state)
    )
    by_state = {row[0]: row[1] for row in state_result.all()}

    # Bookings in range
    booking_count = (await db.execute(
        select(func.count(Booking.id)).where(
            and_(Booking.client_id == client.id, Booking.created_at >= start_date, Booking.created_at <= end_date)
        )
    )).scalar() or 0

    # Avg response time
    avg_response = (await db.execute(
        select(func.avg(Lead.first_response_ms)).where(
            and_(
                Lead.client_id == client.id,
                Lead.created_at >= start_date,
                Lead.created_at <= end_date,
                Lead.first_response_ms.isnot(None),
            )
        )
    )).scalar()

    return {
        "start": start,
        "end": end,
        "total_leads": lead_count,
        "by_state": by_state,
        "bookings": booking_count,
        "avg_response_ms": round(float(avg_response)) if avg_response else None,
    }
