"""
Comprehensive tests for LeadLock utility modules.

Covers: metrics, timezone, encryption, rate_limiter, dead_letter, locks, alerting.
All external dependencies (Redis, settings, DB) are mocked.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest


# ---------------------------------------------------------------------------
# 1. src/utils/metrics.py - Timer + response_time_bucket
# ---------------------------------------------------------------------------


class TestTimer:
    """Tests for the Timer helper class."""

    def test_start_returns_self(self):
        from src.utils.metrics import Timer

        timer = Timer()
        result = timer.start()
        assert result is timer

    def test_elapsed_ms_before_start_returns_zero(self):
        from src.utils.metrics import Timer

        timer = Timer()
        assert timer.elapsed_ms == 0

    def test_elapsed_ms_after_start_returns_positive(self):
        from src.utils.metrics import Timer

        timer = Timer()
        timer.start()
        # Even an immediate read should give a non-negative int
        assert isinstance(timer.elapsed_ms, int)
        assert timer.elapsed_ms >= 0

    def test_stop_returns_elapsed_ms(self):
        from src.utils.metrics import Timer

        timer = Timer()
        timer.start()
        ms = timer.stop()
        assert isinstance(ms, int)
        assert ms >= 0

    def test_elapsed_ms_after_stop_is_frozen(self):
        from src.utils.metrics import Timer

        timer = Timer()
        timer.start()
        timer.stop()
        frozen_value = timer.elapsed_ms
        # Reading again should return the same frozen value
        assert timer.elapsed_ms == frozen_value

    def test_start_stop_measures_sleep(self):
        from src.utils.metrics import Timer

        timer = Timer()
        timer.start()
        time.sleep(0.05)  # 50ms
        ms = timer.stop()
        # Should be at least 40ms (allowing jitter) and less than 500ms
        assert ms >= 40
        assert ms < 500


class TestResponseTimeBucket:
    """Tests for response_time_bucket categorization."""

    def test_under_10s(self):
        from src.utils.metrics import response_time_bucket

        assert response_time_bucket(0) == "0-10s"
        assert response_time_bucket(5000) == "0-10s"
        assert response_time_bucket(9999) == "0-10s"

    def test_10_to_30s(self):
        from src.utils.metrics import response_time_bucket

        assert response_time_bucket(10000) == "10-30s"
        assert response_time_bucket(20000) == "10-30s"
        assert response_time_bucket(29999) == "10-30s"

    def test_30_to_60s(self):
        from src.utils.metrics import response_time_bucket

        assert response_time_bucket(30000) == "30-60s"
        assert response_time_bucket(45000) == "30-60s"
        assert response_time_bucket(59999) == "30-60s"

    def test_over_60s(self):
        from src.utils.metrics import response_time_bucket

        assert response_time_bucket(60000) == "60s+"
        assert response_time_bucket(120000) == "60s+"
        assert response_time_bucket(999999) == "60s+"


# ---------------------------------------------------------------------------
# 2. src/utils/timezone.py - get_timezone_for_state + get_zoneinfo
# ---------------------------------------------------------------------------


class TestGetTimezoneForState:
    """Tests for get_timezone_for_state lookup."""

    def test_texas_returns_chicago(self):
        from src.utils.timezone import get_timezone_for_state

        assert get_timezone_for_state("TX") == "America/Chicago"

    def test_california_returns_los_angeles(self):
        from src.utils.timezone import get_timezone_for_state

        assert get_timezone_for_state("CA") == "America/Los_Angeles"

    def test_none_input_returns_none(self):
        from src.utils.timezone import get_timezone_for_state

        assert get_timezone_for_state(None) is None

    def test_empty_string_returns_none(self):
        from src.utils.timezone import get_timezone_for_state

        assert get_timezone_for_state("") is None

    def test_unknown_state_returns_none(self):
        from src.utils.timezone import get_timezone_for_state

        assert get_timezone_for_state("XX") is None
        assert get_timezone_for_state("ZZ") is None

    def test_case_insensitive_lookup(self):
        from src.utils.timezone import get_timezone_for_state

        assert get_timezone_for_state("tx") == "America/Chicago"
        assert get_timezone_for_state("ca") == "America/Los_Angeles"
        assert get_timezone_for_state("Ny") == "America/New_York"

    def test_all_50_states_plus_dc_are_mapped(self):
        from src.utils.timezone import STATE_TIMEZONE_MAP

        # 50 states + DC = 51
        assert len(STATE_TIMEZONE_MAP) == 51


class TestGetZoneinfo:
    """Tests for get_zoneinfo resolution logic."""

    def test_timezone_str_takes_precedence_over_state(self):
        from src.utils.timezone import get_zoneinfo

        result = get_zoneinfo(state_code="TX", timezone_str="America/Los_Angeles")
        assert result == ZoneInfo("America/Los_Angeles")

    def test_timezone_str_alone(self):
        from src.utils.timezone import get_zoneinfo

        result = get_zoneinfo(timezone_str="America/Denver")
        assert result == ZoneInfo("America/Denver")

    def test_state_code_lookup(self):
        from src.utils.timezone import get_zoneinfo

        result = get_zoneinfo(state_code="CA")
        assert result == ZoneInfo("America/Los_Angeles")

    def test_unknown_state_defaults_to_eastern(self):
        from src.utils.timezone import get_zoneinfo

        result = get_zoneinfo(state_code="XX")
        assert result == ZoneInfo("America/New_York")

    def test_no_args_defaults_to_eastern(self):
        from src.utils.timezone import get_zoneinfo

        result = get_zoneinfo()
        assert result == ZoneInfo("America/New_York")

    def test_none_state_defaults_to_eastern(self):
        from src.utils.timezone import get_zoneinfo

        result = get_zoneinfo(state_code=None, timezone_str=None)
        assert result == ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# 3. src/utils/encryption.py - encrypt_value + decrypt_value
# ---------------------------------------------------------------------------


class TestEncryption:
    """Tests for encrypt_value and decrypt_value."""

    def test_encrypt_no_key_returns_plaintext(self):
        """When encryption_key is not configured, plaintext is returned as-is."""
        mock_cfg = MagicMock()
        mock_cfg.encryption_key = None

        with patch("src.config.get_settings", return_value=mock_cfg):
            from src.utils.encryption import encrypt_value

            result = encrypt_value("secret123")
            assert result == "secret123"

    def test_decrypt_no_key_returns_encrypted_text(self):
        """When encryption_key is not configured, ciphertext is returned as-is."""
        mock_cfg = MagicMock()
        mock_cfg.encryption_key = None

        with patch("src.config.get_settings", return_value=mock_cfg):
            from src.utils.encryption import decrypt_value

            result = decrypt_value("gAAAAAB_some_encrypted_token")
            assert result == "gAAAAAB_some_encrypted_token"

    def test_encrypt_decrypt_round_trip(self):
        """encrypt then decrypt yields original plaintext."""
        from cryptography.fernet import Fernet

        # Generate a real Fernet key for testing
        test_key = Fernet.generate_key().decode()

        mock_cfg = MagicMock()
        mock_cfg.encryption_key = test_key

        with patch("src.config.get_settings", return_value=mock_cfg):
            from src.utils.encryption import encrypt_value, decrypt_value

            plaintext = "my-super-secret-api-key"
            encrypted = encrypt_value(plaintext)

            # Encrypted value should differ from plaintext
            assert encrypted != plaintext

            decrypted = decrypt_value(encrypted)
            assert decrypted == plaintext

    def test_encrypt_empty_string_returns_empty(self):
        """Empty string input is returned as-is without encryption attempt."""
        from src.utils.encryption import encrypt_value

        assert encrypt_value("") == ""

    def test_decrypt_empty_string_returns_empty(self):
        """Empty string input is returned as-is without decryption attempt."""
        from src.utils.encryption import decrypt_value

        assert decrypt_value("") == ""

    def test_decrypt_invalid_token_returns_as_is(self):
        """Legacy plaintext values that are not valid Fernet tokens are returned as-is."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key().decode()
        mock_cfg = MagicMock()
        mock_cfg.encryption_key = test_key

        with patch("src.config.get_settings", return_value=mock_cfg):
            from src.utils.encryption import decrypt_value

            result = decrypt_value("not-a-valid-fernet-token")
            assert result == "not-a-valid-fernet-token"


# ---------------------------------------------------------------------------
# 4. src/utils/rate_limiter.py - check_rate_limit + check_webhook_rate_limits
# ---------------------------------------------------------------------------


def _make_redis_with_pipeline(pipeline_execute_return):
    """Helper: create a MagicMock Redis whose .pipeline() returns a mock pipe."""
    mock_pipe = MagicMock()
    mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
    mock_pipe.zadd = MagicMock(return_value=mock_pipe)
    mock_pipe.zcard = MagicMock(return_value=mock_pipe)
    mock_pipe.expire = MagicMock(return_value=mock_pipe)
    mock_pipe.execute = AsyncMock(return_value=pipeline_execute_return)

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    return mock_redis


class TestCheckRateLimit:
    """Tests for the Redis sliding-window rate limiter."""

    async def test_under_limit_returns_allowed(self):
        """When request count is under the limit, (True, None) is returned."""
        mock_redis = _make_redis_with_pipeline([
            0,     # zremrangebyscore result
            True,  # zadd result
            5,     # zcard -- 5 requests, under default 100
            True,  # expire result
        ])

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.rate_limiter import check_rate_limit

            allowed, retry_after = await check_rate_limit("ip:1.2.3.4", limit=100)
            assert allowed is True
            assert retry_after is None

    async def test_over_limit_returns_not_allowed(self):
        """When request count exceeds the limit, (False, retry_after) is returned."""
        mock_redis = _make_redis_with_pipeline([
            0,     # zremrangebyscore
            True,  # zadd
            101,   # zcard -- 101 requests, over limit of 100
            True,  # expire
        ])

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.rate_limiter import check_rate_limit

            allowed, retry_after = await check_rate_limit("ip:1.2.3.4", limit=100)
            assert allowed is False
            assert isinstance(retry_after, int)
            assert retry_after >= 1

    async def test_redis_failure_graceful_degradation(self):
        """When Redis is unavailable, requests are allowed through (graceful degradation)."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            from src.utils.rate_limiter import check_rate_limit

            allowed, retry_after = await check_rate_limit("ip:1.2.3.4")
            assert allowed is True
            assert retry_after is None

    async def test_pipeline_exception_graceful_degradation(self):
        """Pipeline execution failure allows the request through."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(side_effect=Exception("Pipeline error"))

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.rate_limiter import check_rate_limit

            allowed, retry_after = await check_rate_limit("ip:1.2.3.4")
            assert allowed is True
            assert retry_after is None


class TestCheckWebhookRateLimits:
    """Tests for combined IP + client rate limit checks."""

    async def test_both_limits_pass(self):
        """When both IP and client limits pass, request is allowed."""
        with patch(
            "src.utils.rate_limiter.check_rate_limit",
            new_callable=AsyncMock,
            return_value=(True, None),
        ):
            from src.utils.rate_limiter import check_webhook_rate_limits

            allowed, retry_after = await check_webhook_rate_limits(
                client_ip="1.2.3.4", client_id="client-abc"
            )
            assert allowed is True
            assert retry_after is None

    async def test_ip_limit_exceeded(self):
        """When IP limit is exceeded, request is rejected."""
        async def mock_check(key, limit=100):
            if key.startswith("ip:"):
                return False, 30
            return True, None

        with patch("src.utils.rate_limiter.check_rate_limit", side_effect=mock_check):
            from src.utils.rate_limiter import check_webhook_rate_limits

            allowed, retry_after = await check_webhook_rate_limits(
                client_ip="1.2.3.4", client_id="client-abc"
            )
            assert allowed is False
            assert retry_after == 30

    async def test_client_limit_exceeded(self):
        """When client limit is exceeded but IP limit passes, request is rejected."""
        async def mock_check(key, limit=100):
            if key.startswith("client:"):
                return False, 15
            return True, None

        with patch("src.utils.rate_limiter.check_rate_limit", side_effect=mock_check):
            from src.utils.rate_limiter import check_webhook_rate_limits

            allowed, retry_after = await check_webhook_rate_limits(
                client_ip="1.2.3.4", client_id="client-abc"
            )
            assert allowed is False
            assert retry_after == 15

    async def test_no_client_id_skips_client_check(self):
        """When client_id is None, only IP check runs."""
        call_keys = []

        async def mock_check(key, limit=100):
            call_keys.append(key)
            return True, None

        with patch("src.utils.rate_limiter.check_rate_limit", side_effect=mock_check):
            from src.utils.rate_limiter import check_webhook_rate_limits

            allowed, retry_after = await check_webhook_rate_limits(
                client_ip="1.2.3.4", client_id=None
            )
            assert allowed is True
            # Only IP key should have been checked
            assert len(call_keys) == 1
            assert call_keys[0].startswith("ip:")


# ---------------------------------------------------------------------------
# 5. src/utils/dead_letter.py - retry scheduling + capture/mark/resolve
# ---------------------------------------------------------------------------


class TestNextRetryAt:
    """Tests for the exponential backoff retry calculator."""

    def test_retry_0_delay_1_minute(self):
        from src.utils.dead_letter import _next_retry_at

        before = datetime.now(timezone.utc)
        result = _next_retry_at(0)
        after = datetime.now(timezone.utc)

        assert result is not None
        expected_min = before + timedelta(minutes=1)
        expected_max = after + timedelta(minutes=1)
        assert expected_min <= result <= expected_max

    def test_retry_1_delay_5_minutes(self):
        from src.utils.dead_letter import _next_retry_at

        before = datetime.now(timezone.utc)
        result = _next_retry_at(1)
        after = datetime.now(timezone.utc)

        assert result is not None
        expected_min = before + timedelta(minutes=5)
        expected_max = after + timedelta(minutes=5)
        assert expected_min <= result <= expected_max

    def test_retry_4_delay_240_minutes(self):
        from src.utils.dead_letter import _next_retry_at

        before = datetime.now(timezone.utc)
        result = _next_retry_at(4)
        after = datetime.now(timezone.utc)

        assert result is not None
        expected_min = before + timedelta(minutes=240)
        expected_max = after + timedelta(minutes=240)
        assert expected_min <= result <= expected_max

    def test_retry_5_returns_none(self):
        from src.utils.dead_letter import _next_retry_at

        assert _next_retry_at(5) is None

    def test_retry_beyond_max_returns_none(self):
        from src.utils.dead_letter import _next_retry_at

        assert _next_retry_at(10) is None
        assert _next_retry_at(100) is None


class TestCaptureFailedLead:
    """Tests for capturing failed leads into the dead letter queue."""

    async def test_creates_failed_lead_and_flushes(self):
        """capture_failed_lead creates a FailedLead record and flushes to DB."""
        mock_db = AsyncMock()

        with patch("src.utils.dead_letter.get_correlation_id", return_value="test-corr-123"):
            from src.utils.dead_letter import capture_failed_lead

            error = ValueError("Something broke")
            payload = {"phone": "+15551234567", "name": "Test Lead"}

            result = await capture_failed_lead(
                db=mock_db,
                payload=payload,
                source="twilio_webhook",
                failure_stage="intake",
                error=error,
                client_id="11111111-1111-1111-1111-111111111111",
            )

            assert result.original_payload == payload
            assert result.source == "twilio_webhook"
            assert result.failure_stage == "intake"
            assert result.error_message == "Something broke"
            assert result.retry_count == 0
            assert result.status == "pending"
            assert result.next_retry_at is not None
            assert result.correlation_id == "test-corr-123"
            # Verify db.add and db.flush were called
            mock_db.add.assert_called_once()
            mock_db.flush.assert_awaited_once()

    async def test_creates_with_none_client_id(self):
        """capture_failed_lead works with no client_id."""
        mock_db = AsyncMock()

        with patch("src.utils.dead_letter.get_correlation_id", return_value=None):
            from src.utils.dead_letter import capture_failed_lead

            result = await capture_failed_lead(
                db=mock_db,
                payload={"test": True},
                source="manual",
                failure_stage="webhook",
                error=RuntimeError("test"),
                client_id=None,
            )

            assert result.client_id is None
            assert result.status == "pending"

    async def test_creates_with_invalid_client_id(self):
        """capture_failed_lead handles invalid UUID client_id gracefully."""
        mock_db = AsyncMock()

        with patch("src.utils.dead_letter.get_correlation_id", return_value=None):
            from src.utils.dead_letter import capture_failed_lead

            result = await capture_failed_lead(
                db=mock_db,
                payload={"test": True},
                source="manual",
                failure_stage="webhook",
                error=RuntimeError("test"),
                client_id="not-a-valid-uuid",
            )

            assert result.client_id is None


class TestMarkRetryAttempted:
    """Tests for mark_retry_attempted state transitions."""

    async def test_increments_count_and_schedules_next(self):
        """When retries remain, count increments and next_retry_at is set."""
        from src.utils.dead_letter import mark_retry_attempted

        mock_lead = MagicMock()
        mock_lead.retry_count = 0
        mock_lead.max_retries = 5
        mock_lead.id = uuid.uuid4()

        mock_db = AsyncMock()

        await mark_retry_attempted(mock_db, mock_lead)

        assert mock_lead.retry_count == 1
        assert mock_lead.status == "pending"
        assert mock_lead.next_retry_at is not None

    async def test_marks_dead_when_retries_exhausted(self):
        """When max retries reached, status becomes 'dead' and next_retry_at is None."""
        from src.utils.dead_letter import mark_retry_attempted

        mock_lead = MagicMock()
        mock_lead.retry_count = 4
        mock_lead.max_retries = 5
        mock_lead.id = uuid.uuid4()

        mock_db = AsyncMock()

        await mark_retry_attempted(mock_db, mock_lead)

        assert mock_lead.retry_count == 5
        assert mock_lead.status == "dead"
        assert mock_lead.next_retry_at is None

    async def test_already_at_max_marks_dead(self):
        """If retry_count already equals max_retries, it still marks dead."""
        from src.utils.dead_letter import mark_retry_attempted

        mock_lead = MagicMock()
        mock_lead.retry_count = 5
        mock_lead.max_retries = 5
        mock_lead.id = uuid.uuid4()

        mock_db = AsyncMock()

        await mark_retry_attempted(mock_db, mock_lead)

        assert mock_lead.retry_count == 6
        assert mock_lead.status == "dead"
        assert mock_lead.next_retry_at is None


class TestResolveFailedLead:
    """Tests for resolve_failed_lead state transition."""

    async def test_sets_status_resolved(self):
        """resolve_failed_lead sets status, resolved_at, and resolved_by."""
        from src.utils.dead_letter import resolve_failed_lead

        mock_lead = MagicMock()
        mock_lead.id = uuid.uuid4()

        mock_db = AsyncMock()

        await resolve_failed_lead(mock_db, mock_lead, resolved_by="manual_admin")

        assert mock_lead.status == "resolved"
        assert mock_lead.resolved_at is not None
        assert mock_lead.resolved_by == "manual_admin"

    async def test_default_resolved_by(self):
        """Default resolved_by is 'retry_worker'."""
        from src.utils.dead_letter import resolve_failed_lead

        mock_lead = MagicMock()
        mock_lead.id = uuid.uuid4()

        mock_db = AsyncMock()

        await resolve_failed_lead(mock_db, mock_lead)

        assert mock_lead.resolved_by == "retry_worker"


# ---------------------------------------------------------------------------
# 6. src/utils/locks.py - lead_lock, _acquire_lock, _release_lock
# ---------------------------------------------------------------------------


class TestLeadLock:
    """Tests for the Redis distributed lock context manager."""

    async def test_acquires_and_yields_then_releases(self):
        """lead_lock acquires the lock, yields, and releases on exit."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import lead_lock

            entered = False
            async with lead_lock("lead-123"):
                entered = True

            assert entered is True
            # set was called for acquire (at least once with nx=True)
            mock_redis.set.assert_called()
            # eval was called for release (Lua script)
            mock_redis.eval.assert_called_once()

    async def test_lock_timeout_raises_error(self):
        """When lock cannot be acquired within timeout, LockTimeoutError is raised."""
        mock_redis = AsyncMock()
        # Always return False (lock held by someone else)
        mock_redis.set = AsyncMock(return_value=False)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import lead_lock, LockTimeoutError

            with pytest.raises(LockTimeoutError):
                async with lead_lock("lead-999", wait=0.2):
                    pass  # Should never reach here

    async def test_release_not_called_on_acquisition_failure(self):
        """When lock acquisition fails with timeout, release is NOT called."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)
        mock_redis.eval = AsyncMock()

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import lead_lock, LockTimeoutError

            with pytest.raises(LockTimeoutError):
                async with lead_lock("lead-999", wait=0.2):
                    pass

            # eval (release) should NOT have been called
            mock_redis.eval.assert_not_called()


class TestAcquireLock:
    """Tests for _acquire_lock internal function."""

    async def test_immediate_acquisition(self):
        """Lock acquired on first attempt returns True immediately."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import _acquire_lock

            result = await _acquire_lock("test-key", "test-value", ttl=30, wait=5.0)
            assert result is True
            # Should be called exactly once (immediate success, no polling)
            assert mock_redis.set.call_count == 1

    async def test_redis_failure_returns_true_graceful_degradation(self):
        """When Redis is unavailable, _acquire_lock returns True (graceful degradation)."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Redis down"),
        ):
            from src.utils.locks import _acquire_lock

            result = await _acquire_lock("test-key", "test-value", ttl=30, wait=5.0)
            assert result is True

    async def test_polling_until_acquired(self):
        """Lock fails first attempt but succeeds on second (polling)."""
        mock_redis = AsyncMock()
        # First call returns False, second returns True
        mock_redis.set = AsyncMock(side_effect=[False, True])

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import _acquire_lock

            result = await _acquire_lock("test-key", "test-value", ttl=30, wait=5.0)
            assert result is True
            assert mock_redis.set.call_count == 2


class TestReleaseLock:
    """Tests for _release_lock internal function."""

    async def test_uses_lua_script(self):
        """Release uses a Lua eval script for atomic compare-and-delete."""
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=1)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import _release_lock

            await _release_lock("test-key", "test-value")

            mock_redis.eval.assert_called_once()
            call_args = mock_redis.eval.call_args
            # First positional arg is the Lua script
            lua_script = call_args[0][0]
            assert "redis.call('get'" in lua_script
            assert "redis.call('del'" in lua_script
            # Key and value are passed as arguments
            assert call_args[0][2] == "test-key"
            assert call_args[0][3] == "test-value"

    async def test_redis_failure_on_release_is_silent(self):
        """Redis failure during release is logged but does not raise."""
        mock_redis = AsyncMock()
        mock_redis.eval = AsyncMock(side_effect=ConnectionError("Redis gone"))

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            from src.utils.locks import _release_lock

            # Should NOT raise
            await _release_lock("test-key", "test-value")


# ---------------------------------------------------------------------------
# 7. src/utils/alerting.py - send_alert + _acquire_cooldown
# ---------------------------------------------------------------------------


class TestAcquireCooldown:
    """Tests for the atomic alert rate-limit cooldown (Redis SET NX EX)."""

    async def test_first_alert_is_always_sent(self):
        from src.utils.alerting import _acquire_cooldown

        # SET NX returns True — key didn't exist, acquired successfully
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            test_type = f"test_unique_{uuid.uuid4().hex[:8]}"
            assert await _acquire_cooldown(test_type) is True

    async def test_second_alert_within_cooldown_is_blocked(self):
        from src.utils.alerting import _acquire_cooldown

        # SET NX returns None — key already exists, cooldown active
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            test_type = f"test_cooldown_{uuid.uuid4().hex[:8]}"
            assert await _acquire_cooldown(test_type) is False

    async def test_alert_after_cooldown_expires_is_sent(self):
        from src.utils.alerting import _acquire_cooldown

        # SET NX returns True — TTL expired, key acquired
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            test_type = f"test_expired_{uuid.uuid4().hex[:8]}"
            assert await _acquire_cooldown(test_type) is True

    async def test_different_alert_types_are_independent(self):
        from src.utils.alerting import _acquire_cooldown

        type_a = f"test_a_{uuid.uuid4().hex[:8]}"
        type_b = f"test_b_{uuid.uuid4().hex[:8]}"

        key_a = f"leadlock:alert_cooldown:{type_a}"

        # type_a: SET NX fails (cooldown active), type_b: SET NX succeeds
        async def fake_set(key, value, **kwargs):
            if key == key_a:
                return None  # Already exists
            return True  # New key

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=fake_set)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            assert await _acquire_cooldown(type_a) is False
            assert await _acquire_cooldown(type_b) is True

    async def test_redis_failure_uses_local_fallback(self):
        from src.utils.alerting import _acquire_cooldown, _local_cooldowns

        test_type = f"test_fallback_{uuid.uuid4().hex[:8]}"
        _local_cooldowns.pop(test_type, None)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("Redis down")):
            # First call — no local cooldown, should allow
            assert await _acquire_cooldown(test_type) is True
            # Second call — local cooldown set, should block
            assert await _acquire_cooldown(test_type) is False

        # Cleanup
        _local_cooldowns.pop(test_type, None)


class TestSendAlert:
    """Tests for the send_alert function."""

    async def test_logs_error_message(self):
        """send_alert always logs at ERROR level."""
        test_type = f"test_log_{uuid.uuid4().hex[:8]}"

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=True),
            patch("src.utils.logging.get_correlation_id", return_value="corr-test"),
            patch("src.utils.alerting._send_webhook_alert", new_callable=AsyncMock),
            patch("src.utils.alerting._send_email_alert", new_callable=AsyncMock),
            patch("src.utils.alerting.logger") as mock_logger,
        ):
            from src.utils.alerting import send_alert

            await send_alert(
                alert_type=test_type,
                message="Test alert message",
            )

            mock_logger.error.assert_called_once()
            logged_msg = mock_logger.error.call_args[0][0]
            assert test_type in logged_msg
            assert "Test alert message" in logged_msg

    async def test_logs_critical_for_critical_severity(self):
        """send_alert logs at CRITICAL level when severity is 'critical'."""
        test_type = f"test_crit_{uuid.uuid4().hex[:8]}"

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=True),
            patch("src.utils.logging.get_correlation_id", return_value="corr-crit"),
            patch("src.utils.alerting._send_webhook_alert", new_callable=AsyncMock),
            patch("src.utils.alerting._send_email_alert", new_callable=AsyncMock),
            patch("src.utils.alerting.logger") as mock_logger,
        ):
            from src.utils.alerting import send_alert

            await send_alert(
                alert_type=test_type,
                message="Critical failure",
                severity="critical",
            )

            mock_logger.critical.assert_called_once()

    async def test_calls_webhook_when_url_configured(self):
        """send_alert calls _send_webhook_alert."""
        test_type = f"test_webhook_{uuid.uuid4().hex[:8]}"

        mock_webhook = AsyncMock()
        mock_email = AsyncMock()

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=True),
            patch("src.utils.logging.get_correlation_id", return_value="corr-wh"),
            patch("src.utils.alerting._send_webhook_alert", mock_webhook),
            patch("src.utils.alerting._send_email_alert", mock_email),
        ):
            from src.utils.alerting import send_alert

            await send_alert(
                alert_type=test_type,
                message="Webhook test",
            )

            mock_webhook.assert_called_once_with(
                test_type, "Webhook test", "corr-wh", None
            )

    async def test_rate_limited_alert_is_skipped(self):
        """When _acquire_cooldown returns False, no logging or webhook occurs."""
        mock_webhook = AsyncMock()

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=False),
            patch("src.utils.alerting._send_webhook_alert", mock_webhook),
            patch("src.utils.alerting._send_email_alert", new_callable=AsyncMock),
            patch("src.utils.alerting.logger") as mock_logger,
        ):
            from src.utils.alerting import send_alert

            await send_alert(
                alert_type="throttled_type",
                message="Should not appear",
            )

            mock_logger.error.assert_not_called()
            mock_logger.critical.assert_not_called()
            mock_webhook.assert_not_called()

    async def test_send_webhook_alert_catches_errors(self):
        """_send_webhook_alert catches exceptions and does not raise."""
        mock_settings = MagicMock()
        mock_settings.alert_webhook_url = "https://hooks.example.com/test"

        with patch("src.config.get_settings", return_value=mock_settings):
            # Patch httpx to raise on post
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient", return_value=mock_client):
                from src.utils.alerting import _send_webhook_alert

                # Should NOT raise
                await _send_webhook_alert(
                    alert_type="test",
                    message="Test message",
                    correlation_id="corr-123",
                    extra=None,
                )

    async def test_send_webhook_skips_when_no_url(self):
        """_send_webhook_alert returns early when no webhook URL is configured."""
        mock_settings = MagicMock()
        mock_settings.alert_webhook_url = ""

        with patch("src.config.get_settings", return_value=mock_settings):
            from src.utils.alerting import _send_webhook_alert

            # Should return without error or HTTP call
            await _send_webhook_alert(
                alert_type="test",
                message="No URL configured",
                correlation_id=None,
                extra=None,
            )

    async def test_send_alert_includes_extra_in_payload(self):
        """send_alert passes extra dict through to webhook."""
        test_type = f"test_extra_{uuid.uuid4().hex[:8]}"

        mock_webhook = AsyncMock()

        with (
            patch("src.utils.alerting._acquire_cooldown", return_value=True),
            patch("src.utils.logging.get_correlation_id", return_value="corr-extra"),
            patch("src.utils.alerting._send_webhook_alert", mock_webhook),
            patch("src.utils.alerting._send_email_alert", new_callable=AsyncMock),
        ):
            from src.utils.alerting import send_alert

            extra_data = {"lead_id": "abc-123", "phone": "+1555***"}
            await send_alert(
                alert_type=test_type,
                message="Extra test",
                extra=extra_data,
            )

            mock_webhook.assert_called_once_with(
                test_type, "Extra test", "corr-extra", extra_data
            )
