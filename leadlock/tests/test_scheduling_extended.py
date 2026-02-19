"""
Extended tests for src/services/scheduling.py — covers TimeSlot repr,
Saturday hours, existing bookings deduction, and overflow break.
"""
import pytest
from datetime import date, time, datetime

from src.services.scheduling import TimeSlot, generate_available_slots


# ---------------------------------------------------------------------------
# TimeSlot.__repr__ (line 22)
# ---------------------------------------------------------------------------

class TestTimeSlotRepr:
    """Cover TimeSlot.__repr__ for line 22."""

    def test_repr_format(self):
        slot = TimeSlot(date(2026, 2, 18), time(9, 0), time(11, 0), "Mike")
        r = repr(slot)
        assert "TimeSlot" in r
        assert "2026-02-18" in r
        assert "09:00:00" in r
        assert "11:00:00" in r
        assert "Mike" in r

    def test_repr_without_tech(self):
        slot = TimeSlot(date(2026, 2, 18), time(9, 0), time(11, 0))
        r = repr(slot)
        assert "None" in r


# ---------------------------------------------------------------------------
# Saturday hours (lines 61-65)
# ---------------------------------------------------------------------------

class TestSaturdayHours:
    """Cover Saturday-specific business hours."""

    def test_saturday_with_configured_hours(self):
        """Saturday with custom hours generates slots within those hours (lines 61-63)."""
        # Feb 21, 2026 is a Saturday
        slots = generate_available_slots(
            start_date=date(2026, 2, 21),
            days_ahead=1,
            saturday_hours={"start": "08:00", "end": "14:00"},
            slot_duration_minutes=120,
        )
        assert len(slots) > 0
        for slot in slots:
            assert slot.date == date(2026, 2, 21)
            assert slot.start >= time(8, 0)
            assert slot.end <= time(14, 0)

    def test_saturday_with_partial_saturday_hours(self):
        """Saturday hours uses .get defaults when keys are missing (line 62 defaults)."""
        # Only provide "start" — "end" should default to "14:00"
        slots = generate_available_slots(
            start_date=date(2026, 2, 21),
            days_ahead=1,
            saturday_hours={"start": "09:00"},
            slot_duration_minutes=120,
        )
        assert len(slots) > 0
        for slot in slots:
            assert slot.start >= time(9, 0)
            assert slot.end <= time(14, 0)  # Default end

    def test_saturday_skipped_without_hours(self):
        """Saturday with no saturday_hours configured is skipped (line 65)."""
        slots = generate_available_slots(
            start_date=date(2026, 2, 21),
            days_ahead=1,
            saturday_hours=None,
        )
        assert len(slots) == 0


# ---------------------------------------------------------------------------
# Existing bookings deduction (lines 73-76)
# ---------------------------------------------------------------------------

class TestExistingBookingsDeduction:
    """Cover existing bookings counting logic."""

    def test_existing_bookings_reduce_available_slots(self):
        """Existing bookings deduct from max_daily_bookings (lines 73-76)."""
        existing = [
            {"date": date(2026, 2, 16), "tech": "Mike"},
            {"date": date(2026, 2, 16), "tech": "Carlos"},
        ]
        slots_with = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            max_daily_bookings=4,
            existing_bookings=existing,
        )
        slots_without = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            max_daily_bookings=4,
            existing_bookings=None,
        )
        assert len(slots_with) < len(slots_without)
        assert len(slots_with) == len(slots_without) - 2

    def test_existing_bookings_with_datetime_field(self):
        """Existing bookings with appointment_date (datetime) key (line 74-75)."""
        existing = [
            {"appointment_date": datetime(2026, 2, 16, 9, 0)},
        ]
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            max_daily_bookings=4,
            existing_bookings=existing,
        )
        # Should have 3 slots (4 max - 1 existing)
        assert len(slots) == 3

    def test_existing_bookings_on_different_day_ignored(self):
        """Bookings on a different day do not affect current day's slots."""
        existing = [
            {"date": date(2026, 2, 17)},
        ]
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            max_daily_bookings=4,
            existing_bookings=existing,
        )
        assert len(slots) == 4

    def test_max_bookings_reached_by_existing(self):
        """When existing bookings fill max_daily_bookings, no slots generated."""
        existing = [
            {"date": date(2026, 2, 16)} for _ in range(4)
        ]
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            max_daily_bookings=4,
            existing_bookings=existing,
        )
        assert len(slots) == 0


# ---------------------------------------------------------------------------
# Overflow break: next_minutes >= 24 * 60 (line 104-105)
# ---------------------------------------------------------------------------

class TestSlotOverflow:
    """Cover the 24-hour overflow break."""

    def test_slots_do_not_overflow_past_midnight(self):
        """Slots stop before exceeding 24 hours (lines 104-105)."""
        # Use late business hours with a long slot duration to force overflow
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            business_hours_start="22:00",
            business_hours_end="23:59",
            slot_duration_minutes=60,
            buffer_minutes=60,
            max_daily_bookings=10,
        )
        # With 22:00-23:59, one 60-min slot (22:00-23:00) fits.
        # Next slot would start at 24:00 (23:00 + 60 buffer) which triggers the break.
        assert len(slots) == 1
        assert slots[0].start == time(22, 0)
        assert slots[0].end == time(23, 0)


# ---------------------------------------------------------------------------
# Inactive techs filtered (line 94)
# ---------------------------------------------------------------------------

class TestInactiveTechsFiltered:
    """Cover the active tech filtering."""

    def test_inactive_techs_not_assigned(self):
        """Only active techs are assigned to slots (line 94)."""
        team = [
            {"name": "Mike", "active": True},
            {"name": "Carlos", "active": False},
            {"name": "Sarah", "active": True},
        ]
        slots = generate_available_slots(
            start_date=date(2026, 2, 16),
            days_ahead=1,
            team_members=team,
            max_daily_bookings=4,
        )
        tech_names = {s.tech_name for s in slots}
        assert "Carlos" not in tech_names
        assert "Mike" in tech_names
        assert "Sarah" in tech_names
