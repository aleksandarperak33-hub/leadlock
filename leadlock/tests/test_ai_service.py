"""
Tests for src/services/ai.py - Anthropic primary, OpenAI fallback, and budget cap.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.ai import (
    COST_TABLE,
    DAILY_SPEND_KEY,
    calculate_cost,
    generate_response,
    _check_daily_budget,
    _record_spend,
    _error_result,
)


class TestCalculateCost:
    def test_haiku_pricing(self):
        model = "claude-haiku-4-5-20251001"
        cost = calculate_cost(model, input_tokens=5000, output_tokens=2000)
        expected = (5000 * 1.00 + 2000 * 5.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_sonnet_pricing(self):
        model = "claude-sonnet-4-5-20250929"
        cost = calculate_cost(model, input_tokens=1000, output_tokens=500)
        expected = (1000 * 3.00 + 500 * 15.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_gpt4o_mini_pricing(self):
        model = "gpt-4o-mini"
        cost = calculate_cost(model, input_tokens=5000, output_tokens=2000)
        expected = (5000 * 0.15 + 2000 * 0.60) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_uses_default_pricing(self):
        cost = calculate_cost("unknown-model", input_tokens=1000, output_tokens=500)
        expected = (1000 * 1.0 + 500 * 5.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_cost_table_has_anthropic_and_openai_models(self):
        assert "claude-haiku-4-5-20251001" in COST_TABLE
        assert "claude-sonnet-4-5-20250929" in COST_TABLE
        assert "gpt-4o-mini" in COST_TABLE
        assert "gpt-4o" in COST_TABLE


def _make_mock_settings(**overrides):
    defaults = {
        "openai_api_key": "sk-openai-test",
        "openai_base_url": "",
        "openai_model_fast": "gpt-4o-mini",
        "openai_model_smart": "gpt-4o-mini",
        "openai_max_tokens_fast": 300,
        "openai_max_tokens_smart": 500,
        "openai_timeout_seconds": 10,
        "anthropic_api_key": "sk-ant-test",
        "anthropic_model_fast": "claude-haiku-4-5-20251001",
        "anthropic_model_smart": "claude-sonnet-4-5-20250929",
        "anthropic_max_tokens_fast": 300,
        "anthropic_max_tokens_smart": 500,
        "anthropic_timeout_seconds": 10,
        "ai_daily_budget_usd": 5.0,
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


def _make_anthropic_response(text="Hello", input_tokens=40, output_tokens=15):
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response = MagicMock()
    response.content = [text_block]
    response.usage = usage
    return response


class TestErrorResult:
    def test_returns_standardized_dict(self):
        result = _error_result("test error")
        assert result["content"] == ""
        assert result["provider"] == "none"
        assert result["error"] == "test error"
        assert result["cost_usd"] == 0.0


class TestGenerateResponseAnthropicPrimary:
    @pytest.mark.asyncio
    async def test_anthropic_success(self):
        mock_settings = _make_mock_settings()
        anthropic_resp = _make_anthropic_response("Anthropic reply", 100, 50)

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=anthropic_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
            patch("src.services.ai._check_daily_budget", new_callable=AsyncMock, return_value=(True, 0.0)),
            patch("src.services.ai._record_spend", new_callable=AsyncMock),
        ):
            from src.services.ai import _generate_anthropic
            result = await _generate_anthropic("system", "user", "fast", None, 0.3)

        assert result["content"] == "Anthropic reply"
        assert result["provider"] == "anthropic"
        assert result["model"] == "claude-haiku-4-5-20251001"
        assert result["error"] is None
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50
        assert result["cost_usd"] > 0

    @pytest.mark.asyncio
    async def test_anthropic_smart_tier_uses_sonnet(self):
        mock_settings = _make_mock_settings()
        anthropic_resp = _make_anthropic_response("Smart reply", 100, 50)

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=anthropic_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            from src.services.ai import _generate_anthropic
            result = await _generate_anthropic("system", "user", "smart", None, 0.3)

        assert result["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    async def test_anthropic_strips_think_blocks(self):
        mock_settings = _make_mock_settings()
        anthropic_resp = _make_anthropic_response("<think>internal</think>\n\nclean", 10, 5)

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=anthropic_resp)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("anthropic.AsyncAnthropic", return_value=mock_client),
        ):
            from src.services.ai import _generate_anthropic
            result = await _generate_anthropic("system", "user", "fast", None, 0.3)

        assert result["content"] == "clean"


class TestGenerateResponseRouting:
    @pytest.mark.asyncio
    async def test_anthropic_primary_openai_fallback(self):
        """When Anthropic fails, falls back to OpenAI."""
        mock_settings = _make_mock_settings()
        openai_expected = {
            "content": "openai reply",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "latency_ms": 1,
            "cost_usd": 0.001,
            "input_tokens": 10,
            "output_tokens": 5,
            "error": None,
        }

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.services.ai._check_daily_budget", new_callable=AsyncMock, return_value=(True, 0.0)),
            patch("src.services.ai._record_spend", new_callable=AsyncMock),
            patch(
                "src.services.ai._generate_anthropic",
                new_callable=AsyncMock,
                side_effect=Exception("Anthropic down"),
            ),
            patch(
                "src.services.ai._generate_openai",
                new_callable=AsyncMock,
                return_value=openai_expected,
            ),
        ):
            result = await generate_response("system", "user")

        assert result["provider"] == "openai"
        assert result["content"] == "openai reply"

    @pytest.mark.asyncio
    async def test_no_api_keys_returns_error(self):
        mock_settings = _make_mock_settings(anthropic_api_key="", openai_api_key="")

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.services.ai._check_daily_budget", new_callable=AsyncMock, return_value=(True, 0.0)),
        ):
            result = await generate_response("system", "user")

        assert result["provider"] == "none"
        assert "No AI provider available" in result["error"]

    @pytest.mark.asyncio
    async def test_both_providers_fail_returns_error(self):
        mock_settings = _make_mock_settings()

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.services.ai._check_daily_budget", new_callable=AsyncMock, return_value=(True, 0.0)),
            patch("src.services.ai._generate_anthropic", new_callable=AsyncMock, side_effect=Exception("fail")),
            patch("src.services.ai._generate_openai", new_callable=AsyncMock, side_effect=Exception("fail")),
        ):
            result = await generate_response("system", "user")

        assert result["provider"] == "none"
        assert result["error"] is not None


class TestDailyBudgetCap:
    @pytest.mark.asyncio
    async def test_budget_exceeded_blocks_request(self):
        mock_settings = _make_mock_settings(ai_daily_budget_usd=5.0)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.services.ai._check_daily_budget", new_callable=AsyncMock, return_value=(False, 5.01)),
        ):
            result = await generate_response("system", "user")

        assert result["provider"] == "none"
        assert "budget exceeded" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_budget_check_allows_under_limit(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="2.50")

        mock_settings = _make_mock_settings(ai_daily_budget_usd=5.0)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
        ):
            allowed, current = await _check_daily_budget(0.01)

        assert allowed is True
        assert current == pytest.approx(2.50)

    @pytest.mark.asyncio
    async def test_budget_check_blocks_over_limit(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="4.99")

        mock_settings = _make_mock_settings(ai_daily_budget_usd=5.0)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
        ):
            allowed, current = await _check_daily_budget(0.02)

        assert allowed is False
        assert current == pytest.approx(4.99)

    @pytest.mark.asyncio
    async def test_budget_check_redis_failure_allows(self):
        """If Redis is down, allow the request (fail-open for reliability)."""
        mock_settings = _make_mock_settings(ai_daily_budget_usd=5.0)

        with (
            patch("src.config.get_settings", return_value=mock_settings),
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("Redis down")),
        ):
            allowed, current = await _check_daily_budget(0.01)

        assert allowed is True

    @pytest.mark.asyncio
    async def test_record_spend_calls_redis(self):
        mock_pipe = MagicMock()
        mock_pipe.incrbyfloat = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await _record_spend(0.05)

        mock_pipe.incrbyfloat.assert_called_once_with(DAILY_SPEND_KEY, 0.05)
        mock_pipe.expire.assert_called_once()
        mock_pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_spend_skips_zero_cost(self):
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock) as mock_get_redis:
            await _record_spend(0.0)

        mock_get_redis.assert_not_awaited()


class TestOpenAIFallback:
    @pytest.mark.asyncio
    async def test_openai_success(self):
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

    @pytest.mark.asyncio
    async def test_openai_respects_explicit_max_tokens(self):
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
    async def test_openai_strips_think_blocks(self):
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
