"""
Tests for src/services/notifications.py — owner emergency and booking SMS alerts.
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.services.notifications import (
    notify_owner_emergency,
    notify_owner_booking,
)


# ---------------------------------------------------------------------------
# notify_owner_emergency
# ---------------------------------------------------------------------------

class TestNotifyOwnerEmergency:
    @pytest.mark.asyncio
    async def test_sends_sms_returns_true(self):
        """Successful emergency SMS returns True."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = {"error": None, "sid": "SM_test"}

            result = await notify_owner_emergency(
                owner_phone="+15121234567",
                business_name="HVAC Pro",
                lead_phone="+15129876543",
                emergency_type="gas_leak",
                message_preview="I smell gas in my basement",
            )

        assert result is True
        mock_sms.assert_awaited_once()

        # Verify the SMS body includes key fields
        call_kwargs = mock_sms.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body", "")
        assert "EMERGENCY ALERT" in body
        assert "HVAC Pro" in body
        assert "gas_leak" in body

    @pytest.mark.asyncio
    async def test_sms_error_returns_false(self):
        """When send_sms returns an error, notify returns False."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = {"error": "Twilio error 30007"}

            result = await notify_owner_emergency(
                owner_phone="+15121234567",
                business_name="HVAC Pro",
                lead_phone="+15129876543",
                emergency_type="no_heat",
                message_preview="Our heater stopped working",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_sms_exception_returns_false(self):
        """When send_sms raises an exception, notify returns False."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.side_effect = Exception("Network timeout")

            result = await notify_owner_emergency(
                owner_phone="+15121234567",
                business_name="HVAC Pro",
                lead_phone="+15129876543",
                emergency_type="flooding",
                message_preview="Water everywhere",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_message_preview_truncated(self):
        """Long message previews are truncated to 100 chars in the alert."""
        long_message = "X" * 200

        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = {"error": None}

            await notify_owner_emergency(
                owner_phone="+15121234567",
                business_name="HVAC Pro",
                lead_phone="+15129876543",
                emergency_type="gas_leak",
                message_preview=long_message,
            )

        call_kwargs = mock_sms.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body", "")
        # The preview in the body is sliced to [:100]
        assert "X" * 100 in body
        assert "X" * 101 not in body

    @pytest.mark.asyncio
    async def test_lead_phone_is_masked(self):
        """Lead phone in the alert body should be masked."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = {"error": None}

            await notify_owner_emergency(
                owner_phone="+15121234567",
                business_name="HVAC Pro",
                lead_phone="+15129876543",
                emergency_type="gas_leak",
                message_preview="Help",
            )

        call_kwargs = mock_sms.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body", "")
        # The full lead phone should NOT appear in the body
        assert "+15129876543" not in body


# ---------------------------------------------------------------------------
# notify_owner_booking
# ---------------------------------------------------------------------------

class TestNotifyOwnerBooking:
    @pytest.mark.asyncio
    async def test_sends_formatted_booking_notification(self):
        """Booking notification includes customer name, service, date, time."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = {"error": None}

            result = await notify_owner_booking(
                owner_phone="+15121234567",
                business_name="HVAC Pro",
                lead_name="John Smith",
                service_type="AC Repair",
                appointment_date="2026-03-15",
                time_window="9:00 AM - 11:00 AM",
            )

        assert result is True
        mock_sms.assert_awaited_once()

        call_kwargs = mock_sms.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body", "")
        assert "New Booking" in body
        assert "HVAC Pro" in body
        assert "John Smith" in body
        assert "AC Repair" in body
        assert "2026-03-15" in body
        assert "9:00 AM - 11:00 AM" in body

    @pytest.mark.asyncio
    async def test_sms_error_returns_false(self):
        """When send_sms returns an error, booking notify returns False."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.return_value = {"error": "Delivery failed"}

            result = await notify_owner_booking(
                owner_phone="+15121234567",
                business_name="Plumbing Co",
                lead_name="Jane Doe",
                service_type="Leak Repair",
                appointment_date="2026-04-01",
                time_window="1:00 PM - 3:00 PM",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        """When send_sms raises, booking notify returns False."""
        with patch("src.services.notifications.send_sms", new_callable=AsyncMock) as mock_sms:
            mock_sms.side_effect = RuntimeError("Connection refused")

            result = await notify_owner_booking(
                owner_phone="+15121234567",
                business_name="Roofing LLC",
                lead_name="Bob",
                service_type="Roof Inspection",
                appointment_date="2026-05-01",
                time_window="10:00 AM - 12:00 PM",
            )

        assert result is False
