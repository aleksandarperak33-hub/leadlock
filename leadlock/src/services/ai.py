"""
AI service - Anthropic primary, OpenAI fallback.
Hard 10-second timeout on ALL AI calls. Never block the SMS response path.
Tracks cost, latency, and token usage for every call.
Daily spending cap via Redis to prevent runaway costs.
"""
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Cost per million tokens (input/output)
COST_TABLE = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

DAILY_SPEND_KEY = "leadlock:ai:daily_spend"
DAILY_SPEND_TTL = 86400  # 24 hours


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given model and token count."""
    costs = COST_TABLE.get(model, {"input": 1.0, "output": 5.0})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


def _sanitize_output_text(text: str) -> str:
    """Remove hidden reasoning blocks returned by some providers."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


async def _check_daily_budget(cost_usd: float = 0.0) -> tuple[bool, float]:
    """
    Check if adding cost_usd would exceed the daily AI budget.
    Returns (allowed, current_spend).
    """
    try:
        from src.utils.dedup import get_redis
        from src.config import get_settings
        settings = get_settings()
        budget = settings.ai_daily_budget_usd

        redis = await get_redis()
        current_raw = await redis.get(DAILY_SPEND_KEY)
        current = float(current_raw) if current_raw else 0.0

        if current + cost_usd > budget:
            return False, current
        return True, current
    except Exception as e:
        logger.debug("Budget check failed (allowing): %s", str(e))
        return True, 0.0


async def _record_spend(cost_usd: float) -> None:
    """Record AI spend in Redis with TTL-based daily reset."""
    if cost_usd <= 0:
        return
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        pipe = redis.pipeline()
        pipe.incrbyfloat(DAILY_SPEND_KEY, cost_usd)
        pipe.expire(DAILY_SPEND_KEY, DAILY_SPEND_TTL)
        await pipe.execute()
    except Exception as e:
        logger.debug("Spend recording failed: %s", str(e))


def _error_result(error_msg: str) -> dict:
    """Return a standardized error result dict."""
    return {
        "content": "",
        "provider": "none",
        "model": "none",
        "latency_ms": 0,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "error": error_msg,
    }


async def generate_response(
    system_prompt: str,
    user_message: str,
    model_tier: str = "fast",
    max_tokens: Optional[int] = None,
    temperature: float = 0.3,
    response_format: Optional[str] = None,
) -> dict:
    """
    Generate AI response. Anthropic primary, OpenAI fallback.
    Hard 10-second timeout. Returns structured result with cost tracking.

    Args:
        system_prompt: System instructions for the AI
        user_message: The user/lead message to respond to
        model_tier: "fast" (Haiku) or "smart" (Haiku for cost conservation; only explicit "smart" gets Sonnet)
        max_tokens: Override default max tokens
        temperature: Response randomness (0.0-1.0)
        response_format: "json" to request JSON output

    Returns:
        {
            "content": str,
            "provider": str,
            "model": str,
            "latency_ms": int,
            "cost_usd": float,
            "input_tokens": int,
            "output_tokens": int,
            "error": str|None,
        }
    """
    from src.config import get_settings
    settings = get_settings()

    # Check daily budget before making any API call
    allowed, current_spend = await _check_daily_budget()
    if not allowed:
        logger.warning(
            "AI daily budget exceeded: $%.4f spent of $%.2f limit",
            current_spend, settings.ai_daily_budget_usd,
        )
        return _error_result(
            f"Daily AI budget exceeded (${current_spend:.2f}/${settings.ai_daily_budget_usd:.2f})"
        )

    # Try Anthropic first
    if settings.anthropic_api_key:
        try:
            result = await _generate_anthropic(
                system_prompt, user_message, model_tier, max_tokens, temperature,
            )
            await _record_spend(result.get("cost_usd", 0.0))
            return result
        except Exception as e:
            logger.error("Anthropic failed: %s", str(e))

    # Fallback to OpenAI
    if settings.openai_api_key:
        try:
            result = await _generate_openai(
                system_prompt, user_message, model_tier, max_tokens, temperature,
            )
            await _record_spend(result.get("cost_usd", 0.0))
            return result
        except Exception as e:
            logger.error("OpenAI fallback failed: %s", str(e))

    return _error_result("No AI provider available (check API keys)")


async def _generate_anthropic(
    system_prompt: str,
    user_message: str,
    model_tier: str,
    max_tokens: Optional[int],
    temperature: float,
) -> dict:
    """Generate response using Anthropic Claude API."""
    from anthropic import AsyncAnthropic
    from src.config import get_settings
    settings = get_settings()

    model = (
        settings.anthropic_model_smart if model_tier == "smart"
        else settings.anthropic_model_fast
    )
    tokens = max_tokens or (
        settings.anthropic_max_tokens_smart if model_tier == "smart"
        else settings.anthropic_max_tokens_fast
    )

    client = AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.anthropic_timeout_seconds,
    )

    start = time.monotonic()
    response = await client.messages.create(
        model=model,
        max_tokens=tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    content = ""
    for block in response.content:
        if block.type == "text":
            content += block.text
    content = _sanitize_output_text(content)

    input_tokens = response.usage.input_tokens if response.usage else 0
    output_tokens = response.usage.output_tokens if response.usage else 0

    return {
        "content": content,
        "provider": "anthropic",
        "model": model,
        "latency_ms": latency_ms,
        "cost_usd": calculate_cost(model, input_tokens, output_tokens),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "error": None,
    }


async def _generate_openai(
    system_prompt: str,
    user_message: str,
    model_tier: str,
    max_tokens: Optional[int],
    temperature: float,
) -> dict:
    """Generate response using OpenAI API."""
    from openai import AsyncOpenAI
    from src.config import get_settings
    settings = get_settings()

    model = (
        settings.openai_model_smart if model_tier == "smart"
        else settings.openai_model_fast
    )
    tokens = max_tokens or (
        settings.openai_max_tokens_smart if model_tier == "smart"
        else settings.openai_max_tokens_fast
    )

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=(settings.openai_base_url or None),
        timeout=settings.openai_timeout_seconds,
    )

    start = time.monotonic()
    response = await client.chat.completions.create(
        model=model,
        max_tokens=tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    content = response.choices[0].message.content if response.choices else ""
    content = _sanitize_output_text(content)
    input_tokens = response.usage.prompt_tokens if response.usage else 0
    output_tokens = response.usage.completion_tokens if response.usage else 0

    return {
        "content": content,
        "provider": "openai",
        "model": model,
        "latency_ms": latency_ms,
        "cost_usd": calculate_cost(model, input_tokens, output_tokens),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "error": None,
    }
