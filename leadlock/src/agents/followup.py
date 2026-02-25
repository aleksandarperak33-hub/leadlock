"""
Follow-Up Agent - generates nurture and reminder messages.
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
    booking_url: Optional[str] = None,
    review_url: Optional[str] = None,
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
            internal_notes=f"Cold nurture #{sequence_number}" + (" - FINAL" if should_stop else ""),
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

    elif followup_type == "booking_escalation":
        message = render_template(
            template_key="booking_escalation",
            category="booking_escalation",
            first_name=display_name,
            business_name=business_name,
            booking_url=booking_url or business_name,
        )

        return FollowupResponse(
            message=message,
            followup_type="booking_escalation",
            sequence_number=1,
            internal_notes="Booking escalation - lead stuck in booking state",
        )

    elif followup_type == "same_day_reminder":
        message = render_template(
            template_key="same_day_reminder",
            category="same_day_reminder",
            first_name=display_name,
            business_name=business_name,
            service_type=display_service,
            time_window=time_window or "your scheduled time",
        )

        return FollowupResponse(
            message=message,
            followup_type="same_day_reminder",
            sequence_number=1,
            internal_notes="Same-day appointment reminder (2h before)",
        )

    elif followup_type == "no_show_recovery":
        message = render_template(
            template_key="no_show_recovery",
            category="no_show_recovery",
            first_name=display_name,
            service_type=display_service,
            booking_url=booking_url or business_name,
        )

        return FollowupResponse(
            message=message,
            followup_type="no_show_recovery",
            sequence_number=1,
            internal_notes="No-show recovery message",
        )

    elif followup_type == "review_request_with_link":
        message = render_template(
            template_key="review_request_with_link",
            category="review_request_link",
            first_name=display_name,
            business_name=business_name,
            service_type=display_service,
            review_url=review_url or "",
        )

        return FollowupResponse(
            message=message,
            followup_type="review_request_with_link",
            sequence_number=1,
            internal_notes="Post-service review request with link",
        )

    else:
        logger.warning("Unknown followup type: %s", followup_type)
        return FollowupResponse(
            message=f"Hi {display_name}, just checking in from {business_name}. How can we help?",
            followup_type=followup_type,
            sequence_number=sequence_number,
            internal_notes=f"Unknown type fallback: {followup_type}",
        )
