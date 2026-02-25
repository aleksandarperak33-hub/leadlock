"""
Dashboard auth endpoints — login, signup, password reset, email verification.
Also provides get_current_client/get_current_admin dependency functions.
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.database import get_db
from src.models.client import Client
from src.schemas.api_responses import LoginRequest, LoginResponse

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
        # Fail open - don't block auth if Redis is down, but log it
        logger.warning("Rate limiting unavailable (Redis error): %s", str(e))


# === AUTH ===

@router.post("/api/v1/auth/login")
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

    return {
        "token": token,
        "client_id": str(client.id),
        "business_name": client.business_name,
        "is_admin": client.is_admin,
        "onboarding_status": client.onboarding_status,
        "billing_status": client.billing_status,
    }


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
    except Exception as e:
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

    # Validate phone format if provided
    if phone:
        from src.services.phone_validation import normalize_phone
        normalized = normalize_phone(phone)
        if not normalized:
            raise HTTPException(status_code=400, detail="Invalid phone number format")
        phone = normalized

    # ToS acceptance
    tos_accepted = payload.get("tos_accepted", False)
    if not tos_accepted:
        raise HTTPException(status_code=400, detail="You must accept the Terms of Service")

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
        billing_status="pending",
        onboarding_status="pending",
        tos_accepted_at=datetime.now(timezone.utc),
    )
    db.add(client)
    await db.commit()

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
        "onboarding_status": "pending",
        "billing_status": "pending",
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
    except Exception as e:
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
    except Exception as e:
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
    await db.commit()

    # Delete the used token
    try:
        await redis.delete(f"pw_reset:{token}")
    except Exception as e:
        logger.debug("Token cleanup failed: %s", str(e))

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
    try:
        client_uuid = uuid.UUID(client_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    result = await db.execute(
        select(Client).where(Client.id == client_uuid)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=400, detail="Invalid verification token")

    client.email_verified = True
    await db.commit()

    # Delete the used token
    try:
        await redis.delete(f"email_verify:{token}")
    except Exception as e:
        logger.debug("Token cleanup failed: %s", str(e))

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
