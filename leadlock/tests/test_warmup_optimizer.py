"""
Tests for src/services/warmup_optimizer.py - dynamic warmup pacing.
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestGetStandardLimit:
    def test_day_0_returns_10(self):
        from src.services.warmup_optimizer import _get_standard_limit
        assert _get_standard_limit(0) == 10

    def test_day_5_returns_20(self):
        from src.services.warmup_optimizer import _get_standard_limit
        assert _get_standard_limit(5) == 20

    def test_day_10_returns_40(self):
        from src.services.warmup_optimizer import _get_standard_limit
        assert _get_standard_limit(10) == 40

    def test_day_17_returns_75(self):
        from src.services.warmup_optimizer import _get_standard_limit
        assert _get_standard_limit(17) == 75

    def test_day_25_returns_120(self):
        from src.services.warmup_optimizer import _get_standard_limit
        assert _get_standard_limit(25) == 120

    def test_day_30_past_warmup(self):
        from src.services.warmup_optimizer import _get_standard_limit
        assert _get_standard_limit(30) is None


class TestGetOptimizedWarmupLimit:
    @pytest.mark.asyncio
    async def test_accelerates_on_good_reputation(self):
        """Rep > 90 and bounce < 2% should accelerate 1.5x."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        reputation = {
            "score": 95,
            "metrics": {"bounce_rate": 0.01},
            "throttle": "normal",
        }

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
            patch("src.services.deliverability.get_email_reputation", new_callable=AsyncMock, return_value=reputation),
        ):
            result = await get_optimized_warmup_limit(configured_limit=200, days_since_start=5)

        # Day 5 standard = 20, accelerated = 30
        assert result == 30

    @pytest.mark.asyncio
    async def test_decelerates_on_poor_reputation(self):
        """Rep < 75 should decelerate 0.5x."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        reputation = {
            "score": 60,
            "metrics": {"bounce_rate": 0.03},
            "throttle": "critical",
        }

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
            patch("src.services.deliverability.get_email_reputation", new_callable=AsyncMock, return_value=reputation),
        ):
            result = await get_optimized_warmup_limit(configured_limit=200, days_since_start=10)

        # Day 10 standard = 40, decelerated = 20
        assert result == 20

    @pytest.mark.asyncio
    async def test_standard_on_normal_reputation(self):
        """Normal reputation should use standard schedule."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        reputation = {
            "score": 85,
            "metrics": {"bounce_rate": 0.03},
            "throttle": "normal",
        }

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
            patch("src.services.deliverability.get_email_reputation", new_callable=AsyncMock, return_value=reputation),
        ):
            result = await get_optimized_warmup_limit(configured_limit=200, days_since_start=10)

        # Day 10 standard = 40, no change
        assert result == 40

    @pytest.mark.asyncio
    async def test_never_exceeds_configured_limit(self):
        """Even with acceleration, should not exceed configured limit."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        reputation = {
            "score": 99,
            "metrics": {"bounce_rate": 0.001},
            "throttle": "normal",
        }

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
            patch("src.services.deliverability.get_email_reputation", new_callable=AsyncMock, return_value=reputation),
        ):
            result = await get_optimized_warmup_limit(configured_limit=15, days_since_start=5)

        # Day 5 standard = 20, accelerated = 30, but configured = 15
        assert result == 15

    @pytest.mark.asyncio
    async def test_past_warmup_returns_configured(self):
        """Past warmup period should return configured limit."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        result = await get_optimized_warmup_limit(configured_limit=100, days_since_start=35)
        assert result == 100

    @pytest.mark.asyncio
    async def test_fallback_on_redis_failure(self):
        """Should fallback to standard limit if Redis fails."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        with patch("src.utils.dedup.get_redis", side_effect=Exception("Redis down")):
            result = await get_optimized_warmup_limit(configured_limit=200, days_since_start=5)

        # Day 5 standard = 20
        assert result == 20

    @pytest.mark.asyncio
    async def test_decelerates_on_high_bounce(self):
        """Bounce > 5% should decelerate even with good score."""
        from src.services.warmup_optimizer import get_optimized_warmup_limit

        reputation = {
            "score": 85,
            "metrics": {"bounce_rate": 0.06},
            "throttle": "reduced",
        }

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock),
            patch("src.services.deliverability.get_email_reputation", new_callable=AsyncMock, return_value=reputation),
        ):
            result = await get_optimized_warmup_limit(configured_limit=200, days_since_start=10)

        # Day 10 standard = 40, decelerated = 20
        assert result == 20
