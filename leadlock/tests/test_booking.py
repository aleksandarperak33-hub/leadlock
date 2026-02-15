"""
Booking and scheduling tests.
"""
import pytest
from datetime import date, time
from src.services.scheduling import generate_available_slots


class TestScheduling:
    def test_generates_slots(self):
        """Should generate available slots."""
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),  # Monday
            days_ahead=5,
        )
        assert len(slots) > 0

    def test_respects_business_hours(self):
        """All slots should be within business hours."""
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            business_hours_start="09:00",
            business_hours_end="17:00",
        )
        for slot in slots:
            assert slot.start >= time(9, 0)
            assert slot.end <= time(17, 0)

    def test_skips_sunday(self):
        """No slots should be on Sunday."""
        # Feb 15, 2026 is a Sunday
        slots = generate_available_slots(
            start_date=date(2026, 2, 15),
            days_ahead=1,
        )
        for slot in slots:
            assert slot.date.weekday() != 6

    def test_max_daily_bookings(self):
        """Should not exceed max daily bookings."""
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            max_daily_bookings=3,
        )
        # Count slots for the single day
        day_slots = [s for s in slots if s.date == date(2026, 2, 16)]
        assert len(day_slots) <= 3

    def test_assigns_techs_round_robin(self):
        """Techs should be assigned in round-robin fashion."""
        team = [
            {"name": "Mike", "active": True},
            {"name": "Carlos", "active": True},
        ]
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            team_members=team,
            max_daily_bookings=4,
        )
        if len(slots) >= 2:
            assert slots[0].tech_name == "Mike"
            assert slots[1].tech_name == "Carlos"

    def test_slot_display_format(self):
        """TimeSlot.to_display should return human-readable format."""
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
        )
        if slots:
            display = slots[0].to_display()
            assert "AM" in display or "PM" in display
