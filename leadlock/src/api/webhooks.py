"""
Webhook endpoints — receive leads from all sources.
Each webhook normalizes its payload into a LeadEnvelope and passes to the conductor.

Security layers (in order):
1. Rate limiting (IP + client-level)
2. Signature validation (per-source)
3. Audit trail (webhook_events table)
4. Payload processing
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.database import get_db
from src.models.lead import Lead
from src.models.client import Client
from src.models.webhook_event import WebhookEvent
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
from src.utils.webhook_signatures import validate_webhook_source, compute_payload_hash
from src.utils.rate_limiter import check_webhook_rate_limits
from src.utils.logging import get_correlation_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhook", tags=["webhooks"])


async def _record_webhook_event(
    db: AsyncSession,
    source: str,
    event_type: str,
    raw_payload: dict,
    payload_hash: str,
    client_id: str | None = None,
) -> WebhookEvent:
    """Record a webhook event in the audit trail before processing."""
    client_uuid = None
    if client_id:
        try:
            client_uuid = uuid.UUID(client_id)
        except ValueError:
            pass

    event = WebhookEvent(
        source=source,
        event_type=event_type,
        payload_hash=payload_hash,
        raw_payload=raw_payload,
        client_id=client_uuid,
        processing_status="received",
        correlation_id=get_correlation_id(),
    )
    db.add(event)
    await db.flush()
    return event


async def _complete_webhook_event(
    event: WebhookEvent,
    status: str = "completed",
    error_message: str | None = None,
) -> None:
    """Update webhook event status after processing."""
    event.processing_status = status
    event.error_message = error_message
    event.processed_at = datetime.now(timezone.utc)


async def _enforce_rate_limit(request: Request, client_id: str | None = None) -> None:
    """Check rate limits and raise 429 if exceeded."""
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await check_webhook_rate_limits(client_ip, client_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after or 60)},
        )


async def _validate_signature(
    source: str, request: Request, body: bytes, form_params: dict | None = None,
) -> None:
    """Validate webhook signature and raise 401 if invalid."""
    is_valid = await validate_webhook_source(source, request, body, form_params)
    if not is_valid:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            "Invalid webhook signature: source=%s ip=%s",
            source, client_ip,
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


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
    # Rate limit
    await _enforce_rate_limit(request, client_id)

    # Read raw body for signature validation + audit
    body = await request.body()
    form_data = await request.form()
    form_params = dict(form_data)

    # Signature validation
    await _validate_signature("twilio", request, body, form_params)

    # Audit trail
    payload_hash = compute_payload_hash(body)
    event = await _record_webhook_event(
        db, source="twilio", event_type="inbound_sms",
        raw_payload=form_params, payload_hash=payload_hash, client_id=client_id,
    )

    try:
        from_phone = form_data.get("From", "")
        body_text = form_data.get("Body", "")
        if not from_phone or not body_text:
            await _complete_webhook_event(event, "failed", "Missing From or Body")
            raise HTTPException(status_code=400, detail="Missing From or Body")

        phone = normalize_phone(from_phone)
        if not phone:
            await _complete_webhook_event(event, "failed", "Invalid phone number")
            raise HTTPException(status_code=400, detail="Invalid phone number")

        masked = phone[:6] + "***"
        logger.info("Inbound SMS from %s to client %s", masked, client_id[:8])

        # Load client
        client = await db.get(Client, uuid.UUID(client_id))
        if not client:
            await _complete_webhook_event(event, "failed", "Client not found")
            raise HTTPException(status_code=404, detail="Client not found")

        event.processing_status = "processing"

        # Check if this is an existing lead (reply) or new lead
        existing_lead_result = await db.execute(
            select(Lead).where(
                and_(Lead.client_id == client.id, Lead.phone == phone)
            ).order_by(Lead.created_at.desc()).limit(1)
        )
        existing_lead = existing_lead_result.scalar_one_or_none()

        if existing_lead:
            result = await handle_inbound_reply(db, existing_lead, client, body_text)
        else:
            envelope = LeadEnvelope(
                source="text_in",
                client_id=client_id,
                lead=NormalizedLead(phone=phone),
                metadata=LeadMetadata(raw_payload=form_params),
                consent_type="pec",
                consent_method="text_in",
                inbound_message=body_text,
            )
            result = await handle_new_lead(db, envelope)

        await _complete_webhook_event(event)
        return WebhookPayloadResponse(
            status="accepted",
            lead_id=result.get("lead_id"),
            message=f"Processed in {result.get('response_ms', 0)}ms",
        )
    except HTTPException:
        raise
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Twilio webhook processing error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")


@router.post("/twilio/status")
async def twilio_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Twilio delivery status callback — update message delivery status."""
    body = await request.body()
    form_data = await request.form()
    form_params = dict(form_data)

    # Signature validation
    await _validate_signature("twilio", request, body, form_params)

    # Audit trail
    payload_hash = compute_payload_hash(body)
    event = await _record_webhook_event(
        db, source="twilio", event_type="delivery_status",
        raw_payload=form_params, payload_hash=payload_hash,
    )

    try:
        message_sid = form_data.get("MessageSid", "")
        status = form_data.get("MessageStatus", "")
        error_code = form_data.get("ErrorCode")

        if message_sid and status:
            from src.models.conversation import Conversation
            from src.services.deliverability import record_sms_outcome

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
                    conv.delivered_at = datetime.now(timezone.utc)
                logger.info("SMS %s status: %s", message_sid, status)

                # Record delivery outcome for reputation tracking
                await record_sms_outcome(
                    from_phone=conv.from_phone,
                    to_phone=conv.to_phone,
                    status=status,
                    error_code=error_code,
                    provider="twilio",
                )

        await _complete_webhook_event(event)
        return {"status": "ok"}
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Twilio status webhook error: %s", str(e), exc_info=True)
        return {"status": "error"}


@router.post("/form/{client_id}", response_model=WebhookPayloadResponse)
async def website_form_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Website contact form submission."""
    await _enforce_rate_limit(request, client_id)

    body = await request.body()
    await _validate_signature("website", request, body)

    payload_hash = compute_payload_hash(body)

    # Parse JSON body
    import json
    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payload = WebFormPayload(**payload_dict)

    event = await _record_webhook_event(
        db, source="website", event_type="form_submission",
        raw_payload=payload_dict, payload_hash=payload_hash, client_id=client_id,
    )

    try:
        phone = normalize_phone(payload.phone)
        if not phone:
            await _complete_webhook_event(event, "failed", "Invalid phone number")
            raise HTTPException(status_code=400, detail="Invalid phone number")

        # Parse name
        first_name = payload.first_name
        last_name = payload.last_name
        if not first_name and payload.name:
            parts = payload.name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else None

        event.processing_status = "processing"

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
        await _complete_webhook_event(event)
        return WebhookPayloadResponse(
            status="accepted",
            lead_id=result.get("lead_id"),
            message=f"Processed in {result.get('response_ms', 0)}ms",
        )
    except HTTPException:
        raise
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Form webhook processing error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")


@router.post("/google-lsa/{client_id}", response_model=WebhookPayloadResponse)
async def google_lsa_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Google Local Services Ads lead."""
    await _enforce_rate_limit(request, client_id)

    body = await request.body()
    await _validate_signature("google_lsa", request, body)

    payload_hash = compute_payload_hash(body)

    import json
    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payload = GoogleLsaPayload(**payload_dict)

    event = await _record_webhook_event(
        db, source="google_lsa", event_type="lead",
        raw_payload=payload_dict, payload_hash=payload_hash, client_id=client_id,
    )

    try:
        phone = normalize_phone(payload.phone_number)
        if not phone:
            await _complete_webhook_event(event, "failed", "Invalid phone number")
            raise HTTPException(status_code=400, detail="Invalid phone number")

        first_name = None
        last_name = None
        if payload.customer_name:
            parts = payload.customer_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else None

        event.processing_status = "processing"

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
        await _complete_webhook_event(event)
        return WebhookPayloadResponse(
            status="accepted",
            lead_id=result.get("lead_id"),
            message=f"Processed in {result.get('response_ms', 0)}ms",
        )
    except HTTPException:
        raise
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Google LSA webhook error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")


@router.post("/angi/{client_id}", response_model=WebhookPayloadResponse)
async def angi_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Angi/HomeAdvisor lead."""
    await _enforce_rate_limit(request, client_id)

    body = await request.body()
    await _validate_signature("angi", request, body)

    payload_hash = compute_payload_hash(body)

    import json
    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payload = AngiPayload(**payload_dict)

    event = await _record_webhook_event(
        db, source="angi", event_type="lead",
        raw_payload=payload_dict, payload_hash=payload_hash, client_id=client_id,
    )

    try:
        phone = normalize_phone(payload.phone)
        if not phone:
            await _complete_webhook_event(event, "failed", "Invalid phone number")
            raise HTTPException(status_code=400, detail="Invalid phone number")

        event.processing_status = "processing"

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
        await _complete_webhook_event(event)
        return WebhookPayloadResponse(
            status="accepted",
            lead_id=result.get("lead_id"),
            message=f"Processed in {result.get('response_ms', 0)}ms",
        )
    except HTTPException:
        raise
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Angi webhook error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")


@router.post("/facebook/{client_id}", response_model=WebhookPayloadResponse)
async def facebook_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Facebook Lead Ads webhook."""
    await _enforce_rate_limit(request, client_id)

    body = await request.body()
    await _validate_signature("facebook", request, body)

    payload_hash = compute_payload_hash(body)

    import json
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = await _record_webhook_event(
        db, source="facebook", event_type="lead",
        raw_payload=payload, payload_hash=payload_hash, client_id=client_id,
    )

    try:
        entries = payload.get("entry", [])
        if not entries:
            await _complete_webhook_event(event)
            return WebhookPayloadResponse(status="accepted", message="No entries")

        event.processing_status = "processing"
        processed_count = 0
        last_result = None

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

                last_result = await handle_new_lead(db, envelope)
                processed_count += 1

        await _complete_webhook_event(event)
        if processed_count > 0 and last_result:
            return WebhookPayloadResponse(
                status="accepted",
                lead_id=last_result.get("lead_id"),
                message=f"Processed {processed_count} lead(s)",
            )
        return WebhookPayloadResponse(status="accepted", message="No valid leads found")
    except HTTPException:
        raise
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Facebook webhook error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")


@router.post("/missed-call/{client_id}", response_model=WebhookPayloadResponse)
async def missed_call_webhook(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Missed call notification — creates a lead from the caller."""
    await _enforce_rate_limit(request, client_id)

    body = await request.body()
    await _validate_signature("missed_call", request, body)

    payload_hash = compute_payload_hash(body)

    import json
    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payload = MissedCallPayload(**payload_dict)

    event = await _record_webhook_event(
        db, source="missed_call", event_type="missed_call",
        raw_payload=payload_dict, payload_hash=payload_hash, client_id=client_id,
    )

    try:
        phone = normalize_phone(payload.caller_phone)
        if not phone:
            await _complete_webhook_event(event, "failed", "Invalid phone number")
            raise HTTPException(status_code=400, detail="Invalid phone number")

        first_name = None
        last_name = None
        if payload.caller_name:
            parts = payload.caller_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else None

        event.processing_status = "processing"

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

        result = await handle_new_lead(db, envelope)
        await _complete_webhook_event(event)
        return WebhookPayloadResponse(
            status="accepted",
            lead_id=result.get("lead_id"),
            message=f"Processed in {result.get('response_ms', 0)}ms",
        )
    except HTTPException:
        raise
    except Exception as e:
        await _complete_webhook_event(event, "failed", str(e))
        logger.error("Missed call webhook error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal processing error")
