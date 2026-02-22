"""
Tests for A/B testing service and engine worker.
Covers: experiment creation, variant assignment, event recording, winner declaration.
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_variant(**overrides):
    """Create a mock ABTestVariant."""
    defaults = {
        "id": uuid.uuid4(),
        "experiment_id": uuid.uuid4(),
        "variant_label": "A",
        "subject_instruction": "Use curiosity-based subject line",
        "total_sent": 0,
        "total_opened": 0,
        "total_replied": 0,
        "open_rate": 0.0,
        "is_winner": False,
    }
    defaults.update(overrides)
    v = MagicMock()
    for k, val in defaults.items():
        setattr(v, k, val)
    return v


def _make_experiment(**overrides):
    """Create a mock ABTestExperiment."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Step 1 - all - 2026-02-22",
        "status": "active",
        "sequence_step": 1,
        "target_trade": None,
        "min_sample_per_variant": 30,
        "winning_variant_id": None,
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
    }
    defaults.update(overrides)
    e = MagicMock()
    for k, val in defaults.items():
        setattr(e, k, val)
    return e


# ---------------------------------------------------------------------------
# assign_variant
# ---------------------------------------------------------------------------

class TestAssignVariant:
    def test_returns_variant_from_list(self):
        from src.services.ab_testing import assign_variant

        variants = [
            {"id": "aaa", "label": "A", "instruction": "curiosity"},
            {"id": "bbb", "label": "B", "instruction": "pain-point"},
        ]
        result = assign_variant(variants)
        assert result in variants

    def test_empty_list_returns_empty_dict(self):
        from src.services.ab_testing import assign_variant

        result = assign_variant([])
        assert result == {}


# ---------------------------------------------------------------------------
# create_experiment
# ---------------------------------------------------------------------------

class TestCreateExperiment:
    @pytest.mark.asyncio
    async def test_creates_experiment_on_ai_success(self):
        from src.services.ab_testing import create_experiment

        ai_response = {
            "content": '[{"label": "A", "instruction": "curiosity"}, {"label": "B", "instruction": "pain-point"}]',
            "cost_usd": 0.001,
            "error": None,
        }

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with (
            patch("src.services.ab_testing.generate_response", new_callable=AsyncMock, return_value=ai_response),
            patch("src.services.ab_testing.async_session_factory", return_value=_FakeCtx()),
            patch("src.services.ab_testing._track_agent_cost", new_callable=AsyncMock),
        ):
            result = await create_experiment(sequence_step=1, variant_count=2)

        assert result is not None
        assert "experiment_id" in result
        assert len(result["variants"]) == 2
        assert result["ai_cost_usd"] == 0.001

    @pytest.mark.asyncio
    async def test_returns_none_on_ai_failure(self):
        from src.services.ab_testing import create_experiment

        ai_response = {"content": "", "cost_usd": 0.0, "error": "timeout"}

        with patch("src.services.ab_testing.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await create_experiment(sequence_step=1)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_json(self):
        from src.services.ab_testing import create_experiment

        ai_response = {"content": "not json", "cost_usd": 0.0, "error": None}

        with patch("src.services.ab_testing.generate_response", new_callable=AsyncMock, return_value=ai_response):
            result = await create_experiment(sequence_step=1)

        assert result is None


# ---------------------------------------------------------------------------
# check_and_declare_winner
# ---------------------------------------------------------------------------

class TestCheckAndDeclareWinner:
    @pytest.mark.asyncio
    async def test_no_winner_below_min_sample(self):
        from src.services.ab_testing import check_and_declare_winner

        exp = _make_experiment(min_sample_per_variant=30)
        var_a = _make_variant(total_sent=25, open_rate=0.30)
        var_b = _make_variant(total_sent=25, open_rate=0.10)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=exp)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [var_a, var_b]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with patch("src.services.ab_testing.async_session_factory", return_value=_FakeCtx()):
            result = await check_and_declare_winner(str(exp.id))

        assert result is None

    @pytest.mark.asyncio
    async def test_declares_winner_with_sufficient_data(self):
        from src.services.ab_testing import check_and_declare_winner

        exp = _make_experiment(min_sample_per_variant=30)
        var_a = _make_variant(
            variant_label="A", total_sent=35, total_opened=14, open_rate=0.40,
            subject_instruction="curiosity-based",
        )
        var_b = _make_variant(
            variant_label="B", total_sent=35, total_opened=7, open_rate=0.20,
        )

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=exp)
        mock_db.commit = AsyncMock()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [var_a, var_b]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with patch("src.services.ab_testing.async_session_factory", return_value=_FakeCtx()):
            result = await check_and_declare_winner(str(exp.id))

        assert result is not None
        assert result["winner_label"] == "A"
        assert result["winner_open_rate"] == 0.40
        assert result["improvement_pct"] >= 0.20

    @pytest.mark.asyncio
    async def test_no_winner_when_close_rates(self):
        """No winner when improvement < 20%."""
        from src.services.ab_testing import check_and_declare_winner

        exp = _make_experiment(min_sample_per_variant=30)
        var_a = _make_variant(total_sent=35, open_rate=0.25)
        var_b = _make_variant(total_sent=35, open_rate=0.22)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=exp)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [var_a, var_b]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with patch("src.services.ab_testing.async_session_factory", return_value=_FakeCtx()):
            result = await check_and_declare_winner(str(exp.id))

        assert result is None


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------

class TestRecordEvent:
    @pytest.mark.asyncio
    async def test_increments_sent_count(self):
        from src.services.ab_testing import record_event

        variant = _make_variant(total_sent=5, total_opened=2, open_rate=0.4)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=variant)
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with patch("src.services.ab_testing.async_session_factory", return_value=_FakeCtx()):
            await record_event(str(variant.id), "sent")

        assert variant.total_sent == 6

    @pytest.mark.asyncio
    async def test_increments_opened_count(self):
        from src.services.ab_testing import record_event

        variant = _make_variant(total_sent=10, total_opened=3, open_rate=0.3)
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=variant)
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *a):
                pass

        with patch("src.services.ab_testing.async_session_factory", return_value=_FakeCtx()):
            await record_event(str(variant.id), "opened")

        assert variant.total_opened == 4
