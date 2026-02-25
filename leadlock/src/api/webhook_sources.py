"""
Source-specific webhook payload parsers.
Each function normalizes a raw payload into a LeadEnvelope for the conductor.
Extracted from webhooks.py to keep file sizes under 800 lines.
"""
import logging
from typing import Optional

from src.schemas.lead_envelope import LeadEnvelope, NormalizedLead, LeadMetadata
from src.services.phone_validation import normalize_phone

logger = logging.getLogger(__name__)


def parse_google_lsa_lead(payload, client_id: str) -> tuple[LeadEnvelope, str]:
    """Parse a Google LSA payload into a LeadEnvelope.

    Returns:
        Tuple of (envelope, normalized_phone). Raises ValueError on invalid phone.
    """
    phone = normalize_phone(payload.phone_number)
    if not phone:
        raise ValueError("Invalid phone number")

    first_name = None
    last_name = None
    if payload.customer_name:
        parts = payload.customer_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    envelope = LeadEnvelope(
        source="google_lsa",
        client_id=client_id,
        lead=NormalizedLead(
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            email=payload.email,
            zip_code=payload.postal_code,
            service_type=payload.job_type,
        ),
        metadata=LeadMetadata(
            source_lead_id=payload.lead_id,
            source_timestamp=None,
            raw_payload=payload.model_dump(),
        ),
        consent_type="pec",
        consent_method="google_lsa",
    )
    return envelope, phone


def parse_angi_lead(payload, client_id: str) -> tuple[LeadEnvelope, str]:
    """Parse an Angi/HomeAdvisor payload into a LeadEnvelope."""
    phone = normalize_phone(payload.phone)
    if not phone:
        raise ValueError("Invalid phone number")

    envelope = LeadEnvelope(
        source="angi",
        client_id=client_id,
        lead=NormalizedLead(
            phone=phone,
            first_name=payload.firstName,
            last_name=payload.lastName,
            email=payload.email,
            zip_code=payload.zipCode,
            city=payload.city,
            state_code=payload.state,
            service_type=payload.serviceDescription,
            urgency=payload.urgency,
            property_type=payload.propertyType,
        ),
        metadata=LeadMetadata(
            source_lead_id=payload.leadId,
            raw_payload=payload.model_dump(),
        ),
        consent_type="pec",
        consent_method="angi",
    )
    return envelope, phone


def parse_facebook_leads(payload: dict, client_id: str) -> list[LeadEnvelope]:
    """Parse Facebook Lead Ads payload into a list of LeadEnvelopes."""
    envelopes = []
    entries = payload.get("entry", [])

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            lead_data = value.get("leadgen_data", {}) if "leadgen_data" in value else value

            phone = lead_data.get("phone", lead_data.get("phone_number", ""))
            if not phone:
                continue

            normalized = normalize_phone(phone)
            if not normalized:
                continue

            envelope = LeadEnvelope(
                source="facebook",
                client_id=client_id,
                lead=NormalizedLead(
                    phone=normalized,
                    first_name=lead_data.get("first_name"),
                    last_name=lead_data.get("last_name"),
                    email=lead_data.get("email"),
                ),
                metadata=LeadMetadata(
                    source_lead_id=lead_data.get("leadgen_id", lead_data.get("id")),
                    raw_payload=payload,
                ),
                consent_type="pewc",
                consent_method="facebook",
            )
            envelopes.append(envelope)

    return envelopes


def parse_missed_call_lead(payload, client_id: str) -> tuple[LeadEnvelope, str]:
    """Parse a missed call payload into a LeadEnvelope."""
    phone = normalize_phone(payload.caller_phone)
    if not phone:
        raise ValueError("Invalid phone number")

    first_name = None
    last_name = None
    if payload.caller_name:
        parts = payload.caller_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    envelope = LeadEnvelope(
        source="missed_call",
        client_id=client_id,
        lead=NormalizedLead(
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            city=payload.caller_city,
            state_code=payload.caller_state,
            zip_code=payload.caller_zip,
        ),
        metadata=LeadMetadata(raw_payload=payload.model_dump()),
        consent_type="pec",
        consent_method="missed_call",
    )
    return envelope, phone


def parse_thumbtack_lead(payload, payload_dict: dict, client_id: str) -> tuple[Optional[LeadEnvelope], Optional[str]]:
    """Parse a Thumbtack payload into a LeadEnvelope.

    Returns (None, None) if no phone in payload (Thumbtack often omits it).
    """
    phone_raw = payload.customer_phone
    if not phone_raw:
        return None, None

    phone = normalize_phone(phone_raw)
    if not phone:
        raise ValueError("Invalid phone number")

    first_name = None
    last_name = None
    if payload.customer and payload.customer.name:
        parts = payload.customer.name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    city = None
    state_code = None
    zip_code = None
    if payload.request and payload.request.location:
        loc = payload.request.location
        city = loc.city
        state_code = loc.state
        zip_code = loc.zipCode

    service_type = None
    if payload.request:
        service_type = payload.request.category or payload.request.title

    problem_parts = []
    if payload.request:
        if payload.request.description:
            problem_parts.append(payload.request.description)
        if payload.request.schedule:
            problem_parts.append(f"Schedule: {payload.request.schedule}")
        for detail in payload.request.details:
            if detail.question and detail.answer:
                problem_parts.append(f"{detail.question}: {detail.answer}")
    problem_description = "\n".join(problem_parts) if problem_parts else None

    envelope = LeadEnvelope(
        source="thumbtack",
        client_id=client_id,
        lead=NormalizedLead(
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            email=payload.customer_email,
            city=city,
            state_code=state_code,
            zip_code=zip_code,
            service_type=service_type,
            problem_description=problem_description,
        ),
        metadata=LeadMetadata(
            source_lead_id=payload.leadID,
            raw_payload=payload_dict,
        ),
        consent_type="pec",
        consent_method="thumbtack",
    )
    return envelope, phone


def parse_yelp_lead(payload: dict, client_id: str) -> tuple[LeadEnvelope, str]:
    """Parse a Yelp Leads API payload into a LeadEnvelope.

    Yelp standard fields: customer_name, customer_phone, customer_email, message, category.
    """
    phone_raw = payload.get("customer_phone", "")
    phone = normalize_phone(phone_raw)
    if not phone:
        raise ValueError("Invalid phone number")

    customer_name = payload.get("customer_name", "")
    first_name = None
    last_name = None
    if customer_name:
        parts = customer_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    envelope = LeadEnvelope(
        source="yelp",
        client_id=client_id,
        lead=NormalizedLead(
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            email=payload.get("customer_email"),
            service_type=payload.get("category", "general"),
            problem_description=payload.get("message"),
        ),
        metadata=LeadMetadata(
            source_lead_id=payload.get("lead_id"),
            raw_payload=payload,
        ),
        consent_type="pec",
        consent_method="yelp",
    )
    return envelope, phone
