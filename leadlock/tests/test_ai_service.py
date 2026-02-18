"""
Tests for src/services/ai.py — AI response generation with Anthropic primary + OpenAI fallback.
Covers: cost calculation, model tier selection, provider failover, error dict on total failure.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.ai import calculate_cost, generate_response, COST_TABLE


# ---------------------------------------------------------------------------
# calculate_cost
# ---------------------------------------------------------------------------

class TestCalculateCost:
    """Cost calculation for known and unknown models."""

    def test_haiku_model_pricing(self):
        """Haiku: $1.00/M input, $5.00/M output."""
        model = "claude-haiku-4-5-20251001"
        cost = calculate_cost(model, input_tokens=1000, output_tokens=500)
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_sonnet_model_pricing(self):
        """Sonnet: $3.00/M input, $15.00/M output."""
        model = "claude-sonnet-4-5-20250929"
        cost = calculate_cost(model, input_tokens=2000, output_tokens=1000)
        expected = (2000 * 3.00 + 1000 * 15.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_gpt4o_mini_pricing(self):
        """GPT-4o-mini: $0.15/M input, $0.60/M output."""
        model = "gpt-4o-mini"
        cost = calculate_cost(model, input_tokens=5000, output_tokens=2000)
        expected = (5000 * 0.15 + 2000 * 0.60) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_uses_default_pricing(self):
        """Unknown model falls back to default $1.00/$5.00 pricing."""
        cost = calculate_cost("unknown-model-xyz", input_tokens=1000, output_tokens=500)
        expected = (1000 * 1.0 + 500 * 5.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_zero_tokens_returns_zero(self):
        cost = calculate_cost("claude-haiku-4-5-20251001", input_tokens=0, output_tokens=0)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# generate_response — model tier selection and failover
# ---------------------------------------------------------------------------

def _make_mock_settings(**overrides):
    """Build a mock Settings object with sensible defaults."""
    defaults = {
        "anthropic_api_key": "sk-ant-test",
        "anthropic_model_fast": "claude-haiku-4-5-20251001",
        "anthropic_model_smart": "claude-sonnet-4-5-20250929",
        "anthropic_max_tokens_fast": 300,
        "anthropic_max_tokens_smart": 500,
        "anthropic_timeout_seconds": 10,
        "openai_api_key": "sk-openai-test",
        "openai_model_fast": "gpt-4o-mini",
        "openai_model_smart": "gpt-4o",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _make_anthropic_response(text="Hello", input_tokens=50, output_tokens=20):
    """Build a mock Anthropic messages.create() response."""
    content_block = MagicMock()
    content_block.text = text
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    return response


def _make_openai_response(text="Fallback reply", prompt_tokens=40, completion_tokens=15):
    """Build a mock OpenAI chat.completions.create() response."""
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class TestGenerateResponse:
    """Integration-level tests for generate_response with mocked providers."""

    @pytest.mark.asyncio
    async def test_successful_anthropic_response(self):
        """Happy path: Anthropic returns successfully."""
        mock_settings = _make_mock_settings()
        anthropic_resp = _make_anthropic_response("Test reply", 100, 50)

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=anthropic_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            # Call through the private function to control mocking fully
            from src.services.ai import _generate_anthropic
            result = await _generate_anthropic(
                "system prompt", "user message", "fast", None, 0.3
            )

        assert result["content"] == "Test reply"
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-haiku-4-5-20251001"
        assert result["error"] is None
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_smart_tier_selects_sonnet(self):
        """model_tier='smart' should use the Sonnet model."""
        mock_settings = _make_mock_settings()
        anthropic_resp = _make_anthropic_response()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=anthropic_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            from src.services.ai import _generate_anthropic
            result = await _generate_anthropic(
                "system", "user", "smart", None, 0.3
            )

        assert result["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_anthropic_failure_falls_back_to_openai(self):
        """When Anthropic fails, OpenAI should be tried as fallback."""
        mock_settings = _make_mock_settings()
        openai_resp = _make_openai_response("Fallback reply", 40, 15)

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create = AsyncMock(return_value=openai_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.ai._generate_anthropic",
                new_callable=AsyncMock,
                side_effect=Exception("Anthropic down"),
            ),
            patch("openai.AsyncOpenAI", return_value=mock_openai_client),
        ):
            from src.services.ai import _generate_openai
            result = await _generate_openai(
                "system", "user", "fast", None, 0.3
            )

        assert result["provider"] == "openai"
        assert result["content"] == "Fallback reply"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_both_providers_fail_returns_error_dict(self):
        """When both Anthropic and OpenAI fail, return a structured error."""
        mock_settings = _make_mock_settings()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.ai._generate_anthropic",
                new_callable=AsyncMock,
                side_effect=Exception("Anthropic down"),
            ),
            patch(
                "src.services.ai._generate_openai",
                new_callable=AsyncMock,
                side_effect=Exception("OpenAI down"),
            ),
        ):
            result = await generate_response("system", "user", model_tier="fast")

        assert result["provider"] == "none"
        assert result["content"] == ""
        assert result["error"] == "All AI providers failed"
        assert result["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_both_fail_no_openai_key(self):
        """When Anthropic fails and OpenAI key is empty, return error without trying OpenAI."""
        mock_settings = _make_mock_settings(openai_api_key="")

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.ai._generate_anthropic",
                new_callable=AsyncMock,
                side_effect=Exception("Anthropic down"),
            ),
        ):
            result = await generate_response("system", "user")

        assert result["error"] == "All AI providers failed"
        assert result["provider"] == "none"

    @pytest.mark.asyncio
    async def test_fast_tier_selects_haiku(self):
        """model_tier='fast' should use the Haiku model."""
        mock_settings = _make_mock_settings()
        anthropic_resp = _make_anthropic_response()

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=anthropic_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            from src.services.ai import _generate_anthropic
            result = await _generate_anthropic(
                "system", "user", "fast", None, 0.3
            )

        assert result["model"] == "claude-haiku-4-5-20251001"
