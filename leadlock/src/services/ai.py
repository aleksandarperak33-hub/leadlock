"""
AI service - OpenAI mini primary, Anthropic fallback.
Hard 10-second timeout on ALL AI calls. Never block the SMS response path.
Tracks cost, latency, and token usage for every call.
"""
import json
import logging
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


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given model and token count."""
    costs = COST_TABLE.get(model, {"input": 1.0, "output": 5.0})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


async def generate_response(
    system_prompt: str,
    user_message: str,
    model_tier: str = "fast",
    max_tokens: Optional[int] = None,
    temperature: float = 0.3,
    response_format: Optional[str] = None,
) -> dict:
    """
    Generate AI response with OpenAI mini primary + Anthropic fallback.
    Hard 10-second timeout. Returns structured result with cost tracking.

    Args:
        system_prompt: System instructions for the AI
        user_message: The user/lead message to respond to
        model_tier: "fast" (Haiku) or "smart" (Sonnet)
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
    # Try OpenAI mini first (use fast tier for all requests by default).
    from src.config import get_settings
    settings = get_settings()
    if settings.openai_api_key:
        try:
            result = await _generate_openai(
                system_prompt, user_message, "fast", max_tokens, temperature
            )
            return result
        except Exception as e:
            logger.warning("OpenAI mini failed: %s. Trying Anthropic fallback...", str(e))

    # Fallback to Anthropic (use fast tier to stay in low-cost mode).
    if settings.anthropic_api_key:
        try:
            result = await _generate_anthropic(
                system_prompt, user_message, "fast", max_tokens, temperature
            )
            return result
        except Exception as e:
            logger.error("Anthropic fallback also failed: %s", str(e))

    # Both failed - return error
    return {
        "content": "",
        "provider": "none",
        "model": "none",
        "latency_ms": 0,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "error": "All AI providers failed",
    }


async def _generate_anthropic(
    system_prompt: str,
    user_message: str,
    model_tier: str,
    max_tokens: Optional[int],
    temperature: float,
) -> dict:
    """Generate response using Anthropic Claude API."""
    import anthropic
    from src.config import get_settings
    settings = get_settings()

    model = settings.anthropic_model_fast if model_tier == "fast" else settings.anthropic_model_smart
    tokens = max_tokens or (
        settings.anthropic_max_tokens_fast if model_tier == "fast" else settings.anthropic_max_tokens_smart
    )

    client = anthropic.AsyncAnthropic(
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

    content = response.content[0].text if response.content else ""
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

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

    # Enforce mini model for all paths (\"mini-max\" mode).
    model = settings.openai_model_fast
    tokens = max_tokens or (
        settings.anthropic_max_tokens_fast if model_tier == "fast" else settings.anthropic_max_tokens_smart
    )

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.anthropic_timeout_seconds,
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
