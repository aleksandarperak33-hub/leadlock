"""
Follow-Up Agent — generates nurture and reminder messages.
Max 3 cold outreach messages per lead, ever. Compliance checked before every send.
"""
import logging
from typing import Optional
from src.utils.templates import render_template
from src.schemas.agent_responses import FollowupResponse

logger = logging.getLogger(__name__)


async def process_followup(
    lead_first_name: Optional[str],
    service_type: Optional[str],
    business_name: str,
    rep_name: str,
    followup_type: str,
    sequence_number: int,
    appointment_date: Optional[str] = None,
    time_window: Optional[str] = None,
    tech_name: Optional[str] = None,
) -> FollowupResponse:
    """
    Generate a follow-up message based on type and sequence.
    Template-based for consistency and compliance.

    Types:
    - cold_nurture: Re-engage a cold lead (max 3 messages)
    - day_before_reminder: Appointment reminder
    - review_request: Post-service review ask
    """
    display_name = lead_first_name or "there"
    display_service = service_type or "your service request"

    if followup_type == "cold_nurture":
        template_key = f"cold_nurture_{min(sequence_number, 3)}"
        message = render_template(
            template_key=template_key,
            category="followup",
            first_name=display_name,
            business_name=business_name,
            rep_name=rep_name,
            service_type=display_service,
        )

        # Stop after 3rd message
        should_stop = sequence_number >= 3

        return FollowupResponse(
            message=message,
            followup_type="cold_nurture",
            sequence_number=sequence_number,
            internal_notes=f"Cold nurture #{sequence_number}" + (" — FINAL" if should_stop else ""),
            should_stop_sequence=should_stop,
        )

    elif followup_type == "day_before_reminder":
        message = render_template(
            template_key="day_before_reminder",
            category="followup",
            first_name=display_name,
            business_name=business_name,
            service_type=display_service,
            date=appointment_date or "tomorrow",
            time_window=time_window or "your scheduled time",
            tech_name=tech_name or "our technician",
        )

        return FollowupResponse(
            message=message,
            followup_type="day_before_reminder",
            sequence_number=1,
            internal_notes="Day-before appointment reminder",
        )

    elif followup_type == "review_request":
        message = render_template(
            template_key="review_request",
            category="followup",
            first_name=display_name,
            business_name=business_name,
            service_type=display_service,
        )

        return FollowupResponse(
            message=message,
            followup_type="review_request",
            sequence_number=1,
            internal_notes="Post-service review request",
        )

    else:
        logger.warning("Unknown followup type: %s", followup_type)
        return FollowupResponse(
            message=f"Hi {display_name}, just checking in from {business_name}. How can we help?",
            followup_type=followup_type,
            sequence_number=sequence_number,
            internal_notes=f"Unknown type fallback: {followup_type}",
        )
