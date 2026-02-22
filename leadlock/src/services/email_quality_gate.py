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

    # Personalization check - body should mention prospect or company name
    if prospect_name or company_name:
        body_lower = body_text.lower() if body_text else ""
        has_prospect = (
            prospect_name
            and prospect_name.lower() in body_lower
        )
        has_company = (
            company_name
            and company_name.lower() in body_lower
        )
        if not has_prospect and not has_company:
            issues.append(
                "Body doesn't mention prospect name or company name"
            )

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
