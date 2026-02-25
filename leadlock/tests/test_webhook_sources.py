"""
Tests for source-specific webhook payload parsers (webhook_sources.py).

Covers parse_yelp_lead, parse_google_lsa_lead, and parse_facebook_leads.
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MOCK_CLIENT_ID = "client-uuid-001"
NORMALIZED_PHONE = "+15551234567"


def _valid_yelp_payload() -> dict:
    return {
        "customer_name": "John Smith",
        "customer_phone": "+15551234567",
        "customer_email": "john@example.com",
        "message": "Need AC repair ASAP",
        "category": "hvac",
        "lead_id": "yelp_123",
    }


def _valid_google_lsa_mock() -> MagicMock:
    """Return a MagicMock that mimics a GoogleLsaPayload Pydantic model."""
    payload = MagicMock()
    payload.phone_number = "+15551234567"
    payload.customer_name = "Jane Doe"
    payload.email = "jane@example.com"
    payload.postal_code = "78701"
    payload.job_type = "hvac_repair"
    payload.lead_id = "lsa_456"
    payload.model_dump.return_value = {
        "phone_number": "+15551234567",
        "customer_name": "Jane Doe",
        "email": "jane@example.com",
        "postal_code": "78701",
        "job_type": "hvac_repair",
        "lead_id": "lsa_456",
    }
    return payload


def _valid_facebook_payload() -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "leadgen_data": {
                                "leadgen_id": "fb_789",
                                "first_name": "Alice",
                                "last_name": "Johnson",
                                "email": "alice@example.com",
                                "phone": "+15559876543",
                            }
                        }
                    }
                ]
            }
        ]
    }


# ===========================================================================
# parse_yelp_lead
# ===========================================================================

class TestParseYelpLead:
    """Tests for the Yelp webhook parser."""

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_valid_payload_returns_envelope_and_phone(self, mock_norm: MagicMock) -> None:
        """Valid Yelp payload returns a (LeadEnvelope, phone) tuple."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, phone = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert phone == NORMALIZED_PHONE
        assert envelope.lead.phone == NORMALIZED_PHONE
        mock_norm.assert_called_once_with("+15551234567")

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_source_is_yelp(self, _mock_norm: MagicMock) -> None:
        """Envelope source must be 'yelp'."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.source == "yelp"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_consent_method_is_yelp(self, _mock_norm: MagicMock) -> None:
        """Consent method must be 'yelp'."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.consent_method == "yelp"
        assert envelope.consent_type == "pec"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_customer_name_split_into_first_and_last(self, _mock_norm: MagicMock) -> None:
        """customer_name 'John Smith' should split into first_name/last_name."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.lead.first_name == "John"
        assert envelope.lead.last_name == "Smith"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_single_word_name_has_no_last_name(self, _mock_norm: MagicMock) -> None:
        """A single-word name should set first_name only, last_name is None."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload["customer_name"] = "Madonna"
        envelope, _ = parse_yelp_lead(payload, MOCK_CLIENT_ID)

        assert envelope.lead.first_name == "Madonna"
        assert envelope.lead.last_name is None

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_multi_word_last_name_preserved(self, _mock_norm: MagicMock) -> None:
        """Name with multiple spaces keeps everything after first space in last_name."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload["customer_name"] = "Jean Claude Van Damme"
        envelope, _ = parse_yelp_lead(payload, MOCK_CLIENT_ID)

        assert envelope.lead.first_name == "Jean"
        assert envelope.lead.last_name == "Claude Van Damme"

    @patch("src.api.webhook_sources.normalize_phone", return_value=None)
    def test_missing_phone_raises_value_error(self, _mock_norm: MagicMock) -> None:
        """Payload with no customer_phone should raise ValueError."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload.pop("customer_phone")

        with pytest.raises(ValueError, match="Invalid phone number"):
            parse_yelp_lead(payload, MOCK_CLIENT_ID)

    @patch("src.api.webhook_sources.normalize_phone", return_value=None)
    def test_invalid_phone_raises_value_error(self, _mock_norm: MagicMock) -> None:
        """normalize_phone returning None should raise ValueError."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload["customer_phone"] = "not-a-phone"

        with pytest.raises(ValueError, match="Invalid phone number"):
            parse_yelp_lead(payload, MOCK_CLIENT_ID)

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_missing_customer_name_does_not_crash(self, _mock_norm: MagicMock) -> None:
        """Payload without customer_name should produce None first/last names."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload.pop("customer_name")
        envelope, _ = parse_yelp_lead(payload, MOCK_CLIENT_ID)

        assert envelope.lead.first_name is None
        assert envelope.lead.last_name is None

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_empty_customer_name_does_not_crash(self, _mock_norm: MagicMock) -> None:
        """Empty string customer_name should produce None first/last names."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload["customer_name"] = ""
        envelope, _ = parse_yelp_lead(payload, MOCK_CLIENT_ID)

        assert envelope.lead.first_name is None
        assert envelope.lead.last_name is None

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_category_maps_to_service_type(self, _mock_norm: MagicMock) -> None:
        """Yelp 'category' field should map to lead.service_type."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.lead.service_type == "hvac"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_missing_category_defaults_to_general(self, _mock_norm: MagicMock) -> None:
        """Missing category should default to 'general'."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        payload.pop("category")
        envelope, _ = parse_yelp_lead(payload, MOCK_CLIENT_ID)

        assert envelope.lead.service_type == "general"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_message_maps_to_problem_description(self, _mock_norm: MagicMock) -> None:
        """Yelp 'message' field should map to lead.problem_description."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.lead.problem_description == "Need AC repair ASAP"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_email_carried_through(self, _mock_norm: MagicMock) -> None:
        """customer_email should map to lead.email."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.lead.email == "john@example.com"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_metadata_source_lead_id(self, _mock_norm: MagicMock) -> None:
        """Yelp lead_id should be stored in metadata.source_lead_id."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.metadata.source_lead_id == "yelp_123"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_raw_payload_stored_in_metadata(self, _mock_norm: MagicMock) -> None:
        """The entire raw payload dict should be stored in metadata.raw_payload."""
        from src.api.webhook_sources import parse_yelp_lead

        payload = _valid_yelp_payload()
        envelope, _ = parse_yelp_lead(payload, MOCK_CLIENT_ID)

        assert envelope.metadata.raw_payload == payload

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_client_id_set_on_envelope(self, _mock_norm: MagicMock) -> None:
        """client_id argument should be set on the envelope."""
        from src.api.webhook_sources import parse_yelp_lead

        envelope, _ = parse_yelp_lead(_valid_yelp_payload(), MOCK_CLIENT_ID)

        assert envelope.client_id == MOCK_CLIENT_ID


# ===========================================================================
# parse_google_lsa_lead
# ===========================================================================

class TestParseGoogleLsaLead:
    """Tests for the Google LSA webhook parser."""

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_valid_payload_returns_envelope_and_phone(self, mock_norm: MagicMock) -> None:
        """Valid Google LSA payload returns a (LeadEnvelope, phone) tuple."""
        from src.api.webhook_sources import parse_google_lsa_lead

        payload = _valid_google_lsa_mock()
        envelope, phone = parse_google_lsa_lead(payload, MOCK_CLIENT_ID)

        assert phone == NORMALIZED_PHONE
        assert envelope.lead.phone == NORMALIZED_PHONE
        assert envelope.source == "google_lsa"
        mock_norm.assert_called_once_with("+15551234567")

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_customer_name_split(self, _mock_norm: MagicMock) -> None:
        """customer_name 'Jane Doe' should split into first/last name."""
        from src.api.webhook_sources import parse_google_lsa_lead

        envelope, _ = parse_google_lsa_lead(_valid_google_lsa_mock(), MOCK_CLIENT_ID)

        assert envelope.lead.first_name == "Jane"
        assert envelope.lead.last_name == "Doe"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_fields_mapped_correctly(self, _mock_norm: MagicMock) -> None:
        """Email, postal_code, job_type should map to corresponding lead fields."""
        from src.api.webhook_sources import parse_google_lsa_lead

        envelope, _ = parse_google_lsa_lead(_valid_google_lsa_mock(), MOCK_CLIENT_ID)

        assert envelope.lead.email == "jane@example.com"
        assert envelope.lead.zip_code == "78701"
        assert envelope.lead.service_type == "hvac_repair"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_consent_method_is_google_lsa(self, _mock_norm: MagicMock) -> None:
        """Consent method should be 'google_lsa'."""
        from src.api.webhook_sources import parse_google_lsa_lead

        envelope, _ = parse_google_lsa_lead(_valid_google_lsa_mock(), MOCK_CLIENT_ID)

        assert envelope.consent_method == "google_lsa"
        assert envelope.consent_type == "pec"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_metadata_contains_source_lead_id(self, _mock_norm: MagicMock) -> None:
        """metadata.source_lead_id should match the payload's lead_id."""
        from src.api.webhook_sources import parse_google_lsa_lead

        envelope, _ = parse_google_lsa_lead(_valid_google_lsa_mock(), MOCK_CLIENT_ID)

        assert envelope.metadata.source_lead_id == "lsa_456"

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_metadata_raw_payload_from_model_dump(self, _mock_norm: MagicMock) -> None:
        """raw_payload should come from payload.model_dump()."""
        from src.api.webhook_sources import parse_google_lsa_lead

        payload = _valid_google_lsa_mock()
        envelope, _ = parse_google_lsa_lead(payload, MOCK_CLIENT_ID)

        payload.model_dump.assert_called_once()
        assert envelope.metadata.raw_payload == payload.model_dump.return_value

    @patch("src.api.webhook_sources.normalize_phone", return_value=None)
    def test_invalid_phone_raises_value_error(self, _mock_norm: MagicMock) -> None:
        """normalize_phone returning None should raise ValueError."""
        from src.api.webhook_sources import parse_google_lsa_lead

        with pytest.raises(ValueError, match="Invalid phone number"):
            parse_google_lsa_lead(_valid_google_lsa_mock(), MOCK_CLIENT_ID)

    @patch("src.api.webhook_sources.normalize_phone", return_value=NORMALIZED_PHONE)
    def test_missing_customer_name_gives_none_names(self, _mock_norm: MagicMock) -> None:
        """None customer_name should produce None first/last names."""
        from src.api.webhook_sources import parse_google_lsa_lead

        payload = _valid_google_lsa_mock()
        payload.customer_name = None
        envelope, _ = parse_google_lsa_lead(payload, MOCK_CLIENT_ID)

        assert envelope.lead.first_name is None
        assert envelope.lead.last_name is None


# ===========================================================================
# parse_facebook_leads
# ===========================================================================

class TestParseFacebookLeads:
    """Tests for the Facebook Lead Ads webhook parser."""

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_valid_payload_returns_list_of_envelopes(self, _mock_norm: MagicMock) -> None:
        """Valid Facebook payload should return a non-empty list of envelopes."""
        from src.api.webhook_sources import parse_facebook_leads

        envelopes = parse_facebook_leads(_valid_facebook_payload(), MOCK_CLIENT_ID)

        assert len(envelopes) == 1
        envelope = envelopes[0]
        assert envelope.source == "facebook"
        assert envelope.lead.phone == "+15559876543"

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_lead_fields_mapped(self, _mock_norm: MagicMock) -> None:
        """First/last name and email should be extracted from leadgen_data."""
        from src.api.webhook_sources import parse_facebook_leads

        envelopes = parse_facebook_leads(_valid_facebook_payload(), MOCK_CLIENT_ID)

        envelope = envelopes[0]
        assert envelope.lead.first_name == "Alice"
        assert envelope.lead.last_name == "Johnson"
        assert envelope.lead.email == "alice@example.com"

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_consent_method_is_facebook(self, _mock_norm: MagicMock) -> None:
        """Consent method should be 'facebook', type 'pewc'."""
        from src.api.webhook_sources import parse_facebook_leads

        envelopes = parse_facebook_leads(_valid_facebook_payload(), MOCK_CLIENT_ID)

        assert envelopes[0].consent_method == "facebook"
        assert envelopes[0].consent_type == "pewc"

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_metadata_source_lead_id(self, _mock_norm: MagicMock) -> None:
        """leadgen_id should be stored as source_lead_id in metadata."""
        from src.api.webhook_sources import parse_facebook_leads

        envelopes = parse_facebook_leads(_valid_facebook_payload(), MOCK_CLIENT_ID)

        assert envelopes[0].metadata.source_lead_id == "fb_789"

    @patch("src.api.webhook_sources.normalize_phone")
    def test_skips_entries_with_no_phone(self, mock_norm: MagicMock) -> None:
        """Entries missing phone and phone_number should be skipped entirely."""
        from src.api.webhook_sources import parse_facebook_leads

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "leadgen_data": {
                                    "leadgen_id": "fb_no_phone",
                                    "first_name": "Bob",
                                    "email": "bob@example.com",
                                    # no phone or phone_number
                                }
                            }
                        }
                    ]
                }
            ]
        }
        envelopes = parse_facebook_leads(payload, MOCK_CLIENT_ID)

        assert len(envelopes) == 0
        mock_norm.assert_not_called()

    @patch("src.api.webhook_sources.normalize_phone", return_value=None)
    def test_skips_entries_with_invalid_phone(self, _mock_norm: MagicMock) -> None:
        """Entries where normalize_phone returns None should be skipped."""
        from src.api.webhook_sources import parse_facebook_leads

        envelopes = parse_facebook_leads(_valid_facebook_payload(), MOCK_CLIENT_ID)

        assert len(envelopes) == 0

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_multiple_entries_produce_multiple_envelopes(self, _mock_norm: MagicMock) -> None:
        """Multiple entries with valid phones should each produce an envelope."""
        from src.api.webhook_sources import parse_facebook_leads

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "leadgen_data": {
                                    "leadgen_id": "fb_001",
                                    "first_name": "Alice",
                                    "phone": "+15559876001",
                                }
                            }
                        }
                    ]
                },
                {
                    "changes": [
                        {
                            "value": {
                                "leadgen_data": {
                                    "leadgen_id": "fb_002",
                                    "first_name": "Bob",
                                    "phone": "+15559876002",
                                }
                            }
                        }
                    ]
                },
            ]
        }
        envelopes = parse_facebook_leads(payload, MOCK_CLIENT_ID)

        assert len(envelopes) == 2
        assert envelopes[0].metadata.source_lead_id == "fb_001"
        assert envelopes[1].metadata.source_lead_id == "fb_002"

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_empty_entry_list_returns_empty(self, _mock_norm: MagicMock) -> None:
        """Payload with empty entry list should return an empty list."""
        from src.api.webhook_sources import parse_facebook_leads

        envelopes = parse_facebook_leads({"entry": []}, MOCK_CLIENT_ID)

        assert envelopes == []

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_phone_number_alt_field(self, _mock_norm: MagicMock) -> None:
        """Parser should also accept 'phone_number' as the phone field."""
        from src.api.webhook_sources import parse_facebook_leads

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "leadgen_data": {
                                    "leadgen_id": "fb_alt",
                                    "phone_number": "+15559876543",
                                }
                            }
                        }
                    ]
                }
            ]
        }
        envelopes = parse_facebook_leads(payload, MOCK_CLIENT_ID)

        assert len(envelopes) == 1

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_value_without_leadgen_data_key_uses_value_directly(self, _mock_norm: MagicMock) -> None:
        """When 'leadgen_data' key is absent, the value dict itself is treated as lead data."""
        from src.api.webhook_sources import parse_facebook_leads

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "id": "fb_direct",
                                "first_name": "Charlie",
                                "phone": "+15559876543",
                            }
                        }
                    ]
                }
            ]
        }
        envelopes = parse_facebook_leads(payload, MOCK_CLIENT_ID)

        assert len(envelopes) == 1
        assert envelopes[0].lead.first_name == "Charlie"
        assert envelopes[0].metadata.source_lead_id == "fb_direct"

    @patch("src.api.webhook_sources.normalize_phone", return_value="+15559876543")
    def test_raw_payload_is_full_payload(self, _mock_norm: MagicMock) -> None:
        """metadata.raw_payload should be the entire Facebook payload dict."""
        from src.api.webhook_sources import parse_facebook_leads

        payload = _valid_facebook_payload()
        envelopes = parse_facebook_leads(payload, MOCK_CLIENT_ID)

        assert envelopes[0].metadata.raw_payload == payload
