"""
Tests for analytics service - SQL queries and caching.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_session_factory(rows=None, scalar_value=0):
    """Create a mock session factory that returns configurable query results."""
    mock_db = AsyncMock()

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = rows or []
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar.return_value = scalar_value
    mock_result.fetchall.return_value = rows or []
    mock_db.execute = AsyncMock(return_value=mock_result)

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *a):
            pass

    return _FakeCtx()


class TestGetTradeFunnel:
    @pytest.mark.asyncio
    async def test_returns_funnel_data(self):
        from src.services.analytics import get_trade_funnel

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("src.services.analytics.async_session_factory", return_value=_mock_session_factory(scalar_value=10)),
        ):
            result = await get_trade_funnel(trade="hvac")

        assert result["trade"] == "hvac"
        assert "stages" in result
        assert "total" in result


class TestGetEmailPerformanceByStep:
    @pytest.mark.asyncio
    async def test_returns_step_data(self):
        from src.services.analytics import get_email_performance_by_step

        # Simulate rows: (step, sent, opened, replied)
        mock_rows = [
            (1, 100, 25, 2),
            (2, 80, 15, 1),
            (3, 50, 8, 0),
        ]

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("src.services.analytics.async_session_factory", return_value=_mock_session_factory(rows=mock_rows)),
        ):
            result = await get_email_performance_by_step()

        assert "steps" in result


class TestGetAgentCosts:
    @pytest.mark.asyncio
    async def test_returns_cost_breakdown(self):
        from src.services.analytics import get_agent_costs

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={
            b"ab_testing": b"0.001",
            b"winback": b"0.002",
        })

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await get_agent_costs(days=1)

        assert result["period_days"] == 1
        assert result["total_by_agent"]["ab_testing"] == 0.001
        assert result["total_by_agent"]["winback"] == 0.002
        assert result["total_usd"] == pytest.approx(0.003, abs=0.0001)

    @pytest.mark.asyncio
    async def test_handles_redis_failure(self):
        from src.services.analytics import get_agent_costs

        with patch("src.utils.dedup.get_redis", side_effect=Exception("Redis down")):
            result = await get_agent_costs(days=7)

        assert result["total_usd"] == 0.0
        assert result["total_by_agent"] == {}


class TestGetAbTestResults:
    @pytest.mark.asyncio
    async def test_returns_experiment_list(self):
        from src.services.analytics import get_ab_test_results

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("src.services.analytics.async_session_factory", return_value=_FakeCtx()),
        ):
            result = await get_ab_test_results()

        assert "experiments" in result
        assert isinstance(result["experiments"], list)
