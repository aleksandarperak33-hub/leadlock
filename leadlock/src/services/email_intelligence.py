"""
Email intelligence service - content feature extraction and engagement correlation.

Pure functions for feature extraction (no IO), plus analytics queries for
correlating content features with open/reply rates.
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy import select, func, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Pure feature extraction (no IO)
# ---------------------------------------------------------------------------

def extract_content_features(
    subject: str,
    body_text: str,
    prospect_name: Optional[str] = None,
    company: Optional[str] = None,
    city: Optional[str] = None,
    trade: Optional[str] = None,
    has_booking_url: bool = False,
) -> dict:
    """
    Extract structured content features from an email for intelligence tracking.
    Pure function - no IO, no side effects.

    Returns dict of measurable email characteristics.
    """
    subject = subject or ""
    body_text = body_text or ""
    first_name = _extract_first_name(prospect_name) if prospect_name else ""

    # Subject features
    subject_lower = subject.lower()
    subject_length = len(subject)
    subject_has_name = bool(first_name and first_name.lower() in subject_lower)
    subject_has_company = bool(company and company.lower() in subject_lower)
    subject_has_question = "?" in subject
    subject_has_number = bool(re.search(r"\d", subject))

    # Body features
    body_words = body_text.split()
    body_word_count = len(body_words)
    body_paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    body_paragraph_count = max(len(body_paragraphs), 1)

    # Content signals
    body_lower = body_text.lower()
    has_rating_mention = bool(
        re.search(r"\d+\.?\d*\s*(star|rating|review)", body_lower)
    )
    has_dollar_amount = bool(re.search(r"\$[\d,]+", body_text))

    # Greeting type
    greeting_type = _classify_greeting(body_text, first_name, company)

    # Personalization depth: count distinct personalization signals used
    personalization_signals = sum([
        bool(first_name and first_name.lower() in body_lower),
        bool(company and company.lower() in body_lower),
        bool(city and city.lower() in body_lower),
        bool(trade and trade.lower() in body_lower),
        has_rating_mention,
        has_dollar_amount,
    ])

    return {
        "subject_length": subject_length,
        "subject_has_name": subject_has_name,
        "subject_has_company": subject_has_company,
        "subject_has_question": subject_has_question,
        "subject_has_number": subject_has_number,
        "body_word_count": body_word_count,
        "body_paragraph_count": body_paragraph_count,
        "has_rating_mention": has_rating_mention,
        "has_dollar_amount": has_dollar_amount,
        "has_booking_url": has_booking_url,
        "greeting_type": greeting_type,
        "personalization_depth": personalization_signals,
    }


def _extract_first_name(full_name: str) -> str:
    """Extract first name from a full name string."""
    if not full_name:
        return ""
    parts = full_name.strip().split()
    return parts[0] if parts else ""


def _classify_greeting(
    body_text: str, first_name: str, company: Optional[str]
) -> str:
    """Classify the greeting type used in the email."""
    if not body_text:
        return "generic"
    # Check first ~80 chars for greeting pattern
    opening = body_text[:80].lower()
    if first_name and first_name.lower() in opening:
        return "first_name"
    if company and company.lower() in opening and "team" in opening:
        return "company_team"
    return "generic"


# ---------------------------------------------------------------------------
# Analytics queries
# ---------------------------------------------------------------------------

async def _cached_intelligence_query(
    cache_key: str, query_fn, ttl: int = CACHE_TTL_SECONDS,
) -> dict:
    """Execute query with Redis caching (mirrors analytics.py pattern)."""
    full_key = f"leadlock:email_intel:{cache_key}"
    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        cached = await redis.get(full_key)
        if cached:
            raw = cached.decode() if isinstance(cached, bytes) else str(cached)
            return json.loads(raw)
    except Exception as e:
        logger.debug("Email intelligence cache read failed: %s", str(e))

    result = await query_fn()

    try:
        from src.utils.dedup import get_redis
        redis = await get_redis()
        await redis.set(full_key, json.dumps(result, default=str), ex=ttl)
    except Exception as e:
        logger.debug("Email intelligence cache write failed: %s", str(e))

    return result


async def get_feature_engagement_correlation(
    feature_name: str,
    min_sample: int = 30,
) -> dict:
    """
    Group outbound emails by a content_features JSONB field value and
    compute open/reply rates per value bucket.

    Only returns buckets with >= min_sample sends.
    """
    cache_key = f"feature_corr:{feature_name}"

    async def _query():
        async with async_session_factory() as db:
            # Use JSONB extraction for the feature
            feature_expr = OutreachEmail.content_features[feature_name].as_string()

            result = await db.execute(
                select(
                    feature_expr.label("feature_value"),
                    func.count(OutreachEmail.id).label("total_sent"),
                    func.count(OutreachEmail.opened_at).label("total_opened"),
                    func.count(
                        case(
                            (OutreachEmail.reply_classification == "interested", OutreachEmail.id),
                        )
                    ).label("interested_replies"),
                )
                .where(
                    and_(
                        OutreachEmail.direction == "outbound",
                        OutreachEmail.content_features.isnot(None),
                        OutreachEmail.content_features[feature_name].isnot(None),
                    )
                )
                .group_by(feature_expr)
                .having(func.count(OutreachEmail.id) >= min_sample)
            )
            rows = result.fetchall()

            buckets = []
            for row in rows:
                sent = row[1] or 0
                opened = row[2] or 0
                replies = row[3] or 0
                buckets.append({
                    "value": row[0],
                    "total_sent": sent,
                    "open_rate": round(opened / sent, 4) if sent > 0 else 0.0,
                    "reply_rate": round(replies / sent, 4) if sent > 0 else 0.0,
                })

            return {"feature": feature_name, "buckets": buckets}

    return await _cached_intelligence_query(cache_key, _query)


async def get_content_intelligence_summary() -> dict:
    """
    Aggregate feature correlations across key content dimensions.
    Returns a summary of which features correlate with higher engagement.
    """
    cache_key = "content_summary"

    async def _query():
        features_to_check = [
            "subject_has_question",
            "subject_has_name",
            "subject_has_company",
            "subject_has_number",
            "has_dollar_amount",
            "has_rating_mention",
            "has_booking_url",
            "greeting_type",
        ]

        correlations = {}
        for feature in features_to_check:
            try:
                data = await get_feature_engagement_correlation(feature, min_sample=20)
                if data.get("buckets"):
                    correlations[feature] = data["buckets"]
            except Exception as e:
                logger.debug("Feature correlation failed for %s: %s", feature, str(e))

        # Word count bucket analysis (group into ranges)
        try:
            word_count_data = await _get_word_count_buckets()
            if word_count_data:
                correlations["body_word_count_bucket"] = word_count_data
        except Exception as e:
            logger.debug("Word count bucket analysis failed: %s", str(e))

        return {"correlations": correlations}

    return await _cached_intelligence_query(cache_key, _query)


async def _get_word_count_buckets() -> list[dict]:
    """Group emails by word count ranges and compute engagement rates."""
    async with async_session_factory() as db:
        word_count_expr = OutreachEmail.content_features["body_word_count"].as_integer()

        bucket_expr = case(
            (word_count_expr < 50, "under_50"),
            (word_count_expr < 80, "50_to_80"),
            (word_count_expr < 120, "80_to_120"),
            else_="over_120",
        )

        result = await db.execute(
            select(
                bucket_expr.label("bucket"),
                func.count(OutreachEmail.id).label("total_sent"),
                func.count(OutreachEmail.opened_at).label("total_opened"),
                func.count(
                    case(
                        (OutreachEmail.reply_classification == "interested", OutreachEmail.id),
                    )
                ).label("interested_replies"),
            )
            .where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.content_features.isnot(None),
                )
            )
            .group_by(bucket_expr)
            .having(func.count(OutreachEmail.id) >= 15)
        )
        rows = result.fetchall()

        return [
            {
                "value": row[0],
                "total_sent": row[1] or 0,
                "open_rate": round((row[2] or 0) / row[1], 4) if row[1] else 0.0,
                "reply_rate": round((row[3] or 0) / row[1], 4) if row[1] else 0.0,
            }
            for row in rows
        ]


async def format_content_intelligence_for_prompt(
    trade: Optional[str] = None,
    step: Optional[int] = None,
) -> str:
    """
    Convert content feature correlations into prescriptive instructions
    for the AI email generation prompt.

    Returns a multi-line string of actionable insights, or empty string
    if insufficient data.
    """
    try:
        summary = await get_content_intelligence_summary()
    except Exception as e:
        logger.debug("Content intelligence query failed: %s", str(e))
        return ""

    correlations = summary.get("correlations", {})
    if not correlations:
        return ""

    insights: list[str] = []

    # Word count insights
    wc_buckets = correlations.get("body_word_count_bucket", [])
    if len(wc_buckets) >= 2:
        best_bucket = max(wc_buckets, key=lambda b: b.get("reply_rate", 0))
        if best_bucket.get("reply_rate", 0) > 0:
            label = best_bucket["value"].replace("_", " ")
            rate_pct = round(best_bucket["reply_rate"] * 100, 1)
            insights.append(
                f"Emails with {label} words get {rate_pct}% reply rate"
            )

    # Boolean feature insights
    for feature in ["subject_has_question", "subject_has_name", "has_dollar_amount"]:
        buckets = correlations.get(feature, [])
        true_bucket = next((b for b in buckets if b.get("value") in ("true", "True", "1")), None)
        false_bucket = next((b for b in buckets if b.get("value") in ("false", "False", "0")), None)
        if true_bucket and false_bucket:
            true_rate = true_bucket.get("open_rate", 0)
            false_rate = false_bucket.get("open_rate", 0)
            if true_rate > false_rate and false_rate > 0:
                lift_pct = round(((true_rate - false_rate) / false_rate) * 100)
                feature_label = feature.replace("_", " ").replace("subject ", "")
                insights.append(
                    f"Subject lines with {feature_label} get {lift_pct}% more opens"
                )

    # Greeting type insights
    greeting_buckets = correlations.get("greeting_type", [])
    if len(greeting_buckets) >= 2:
        best_greeting = max(greeting_buckets, key=lambda b: b.get("reply_rate", 0))
        if best_greeting.get("reply_rate", 0) > 0:
            gtype = best_greeting["value"].replace("_", " ")
            insights.append(f"Best performing greeting: {gtype}")

    if not insights:
        return ""

    # Cap at 4 insights to avoid prompt bloat
    capped = insights[:4]
    trade_label = f" for {trade}" if trade else ""
    return (
        f"Content intelligence{trade_label}:\n"
        + "\n".join(f"- {i}" for i in capped)
    )
