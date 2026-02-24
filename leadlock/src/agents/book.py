"""
Book Agent - appointment scheduling with CRM availability.
Uses Claude Haiku for speed. Confirms appointments and records bookings.
"""
import json
import logging
from datetime import date, time, timedelta
from typing import Optional
from src.services.ai import generate_response
from src.services.scheduling import generate_available_slots
from src.schemas.agent_responses import BookResponse
from src.prompts.humanizer import SMS_HUMANIZER

logger = logging.getLogger(__name__)


def _escape_braces(text: str) -> str:
    """Escape { and } in user-controlled text to prevent .format() injection."""
    return text.replace("{", "{{").replace("}", "}}")

BOOK_SYSTEM_PROMPT = """You are {rep_name}, scheduling an appointment for {business_name}.

The customer needs: {service_type}
Customer name: {first_name}
Preferred date/time: {preferred_date}

CONVERSATION HISTORY:
{conversation_history}

AVAILABLE SLOTS:
{available_slots}

RULES:
- Offer the closest available slot to their preferred time.
- If their preferred time isn't available, suggest 2-3 alternatives.
- Keep messages SHORT - this is SMS.
- Once they confirm, set booking_confirmed to true.
- If they need a time we don't have, set needs_human_handoff to true.
- Include the technician name if assigned.
- Use context from the conversation history - don't re-ask things the customer already told you.

""" + SMS_HUMANIZER + """

Respond with JSON:
{{
    "message": "Your SMS response",
    "appointment_date": "YYYY-MM-DD or null",
    "time_window_start": "HH:MM or null",
    "time_window_end": "HH:MM or null",
    "tech_name": "string or null",
    "booking_confirmed": false,
    "needs_human_handoff": false,
    "internal_notes": ""
}}"""


async def process_booking(
    lead_message: str,
    first_name: str,
    service_type: str,
    preferred_date: Optional[str],
    business_name: str,
    rep_name: str,
    scheduling_config: dict,
    team_members: list,
    hours_config: dict,
    conversation_history: list[dict],
) -> BookResponse:
    """
    Process a booking request. Generates available slots and uses AI to
    negotiate the appointment with the lead.
    """
    # Generate available slots
    saturday_hours = None
    sat_config = hours_config.get("saturday")
    if sat_config:
        saturday_hours = {"start": sat_config.get("start", "08:00"), "end": sat_config.get("end", "14:00")}

    slots = generate_available_slots(
        start_date=date.today(),
        days_ahead=scheduling_config.get("advance_booking_days", 14),
        business_hours_start=hours_config.get("business", {}).get("start", "07:00"),
        business_hours_end=hours_config.get("business", {}).get("end", "18:00"),
        slot_duration_minutes=scheduling_config.get("slot_duration_minutes", 120),
        buffer_minutes=scheduling_config.get("buffer_minutes", 30),
        max_daily_bookings=scheduling_config.get("max_daily_bookings", 8),
        team_members=team_members,
        saturday_hours=saturday_hours,
    )

    # Format slots for the prompt (show next 10)
    slots_text = ""
    for slot in slots[:10]:
        tech = f" (Tech: {slot.tech_name})" if slot.tech_name else ""
        slots_text += f"- {slot.date.strftime('%A, %B %d')} from {slot.to_display()}{tech}\n"

    if not slots_text:
        slots_text = "No available slots found in the next 14 days."

    # Format conversation history for the prompt (last 8 messages)
    # Escape braces in user-controlled content to prevent .format() injection
    history_text = ""
    for msg in conversation_history[-8:]:
        direction = "Customer" if msg.get("direction") == "inbound" else _escape_braces(rep_name)
        history_text += f"{direction}: {_escape_braces(msg.get('content', ''))}\n"

    # Build prompt - escape all user-controlled fields
    system = BOOK_SYSTEM_PROMPT.format(
        rep_name=_escape_braces(rep_name),
        business_name=_escape_braces(business_name),
        service_type=_escape_braces(service_type or "service"),
        first_name=_escape_braces(first_name or "there"),
        preferred_date=_escape_braces(preferred_date or "not specified"),
        available_slots=_escape_braces(slots_text),
        conversation_history=history_text or "No prior conversation.",
    )

    # Generate response
    result = await generate_response(
        system_prompt=system,
        user_message=f"Customer: {lead_message}",
        model_tier="fast",
        temperature=0.2,
    )

    if result.get("error"):
        logger.error("Book agent AI failed: %s", result["error"])
        fallback = _fallback_booking(slots)
        fallback.ai_cost_usd = 0.0
        fallback.ai_latency_ms = 0
        return fallback

    ai_cost = result.get("cost_usd", 0.0)
    ai_latency = result.get("latency_ms", 0)

    # Parse response - strip markdown fences if present
    raw = result["content"].strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw)
        response = BookResponse(
            message=parsed["message"],
            appointment_date=parsed.get("appointment_date"),
            time_window_start=parsed.get("time_window_start"),
            time_window_end=parsed.get("time_window_end"),
            tech_name=parsed.get("tech_name"),
            booking_confirmed=parsed.get("booking_confirmed", False),
            needs_human_handoff=parsed.get("needs_human_handoff", False),
            internal_notes=parsed.get("internal_notes", ""),
        )
        response.ai_cost_usd = ai_cost
        response.ai_latency_ms = ai_latency
        return response
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse book response: %s", str(e))
        response = BookResponse(
            message=result["content"][:300] if result["content"] else _fallback_booking(slots).message,
            internal_notes=f"Parse error: {str(e)}",
        )
        response.ai_cost_usd = ai_cost
        response.ai_latency_ms = ai_latency
        return response


def _fallback_booking(slots: list) -> BookResponse:
    """Fallback when AI fails - offer the first available slot."""
    if slots:
        slot = slots[0]
        tech_text = f" with {slot.tech_name}" if slot.tech_name else ""
        msg = (
            f"I'd love to get you scheduled! Our next available time is "
            f"{slot.date.strftime('%A, %B %d')} from {slot.to_display()}{tech_text}. "
            f"Does that work for you?"
        )
        return BookResponse(
            message=msg,
            appointment_date=str(slot.date),
            time_window_start=slot.start.strftime("%H:%M"),
            time_window_end=slot.end.strftime("%H:%M"),
            tech_name=slot.tech_name,
            internal_notes="AI fallback - offered first available slot",
        )

    return BookResponse(
        message="Let me check our schedule and get back to you with available times. One moment!",
        needs_human_handoff=True,
        internal_notes="AI fallback - no slots available",
    )
