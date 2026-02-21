"""
Scheduling service - appointment slot management.
Works with CRM availability data to find open slots.
"""
import logging
from datetime import datetime, date, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TimeSlot:
    """Represents an available appointment time slot."""

    def __init__(self, slot_date: date, start: time, end: time, tech_name: Optional[str] = None):
        self.date = slot_date
        self.start = start
        self.end = end
        self.tech_name = tech_name

    def __repr__(self) -> str:
        return f"<TimeSlot {self.date} {self.start}-{self.end} tech={self.tech_name}>"

    def to_display(self) -> str:
        """Human-readable time window string."""
        start_str = self.start.strftime("%-I:%M %p")
        end_str = self.end.strftime("%-I:%M %p")
        return f"{start_str} - {end_str}"


def generate_available_slots(
    start_date: date,
    days_ahead: int = 14,
    business_hours_start: str = "07:00",
    business_hours_end: str = "18:00",
    slot_duration_minutes: int = 120,
    buffer_minutes: int = 30,
    max_daily_bookings: int = 8,
    existing_bookings: Optional[list] = None,
    team_members: Optional[list] = None,
    saturday_hours: Optional[dict] = None,
) -> list[TimeSlot]:
    """
    Generate available appointment slots for the next N days.
    Accounts for business hours, slot duration, buffer time, and existing bookings.
    """
    slots = []
    bh_start = _parse_time(business_hours_start)
    bh_end = _parse_time(business_hours_end)

    for day_offset in range(days_ahead):
        current_date = start_date + timedelta(days=day_offset)
        weekday = current_date.weekday()

        # Skip Sunday by default
        if weekday == 6:
            continue

        # Saturday hours
        if weekday == 5:
            if saturday_hours:
                day_start = _parse_time(saturday_hours.get("start", "08:00"))
                day_end = _parse_time(saturday_hours.get("end", "14:00"))
            else:
                continue  # Skip Saturday if no hours configured
        else:
            day_start = bh_start
            day_end = bh_end

        # Count existing bookings for this day to deduct from max
        existing_count = 0
        if existing_bookings:
            for b in existing_bookings:
                b_date = b.get("date") or b.get("appointment_date")
                if b_date == current_date or (hasattr(b_date, "date") and b_date.date() == current_date):
                    existing_count += 1

        # Generate time slots for this day
        current_time = day_start
        daily_count = existing_count  # Start counting from existing bookings

        while daily_count < max_daily_bookings:
            slot_end_minutes = (
                current_time.hour * 60 + current_time.minute + slot_duration_minutes
            )
            if slot_end_minutes > day_end.hour * 60 + day_end.minute:
                break

            slot_end = time(slot_end_minutes // 60, slot_end_minutes % 60)

            # Assign tech if available
            tech_name = None
            if team_members:
                active_techs = [t for t in team_members if t.get("active", True)]
                if active_techs:
                    tech_idx = daily_count % len(active_techs)
                    tech_name = active_techs[tech_idx].get("name")

            slots.append(TimeSlot(current_date, current_time, slot_end, tech_name))
            daily_count += 1

            # Advance by slot duration + buffer
            next_minutes = slot_end_minutes + buffer_minutes
            if next_minutes >= 24 * 60:
                break
            current_time = time(next_minutes // 60, next_minutes % 60)

    return slots


def _parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))
