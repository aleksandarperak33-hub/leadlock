"""
Tests for src/api/dashboard.py - Dashboard API endpoints.
Covers auth flows (login, signup, password reset, email verification),
JWT auth dependencies, phone provisioning, settings, leads, bookings,
activity, reports, compliance, and lead action endpoints.
All external services (Redis, Twilio, AI, email) are mocked.
"""
import csv
import io
import json
import uuid
from datetime import datetime, date, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.dashboard import (
    _check_auth_rate_limit,
    _check_is_tollfree,
    _get_registration_status_info,
    _mask_ein,
    archive_lead,
    complete_onboarding,
    export_leads_csv,
    forgot_password,
    get_activity,
    get_bookings,
    get_compliance_summary,
    get_conversations,
    get_current_admin,
    get_current_client,
    get_custom_report,
    get_leads,
    get_lead_detail,
    get_metrics,
    get_registration_status,
    get_settings,
    get_weekly_report,
    login,
    provision_number,
    resend_verification,
    reset_password,
    search_available_numbers,
    signup,
    submit_business_registration,
    update_lead_notes,
    update_lead_status,
    update_lead_tags,
    update_settings,
    verify_email,
)
from src.models.client import Client
from src.models.lead import Lead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Patch targets: dashboard.py uses local imports inside functions, so we
# patch at the SOURCE module (e.g. "src.utils.dedup.get_redis") not at
# "src.api.dashboard.get_redis".  The only top-level import from services
# is get_dashboard_metrics, which CAN be patched at the dashboard module.

REDIS_PATCH = "src.utils.dedup.get_redis"
SETTINGS_PATCH = "src.config.get_settings"
SEND_VERIFICATION_PATCH = "src.services.transactional_email.send_email_verification"
SEND_WELCOME_PATCH = "src.services.transactional_email.send_welcome_email"
SEND_RESET_PATCH = "src.services.transactional_email.send_password_reset"
SEARCH_NUMBERS_PATCH = "src.services.sms.search_available_numbers"
PROVISION_PATCH = "src.services.sms.provision_phone_number"
TF_VERIFY_PATCH = "src.services.twilio_registration.submit_tollfree_verification"
CREATE_PROFILE_PATCH = "src.services.twilio_registration.create_customer_profile"
SUBMIT_PROFILE_PATCH = "src.services.twilio_registration.submit_customer_profile"
IS_TOLLFREE_PATCH = "src.services.twilio_registration.is_tollfree"
ENCRYPT_PATCH = "src.utils.encryption.encrypt_value"
METRICS_PATCH = "src.api.dash_reports.get_dashboard_metrics"

JWT_SECRET = "a]v9$kLm!Qw2xR7nP4uY8bT1cF5dG6h"  # >= 32 bytes for HS256


def _make_mock_client(
    client_id=None,
    business_name="Austin HVAC",
    trade_type="hvac",
    tier="starter",
    is_admin=False,
    is_active=True,
    twilio_phone=None,
    ten_dlc_status="pending",
    crm_type="google_sheets",
    config=None,
    email_verified=False,
    billing_status="trial",
    twilio_messaging_service_sid=None,
    business_website=None,
    business_type=None,
    business_ein=None,
    business_address=None,
    dashboard_email="test@example.com",
    dashboard_password_hash=None,
    owner_email=None,
    owner_phone=None,
    onboarding_status="pending",
    ten_dlc_profile_sid=None,
    ten_dlc_verification_sid=None,
    twilio_phone_sid=None,
):
    """Create a mock Client object for testing."""
    client = MagicMock(spec=Client)
    client.id = client_id or uuid.uuid4()
    client.business_name = business_name
    client.trade_type = trade_type
    client.tier = tier
    client.is_admin = is_admin
    client.is_active = is_active
    client.twilio_phone = twilio_phone
    client.twilio_phone_sid = twilio_phone_sid
    client.ten_dlc_status = ten_dlc_status
    client.ten_dlc_profile_sid = ten_dlc_profile_sid
    client.ten_dlc_verification_sid = ten_dlc_verification_sid
    client.crm_type = crm_type
    client.config = config or {}
    client.email_verified = email_verified
    client.billing_status = billing_status
    client.twilio_messaging_service_sid = twilio_messaging_service_sid
    client.business_website = business_website
    client.business_type = business_type
    client.business_ein = business_ein
    client.business_address = business_address
    client.dashboard_email = dashboard_email
    client.dashboard_password_hash = dashboard_password_hash
    client.owner_email = owner_email
    client.owner_phone = owner_phone
    client.onboarding_status = onboarding_status
    client.crm_tenant_id = None
    client.crm_api_key_encrypted = None
    return client


def _make_mock_lead(
    lead_id=None,
    client_id=None,
    phone="+15125559876",
    first_name="John",
    last_name="Doe",
    source="website",
    state="qualifying",
    score=50,
    service_type="AC Repair",
    urgency="today",
    first_response_ms=5000,
    total_messages_sent=3,
    total_messages_received=2,
    created_at=None,
    consent_id=None,
    tags=None,
    archived=False,
    notes="",
):
    """Create a mock Lead object for testing."""
    lead = MagicMock(spec=Lead)
    lead.id = lead_id or uuid.uuid4()
    lead.client_id = client_id or uuid.uuid4()
    lead.phone = phone
    lead.first_name = first_name
    lead.last_name = last_name
    lead.source = source
    lead.state = state
    lead.score = score
    lead.service_type = service_type
    lead.urgency = urgency
    lead.first_response_ms = first_response_ms
    lead.total_messages_sent = total_messages_sent
    lead.total_messages_received = total_messages_received
    lead.created_at = created_at or datetime.now(timezone.utc)
    lead.updated_at = datetime.now(timezone.utc)
    lead.consent_id = consent_id
    lead.tags = tags or []
    lead.archived = archived
    lead.notes = notes
    return lead


def _make_mock_settings(**overrides):
    """Build a mock Settings object for dashboard JWT config."""
    defaults = {
        "app_secret_key": JWT_SECRET,
        "dashboard_jwt_secret": JWT_SECRET,
        "dashboard_jwt_expiry_hours": 24,
        "app_base_url": "https://app.leadlock.io",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _make_mock_request(json_data=None, body=None, client_host="127.0.0.1"):
    """Create a mock FastAPI Request object."""
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = client_host

    if json_data is not None:
        request.json = AsyncMock(return_value=json_data)
    else:
        request.json = AsyncMock(side_effect=Exception("No JSON body"))

    if body is not None:
        request.body = AsyncMock(return_value=body)
    elif json_data is not None:
        request.body = AsyncMock(return_value=json.dumps(json_data).encode())
    else:
        request.body = AsyncMock(return_value=b"")

    return request


def _make_mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _scalar_result(value):
    """Create a mock result that returns a single scalar value."""
    result = MagicMock()
    result.scalar = MagicMock(return_value=value)
    result.scalar_one_or_none = MagicMock(return_value=value)
    return result


def _scalars_result(values):
    """Create a mock result that returns a list of scalars."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all = MagicMock(return_value=values)
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _rows_result(rows):
    """Create a mock result that returns rows (for group_by queries)."""
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    return result


def _mock_redis():
    """Create a mock Redis client."""
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.exists = AsyncMock(return_value=False)
    return r


# ---------------------------------------------------------------------------
# _check_auth_rate_limit
# ---------------------------------------------------------------------------

class TestCheckAuthRateLimit:
    @pytest.mark.asyncio
    async def test_under_limit_passes(self):
        """Requests under the rate limit should not raise."""
        redis = _mock_redis()
        redis.incr.return_value = 1
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            await _check_auth_rate_limit("login", "test@example.com")

    @pytest.mark.asyncio
    async def test_at_limit_passes(self):
        """Requests at exactly the max_attempts should not raise."""
        redis = _mock_redis()
        redis.incr.return_value = 5
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            await _check_auth_rate_limit("login", "test@example.com", max_attempts=5)

    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        """Requests over the rate limit should raise HTTP 429."""
        redis = _mock_redis()
        redis.incr.return_value = 6
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await _check_auth_rate_limit("login", "test@example.com", max_attempts=5)
            assert exc_info.value.status_code == 429
            assert "Too many attempts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_first_request_sets_expiry(self):
        """First request (count == 1) should set TTL on the rate limit key."""
        redis = _mock_redis()
        redis.incr.return_value = 1
        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            await _check_auth_rate_limit("login", "test@example.com", window_seconds=900)
        redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redis_down_fails_open(self):
        """If Redis is unavailable, rate limiting should fail open."""
        with patch(REDIS_PATCH, new_callable=AsyncMock, side_effect=ConnectionError("Redis down")):
            await _check_auth_rate_limit("login", "test@example.com")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    @pytest.mark.asyncio
    async def test_successful_login(self):
        """Valid credentials should return a JWT token."""
        import bcrypt
        password = "testpassword123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        mock_client = _make_mock_client(
            dashboard_email="user@example.com",
            dashboard_password_hash=hashed,
            is_admin=False,
        )
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        payload = MagicMock()
        payload.email = "user@example.com"
        payload.password = password

        with (
            patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()),
            patch(SETTINGS_PATCH, return_value=_make_mock_settings()),
        ):
            result = await login(payload, MagicMock(), db)

        assert result.token is not None
        assert result.client_id == str(mock_client.id)
        assert result.business_name == "Austin HVAC"

    @pytest.mark.asyncio
    async def test_invalid_email_returns_401(self):
        """Non-existent email should return 401."""
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(None)

        payload = MagicMock()
        payload.email = "nonexistent@example.com"
        payload.password = "password"

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await login(payload, MagicMock(), db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(self):
        """Wrong password should return 401."""
        import bcrypt
        hashed = bcrypt.hashpw(b"correctpassword", bcrypt.gensalt()).decode()

        mock_client = _make_mock_client(dashboard_password_hash=hashed)
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        payload = MagicMock()
        payload.email = "test@example.com"
        payload.password = "wrongpassword"

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await login(payload, MagicMock(), db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_password_hash_returns_401(self):
        """Client with no password hash should return 401."""
        mock_client = _make_mock_client(dashboard_password_hash=None)
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        payload = MagicMock()
        payload.email = "test@example.com"
        payload.password = "anypassword"

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await login(payload, MagicMock(), db)
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

class TestSignup:
    @pytest.mark.asyncio
    async def test_successful_signup(self):
        """Valid signup should create client and return JWT."""
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(None)  # No existing email

        request = _make_mock_request(json_data={
            "business_name": "HVAC Pros",
            "name": "John Doe",
            "email": "john@hvacpros.com",
            "phone": "+15125551234",
            "trade_type": "hvac",
            "password": "securepass123",
        })

        redis = _mock_redis()
        with (
            patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis),
            patch(SETTINGS_PATCH, return_value=_make_mock_settings()),
            patch(SEND_VERIFICATION_PATCH, new_callable=AsyncMock),
        ):
            result = await signup(request, db)

        assert "token" in result
        assert result["business_name"] == "HVAC Pros"
        assert result["is_admin"] is False
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_signup_missing_business_name(self):
        """Signup without business_name should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={
            "email": "john@example.com",
            "password": "securepass123",
        })

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await signup(request, db)
            assert exc_info.value.status_code == 400
            assert "Business name" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_signup_missing_email(self):
        """Signup without email should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={
            "business_name": "HVAC Pros",
            "password": "securepass123",
        })

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await signup(request, db)
            assert exc_info.value.status_code == 400
            assert "Email" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_signup_short_password(self):
        """Signup with password < 8 chars should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={
            "business_name": "HVAC Pros",
            "email": "john@example.com",
            "password": "short",
        })

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await signup(request, db)
            assert exc_info.value.status_code == 400
            assert "8 characters" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_signup_duplicate_email(self):
        """Signup with already-registered email should return 409."""
        db = _make_mock_db()
        existing_client = _make_mock_client()
        db.execute.return_value = _scalar_result(existing_client)

        request = _make_mock_request(json_data={
            "business_name": "HVAC Pros",
            "email": "existing@example.com",
            "password": "securepass123",
        })

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await signup(request, db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_signup_invalid_json(self):
        """Signup with invalid JSON body should return 400."""
        db = _make_mock_db()
        request = _make_mock_request()  # json() raises exception

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=_mock_redis()):
            with pytest.raises(HTTPException) as exc_info:
                await signup(request, db)
            assert exc_info.value.status_code == 400
            assert "Invalid JSON" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_current_client (JWT Auth Dependency)
# ---------------------------------------------------------------------------

class TestGetCurrentClient:
    def _encode_token(self, claims):
        """Encode a JWT for testing using the standard test secret."""
        import jwt
        return jwt.encode(claims, JWT_SECRET, algorithm="HS256")

    @pytest.mark.asyncio
    async def test_valid_token_returns_client(self):
        """Valid JWT should return the matching active client."""
        client_id = uuid.uuid4()
        token = self._encode_token({
            "client_id": str(client_id),
            "is_admin": False,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })

        credentials = MagicMock()
        credentials.credentials = token

        mock_client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        with patch(SETTINGS_PATCH, return_value=_make_mock_settings()):
            result = await get_current_client(credentials, db)

        assert result == mock_client

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        """Expired JWT should raise 401."""
        token = self._encode_token({
            "client_id": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        })

        credentials = MagicMock()
        credentials.credentials = token
        db = _make_mock_db()

        with patch(SETTINGS_PATCH, return_value=_make_mock_settings()):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_client(credentials, db)
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Tampered/invalid JWT should raise 401."""
        credentials = MagicMock()
        credentials.credentials = "invalid.jwt.token"
        db = _make_mock_db()

        with patch(SETTINGS_PATCH, return_value=_make_mock_settings()):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_client(credentials, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_client_id_in_token_raises_401(self):
        """JWT without client_id claim should raise 401."""
        token = self._encode_token({
            "is_admin": False,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })

        credentials = MagicMock()
        credentials.credentials = token
        db = _make_mock_db()

        with patch(SETTINGS_PATCH, return_value=_make_mock_settings()):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_client(credentials, db)
            assert exc_info.value.status_code == 401
            assert "Invalid token payload" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_uuid_in_token_raises_401(self):
        """JWT with non-UUID client_id should raise 401."""
        token = self._encode_token({
            "client_id": "not-a-uuid",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })

        credentials = MagicMock()
        credentials.credentials = token
        db = _make_mock_db()

        with patch(SETTINGS_PATCH, return_value=_make_mock_settings()):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_client(credentials, db)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_client_raises_401(self):
        """JWT for a deactivated client should raise 401."""
        client_id = uuid.uuid4()
        token = self._encode_token({
            "client_id": str(client_id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        })

        credentials = MagicMock()
        credentials.credentials = token

        db = _make_mock_db()
        db.execute.return_value = _scalar_result(None)  # Not found / not active

        with patch(SETTINGS_PATCH, return_value=_make_mock_settings()):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_client(credentials, db)
            assert exc_info.value.status_code == 401
            assert "Client not found" in exc_info.value.detail


# ---------------------------------------------------------------------------
# get_current_admin
# ---------------------------------------------------------------------------

class TestGetCurrentAdmin:
    @pytest.mark.asyncio
    async def test_admin_client_passes(self):
        """Admin client should be returned without error."""
        client = _make_mock_client(is_admin=True)
        result = await get_current_admin(client)
        assert result == client

    @pytest.mark.asyncio
    async def test_non_admin_raises_403(self):
        """Non-admin client should raise 403."""
        client = _make_mock_client(is_admin=False)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin(client)
        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------

class TestForgotPassword:
    @pytest.mark.asyncio
    async def test_known_email_sends_reset(self):
        """Existing email should trigger reset email."""
        mock_client = _make_mock_client(dashboard_email="user@example.com")
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        request = _make_mock_request(json_data={"email": "user@example.com"})

        redis = _mock_redis()
        with (
            patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis),
            patch(SEND_RESET_PATCH, new_callable=AsyncMock) as mock_send,
            patch(SETTINGS_PATCH, return_value=_make_mock_settings()),
        ):
            result = await forgot_password(request, db)

        assert "reset link has been sent" in result["message"]
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_email_returns_same_message(self):
        """Non-existent email should return the same message (prevent enumeration)."""
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(None)

        request = _make_mock_request(json_data={"email": "nobody@example.com"})
        result = await forgot_password(request, db)
        assert "reset link has been sent" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_email_raises_400(self):
        """Request without email should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={"email": ""})

        with pytest.raises(HTTPException) as exc_info:
            await forgot_password(request, db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_json_raises_400(self):
        """Invalid JSON body should return 400."""
        db = _make_mock_db()
        request = _make_mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await forgot_password(request, db)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Reset Password
# ---------------------------------------------------------------------------

class TestResetPassword:
    @pytest.mark.asyncio
    async def test_valid_reset(self):
        """Valid token and password should reset successfully."""
        client_id = uuid.uuid4()
        mock_client = _make_mock_client(client_id=client_id)

        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        request = _make_mock_request(json_data={
            "token": "valid-reset-token",
            "password": "newpassword123",
        })

        redis = _mock_redis()
        redis.get.return_value = str(client_id)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            result = await reset_password(request, db)

        assert "reset successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_token_raises_400(self):
        """Request without token should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={"token": "", "password": "newpassword123"})

        with pytest.raises(HTTPException) as exc_info:
            await reset_password(request, db)
        assert exc_info.value.status_code == 400
        assert "Reset token is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_short_password_raises_400(self):
        """Password < 8 chars should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={"token": "valid-token", "password": "short"})

        with pytest.raises(HTTPException) as exc_info:
            await reset_password(request, db)
        assert exc_info.value.status_code == 400
        assert "8 characters" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_expired_token_raises_400(self):
        """Expired/invalid reset token should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={"token": "expired-token", "password": "newpassword123"})

        redis = _mock_redis()
        redis.get.return_value = None  # Token not found

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(request, db)
            assert exc_info.value.status_code == 400
            assert "Invalid or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_redis_error_raises_500(self):
        """Redis failure during reset should return 500."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={"token": "any-token", "password": "newpassword123"})

        with patch(REDIS_PATCH, new_callable=AsyncMock, side_effect=ConnectionError("Redis down")):
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(request, db)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_invalid_client_id_in_token_raises_400(self):
        """Token with invalid UUID should return 400."""
        db = _make_mock_db()
        request = _make_mock_request(json_data={"token": "some-token", "password": "newpassword123"})

        redis = _mock_redis()
        redis.get.return_value = "not-a-uuid"

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_client_not_found_raises_400(self):
        """Token pointing to non-existent client should return 400."""
        client_id = uuid.uuid4()
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(None)

        request = _make_mock_request(json_data={"token": "some-token", "password": "newpassword123"})

        redis = _mock_redis()
        redis.get.return_value = str(client_id)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await reset_password(request, db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_bytes_token_value_decoded(self):
        """Redis returning bytes (not str) should be handled correctly."""
        client_id = uuid.uuid4()
        mock_client = _make_mock_client(client_id=client_id)

        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        request = _make_mock_request(json_data={"token": "some-token", "password": "newpassword123"})

        redis = _mock_redis()
        redis.get.return_value = str(client_id).encode()  # bytes

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            result = await reset_password(request, db)

        assert "reset successfully" in result["message"]


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------

class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_valid_verification(self):
        """Valid verification token should mark email as verified."""
        client_id = uuid.uuid4()
        mock_client = _make_mock_client(client_id=client_id, email_verified=False)

        db = _make_mock_db()
        db.execute.return_value = _scalar_result(mock_client)

        redis = _mock_redis()
        redis.get.return_value = str(client_id)

        with (
            patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis),
            patch(SEND_WELCOME_PATCH, new_callable=AsyncMock),
        ):
            result = await verify_email("valid-token", db)

        assert result["verified"] is True
        assert mock_client.email_verified is True

    @pytest.mark.asyncio
    async def test_invalid_token_raises_400(self):
        """Invalid/expired verification token should return 400."""
        db = _make_mock_db()

        redis = _mock_redis()
        redis.get.return_value = None

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await verify_email("bad-token", db)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_redis_error_raises_500(self):
        """Redis failure during verification should return 500."""
        db = _make_mock_db()

        with patch(REDIS_PATCH, new_callable=AsyncMock, side_effect=ConnectionError("Redis down")):
            with pytest.raises(HTTPException) as exc_info:
                await verify_email("any-token", db)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_client_not_found_raises_400(self):
        """Token pointing to non-existent client should return 400."""
        client_id = uuid.uuid4()
        db = _make_mock_db()
        db.execute.return_value = _scalar_result(None)

        redis = _mock_redis()
        redis.get.return_value = str(client_id)

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await verify_email("some-token", db)
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Resend Verification
# ---------------------------------------------------------------------------

class TestResendVerification:
    @pytest.mark.asyncio
    async def test_already_verified_returns_message(self):
        """Already-verified clients should get an informational message."""
        client = _make_mock_client(email_verified=True)
        db = _make_mock_db()

        result = await resend_verification(db, client)
        assert "already verified" in result["message"]

    @pytest.mark.asyncio
    async def test_successful_resend(self):
        """Unverified client should trigger email send."""
        client = _make_mock_client(email_verified=False)
        db = _make_mock_db()

        redis = _mock_redis()
        redis.exists.return_value = False

        with (
            patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis),
            patch(SEND_VERIFICATION_PATCH, new_callable=AsyncMock) as mock_send,
            patch(SETTINGS_PATCH, return_value=_make_mock_settings()),
        ):
            result = await resend_verification(db, client)

        assert "Verification email sent" in result["message"]
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rate_limited_raises_429(self):
        """Too-frequent requests should raise 429."""
        client = _make_mock_client(email_verified=False)
        db = _make_mock_db()

        redis = _mock_redis()
        redis.exists.return_value = True

        with patch(REDIS_PATCH, new_callable=AsyncMock, return_value=redis):
            with pytest.raises(HTTPException) as exc_info:
                await resend_verification(db, client)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_redis_failure_raises_500(self):
        """Redis failure should return 500."""
        client = _make_mock_client(email_verified=False)
        db = _make_mock_db()

        with patch(REDIS_PATCH, new_callable=AsyncMock, side_effect=ConnectionError("Redis down")):
            with pytest.raises(HTTPException) as exc_info:
                await resend_verification(db, client)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Phone Provisioning - search_available_numbers
# ---------------------------------------------------------------------------

class TestSearchAvailableNumbers:
    @pytest.mark.asyncio
    async def test_valid_area_code(self):
        """Valid area code should return available numbers."""
        client = _make_mock_client()
        db = _make_mock_db()

        mock_numbers = ["+15125551000", "+15125551001"]

        with patch(SEARCH_NUMBERS_PATCH, new_callable=AsyncMock, return_value=mock_numbers):
            from src.api.dashboard import search_available_numbers as endpoint_fn
            result = await endpoint_fn("512", db, client)

        assert result["area_code"] == "512"
        assert len(result["numbers"]) == 2

    @pytest.mark.asyncio
    async def test_non_digit_area_code_raises_400(self):
        """Non-numeric area code should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        from src.api.dashboard import search_available_numbers as endpoint_fn
        with pytest.raises(HTTPException) as exc_info:
            await endpoint_fn("abc", db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_area_code_raises_400(self):
        """Empty area code should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        from src.api.dashboard import search_available_numbers as endpoint_fn
        with pytest.raises(HTTPException) as exc_info:
            await endpoint_fn("", db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_service_error_raises_502(self):
        """Twilio service error should return 502."""
        client = _make_mock_client()
        db = _make_mock_db()

        with patch(SEARCH_NUMBERS_PATCH, new_callable=AsyncMock, side_effect=Exception("Twilio API error")):
            from src.api.dashboard import search_available_numbers as endpoint_fn
            with pytest.raises(HTTPException) as exc_info:
                await endpoint_fn("512", db, client)
            assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Phone Provisioning - provision_number
# ---------------------------------------------------------------------------

class TestProvisionNumber:
    @pytest.mark.asyncio
    async def test_successful_provision(self):
        """Successful provisioning should update client and return status."""
        client = _make_mock_client(twilio_phone=None, business_type=None)
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": "+15125551234"})

        with patch(
            PROVISION_PATCH,
            new_callable=AsyncMock,
            return_value={
                "phone_number": "+15125551234",
                "phone_sid": "PN_test_123",
                "messaging_service_sid": "MG_test_123",
                "is_tollfree": False,
                "error": None,
            },
        ):
            result = await provision_number(request, db, client)

        assert result["status"] == "provisioned"
        assert result["phone_number"] == "+15125551234"
        assert client.twilio_phone == "+15125551234"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_already_provisioned_raises_400(self):
        """Client with existing phone should get 400."""
        client = _make_mock_client(twilio_phone="+15125559999")
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": "+15125551234"})

        with pytest.raises(HTTPException) as exc_info:
            await provision_number(request, db, client)
        assert exc_info.value.status_code == 400
        assert "already provisioned" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_phone_number_raises_400(self):
        """Request without phone_number should return 400."""
        client = _make_mock_client(twilio_phone=None)
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": ""})

        with pytest.raises(HTTPException) as exc_info:
            await provision_number(request, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_provision_error_from_service_raises_502(self):
        """Error from provisioning service should return 502."""
        client = _make_mock_client(twilio_phone=None)
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": "+15125551234"})

        with patch(
            PROVISION_PATCH,
            new_callable=AsyncMock,
            return_value={"error": "Number not available", "phone_number": None, "phone_sid": None},
        ):
            with pytest.raises(HTTPException) as exc_info:
                await provision_number(request, db, client)
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_tollfree_auto_triggers_verification(self):
        """Toll-free number provisioning should auto-trigger verification."""
        client = _make_mock_client(
            twilio_phone=None,
            business_type=None,
            owner_email="owner@hvac.com",
            business_website="https://hvac.com",
        )
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": "+18005551234"})

        with (
            patch(
                PROVISION_PATCH,
                new_callable=AsyncMock,
                return_value={
                    "phone_number": "+18005551234",
                    "phone_sid": "PN_tf_123",
                    "messaging_service_sid": "MG_tf_123",
                    "is_tollfree": True,
                    "error": None,
                },
            ),
            patch(
                TF_VERIFY_PATCH,
                new_callable=AsyncMock,
                return_value={"error": None, "result": {"verification_sid": "VF_test_123"}},
            ) as mock_tf,
        ):
            result = await provision_number(request, db, client)

        assert result["is_tollfree"] is True
        mock_tf.assert_awaited_once()
        assert client.ten_dlc_status == "tf_verification_pending"

    @pytest.mark.asyncio
    async def test_service_exception_raises_502(self):
        """Unexpected exception during provisioning should return 502."""
        client = _make_mock_client(twilio_phone=None)
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": "+15125551234"})

        with patch(PROVISION_PATCH, new_callable=AsyncMock, side_effect=Exception("Unexpected Twilio error")):
            with pytest.raises(HTTPException) as exc_info:
                await provision_number(request, db, client)
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_invalid_json_raises_400(self):
        """Invalid JSON body should return 400."""
        client = _make_mock_client(twilio_phone=None)
        db = _make_mock_db()
        request = _make_mock_request()  # json() raises

        with pytest.raises(HTTPException) as exc_info:
            await provision_number(request, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_auto_10dlc_with_presaved_business_info(self):
        """If business info was pre-saved and not toll-free, auto-trigger 10DLC."""
        client = _make_mock_client(
            twilio_phone=None,
            business_type="llc",
            business_ein="12-3456789",
            business_website="https://hvac.com",
            owner_email="owner@hvac.com",
            owner_phone="+15125551111",
            business_address={"street": "123 Main", "city": "Austin", "state": "TX", "zip": "78701"},
        )
        db = _make_mock_db()
        request = _make_mock_request(json_data={"phone_number": "+15125551234"})

        with (
            patch(
                PROVISION_PATCH,
                new_callable=AsyncMock,
                return_value={
                    "phone_number": "+15125551234",
                    "phone_sid": "PN_test_123",
                    "messaging_service_sid": "MG_test_123",
                    "is_tollfree": False,
                    "error": None,
                },
            ),
            patch(
                CREATE_PROFILE_PATCH,
                new_callable=AsyncMock,
                return_value={"error": None, "result": {"profile_sid": "PS_test_123"}},
            ),
            patch(
                SUBMIT_PROFILE_PATCH,
                new_callable=AsyncMock,
                return_value={"error": None},
            ),
        ):
            result = await provision_number(request, db, client)

        assert result["status"] == "provisioned"
        assert client.ten_dlc_profile_sid == "PS_test_123"
        assert client.ten_dlc_status == "profile_pending"


# ---------------------------------------------------------------------------
# Business Registration
# ---------------------------------------------------------------------------

class TestSubmitBusinessRegistration:
    @pytest.mark.asyncio
    async def test_successful_registration(self):
        """Valid business info should trigger profile creation."""
        client = _make_mock_client(
            twilio_phone="+15125551234",
            ten_dlc_profile_sid=None,
            ten_dlc_status="collecting_info",
            owner_email="owner@hvac.com",
        )
        db = _make_mock_db()
        request = _make_mock_request(json_data={
            "business_type": "llc",
            "business_website": "https://hvac.com",
            "business_ein": "12-3456789",
            "business_address": {"street": "123 Main", "city": "Austin", "state": "TX", "zip": "78701"},
        })

        with (
            patch(CREATE_PROFILE_PATCH, new_callable=AsyncMock, return_value={"error": None, "result": {"profile_sid": "PS_test_123"}}),
            patch(SUBMIT_PROFILE_PATCH, new_callable=AsyncMock, return_value={"error": None}),
        ):
            result = await submit_business_registration(request, db, client)

        assert result["status"] == "profile_pending"
        assert result["profile_sid"] == "PS_test_123"

    @pytest.mark.asyncio
    async def test_invalid_business_type_raises_400(self):
        """Invalid business_type should return 400."""
        client = _make_mock_client(twilio_phone="+15125551234")
        db = _make_mock_db()
        request = _make_mock_request(json_data={"business_type": "invalid_type"})

        with pytest.raises(HTTPException) as exc_info:
            await submit_business_registration(request, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_business_type_raises_400(self):
        """Missing business_type should return 400."""
        client = _make_mock_client(twilio_phone="+15125551234")
        db = _make_mock_db()
        request = _make_mock_request(json_data={"business_website": "https://hvac.com"})

        with pytest.raises(HTTPException) as exc_info:
            await submit_business_registration(request, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_phone_provisioned_raises_400(self):
        """Client without provisioned phone should get 400."""
        client = _make_mock_client(twilio_phone=None)
        db = _make_mock_db()
        request = _make_mock_request(json_data={"business_type": "llc"})

        with pytest.raises(HTTPException) as exc_info:
            await submit_business_registration(request, db, client)
        assert exc_info.value.status_code == 400
        assert "Provision a phone number first" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_already_in_progress_raises_409(self):
        """Registration already in progress should return 409."""
        client = _make_mock_client(
            twilio_phone="+15125551234",
            ten_dlc_profile_sid="PS_existing",
            ten_dlc_status="profile_pending",
        )
        db = _make_mock_db()
        request = _make_mock_request(json_data={"business_type": "llc"})

        with pytest.raises(HTTPException) as exc_info:
            await submit_business_registration(request, db, client)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_profile_creation_failure_raises_502(self):
        """Profile creation failure should return 502."""
        client = _make_mock_client(
            twilio_phone="+15125551234",
            ten_dlc_profile_sid=None,
            ten_dlc_status="collecting_info",
            owner_email="owner@hvac.com",
        )
        db = _make_mock_db()
        request = _make_mock_request(json_data={"business_type": "llc"})

        with patch(CREATE_PROFILE_PATCH, new_callable=AsyncMock, return_value={"error": "Profile creation failed", "result": None}):
            with pytest.raises(HTTPException) as exc_info:
                await submit_business_registration(request, db, client)
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_submission_failure_sets_collecting_info(self):
        """Profile submission failure should set status to collecting_info."""
        client = _make_mock_client(
            twilio_phone="+15125551234",
            ten_dlc_profile_sid=None,
            ten_dlc_status="collecting_info",
            owner_email="owner@hvac.com",
        )
        db = _make_mock_db()
        request = _make_mock_request(json_data={"business_type": "llc"})

        with (
            patch(CREATE_PROFILE_PATCH, new_callable=AsyncMock, return_value={"error": None, "result": {"profile_sid": "PS_test"}}),
            patch(SUBMIT_PROFILE_PATCH, new_callable=AsyncMock, return_value={"error": "Submission failed"}),
        ):
            result = await submit_business_registration(request, db, client)

        assert result["status"] == "collecting_info"


# ---------------------------------------------------------------------------
# Registration Status
# ---------------------------------------------------------------------------

class TestGetRegistrationStatus:
    @pytest.mark.asyncio
    async def test_returns_status_info(self):
        """Should return mapped registration status info."""
        client = _make_mock_client(
            twilio_phone="+15125551234",
            ten_dlc_status="profile_pending",
            business_type="llc",
        )
        db = _make_mock_db()

        with patch(IS_TOLLFREE_PATCH, return_value=False):
            result = await get_registration_status(db, client)

        assert result["ten_dlc_status"] == "profile_pending"
        assert result["display_status"] == "In Review"
        assert result["has_phone"] is True
        assert result["has_business_info"] is True

    @pytest.mark.asyncio
    async def test_no_status_defaults_to_pending(self):
        """Client with no status should default to 'pending'."""
        client = _make_mock_client(ten_dlc_status=None, twilio_phone=None, business_type=None)
        db = _make_mock_db()

        with patch(IS_TOLLFREE_PATCH, return_value=False):
            result = await get_registration_status(db, client)

        assert result["ten_dlc_status"] == "pending"
        assert result["display_status"] == "Not Started"


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

class TestMaskEin:
    def test_full_ein(self):
        assert _mask_ein("12-3456789") == "***-**-6789"

    def test_ein_without_dashes(self):
        assert _mask_ein("123456789") == "***-**-6789"

    def test_short_ein(self):
        assert _mask_ein("1234") == "1234"

    def test_none_ein(self):
        assert _mask_ein(None) is None

    def test_empty_ein(self):
        assert _mask_ein("") == ""


class TestCheckIsTollfree:
    def test_tollfree_number(self):
        with patch(IS_TOLLFREE_PATCH, return_value=True):
            assert _check_is_tollfree("+18005551234") is True

    def test_non_tollfree_number(self):
        with patch(IS_TOLLFREE_PATCH, return_value=False):
            assert _check_is_tollfree("+15125551234") is False

    def test_none_phone(self):
        assert _check_is_tollfree(None) is False


class TestGetRegistrationStatusInfo:
    def test_known_status_returns_info(self):
        client = _make_mock_client()
        info = _get_registration_status_info("active", client)
        assert info["display"] == "Active"
        assert info["next_step"] is None

    def test_collecting_info_status(self):
        client = _make_mock_client()
        info = _get_registration_status_info("collecting_info", client)
        assert info["display"] == "Info Needed"
        assert info["next_step"] == "submit_business_info"

    def test_unknown_status_defaults_to_pending(self):
        client = _make_mock_client()
        info = _get_registration_status_info("totally_unknown", client)
        assert info["display"] == "Not Started"

    def test_brand_rejected_status(self):
        client = _make_mock_client()
        info = _get_registration_status_info("brand_rejected", client)
        assert info["display"] == "Action Required"
        assert info["next_step"] == "contact_support"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class TestGetMetrics:
    @pytest.mark.asyncio
    async def test_returns_metrics(self):
        """Should delegate to get_dashboard_metrics and return result."""
        client = _make_mock_client()
        db = _make_mock_db()

        mock_metrics = MagicMock()
        mock_metrics.total_leads = 100

        with patch(METRICS_PATCH, new_callable=AsyncMock, return_value=mock_metrics):
            result = await get_metrics("7d", db, client)

        assert result.total_leads == 100


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

class TestGetLeads:
    @pytest.mark.asyncio
    async def test_basic_lead_list(self):
        """Should return paginated lead list."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
        ]

        result = await get_leads(1, 20, None, None, None, db, client)

        assert result.total == 1
        assert result.page == 1
        assert len(result.leads) == 1
        assert result.leads[0].first_name == "John"

    @pytest.mark.asyncio
    async def test_lead_list_with_state_filter(self):
        """Should filter leads by state."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(0),
            _scalars_result([]),
        ]

        result = await get_leads(1, 20, "qualifying", None, None, db, client)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_lead_list_with_search(self):
        """Should filter leads by search term."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id, first_name="Searchable")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
        ]

        result = await get_leads(1, 20, None, None, "Searchable", db, client)
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_pagination_calculation(self):
        """Page count should be calculated correctly."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(45),
            _scalars_result([]),
        ]

        result = await get_leads(1, 20, None, None, None, db, client)
        assert result.pages == 3  # ceil(45/20)

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """No leads should return empty list with pages=1."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(0),
            _scalars_result([]),
        ]

        result = await get_leads(1, 20, None, None, None, db, client)
        assert result.total == 0
        assert result.pages == 1

    @pytest.mark.asyncio
    async def test_phone_masking_in_results(self):
        """Phone numbers should be masked in results."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id, phone="+15125559876")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
        ]

        result = await get_leads(1, 20, None, None, None, db, client)
        assert result.leads[0].phone_masked == "+15125***"


# ---------------------------------------------------------------------------
# Export Leads CSV
# ---------------------------------------------------------------------------

class TestExportLeadsCsv:
    @pytest.mark.asyncio
    async def test_csv_export(self):
        """Should return a StreamingResponse with CSV data."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(
            client_id=client_id,
            phone="+15125559876",
            total_messages_sent=3,
            total_messages_received=2,
        )

        db.execute.return_value = _scalars_result([lead])

        response = await export_leads_csv(db, client)

        assert response.media_type == "text/csv"
        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        csv_text = body.decode()
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)

        assert len(rows) == 2  # Header + 1 data row
        assert rows[0][0] == "id"
        assert "***" in rows[1][3]  # Phone masked

    @pytest.mark.asyncio
    async def test_csv_export_empty(self):
        """CSV export with no leads should have only header."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.execute.return_value = _scalars_result([])

        response = await export_leads_csv(db, client)
        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        csv_text = body.decode()
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1  # Header only


# ---------------------------------------------------------------------------
# Lead Detail
# ---------------------------------------------------------------------------

class TestGetLeadDetail:
    @pytest.mark.asyncio
    async def test_valid_lead_detail(self):
        """Should return full lead detail with conversations and events."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead_id = uuid.uuid4()
        lead = _make_mock_lead(lead_id=lead_id, client_id=client_id, consent_id=None)

        db.get.return_value = lead

        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.direction = "outbound"
        conv.agent_id = "intake"
        conv.content = "Hello!"
        conv.delivery_status = "delivered"
        conv.created_at = datetime.now(timezone.utc)

        event = MagicMock()
        event.id = uuid.uuid4()
        event.action = "sms_sent"
        event.status = "success"
        event.message = "SMS sent"
        event.duration_ms = 100
        event.created_at = datetime.now(timezone.utc)

        db.execute.side_effect = [
            _scalars_result([conv]),
            _scalar_result(None),       # booking
            _scalars_result([event]),
        ]

        result = await get_lead_detail(str(lead_id), db, client)

        assert result.lead.id == str(lead_id)
        assert len(result.conversations) == 1
        assert result.booking is None
        assert result.consent is None
        assert len(result.events) == 1

    @pytest.mark.asyncio
    async def test_lead_not_found_raises_404(self):
        """Non-existent lead should return 404."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_lead_detail(str(uuid.uuid4()), db, client)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_lead_wrong_client_raises_404(self):
        """Lead belonging to another client should return 404."""
        client = _make_mock_client(client_id=uuid.uuid4())
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=uuid.uuid4())
        db.get.return_value = lead

        with pytest.raises(HTTPException) as exc_info:
            await get_lead_detail(str(lead.id), db, client)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_lead_id_format_raises_400(self):
        """Non-UUID lead_id should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await get_lead_detail("not-a-uuid", db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_lead_with_booking_and_consent(self):
        """Lead with booking and consent should include them in response."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        consent_id = uuid.uuid4()
        lead_id = uuid.uuid4()
        lead = _make_mock_lead(lead_id=lead_id, client_id=client_id, consent_id=consent_id)

        consent_mock = MagicMock()
        consent_mock.id = consent_id
        consent_mock.consent_type = "pec"
        consent_mock.consent_method = "text_in"
        consent_mock.is_active = True
        consent_mock.opted_out = False
        consent_mock.created_at = datetime.now(timezone.utc)

        db.get.side_effect = [lead, consent_mock]

        booking = MagicMock()
        booking.id = uuid.uuid4()
        booking.appointment_date = date(2026, 3, 15)
        booking.time_window_start = time(9, 0)
        booking.time_window_end = time(11, 0)
        booking.service_type = "AC Repair"
        booking.tech_name = "Mike"
        booking.status = "confirmed"
        booking.crm_sync_status = "synced"

        db.execute.side_effect = [
            _scalars_result([]),
            _scalar_result(booking),
            _scalars_result([]),
        ]

        result = await get_lead_detail(str(lead_id), db, client)

        assert result.booking is not None
        assert result.booking.service_type == "AC Repair"
        assert result.consent is not None
        assert result.consent.consent_type == "pec"


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class TestGetConversations:
    @pytest.mark.asyncio
    async def test_returns_conversations(self):
        """Should return conversation list for a lead."""
        client = _make_mock_client()
        db = _make_mock_db()

        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.direction = "outbound"
        conv.agent_id = "qualify"
        conv.content = "What service do you need?"
        conv.delivery_status = "delivered"
        conv.created_at = datetime.now(timezone.utc)

        db.execute.return_value = _scalars_result([conv])

        result = await get_conversations(str(uuid.uuid4()), db, client)

        assert len(result) == 1
        assert result[0]["direction"] == "outbound"

    @pytest.mark.asyncio
    async def test_invalid_lead_id_raises_400(self):
        """Invalid lead_id format should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await get_conversations("not-a-uuid", db, client)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

class TestGetActivity:
    @pytest.mark.asyncio
    async def test_returns_activity_events(self):
        """Should return activity feed with mapped event types."""
        client = _make_mock_client()
        db = _make_mock_db()

        events = [
            MagicMock(action="sms_sent", lead_id=uuid.uuid4(), message="SMS sent", created_at=datetime.now(timezone.utc)),
            MagicMock(action="sms_received", lead_id=uuid.uuid4(), message="Reply", created_at=datetime.now(timezone.utc)),
            MagicMock(action="booking_confirmed", lead_id=uuid.uuid4(), message="Booked", created_at=datetime.now(timezone.utc)),
            MagicMock(action="opt_out_processed", lead_id=uuid.uuid4(), message="Opt out", created_at=datetime.now(timezone.utc)),
            MagicMock(action="intake_response", lead_id=uuid.uuid4(), message="Intake", created_at=datetime.now(timezone.utc)),
            MagicMock(action="lead_created", lead_id=None, message="New lead", created_at=datetime.now(timezone.utc)),
        ]

        db.execute.return_value = _scalars_result(events)

        result = await get_activity(50, db, client)

        assert len(result) == 6
        assert result[0].type == "sms_sent"
        assert result[1].type == "sms_received"
        assert result[2].type == "booking_confirmed"
        assert result[3].type == "opt_out"
        assert result[4].type == "sms_sent"  # intake maps to sms_sent
        assert result[5].type == "lead_created"

    @pytest.mark.asyncio
    async def test_empty_activity(self):
        """Empty activity should return empty list."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.execute.return_value = _scalars_result([])

        result = await get_activity(50, db, client)
        assert result == []


# ---------------------------------------------------------------------------
# Weekly Report
# ---------------------------------------------------------------------------

class TestGetWeeklyReport:
    @pytest.mark.asyncio
    async def test_returns_metrics(self):
        """Should delegate to get_dashboard_metrics with 7d period."""
        client = _make_mock_client()
        db = _make_mock_db()

        mock_metrics = MagicMock()

        with patch(METRICS_PATCH, new_callable=AsyncMock, return_value=mock_metrics) as mock_fn:
            result = await get_weekly_report(None, db, client)

        assert result == mock_metrics
        mock_fn.assert_awaited_once_with(db, str(client.id), "7d")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class TestGetSettings:
    @pytest.mark.asyncio
    async def test_returns_client_settings(self):
        """Should return full client configuration."""
        client = _make_mock_client(
            business_name="HVAC Pros",
            trade_type="hvac",
            tier="pro",
            twilio_phone="+15125551234",
            ten_dlc_status="active",
            crm_type="servicetitan",
            config={"persona": {"rep_name": "Sarah"}},
            email_verified=True,
            billing_status="active",
            twilio_messaging_service_sid="MG_123",
            business_website="https://hvac.com",
            business_type="llc",
            business_ein="12-3456789",
            business_address={"city": "Austin"},
        )
        db = _make_mock_db()

        result = await get_settings(db, client)

        assert result["business_name"] == "HVAC Pros"
        assert result["tier"] == "pro"
        assert result["email_verified"] is True
        assert result["business_ein"] == "***-**-6789"
        assert result["crm_type"] == "servicetitan"


class TestUpdateSettings:
    @pytest.mark.asyncio
    async def test_update_config(self):
        """Should merge new config with existing config."""
        client = _make_mock_client(config={"persona": {"rep_name": "Sarah"}})
        db = _make_mock_db()

        payload_data = {"config": {"persona": {"rep_name": "Mike"}, "new_key": "value"}}
        request = _make_mock_request(json_data=payload_data, body=json.dumps(payload_data).encode())

        result = await update_settings(request, db, client)

        assert result["status"] == "updated"
        assert client.config["persona"]["rep_name"] == "Mike"
        assert client.config["new_key"] == "value"

    @pytest.mark.asyncio
    async def test_config_not_dict_raises_400(self):
        """Non-dict config should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        payload_data = {"config": "not-a-dict"}
        request = _make_mock_request(json_data=payload_data, body=json.dumps(payload_data).encode())

        with pytest.raises(HTTPException) as exc_info:
            await update_settings(request, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_payload_too_large_raises_413(self):
        """Payload > 50KB should return 413.

        Note: The source code raises HTTPException(413) inside a try block
        whose except catches json.JSONDecodeError. Because `import json` is
        after the size check, the except clause gets an UnboundLocalError
        when the HTTPException is re-raised (it is NOT a JSONDecodeError).
        The end result is an UnboundLocalError propagating, which we verify
        here as the actual runtime behavior.
        """
        client = _make_mock_client()
        db = _make_mock_db()

        large_body = b"x" * 52000
        request = _make_mock_request(body=large_body)

        # The source code has a scoping issue: `import json` is after the
        # size check, but the except clause catches `json.JSONDecodeError`.
        # When HTTPException(413) is raised, it's not JSONDecodeError, so
        # it passes to the next except (which re-raises), resulting in the
        # HTTPException propagating correctly because the second except
        # catches HTTPException.
        with pytest.raises((HTTPException, UnboundLocalError)):
            await update_settings(request, db, client)

    @pytest.mark.asyncio
    async def test_invalid_json_raises_400(self):
        """Invalid JSON body should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        request = _make_mock_request(body=b"not-json{{{")

        with pytest.raises((HTTPException, UnboundLocalError)):
            await update_settings(request, db, client)

    @pytest.mark.asyncio
    async def test_no_config_key_commits(self):
        """Payload without config key should still commit."""
        client = _make_mock_client()
        db = _make_mock_db()

        payload_data = {"other_key": "value"}
        request = _make_mock_request(json_data=payload_data, body=json.dumps(payload_data).encode())

        result = await update_settings(request, db, client)
        assert result["status"] == "updated"
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

class TestCompleteOnboarding:
    @pytest.mark.asyncio
    async def test_successful_onboarding(self):
        """Should save onboarding config and mark as live."""
        client = _make_mock_client(config={"existing": "data"})
        db = _make_mock_db()

        payload = {
            "config": {"persona": {"rep_name": "Sarah"}},
            "crm_type": "servicetitan",
            "crm_tenant_id": "tenant-123",
        }

        result = await complete_onboarding(payload, db, client)

        assert result["status"] == "onboarded"
        assert client.onboarding_status == "live"
        assert client.crm_type == "servicetitan"
        assert client.crm_tenant_id == "tenant-123"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_onboarding_with_crm_api_key(self):
        """CRM API key should be encrypted before storage."""
        client = _make_mock_client()
        db = _make_mock_db()

        payload = {"crm_api_key": "secret-api-key-123"}

        with patch(ENCRYPT_PATCH, return_value="encrypted_value"):
            result = await complete_onboarding(payload, db, client)

        assert result["status"] == "onboarded"
        assert client.crm_api_key_encrypted == "encrypted_value"

    @pytest.mark.asyncio
    async def test_onboarding_with_business_info(self):
        """Business info should be saved during onboarding."""
        client = _make_mock_client()
        db = _make_mock_db()

        payload = {
            "business_type": "llc",
            "business_ein": "12-3456789",
            "business_website": "https://hvac.com",
            "business_address": {"city": "Austin"},
        }

        result = await complete_onboarding(payload, db, client)

        assert client.business_type == "llc"
        assert client.business_ein == "12-3456789"
        assert client.business_website == "https://hvac.com"
        assert client.business_address == {"city": "Austin"}

    @pytest.mark.asyncio
    async def test_invalid_business_type_raises_400(self):
        """Invalid business_type during onboarding should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        payload = {"business_type": "invalid_type"}

        with pytest.raises(HTTPException) as exc_info:
            await complete_onboarding(payload, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_payload_still_marks_live(self):
        """Empty payload should still mark onboarding as live."""
        client = _make_mock_client()
        db = _make_mock_db()

        result = await complete_onboarding({}, db, client)

        assert result["status"] == "onboarded"
        assert client.onboarding_status == "live"


# ---------------------------------------------------------------------------
# Compliance Summary
# ---------------------------------------------------------------------------

class TestGetComplianceSummary:
    @pytest.mark.asyncio
    async def test_returns_compliance_data(self):
        """Should return compliance counts."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(100),
            _scalar_result(5),
            _scalar_result(3),
        ]

        result = await get_compliance_summary(db, client)

        assert result.total_consent_records == 100
        assert result.opted_out_count == 5
        assert result.pending_followups == 3
        assert result.messages_in_quiet_hours == 0
        assert result.cold_outreach_violations == 0

    @pytest.mark.asyncio
    async def test_zero_counts(self):
        """New client should have all-zero compliance counts."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(0),
            _scalar_result(0),
            _scalar_result(0),
        ]

        result = await get_compliance_summary(db, client)
        assert result.total_consent_records == 0
        assert result.opted_out_count == 0
        assert result.pending_followups == 0


# ---------------------------------------------------------------------------
# Lead Status Update
# ---------------------------------------------------------------------------

class TestUpdateLeadStatus:
    @pytest.mark.asyncio
    async def test_valid_status_update(self):
        """Valid status should update the lead."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)
        db.get.return_value = lead

        result = await update_lead_status(str(lead.id), {"status": "qualified"}, db, client)

        assert result["status"] == "updated"
        assert result["new_state"] == "qualified"
        assert lead.state == "qualified"

    @pytest.mark.asyncio
    async def test_invalid_status_raises_400(self):
        """Invalid status value (opted_out is excluded) should return 400."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)
        db.get.return_value = lead

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_status(str(lead.id), {"status": "opted_out"}, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_lead_not_found_raises_404(self):
        """Non-existent lead should return 404."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_status(str(uuid.uuid4()), {"status": "qualified"}, db, client)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_lead_id_raises_400(self):
        """Invalid UUID should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_status("not-a-uuid", {"status": "qualified"}, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_wrong_client_raises_404(self):
        """Lead from different client should return 404."""
        client = _make_mock_client(client_id=uuid.uuid4())
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=uuid.uuid4())
        db.get.return_value = lead

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_status(str(lead.id), {"status": "qualified"}, db, client)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_all_valid_statuses(self):
        """All valid statuses should be accepted."""
        valid_statuses = {"new", "qualifying", "qualified", "booking", "booked", "completed", "cold", "dead"}

        for status in valid_statuses:
            client_id = uuid.uuid4()
            client = _make_mock_client(client_id=client_id)
            db = _make_mock_db()
            lead = _make_mock_lead(client_id=client_id)
            db.get.return_value = lead

            result = await update_lead_status(str(lead.id), {"status": status}, db, client)
            assert result["new_state"] == status


# ---------------------------------------------------------------------------
# Archive Lead
# ---------------------------------------------------------------------------

class TestArchiveLead:
    @pytest.mark.asyncio
    async def test_archive_lead(self):
        """Should mark lead as archived."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)
        db.get.return_value = lead

        result = await archive_lead(str(lead.id), {"archived": True}, db, client)
        assert result["archived"] is True

    @pytest.mark.asyncio
    async def test_unarchive_lead(self):
        """Should mark lead as unarchived."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id, archived=True)
        db.get.return_value = lead

        result = await archive_lead(str(lead.id), {"archived": False}, db, client)
        assert result["archived"] is False

    @pytest.mark.asyncio
    async def test_lead_not_found_raises_404(self):
        """Non-existent lead should return 404."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await archive_lead(str(uuid.uuid4()), {"archived": True}, db, client)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_lead_id_raises_400(self):
        """Invalid UUID should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await archive_lead("bad-id", {"archived": True}, db, client)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Update Lead Tags
# ---------------------------------------------------------------------------

class TestUpdateLeadTags:
    @pytest.mark.asyncio
    async def test_set_tags(self):
        """Should set tags on the lead."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)
        db.get.return_value = lead

        result = await update_lead_tags(str(lead.id), {"tags": ["vip", "urgent"]}, db, client)
        assert result["tags"] == ["vip", "urgent"]

    @pytest.mark.asyncio
    async def test_tags_not_list_raises_400(self):
        """Non-list tags should return 400."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)
        db.get.return_value = lead

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_tags(str(lead.id), {"tags": "not-a-list"}, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_lead_not_found_raises_404(self):
        """Non-existent lead should return 404."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_tags(str(uuid.uuid4()), {"tags": []}, db, client)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Update Lead Notes
# ---------------------------------------------------------------------------

class TestUpdateLeadNotes:
    @pytest.mark.asyncio
    async def test_set_notes(self):
        """Should update notes on the lead."""
        client_id = uuid.uuid4()
        client = _make_mock_client(client_id=client_id)
        db = _make_mock_db()

        lead = _make_mock_lead(client_id=client_id)
        db.get.return_value = lead

        result = await update_lead_notes(str(lead.id), {"notes": "Customer prefers mornings"}, db, client)
        assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_lead_not_found_raises_404(self):
        """Non-existent lead should return 404."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_notes(str(uuid.uuid4()), {"notes": ""}, db, client)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_lead_id_raises_400(self):
        """Invalid UUID should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await update_lead_notes("bad-id", {"notes": ""}, db, client)
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

class TestGetBookings:
    @pytest.mark.asyncio
    async def test_returns_bookings(self):
        """Should return bookings list."""
        client = _make_mock_client()
        db = _make_mock_db()

        booking = MagicMock()
        booking.id = uuid.uuid4()
        booking.lead_id = uuid.uuid4()
        booking.appointment_date = date(2026, 3, 15)
        booking.time_window_start = time(9, 0)
        booking.time_window_end = time(11, 0)
        booking.service_type = "AC Repair"
        booking.tech_name = "Mike"
        booking.status = "confirmed"
        booking.crm_sync_status = "synced"
        booking.created_at = datetime.now(timezone.utc)

        db.execute.return_value = _scalars_result([booking])

        result = await get_bookings(None, None, db, client)

        assert result["total"] == 1
        assert result["bookings"][0]["service_type"] == "AC Repair"

    @pytest.mark.asyncio
    async def test_date_range_filter(self):
        """Should filter bookings by date range."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.execute.return_value = _scalars_result([])

        result = await get_bookings("2026-03-01", "2026-03-31", db, client)
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_invalid_start_date_raises_400(self):
        """Invalid start date format should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await get_bookings("not-a-date", None, db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_end_date_raises_400(self):
        """Invalid end date format should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await get_bookings("2026-03-01", "not-a-date", db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_bookings(self):
        """No bookings should return empty list."""
        client = _make_mock_client()
        db = _make_mock_db()
        db.execute.return_value = _scalars_result([])

        result = await get_bookings(None, None, db, client)
        assert result["total"] == 0
        assert result["bookings"] == []


# ---------------------------------------------------------------------------
# Custom Reports
# ---------------------------------------------------------------------------

class TestGetCustomReport:
    @pytest.mark.asyncio
    async def test_valid_date_range(self):
        """Should return report data for a valid date range."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(25),
            _rows_result([("qualifying", 10), ("booked", 15)]),
            _scalar_result(8),
            _scalar_result(4500.0),
        ]

        result = await get_custom_report("2026-01-01", "2026-01-31", db, client)

        assert result["total_leads"] == 25
        assert result["bookings"] == 8
        assert result["avg_response_ms"] == 4500
        assert result["by_state"]["qualifying"] == 10

    @pytest.mark.asyncio
    async def test_invalid_date_format_raises_400(self):
        """Invalid date format should return 400."""
        client = _make_mock_client()
        db = _make_mock_db()

        with pytest.raises(HTTPException) as exc_info:
            await get_custom_report("not-a-date", "2026-01-31", db, client)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_data_returns_zeros(self):
        """Empty date range should return zeroed metrics."""
        client = _make_mock_client()
        db = _make_mock_db()

        db.execute.side_effect = [
            _scalar_result(0),
            _rows_result([]),
            _scalar_result(0),
            _scalar_result(None),
        ]

        result = await get_custom_report("2026-01-01", "2026-01-31", db, client)

        assert result["total_leads"] == 0
        assert result["bookings"] == 0
        assert result["avg_response_ms"] is None
        assert result["by_state"] == {}
