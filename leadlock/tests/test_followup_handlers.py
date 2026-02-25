"""
Tests for the 4 new followup agent handlers:
  - booking_escalation
  - same_day_reminder
  - no_show_recovery
  - review_request_with_link

Also tests unknown-type fallback and missing optional params.
"""
import pytest

from src.agents.followup import process_followup
from src.schemas.agent_responses import FollowupResponse


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

COMMON_KWARGS = {
    "lead_first_name": "John",
    "service_type": "AC Repair",
    "business_name": "Cool Air HVAC",
    "rep_name": "Sarah",
    "sequence_number": 1,
}


# ---------------------------------------------------------------------------
# booking_escalation
# ---------------------------------------------------------------------------


class TestBookingEscalation:
    """Tests for followup_type='booking_escalation'."""

    @pytest.mark.asyncio
    async def test_returns_followup_response_with_booking_url(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="booking_escalation",
            booking_url="https://calendly.com/cool-air",
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "booking_escalation"
        assert len(result.message) > 0
        assert "calendly.com/cool-air" in result.message

    @pytest.mark.asyncio
    async def test_internal_notes_reference_booking(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="booking_escalation",
            booking_url="https://calendly.com/cool-air",
        )

        assert "booking" in result.internal_notes.lower()
        assert "escalation" in result.internal_notes.lower()

    @pytest.mark.asyncio
    async def test_sequence_number_is_one(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="booking_escalation",
            booking_url="https://calendly.com/cool-air",
        )

        assert result.sequence_number == 1

    @pytest.mark.asyncio
    async def test_should_not_stop_sequence(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="booking_escalation",
            booking_url="https://calendly.com/cool-air",
        )

        assert result.should_stop_sequence is False

    @pytest.mark.asyncio
    async def test_booking_url_none_falls_back_to_business_name(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="booking_escalation",
            booking_url=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "booking_escalation"
        assert len(result.message) > 0
        # When booking_url is None, the fallback is business_name
        assert "Cool Air HVAC" in result.message


# ---------------------------------------------------------------------------
# same_day_reminder
# ---------------------------------------------------------------------------


class TestSameDayReminder:
    """Tests for followup_type='same_day_reminder'."""

    @pytest.mark.asyncio
    async def test_returns_followup_response_with_time_window(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="same_day_reminder",
            time_window="2-4 PM",
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "same_day_reminder"
        assert len(result.message) > 0
        assert "2-4 PM" in result.message

    @pytest.mark.asyncio
    async def test_internal_notes_reference_same_day(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="same_day_reminder",
            time_window="2-4 PM",
        )

        assert "same-day" in result.internal_notes.lower() or "same_day" in result.internal_notes.lower()

    @pytest.mark.asyncio
    async def test_message_contains_service_type(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="same_day_reminder",
            time_window="10 AM - 12 PM",
        )

        assert "AC Repair" in result.message

    @pytest.mark.asyncio
    async def test_time_window_none_uses_fallback(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="same_day_reminder",
            time_window=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "same_day_reminder"
        assert len(result.message) > 0
        assert "your scheduled time" in result.message

    @pytest.mark.asyncio
    async def test_sequence_number_is_one(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="same_day_reminder",
        )

        assert result.sequence_number == 1


# ---------------------------------------------------------------------------
# no_show_recovery
# ---------------------------------------------------------------------------


class TestNoShowRecovery:
    """Tests for followup_type='no_show_recovery'."""

    @pytest.mark.asyncio
    async def test_returns_followup_response_with_booking_url(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="no_show_recovery",
            booking_url="https://calendly.com/cool-air/reschedule",
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "no_show_recovery"
        assert len(result.message) > 0
        assert "calendly.com/cool-air/reschedule" in result.message

    @pytest.mark.asyncio
    async def test_internal_notes_reference_no_show(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="no_show_recovery",
            booking_url="https://calendly.com/cool-air/reschedule",
        )

        assert "no-show" in result.internal_notes.lower() or "no_show" in result.internal_notes.lower()

    @pytest.mark.asyncio
    async def test_message_includes_lead_name(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="no_show_recovery",
            booking_url="https://calendly.com/cool-air",
        )

        assert "John" in result.message

    @pytest.mark.asyncio
    async def test_booking_url_none_falls_back_to_business_name(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="no_show_recovery",
            booking_url=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "no_show_recovery"
        assert len(result.message) > 0
        # Fallback: booking_url replaced by business_name
        assert "Cool Air HVAC" in result.message

    @pytest.mark.asyncio
    async def test_should_not_stop_sequence(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="no_show_recovery",
            booking_url="https://calendly.com/cool-air",
        )

        assert result.should_stop_sequence is False


# ---------------------------------------------------------------------------
# review_request_with_link
# ---------------------------------------------------------------------------


class TestReviewRequestWithLink:
    """Tests for followup_type='review_request_with_link'."""

    @pytest.mark.asyncio
    async def test_returns_followup_response_with_review_url(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="review_request_with_link",
            review_url="https://g.page/cool-air-hvac/review",
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "review_request_with_link"
        assert len(result.message) > 0
        assert "g.page/cool-air-hvac/review" in result.message

    @pytest.mark.asyncio
    async def test_internal_notes_reference_review(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="review_request_with_link",
            review_url="https://g.page/cool-air-hvac/review",
        )

        assert "review" in result.internal_notes.lower()
        assert "link" in result.internal_notes.lower()

    @pytest.mark.asyncio
    async def test_message_includes_service_type(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="review_request_with_link",
            review_url="https://g.page/cool-air-hvac/review",
        )

        assert "AC Repair" in result.message

    @pytest.mark.asyncio
    async def test_review_url_none_does_not_crash(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="review_request_with_link",
            review_url=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "review_request_with_link"
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_sequence_number_is_one(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="review_request_with_link",
            review_url="https://g.page/cool-air-hvac/review",
        )

        assert result.sequence_number == 1


# ---------------------------------------------------------------------------
# Unknown followup_type fallback
# ---------------------------------------------------------------------------


class TestUnknownFollowupType:
    """Tests that an unrecognized followup_type returns a safe fallback."""

    @pytest.mark.asyncio
    async def test_unknown_type_returns_followup_response(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="nonexistent_type",
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "nonexistent_type"
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_unknown_type_internal_notes_mention_fallback(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="totally_made_up",
        )

        assert "fallback" in result.internal_notes.lower() or "unknown" in result.internal_notes.lower()

    @pytest.mark.asyncio
    async def test_unknown_type_preserves_sequence_number(self) -> None:
        result = await process_followup(
            lead_first_name="John",
            service_type="AC Repair",
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="bogus",
            sequence_number=5,
        )

        assert result.sequence_number == 5

    @pytest.mark.asyncio
    async def test_unknown_type_message_includes_lead_name(self) -> None:
        result = await process_followup(
            **COMMON_KWARGS,
            followup_type="bogus",
        )

        assert "John" in result.message


# ---------------------------------------------------------------------------
# Missing optional params
# ---------------------------------------------------------------------------


class TestMissingOptionalParams:
    """Tests that None values for optional params do not cause crashes."""

    @pytest.mark.asyncio
    async def test_booking_escalation_all_optionals_none(self) -> None:
        result = await process_followup(
            lead_first_name=None,
            service_type=None,
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="booking_escalation",
            sequence_number=1,
            booking_url=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "booking_escalation"
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_same_day_reminder_all_optionals_none(self) -> None:
        result = await process_followup(
            lead_first_name=None,
            service_type=None,
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="same_day_reminder",
            sequence_number=1,
            time_window=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "same_day_reminder"
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_no_show_recovery_all_optionals_none(self) -> None:
        result = await process_followup(
            lead_first_name=None,
            service_type=None,
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="no_show_recovery",
            sequence_number=1,
            booking_url=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "no_show_recovery"
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_review_request_with_link_all_optionals_none(self) -> None:
        result = await process_followup(
            lead_first_name=None,
            service_type=None,
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="review_request_with_link",
            sequence_number=1,
            review_url=None,
        )

        assert isinstance(result, FollowupResponse)
        assert result.followup_type == "review_request_with_link"
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_none_first_name_uses_fallback_display_name(self) -> None:
        result = await process_followup(
            lead_first_name=None,
            service_type="Plumbing",
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="booking_escalation",
            sequence_number=1,
            booking_url="https://calendly.com/cool-air",
        )

        assert isinstance(result, FollowupResponse)
        # "there" is the fallback for a None first name
        assert "there" in result.message

    @pytest.mark.asyncio
    async def test_none_service_type_uses_fallback_display_service(self) -> None:
        result = await process_followup(
            lead_first_name="John",
            service_type=None,
            business_name="Cool Air HVAC",
            rep_name="Sarah",
            followup_type="same_day_reminder",
            sequence_number=1,
            time_window="2-4 PM",
        )

        assert isinstance(result, FollowupResponse)
        # "your service request" is the fallback for a None service_type
        assert "your service request" in result.message
