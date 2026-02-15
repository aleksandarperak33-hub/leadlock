"""
Agent tests — test agent responses and fallback behavior.
"""
import pytest
from unittest.mock import patch, AsyncMock
from src.agents.intake import process_intake
from src.agents.followup import process_followup


class TestIntakeAgent:
    @pytest.mark.asyncio
    async def test_standard_intake(self):
        """Standard intake should use template with STOP language."""
        result = await process_intake(
            first_name="John",
            service_type="AC Repair",
            source="website",
            business_name="Austin HVAC",
            rep_name="Sarah",
        )
        assert "Austin HVAC" in result.message
        assert "STOP" in result.message
        assert result.is_emergency is False
        assert "intake_standard" in result.template_id

    @pytest.mark.asyncio
    async def test_missed_call_intake(self):
        """Missed call source should use missed_call template."""
        result = await process_intake(
            first_name="Jane",
            service_type=None,
            source="missed_call",
            business_name="Austin HVAC",
            rep_name="Sarah",
        )
        assert "missed" in result.message.lower() or "call" in result.message.lower()
        assert "STOP" in result.message
        assert "intake_missed_call" in result.template_id

    @pytest.mark.asyncio
    async def test_emergency_intake(self):
        """Emergency message should flag as emergency."""
        result = await process_intake(
            first_name="Bob",
            service_type="Heating",
            source="website",
            business_name="Austin HVAC",
            rep_name="Sarah",
            message_text="We have a gas leak in the house!",
        )
        assert result.is_emergency is True
        assert result.emergency_type == "gas_or_co"
        assert "intake_emergency" in result.template_id

    @pytest.mark.asyncio
    async def test_text_in_intake(self):
        """Text-in without service type uses text_in template."""
        result = await process_intake(
            first_name=None,
            service_type=None,
            source="text_in",
            business_name="Austin HVAC",
            rep_name="Sarah",
        )
        assert "STOP" in result.message
        assert "intake_text_in" in result.template_id

    @pytest.mark.asyncio
    async def test_after_hours_intake(self):
        """After hours should use after_hours template."""
        result = await process_intake(
            first_name="John",
            service_type="AC Repair",
            source="website",
            business_name="Austin HVAC",
            rep_name="Sarah",
            is_after_hours=True,
        )
        assert "intake_after_hours" in result.template_id

    @pytest.mark.asyncio
    async def test_intake_always_has_business_name(self):
        """Every intake message must include the business name."""
        result = await process_intake(
            first_name="Test",
            service_type="Plumbing",
            source="website",
            business_name="Reliable Plumbing",
            rep_name="Tom",
        )
        assert "Reliable Plumbing" in result.message


class TestFollowupAgent:
    @pytest.mark.asyncio
    async def test_cold_nurture_1(self):
        result = await process_followup(
            lead_first_name="John",
            service_type="AC Repair",
            business_name="Austin HVAC",
            rep_name="Sarah",
            followup_type="cold_nurture",
            sequence_number=1,
        )
        assert "Austin HVAC" in result.message
        assert result.should_stop_sequence is False

    @pytest.mark.asyncio
    async def test_cold_nurture_3_stops(self):
        """3rd cold nurture should set should_stop_sequence=True."""
        result = await process_followup(
            lead_first_name="John",
            service_type="AC Repair",
            business_name="Austin HVAC",
            rep_name="Sarah",
            followup_type="cold_nurture",
            sequence_number=3,
        )
        assert result.should_stop_sequence is True

    @pytest.mark.asyncio
    async def test_day_before_reminder(self):
        result = await process_followup(
            lead_first_name="John",
            service_type="AC Repair",
            business_name="Austin HVAC",
            rep_name="Sarah",
            followup_type="day_before_reminder",
            sequence_number=1,
            appointment_date="Monday, February 16",
            time_window="8:00 AM - 10:00 AM",
        )
        assert "tomorrow" in result.message.lower() or "Monday" in result.message or "reminder" in result.message.lower()

    @pytest.mark.asyncio
    async def test_review_request(self):
        result = await process_followup(
            lead_first_name="John",
            service_type="AC Repair",
            business_name="Austin HVAC",
            rep_name="Sarah",
            followup_type="review_request",
            sequence_number=1,
        )
        assert "review" in result.message.lower() or "feedback" in result.message.lower()
