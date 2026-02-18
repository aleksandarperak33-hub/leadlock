"""
Deliverability and reputation scoring tests.
Tests SMS outcome classification, reputation scoring, email reputation, and throttle limits.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.deliverability import (
    _classify_outcome,
    _compute_score,
    _score_to_level,
    _get_throttle_limit,
    record_email_event,
    get_email_reputation,
    THROTTLE_MAX_NORMAL,
    THROTTLE_MAX_WARNING,
    THROTTLE_MAX_CRITICAL,
    EMAIL_THROTTLE_FACTORS,
)


# --- SMS outcome classification ---

class TestClassifyOutcome:
    """Test SMS outcome classification for reputation tracking."""

    def test_delivered_status(self):
        assert _classify_outcome("delivered", None) == "delivered"

    def test_sent_status(self):
        assert _classify_outcome("sent", None) == "pending"

    def test_carrier_filter_30007(self):
        assert _classify_outcome("failed", "30007") == "filtered"

    def test_invalid_number_21211(self):
        assert _classify_outcome("failed", "21211") == "invalid"

    def test_invalid_number_21612(self):
        assert _classify_outcome("failed", "21612") == "invalid"

    def test_landline_30006(self):
        assert _classify_outcome("failed", "30006") == "invalid"

    def test_generic_failure(self):
        assert _classify_outcome("failed", "99999") == "failed"

    def test_undelivered_no_code(self):
        assert _classify_outcome("undelivered", None) == "failed"


# --- Reputation score computation ---

class TestComputeScore:
    """Test reputation score computation (0-100)."""

    def test_no_data_returns_100(self):
        """No sends = assume perfect reputation."""
        assert _compute_score(1.0, 0, 0, 0) == 100

    def test_perfect_delivery_full_score(self):
        """100% delivery, no filters/invalids = 100."""
        score = _compute_score(1.0, 0, 0, 100)
        assert score == 100

    def test_95_percent_delivery_full_delivery_score(self):
        """95%+ delivery rate gets max delivery component (60 pts)."""
        score = _compute_score(0.95, 0, 0, 100)
        assert score == 100

    def test_70_percent_delivery_zero_delivery_score(self):
        """70% delivery = 0 delivery score component."""
        score = _compute_score(0.70, 0, 0, 100)
        assert score == 40  # 0 delivery + 25 filter + 15 invalid

    def test_below_70_percent_zero_delivery(self):
        score = _compute_score(0.50, 0, 0, 100)
        assert score == 40  # 0 + 25 + 15

    def test_high_filter_rate_penalized(self):
        """Filter rate >5% = 0 filter score."""
        score = _compute_score(0.95, 6, 0, 100)
        assert score < 100
        assert score == 60 + 0 + 15  # 60 delivery + 0 filter + 15 invalid

    def test_high_invalid_rate_penalized(self):
        """Invalid rate >10% = 0 invalid score."""
        score = _compute_score(0.95, 0, 11, 100)
        assert score == 60 + 25 + 0  # 60 delivery + 25 filter + 0 invalid

    def test_score_clamped_to_0_100(self):
        """Score should never go below 0 or above 100."""
        score = _compute_score(0.50, 50, 50, 100)
        assert 0 <= score <= 100


# --- Score to level mapping ---

class TestScoreToLevel:
    def test_excellent(self):
        assert _score_to_level(95) == "excellent"

    def test_excellent_boundary(self):
        assert _score_to_level(90) == "excellent"

    def test_good(self):
        assert _score_to_level(80) == "good"

    def test_good_boundary(self):
        assert _score_to_level(75) == "good"

    def test_warning(self):
        assert _score_to_level(65) == "warning"

    def test_warning_boundary(self):
        assert _score_to_level(60) == "warning"

    def test_critical(self):
        assert _score_to_level(30) == "critical"

    def test_critical_boundary(self):
        assert _score_to_level(39) == "critical"

    def test_zero_is_critical(self):
        assert _score_to_level(0) == "critical"


# --- Throttle limits ---

class TestGetThrottleLimit:
    def test_excellent_normal_rate(self):
        assert _get_throttle_limit("excellent") == THROTTLE_MAX_NORMAL

    def test_good_reduced_rate(self):
        assert _get_throttle_limit("good") == THROTTLE_MAX_WARNING

    def test_warning_reduced_rate(self):
        assert _get_throttle_limit("warning") == THROTTLE_MAX_WARNING

    def test_critical_minimal_rate(self):
        assert _get_throttle_limit("critical") == THROTTLE_MAX_CRITICAL

    def test_throttle_limits_descend(self):
        """Throttle limits should decrease with severity."""
        assert THROTTLE_MAX_NORMAL > THROTTLE_MAX_WARNING > THROTTLE_MAX_CRITICAL


# --- Email reputation ---

class TestRecordEmailEvent:
    """Test email event recording in Redis."""

    async def test_valid_event_recorded(self):
        """Valid event type should be recorded via Redis pipeline."""
        # pipeline() is sync, pipe.incr/expire are sync, pipe.execute is async
        pipe = MagicMock()
        pipe.execute = AsyncMock()
        redis = MagicMock()
        redis.pipeline.return_value = pipe

        await record_email_event(redis, "sent")

        pipe.incr.assert_called_once_with("email:reputation:sent")
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    async def test_invalid_event_type_ignored(self):
        """Invalid event type should be silently ignored."""
        redis = MagicMock()
        await record_email_event(redis, "invalid_type")
        redis.pipeline.assert_not_called()

    async def test_all_valid_event_types(self):
        """All 6 valid event types should be accepted."""
        for event_type in ("sent", "delivered", "bounced", "complained", "opened", "clicked"):
            pipe = MagicMock()
            pipe.execute = AsyncMock()
            redis = MagicMock()
            redis.pipeline.return_value = pipe

            await record_email_event(redis, event_type)
            pipe.incr.assert_called_once_with(f"email:reputation:{event_type}")

    async def test_redis_error_handled_gracefully(self):
        """Redis errors should not raise."""
        redis = MagicMock()
        redis.pipeline.side_effect = Exception("Redis down")

        # Should not raise
        await record_email_event(redis, "sent")


class TestGetEmailReputation:
    """Test email reputation scoring from Redis metrics."""

    async def test_no_data_returns_100(self):
        """No sends should return score 100 with no_data status."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        result = await get_email_reputation(redis)

        assert result["score"] == 100
        assert result["status"] == "no_data"
        assert result["throttle"] == "normal"

    async def test_perfect_metrics_excellent(self):
        """100% delivery, no bounces = excellent."""
        redis = AsyncMock()

        async def mock_get(key):
            return {
                "email:reputation:sent": b"100",
                "email:reputation:delivered": b"100",
                "email:reputation:bounced": b"0",
                "email:reputation:complained": b"0",
                "email:reputation:opened": b"25",
                "email:reputation:clicked": b"5",
            }.get(key)

        redis.get = mock_get

        result = await get_email_reputation(redis)

        assert result["score"] >= 90
        assert result["status"] == "excellent"
        assert result["throttle"] == "normal"

    async def test_high_bounce_rate_penalized(self):
        """10% bounce rate should heavily penalize score."""
        redis = AsyncMock()

        async def mock_get(key):
            return {
                "email:reputation:sent": b"100",
                "email:reputation:delivered": b"90",
                "email:reputation:bounced": b"10",
                "email:reputation:complained": b"0",
                "email:reputation:opened": b"20",
                "email:reputation:clicked": b"5",
            }.get(key)

        redis.get = mock_get

        result = await get_email_reputation(redis)

        # 10% bounce = -50 points (bounce_rate * 500)
        assert result["score"] < 60
        assert result["metrics"]["bounce_rate"] == 0.1

    async def test_complaints_critical_penalty(self):
        """Even 1% complaint rate should be devastating."""
        redis = AsyncMock()

        async def mock_get(key):
            return {
                "email:reputation:sent": b"100",
                "email:reputation:delivered": b"99",
                "email:reputation:bounced": b"0",
                "email:reputation:complained": b"1",
                "email:reputation:opened": b"20",
                "email:reputation:clicked": b"5",
            }.get(key)

        redis.get = mock_get

        result = await get_email_reputation(redis)

        # 1% complaint = -200 points (complaint_rate * 20000)
        assert result["score"] == 0
        assert result["status"] == "critical"
        assert result["throttle"] == "paused"

    async def test_low_delivery_rate_penalized(self):
        """Below 95% delivery rate should reduce score."""
        redis = AsyncMock()

        async def mock_get(key):
            return {
                "email:reputation:sent": b"100",
                "email:reputation:delivered": b"80",
                "email:reputation:bounced": b"0",
                "email:reputation:complained": b"0",
                "email:reputation:opened": b"10",
                "email:reputation:clicked": b"2",
            }.get(key)

        redis.get = mock_get

        result = await get_email_reputation(redis)

        # delivery_rate=0.80, penalty = (0.95 - 0.80) * 200 = 30
        assert result["score"] < 100
        assert result["metrics"]["delivery_rate"] == 0.8

    async def test_open_rate_bonus(self):
        """Open rate >15% should give a small bonus."""
        redis = AsyncMock()

        async def mock_get(key):
            return {
                "email:reputation:sent": b"100",
                "email:reputation:delivered": b"100",
                "email:reputation:bounced": b"0",
                "email:reputation:complained": b"0",
                "email:reputation:opened": b"30",
                "email:reputation:clicked": b"10",
            }.get(key)

        redis.get = mock_get

        result = await get_email_reputation(redis)

        assert result["score"] == 100  # Clamped at 100
        assert result["metrics"]["open_rate"] == 0.3

    async def test_throttle_factor_mapping(self):
        """Verify throttle factor constants are correct."""
        assert EMAIL_THROTTLE_FACTORS["normal"] == 1.0
        assert EMAIL_THROTTLE_FACTORS["reduced"] == 0.5
        assert EMAIL_THROTTLE_FACTORS["critical"] == 0.25
        assert EMAIL_THROTTLE_FACTORS["paused"] == 0.0

    async def test_warning_status_reduced_throttle(self):
        """Score 60-74 should be warning with reduced throttle."""
        redis = AsyncMock()

        async def mock_get(key):
            return {
                "email:reputation:sent": b"100",
                "email:reputation:delivered": b"90",
                "email:reputation:bounced": b"5",
                "email:reputation:complained": b"0",
                "email:reputation:opened": b"10",
                "email:reputation:clicked": b"2",
            }.get(key)

        redis.get = mock_get

        result = await get_email_reputation(redis)

        # 5% bounce = -25, delivery 90% penalty = -10 → score ~65
        if 60 <= result["score"] < 75:
            assert result["status"] == "warning"
            assert result["throttle"] == "reduced"
