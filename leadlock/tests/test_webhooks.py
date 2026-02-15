"""
Webhook endpoint tests.
"""
import pytest
import uuid
from unittest.mock import patch, AsyncMock


class TestWebFormWebhook:
    """Test the website form webhook."""

    @pytest.mark.asyncio
    async def test_valid_form_submission(self):
        """Valid form submission should create a lead."""
        from src.schemas.webhook_payloads import WebFormPayload
        payload = WebFormPayload(
            name="John Smith",
            phone="+15125559876",
            email="john@example.com",
            service="AC Repair",
            message="AC stopped working",
            zip="78701",
        )
        assert payload.phone == "+15125559876"
        assert payload.service == "AC Repair"

    def test_form_payload_without_name(self):
        """Form can have first/last name instead of single name field."""
        from src.schemas.webhook_payloads import WebFormPayload
        payload = WebFormPayload(
            first_name="John",
            last_name="Smith",
            phone="5125559876",
        )
        assert payload.first_name == "John"
        assert payload.last_name == "Smith"


class TestTwilioSmsPayload:
    def test_valid_twilio_payload(self):
        from src.schemas.webhook_payloads import TwilioSmsPayload
        payload = TwilioSmsPayload(
            MessageSid="SM123",
            AccountSid="AC123",
            From="+15125559876",
            To="+15125551234",
            Body="I need AC repair",
        )
        assert payload.Body == "I need AC repair"
        assert payload.From == "+15125559876"


class TestGoogleLsaPayload:
    def test_valid_lsa_payload(self):
        from src.schemas.webhook_payloads import GoogleLsaPayload
        payload = GoogleLsaPayload(
            lead_id="lsa_123",
            customer_name="Jane Doe",
            phone_number="+15125559876",
            job_type="hvac_repair",
            postal_code="78701",
        )
        assert payload.lead_id == "lsa_123"
        assert payload.job_type == "hvac_repair"


class TestAngiPayload:
    def test_valid_angi_payload(self):
        from src.schemas.webhook_payloads import AngiPayload
        payload = AngiPayload(
            leadId="angi_456",
            firstName="Bob",
            lastName="Builder",
            phone="+15125559876",
            serviceDescription="Plumbing repair",
            zipCode="78702",
        )
        assert payload.leadId == "angi_456"


class TestMissedCallPayload:
    def test_valid_missed_call(self):
        from src.schemas.webhook_payloads import MissedCallPayload
        payload = MissedCallPayload(
            caller_phone="+15125559876",
            called_phone="+15125551234",
            call_duration=0,
            caller_name="Unknown Caller",
        )
        assert payload.caller_phone == "+15125559876"


class TestTwilioStatusPayload:
    def test_delivery_status(self):
        from src.schemas.webhook_payloads import TwilioStatusPayload
        payload = TwilioStatusPayload(
            MessageSid="SM123",
            MessageStatus="delivered",
        )
        assert payload.MessageStatus == "delivered"

    def test_failed_status(self):
        from src.schemas.webhook_payloads import TwilioStatusPayload
        payload = TwilioStatusPayload(
            MessageSid="SM123",
            MessageStatus="failed",
            ErrorCode="30003",
            ErrorMessage="Unreachable destination handset",
        )
        assert payload.ErrorCode == "30003"
