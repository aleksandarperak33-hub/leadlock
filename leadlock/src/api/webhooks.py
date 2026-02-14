"""
Webhook endpoints — receive leads from all sources.
Each webhook normalizes its payload into a LeadEnvelope and passes to the conductor.
"""
import logging
import uuid
from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.database import get_db
from src.models.lead import Lead
from src.models.client import Client
from src.schemas.lead_envelope import LeadEnvelope, NormalizedLead, LeadMetadata
from src.schemas.webhook_payloads import (
    WebFormPayload,
    GoogleLsaPayload,
    AngiPayload,
    MissedCallPayload,
)
from src.schemas.api_responses import WebhookPayloadResponse
from src.agents.conductor import handle_new_lead, handle_inbound_reply
from src.services.phone_validation import normalize_phone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhook", tags=["webhooks"])


@router.post("/twilio/sms/{client_id}", response_model=WebhookPayloadResponse)
async def twilio_sms_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Twilio inbound SMS webhook — handles both new leads and replies.
    Twilio sends form-encoded data, not JSON.
    """
    form_data = await request.form()
    from_phone = form_data.get("From", "")
    body = form_data.get("Body", "")
    to_phone = form_data.get("To", "")

    if not from_phone or not body:
        raise HTTPException(status_code=400, detail="Missing From or Body")

    phone = normalize_phone(from_phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    masked = phone[:6] + "***"
    logger.info("Inbound SMS from %s to client %s", masked, client_id[:8])

    # Load client
    client = await db.get(Client, uuid.UUID(client_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check if this is an existing lead (reply) or new lead
    existing_lead_result = await db.execute(
        select(Lead).where(
            and_(Lead.client_id == client.id, Lead.phone == phone)
        ).order_by(Lead.created_at.desc()).limit(1)
    )
    existing_lead = existing_lead_result.scalar_one_or_none()

    if existing_lead:
        # This is a reply to an existing conversation
        result = await handle_inbound_reply(db, existing_lead, client, body)
    else:
        # New lead via text-in
        envelope = LeadEnvelope(
            source="text_in",
            client_id=client_id,
            lead=NormalizedLead(
                phone=phone,
            ),
            metadata=LeadMetadata(
                raw_payload=dict(form_data),
            ),
            consent_type="pec",
            consent_method="text_in",
            inbound_message=body,
        )
        result = await handle_new_lead(db, envelope)

    return WebhookPayloadResponse(
        status="accepted",
        lead_id=result.get("lead_id"),
        message=f"Processed in {result.get('response_ms', 0)}ms",
    )


@router.post("/twilio/status")
async def twilio_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Twilio delivery status callback — update message delivery status."""
    form_data = await request.form()
    message_sid = form_data.get("MessageSid", "")
    status = form_data.get("MessageStatus", "")
    error_code = form_data.get("ErrorCode")

    if message_sid and status:
        from src.models.conversation import Conversation
        from datetime import datetime

        result = await db.execute(
            select(Conversation).where(Conversation.sms_sid == message_sid)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.delivery_status = status
            if error_code:
                conv.delivery_error_code = error_code
                conv.delivery_error_message = form_data.get("ErrorMessage")
            if status == "delivered":
                conv.delivered_at = datetime.utcnow()
            await db.commit()
            logger.info("SMS %s status: %s", message_sid, status)

    return {"status": "ok"}


@router.post("/form/{client_id}", response_model=WebhookPayloadResponse)
async def website_form_webhook(
    client_id: str,
    payload: WebFormPayload,
    db: AsyncSession = Depends(get_db),
):
    """Website contact form submission."""
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    # Parse name
    first_name = payload.first_name
    last_name = payload.last_name
    if not first_name and payload.name:
        parts = payload.name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    envelope = LeadEnvelope(
        source="website",
        client_id=client_id,
        lead=NormalizedLead(
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            email=payload.email,
            address=payload.address,
            zip_code=payload.zip,
            city=payload.city,
            state_code=payload.state,
            service_type=payload.service,
            problem_description=payload.message,
            urgency=payload.urgency,
            property_type=payload.property_type,
        ),
        metadata=LeadMetadata(
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            raw_payload=payload.model_dump(),
        ),
        consent_type="pewc",
        consent_method="web_form",
        inbound_message=payload.message,
    )

    result = await handle_new_lead(db, envelope)
    return WebhookPayloadResponse(
        status="accepted",
        lead_id=result.get("lead_id"),
        message=f"Processed in {result.get('response_ms', 0)}ms",
    )


@router.post("/google-lsa/{client_id}", response_model=WebhookPayloadResponse)
async def google_lsa_webhook(
    client_id: str,
    payload: GoogleLsaPayload,
    db: AsyncSession = Depends(get_db),
):
    """Google Local Services Ads lead."""
    phone = normalize_phone(payload.phone_number)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    # Parse name
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

    result = await handle_new_lead(db, envelope)
    return WebhookPayloadResponse(
        status="accepted",
        lead_id=result.get("lead_id"),
        message=f"Processed in {result.get('response_ms', 0)}ms",
    )


@router.post("/angi/{client_id}", response_model=WebhookPayloadResponse)
async def angi_webhook(
    client_id: str,
    payload: AngiPayload,
    db: AsyncSession = Depends(get_db),
):
    """Angi/HomeAdvisor lead."""
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

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

    result = await handle_new_lead(db, envelope)
    return WebhookPayloadResponse(
        status="accepted",
        lead_id=result.get("lead_id"),
        message=f"Processed in {result.get('response_ms', 0)}ms",
    )


@router.post("/facebook/{client_id}", response_model=WebhookPayloadResponse)
async def facebook_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Facebook Lead Ads webhook."""
    payload = await request.json()
    entries = payload.get("entry", [])

    if not entries:
        return WebhookPayloadResponse(status="accepted", message="No entries")

    # Process the first lead entry
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

            result = await handle_new_lead(db, envelope)
            return WebhookPayloadResponse(
                status="accepted",
                lead_id=result.get("lead_id"),
                message=f"Processed in {result.get('response_ms', 0)}ms",
            )

    return WebhookPayloadResponse(status="accepted", message="No valid leads found")


@router.post("/missed-call/{client_id}", response_model=WebhookPayloadResponse)
async def missed_call_webhook(
    client_id: str,
    payload: MissedCallPayload,
    db: AsyncSession = Depends(get_db),
):
    """Missed call notification — creates a lead from the caller."""
    phone = normalize_phone(payload.caller_phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    # Parse caller name
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
        metadata=LeadMetadata(
            raw_payload=payload.model_dump(),
        ),
        consent_type="pec",
        consent_method="missed_call",
    )

    result = await handle_new_lead(db, envelope)
    return WebhookPayloadResponse(
        status="accepted",
        lead_id=result.get("lead_id"),
        message=f"Processed in {result.get('response_ms', 0)}ms",
    )
