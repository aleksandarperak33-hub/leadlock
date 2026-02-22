"""
Tests for winning patterns service.
Covers: confidence calculation, store, query, format for prompt.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

class TestConfidenceCalculation:
    def test_zero_sample_returns_zero(self):
        from src.services.winning_patterns import _calculate_confidence
        assert _calculate_confidence(0, 0.5) == 0.0

    def test_negative_sample_returns_zero(self):
        from src.services.winning_patterns import _calculate_confidence
        assert _calculate_confidence(-1, 0.5) == 0.0

    def test_small_sample_low_confidence(self):
        from src.services.winning_patterns import _calculate_confidence
        result = _calculate_confidence(10, 0.3)
        assert 0.0 < result < 0.5

    def test_large_sample_high_confidence(self):
        from src.services.winning_patterns import _calculate_confidence
        result = _calculate_confidence(100, 0.5)
        assert result > 0.5

    def test_very_large_sample_near_max(self):
        from src.services.winning_patterns import _calculate_confidence
        result = _calculate_confidence(500, 0.6)
        assert result > 0.8

    def test_zero_open_rate_still_has_confidence(self):
        from src.services.winning_patterns import _calculate_confidence
        result = _calculate_confidence(100, 0.0)
        assert result > 0.0  # size_factor * 0.5

    def test_confidence_never_exceeds_one(self):
        from src.services.winning_patterns import _calculate_confidence
        result = _calculate_confidence(10000, 1.0)
        assert result <= 1.0


# ---------------------------------------------------------------------------
# store_winning_pattern
# ---------------------------------------------------------------------------

class TestStoreWinningPattern:
    @pytest.mark.asyncio
    async def test_stores_pattern_returns_id(self):
        from src.services.winning_patterns import store_winning_pattern

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.winning_patterns.async_session_factory", return_value=mock_session):
            result = await store_winning_pattern(
                source="ab_test",
                instruction_text="Use curiosity-driven subject with a specific stat",
                trade="hvac",
                step=1,
                open_rate=0.35,
                sample_size=50,
            )

        # Should have added a pattern and committed
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_empty_instruction_returns_none(self):
        from src.services.winning_patterns import store_winning_pattern

        result = await store_winning_pattern(
            source="ab_test",
            instruction_text="",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_instruction_returns_none(self):
        from src.services.winning_patterns import store_winning_pattern

        result = await store_winning_pattern(
            source="reflection",
            instruction_text="   ",
        )
        assert result is None


# ---------------------------------------------------------------------------
# get_winning_patterns
# ---------------------------------------------------------------------------

class TestGetWinningPatterns:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_patterns(self):
        from src.services.winning_patterns import get_winning_patterns

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.winning_patterns.async_session_factory", return_value=mock_session):
            result = await get_winning_patterns(trade="hvac", step=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_pattern_dicts(self):
        from src.services.winning_patterns import get_winning_patterns
        import uuid

        mock_pattern = MagicMock()
        mock_pattern.id = uuid.uuid4()
        mock_pattern.instruction_text = "Use pain-point approach"
        mock_pattern.trade = "hvac"
        mock_pattern.sequence_step = 1
        mock_pattern.open_rate = 0.35
        mock_pattern.reply_rate = 0.05
        mock_pattern.confidence = 0.8
        mock_pattern.source = "ab_test"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_pattern]
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.winning_patterns.async_session_factory", return_value=mock_session):
            result = await get_winning_patterns(trade="hvac", step=1)

        assert len(result) == 1
        assert result[0]["instruction"] == "Use pain-point approach"
        assert result[0]["open_rate"] == 0.35
        assert result[0]["confidence"] == 0.8


# ---------------------------------------------------------------------------
# format_patterns_for_prompt
# ---------------------------------------------------------------------------

class TestFormatPatternsForPrompt:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_no_patterns(self):
        from src.services.winning_patterns import format_patterns_for_prompt

        with patch("src.services.winning_patterns.get_winning_patterns", return_value=[]):
            result = await format_patterns_for_prompt(trade="hvac", step=1)

        assert result == ""

    @pytest.mark.asyncio
    async def test_formats_patterns_with_rates(self):
        from src.services.winning_patterns import format_patterns_for_prompt

        mock_patterns = [
            {
                "id": "abc",
                "instruction": "Use curiosity hook",
                "trade": "hvac",
                "step": 1,
                "open_rate": 0.35,
                "reply_rate": 0.05,
                "confidence": 0.8,
                "source": "ab_test",
            },
        ]
        with patch("src.services.winning_patterns.get_winning_patterns", return_value=mock_patterns):
            result = await format_patterns_for_prompt(trade="hvac", step=1)

        assert "Proven winning approaches" in result
        assert "Use curiosity hook" in result
        assert "open rate: 35%" in result
        assert "reply rate: 5%" in result

    @pytest.mark.asyncio
    async def test_omits_reply_rate_when_zero(self):
        from src.services.winning_patterns import format_patterns_for_prompt

        mock_patterns = [
            {
                "id": "abc",
                "instruction": "Test instruction",
                "trade": None,
                "step": None,
                "open_rate": 0.40,
                "reply_rate": 0.0,
                "confidence": 0.7,
                "source": "reflection",
            },
        ]
        with patch("src.services.winning_patterns.get_winning_patterns", return_value=mock_patterns):
            result = await format_patterns_for_prompt()

        assert "reply rate" not in result
        assert "open rate: 40%" in result
