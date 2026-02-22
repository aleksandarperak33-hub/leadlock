"""
Content generation service - AI prompts for each content type.
Generates blog posts, social media posts, and lead magnet outlines.

One-Writer for content_pieces table.
"""
import json
import logging
from typing import Optional

from src.services.ai import generate_response
from src.utils.agent_cost import track_agent_cost
from src.database import async_session_factory
from src.models.content_piece import ContentPiece

logger = logging.getLogger(__name__)

# SEO keywords organized by trade
SEO_KEYWORDS = {
    "hvac": [
        "HVAC lead response time",
        "HVAC speed to lead",
        "HVAC contractor lead management",
        "HVAC missed leads cost",
    ],
    "plumbing": [
        "plumbing lead response time",
        "plumber speed to lead",
        "plumbing contractor leads",
    ],
    "roofing": [
        "roofing lead response time",
        "roofing contractor leads",
        "roofing speed to lead",
    ],
    "electrical": [
        "electrician lead response",
        "electrical contractor leads",
    ],
    "solar": [
        "solar lead response time",
        "solar installer leads",
    ],
    "general": [
        "speed to lead home services",
        "home services lead response time",
        "contractor lead management",
        "home services missed leads",
    ],
}

BLOG_POST_PROMPT = """You write SEO-optimized blog posts for LeadLock, an AI speed-to-lead platform
for home services contractors.

Write a 1000-word blog post targeting the keyword: "{keyword}"

RULES:
- Write for contractors, not marketers. Use their language.
- Include the target keyword naturally 3-5 times (no keyword stuffing).
- Use specific stats and data points about lead response in home services.
- Include actionable takeaways, not just theory.
- Structure: H1 title, intro paragraph, 3-4 H2 sections, conclusion with CTA.
- CTA should mention LeadLock naturally (not pushy).
- Write in second person ("you") addressing contractors directly.
- No em dashes, no exclamation marks.

Output valid JSON:
{{"title": "...", "body": "...", "seo_meta": "...", "word_count": N}}

body: Full markdown content with ## headings.
seo_meta: 155-character meta description for SEO."""

TWITTER_PROMPT = """Write a short Twitter/X post about speed-to-lead in home services.

Topic: {topic}

RULES:
- Under 280 characters.
- Include one specific stat or insight.
- No hashtags (they reduce engagement in 2025).
- Punchy, direct, conversational tone.
- No emojis, no exclamation marks.
- Must stand alone without context.

Output valid JSON:
{{"title": "tweet", "body": "...", "word_count": N}}"""

LINKEDIN_PROMPT = """Write a LinkedIn post about lead response in home services contracting.

Topic: {topic}

RULES:
- 150-300 words. Professional but not corporate.
- Hook in first line (this appears above the fold).
- Business case format: problem -> data -> solution insight.
- Reference specific numbers or industry data.
- End with a question to drive engagement.
- No emojis, no exclamation marks.
- LeadLock mention optional and subtle if included.

Output valid JSON:
{{"title": "linkedin_post", "body": "...", "word_count": N}}"""

REDDIT_PROMPT = """Write a Reddit post for r/{subreddit} that provides genuine value about lead management.

Topic: {topic}

RULES:
- Value-first, NON-PROMOTIONAL. Reddit hates sales pitches.
- Share an insight, ask a question, or present data.
- Write like a fellow contractor or industry observer, not a vendor.
- 100-200 words. Conversational.
- Do NOT mention LeadLock or any specific product.
- End with a question to spark discussion.

Output valid JSON:
{{"title": "...", "body": "...", "word_count": N}}"""

LEAD_MAGNET_PROMPT = """Create an outline for a lead magnet (PDF guide or ROI calculator) for home services contractors.

Topic: {topic}

RULES:
- Practical, actionable content contractors would actually download.
- 5-7 sections with clear value.
- Include what data/stats each section would contain.
- Suggest a compelling title.
- 200-300 words for the outline.

Output valid JSON:
{{"title": "...", "body": "...", "word_count": N}}"""

# Content generation configs
CONTENT_CONFIGS = {
    "blog_post": {
        "prompt_template": BLOG_POST_PROMPT,
        "model_tier": "smart",
        "max_tokens": 2000,
        "temperature": 0.5,
    },
    "twitter": {
        "prompt_template": TWITTER_PROMPT,
        "model_tier": "fast",
        "max_tokens": 200,
        "temperature": 0.7,
    },
    "linkedin": {
        "prompt_template": LINKEDIN_PROMPT,
        "model_tier": "fast",
        "max_tokens": 500,
        "temperature": 0.5,
    },
    "reddit": {
        "prompt_template": REDDIT_PROMPT,
        "model_tier": "fast",
        "max_tokens": 400,
        "temperature": 0.6,
    },
    "lead_magnet": {
        "prompt_template": LEAD_MAGNET_PROMPT,
        "model_tier": "fast",
        "max_tokens": 500,
        "temperature": 0.5,
    },
}

# Topics for social content
SOCIAL_TOPICS = [
    "The cost of slow lead response for home services contractors",
    "Why the first contractor to call back wins 78% of jobs",
    "How long it takes the average contractor to respond to a lead",
    "What homeowners actually think when a contractor takes 4 hours to call back",
    "The difference between a 30-second and 30-minute lead response",
    "Why contractors lose $2,400/month to slow lead response",
    "How AI is changing lead response for small contractors",
    "The busiest contractors have the worst lead response times",
]

REDDIT_SUBREDDITS = ["HVAC", "Plumbing", "smallbusiness"]


async def generate_content_piece(
    content_type: str,
    target_trade: Optional[str] = None,
    target_keyword: Optional[str] = None,
    topic: Optional[str] = None,
    subreddit: Optional[str] = None,
) -> dict:
    """
    Generate a single content piece and store in DB.

    Args:
        content_type: blog_post, twitter, linkedin, reddit, lead_magnet
        target_trade: Trade to target (for keyword selection)
        target_keyword: Specific SEO keyword (for blog posts)
        topic: Topic for social posts
        subreddit: Reddit subreddit name

    Returns:
        {"content_id": str, "title": str, "word_count": int, "ai_cost_usd": float}
    """
    config = CONTENT_CONFIGS.get(content_type)
    if not config:
        return {"error": f"Unknown content type: {content_type}"}

    # Build prompt
    trade = target_trade or "general"
    prompt_template = config["prompt_template"]

    if content_type == "blog_post":
        keyword = target_keyword or _pick_keyword(trade)
        user_message = prompt_template.format(keyword=keyword)
    elif content_type == "reddit":
        sub = subreddit or "HVAC"
        t = topic or SOCIAL_TOPICS[0]
        user_message = prompt_template.format(subreddit=sub, topic=t)
    else:
        t = topic or SOCIAL_TOPICS[0]
        user_message = prompt_template.format(topic=t)

    result = await generate_response(
        system_prompt="You are a content writer for the home services industry.",
        user_message=user_message,
        model_tier=config["model_tier"],
        max_tokens=config["max_tokens"],
        temperature=config["temperature"],
    )

    if result.get("error"):
        logger.error("Content generation failed for %s: %s", content_type, result["error"])
        return {"error": result["error"], "ai_cost_usd": result.get("cost_usd", 0.0)}

    ai_cost = result.get("cost_usd", 0.0)
    await track_agent_cost("content_factory", ai_cost)

    try:
        content = result["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error("Failed to parse content response: %s", str(e))
        return {"error": f"JSON parse error: {str(e)}", "ai_cost_usd": ai_cost}

    title = parsed.get("title", "").strip()
    body = parsed.get("body", "").strip()
    word_count = parsed.get("word_count", len(body.split()))
    seo_meta = parsed.get("seo_meta", "")

    if not body:
        return {"error": "Empty content body", "ai_cost_usd": ai_cost}

    # Store in DB
    async with async_session_factory() as db:
        piece = ContentPiece(
            content_type=content_type,
            title=title,
            body=body,
            target_trade=target_trade,
            target_keyword=target_keyword or (keyword if content_type == "blog_post" else None),
            word_count=word_count,
            seo_meta=seo_meta[:320] if seo_meta else None,
            ai_model=result.get("model"),
            ai_cost_usd=ai_cost,
        )
        db.add(piece)
        await db.commit()

        logger.info(
            "Content generated: type=%s title='%s' words=%d cost=$%.4f",
            content_type, title[:50], word_count, ai_cost,
        )

        return {
            "content_id": str(piece.id),
            "title": title,
            "word_count": word_count,
            "ai_cost_usd": ai_cost,
        }


def _pick_keyword(trade: str) -> str:
    """Pick an SEO keyword for a trade."""
    import random
    keywords = SEO_KEYWORDS.get(trade, SEO_KEYWORDS["general"])
    return random.choice(keywords)


