"""
Tests for src/services/ai.py - OpenAI mini-only routing and error handling.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.ai import COST_TABLE, calculate_cost, generate_response


class TestCalculateCost:
    def test_gpt4o_mini_pricing(self):
        model = "gpt-4o-mini"
        cost = calculate_cost(model, input_tokens=5000, output_tokens=2000)
        expected = (5000 * 0.15 + 2000 * 0.60) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_uses_default_pricing(self):
        cost = calculate_cost("unknown-model", input_tokens=1000, output_tokens=500)
        expected = (1000 * 1.0 + 500 * 5.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_cost_table_has_only_openai_models(self):
        assert set(COST_TABLE.keys()) == {"gpt-4o-mini", "gpt-4o"}


def _make_mock_settings(**overrides):
    defaults = {
        "openai_api_key": "sk-openai-test",
        "openai_model_fast": "gpt-4o-mini",
        "openai_model_smart": "gpt-4o-mini",
        "openai_max_tokens_fast": 300,
        "openai_max_tokens_smart": 500,
        "openai_timeout_seconds": 10,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for key, value in defaults.items():
        setattr(settings, key, value)
    return settings


def _make_openai_response(text="Hello", prompt_tokens=40, completion_tokens=15):
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
    @pytest.mark.asyncio
    async def test_missing_openai_key_returns_config_error(self):
        with patch("src.config.get_settings", return_value=_make_mock_settings(openai_api_key="")):
            result = await generate_response("system", "user")

        assert result["provider"] == "none"
        assert result["error"] == "OpenAI API key not configured"

    @pytest.mark.asyncio
    async def test_openai_success_returns_structured_result(self):
        mock_settings = _make_mock_settings()
        openai_resp = _make_openai_response("Test reply", 100, 50)

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create = AsyncMock(return_value=openai_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("openai.AsyncOpenAI", return_value=mock_openai_client),
        ):
            from src.services.ai import _generate_openai
            result = await _generate_openai("system", "user", "fast", None, 0.3)

        assert result["content"] == "Test reply"
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o-mini"
        assert result["error"] is None
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_generate_response_forces_fast_tier(self):
        mock_settings = _make_mock_settings()
        expected = {
            "content": "ok",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "latency_ms": 1,
            "cost_usd": 0.0,
            "input_tokens": 1,
            "output_tokens": 1,
            "error": None,
        }

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.services.ai._generate_openai", new_callable=AsyncMock, return_value=expected) as mock_openai,
        ):
            result = await generate_response("system", "user", model_tier="smart")

        assert result == expected
        call_args = mock_openai.call_args[0]
        assert call_args[2] == "fast"

    @pytest.mark.asyncio
    async def test_openai_failure_returns_error_dict(self):
        mock_settings = _make_mock_settings()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch(
                "src.services.ai._generate_openai",
                new_callable=AsyncMock,
                side_effect=Exception("OpenAI down"),
            ),
        ):
            result = await generate_response("system", "user")

        assert result["provider"] == "none"
        assert result["content"] == ""
        assert result["error"] == "OpenAI request failed"

    @pytest.mark.asyncio
    async def test_generate_openai_respects_explicit_max_tokens(self):
        mock_settings = _make_mock_settings()
        openai_resp = _make_openai_response()

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create = AsyncMock(return_value=openai_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("openai.AsyncOpenAI", return_value=mock_openai_client),
        ):
            from src.services.ai import _generate_openai
            await _generate_openai("system", "user", "fast", 123, 0.3)

        kwargs = mock_openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == 123

    @pytest.mark.asyncio
    async def test_generate_openai_strips_think_blocks(self):
        mock_settings = _make_mock_settings()
        openai_resp = _make_openai_response("<think>internal</think>\n\nok")

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create = AsyncMock(return_value=openai_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("openai.AsyncOpenAI", return_value=mock_openai_client),
        ):
            from src.services.ai import _generate_openai
            result = await _generate_openai("system", "user", "fast", None, 0.3)

        assert result["content"] == "ok"
