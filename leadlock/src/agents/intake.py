"""
Intake Agent - first response to every new lead.
TEMPLATE-BASED ONLY. No free-form AI on the first message.
Must respond in <2 seconds. Uses pre-built templates for speed and compliance.

Why template-based:
1. Speed - templates render in microseconds, AI takes 1-3 seconds
2. Compliance - templates are pre-approved, guaranteed to include STOP language
3. Consistency - every first message follows the same pattern
4. Cost - zero AI cost for the first message
"""
import logging
from typing import Optional
from src.utils.templates import render_template
from src.utils.emergency import detect_emergency
from src.schemas.agent_responses import IntakeResponse

logger = logging.getLogger(__name__)


async def process_intake(
    first_name: Optional[str],
    service_type: Optional[str],
    source: str,
    business_name: str,
    rep_name: str,
    message_text: Optional[str] = None,
    is_after_hours: bool = False,
    custom_emergency_keywords: Optional[list[str]] = None,
) -> IntakeResponse:
    """
    Generate the first response to a new lead using templates.
    No AI involved - pure template selection and rendering.

    Template selection logic:
    1. If emergency detected → emergency template
    2. If after hours → after_hours template
    3. If missed call → missed_call template
    4. If text-in (no context) → text_in template
    5. Default → standard template
    """
    # Default values for missing info
    display_name = first_name or "there"
    display_service = service_type or "your request"

    # Check for emergency
    emergency_result = {"is_emergency": False, "severity": None, "emergency_type": None}
    if message_text:
        emergency_result = detect_emergency(message_text, custom_emergency_keywords)

    # Select template
    if emergency_result["is_emergency"]:
        template_key = "emergency"
        logger.warning(
            "EMERGENCY intake: %s (%s)",
            emergency_result["emergency_type"],
            emergency_result["severity"],
        )
    elif is_after_hours:
        template_key = "after_hours"
    elif source == "missed_call":
        template_key = "missed_call"
    elif source == "text_in" and not service_type:
        template_key = "text_in"
    else:
        template_key = "standard"

    # Render template
    message = render_template(
        template_key=template_key,
        category="intake",
        first_name=display_name,
        rep_name=rep_name,
        business_name=business_name,
        service_type=display_service,
    )

    return IntakeResponse(
        message=message,
        template_id=f"intake_{template_key}",
        is_emergency=emergency_result["is_emergency"],
        emergency_type=emergency_result.get("emergency_type"),
        internal_notes=f"Template: {template_key}, Source: {source}",
    )
