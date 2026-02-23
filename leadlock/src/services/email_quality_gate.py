"""
Email quality gate - lightweight pre-send validation.
Pure string checks, no AI calls. Zero latency on happy path.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_SUBJECT_LENGTH = 60
MIN_BODY_WORDS = 50
MAX_BODY_WORDS = 200

FORBIDDEN_WORDS = frozenset({
    "game-changer",
    "game changer",
    "revolutionary",
    "transform",
    "unlock",
    "synergy",
    "paradigm",
    "guaranteed",
    "free trial",
    "leverage",
    "disrupting",
    "disruptive",
    "best-in-class",
    "world-class",
    "cutting-edge",
    "next-gen",
    "next generation",
    "turnkey",
    "scalable solution",
    "empower",
    "holistic",
})


def check_email_quality(
    subject: str,
    body_text: str,
    prospect_name: Optional[str] = None,
    company_name: Optional[str] = None,
    city: Optional[str] = None,
    trade_type: Optional[str] = None,
) -> dict:
    """
    Validate email quality before sending.

    Args:
        subject: Email subject line
        body_text: Plain text email body
        prospect_name: Prospect's name (for personalization check)
        company_name: Company name (for personalization check)

    Returns:
        {"passed": bool, "issues": [str]}
    """
    issues: list[str] = []

    # Subject length check
    if len(subject) > MAX_SUBJECT_LENGTH:
        issues.append(
            f"Subject too long: {len(subject)} chars (max {MAX_SUBJECT_LENGTH})"
        )

    # Body word count check
    words = body_text.split() if body_text else []
    word_count = len(words)
    if word_count < MIN_BODY_WORDS:
        issues.append(
            f"Body too short: {word_count} words (min {MIN_BODY_WORDS})"
        )
    elif word_count > MAX_BODY_WORDS:
        issues.append(
            f"Body too long: {word_count} words (max {MAX_BODY_WORDS})"
        )

    # Personalization check - body should mention prospect, company, city, or trade.
    if prospect_name or company_name:
        body_lower = body_text.lower() if body_text else ""
        subject_lower = subject.lower() if subject else ""
        first_name = prospect_name.split()[0].lower() if prospect_name else ""
        has_prospect = (
            prospect_name
            and (
                prospect_name.lower() in body_lower
                or (first_name and first_name in body_lower)
            )
        )
        has_company = (
            company_name
            and company_name.lower() in body_lower
        )
        has_city = city and city.lower() in body_lower
        has_trade = trade_type and trade_type.lower() in body_lower
        if not has_prospect and not has_company and not has_city and not has_trade:
            issues.append(
                "Body doesn't mention prospect/company or local context (city/trade)"
            )

        # Subject should carry at least one personalization token.
        subject_tokens = []
        if first_name and len(first_name) >= 3:
            subject_tokens.append(first_name)
        if company_name:
            subject_tokens.extend(
                [w for w in company_name.lower().split() if len(w) >= 4]
            )
        if city and len(city) >= 3:
            subject_tokens.append(city.lower())
        if trade_type and len(trade_type) >= 3:
            subject_tokens.append(trade_type.lower())
        if subject_tokens and not any(tok in subject_lower for tok in subject_tokens):
            issues.append("Subject lacks personalization (name/company/city/trade)")

    # Generic mass-blast phrasing checks
    combined_text = f"{(subject or '').lower()} {(body_text or '').lower()}"
    if "hey there" in combined_text:
        issues.append("Contains generic greeting: 'Hey there'")

    # Forbidden words check
    body_lower = body_text.lower() if body_text else ""
    subject_lower = subject.lower() if subject else ""
    combined = f"{subject_lower} {body_lower}"
    for word in FORBIDDEN_WORDS:
        if word in combined:
            issues.append(f"Contains forbidden word: '{word}'")
            break  # One forbidden word is enough to flag

    passed = len(issues) == 0
    if not passed:
        logger.info(
            "Email quality gate failed: %d issues - %s",
            len(issues), "; ".join(issues),
        )

    return {"passed": passed, "issues": issues}
