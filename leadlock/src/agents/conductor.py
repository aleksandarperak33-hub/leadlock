"""
Conductor - THE BRAIN. State machine orchestrator for the lead pipeline.
Routes leads through agents, enforces compliance, manages state transitions.

CRITICAL PRINCIPLE: RESPOND FIRST, SYNC LATER.
The SMS response MUST go out in <10 seconds. All CRM operations happen asynchronously AFTER.

State machine:
  new → intake_sent → qualifying → qualified → booking → booked → completed
  Any state → opted_out (on STOP keyword)
  qualifying/qualified → cold (on timeout/unresponsive)
  cold → dead (after max followups exhausted)
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from src.models.lead import Lead
from src.models.client import Client
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.event_log import EventLog
from src.schemas.lead_envelope import LeadEnvelope
from src.schemas.client_config import ClientConfig
from src.services.compliance import (
    full_compliance_check,
    is_stop_keyword,
    needs_ai_disclosure,
    get_ai_disclosure,
)
from src.services.sms import send_sms, mask_phone
from src.services.phone_validation import normalize_phone
from src.utils.emergency import detect_emergency
from src.utils.dedup import is_duplicate
from src.utils.locks import lead_lock, LockTimeoutError
from src.utils.metrics import Timer
from src.agents.intake import process_intake
from src.agents.qualify import process_qualify
from src.agents.book import process_booking
from src.services.plan_limits import get_monthly_lead_limit

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS = {
    "new": ["intake_sent", "opted_out"],
    "intake_sent": ["qualifying", "opted_out"],
    "qualifying": ["qualified", "booking", "cold", "opted_out"],
    "qualified": ["booking", "cold", "opted_out"],
    "booking": ["booked", "qualifying", "cold", "opted_out"],
    "booked": ["completed", "opted_out"],
    "cold": ["qualifying", "dead", "opted_out"],  # Can re-engage
    "completed": ["opted_out"],
    "dead": ["opted_out"],
    "opted_out": [],  # Terminal - no transitions out
}


async def handle_new_lead(
    db: AsyncSession,
    envelope: LeadEnvelope,
) -> dict:
    """
    Process a brand new lead from any source.
    This is the entry point for the entire pipeline.

    Returns: {"lead_id": str, "status": str, "response_ms": int}
    """
    timer = Timer().start()

    # Normalize phone
    phone = normalize_phone(envelope.lead.phone)
    if not phone:
        logger.warning("Invalid phone number: %s", envelope.lead.phone[:6] + "***")
        return {"lead_id": None, "status": "invalid_phone", "response_ms": timer.elapsed_ms}

    # Dedup check + client load in parallel (independent operations)
    is_dupe, client = await asyncio.gather(
        is_duplicate(envelope.client_id, phone, envelope.source),
        db.get(Client, uuid.UUID(envelope.client_id)),
    )

    if is_dupe:
        # Send brief acknowledgment so customer doesn't think we're ignoring them
        if client and client.twilio_phone:
            try:
                await send_sms(
                    to=phone,
                    body=f"Got it, {envelope.lead.first_name or 'thanks'}! We're on it. Someone will be in touch shortly.",
                    from_phone=client.twilio_phone,
                )
            except Exception as sms_err:
                logger.warning("Duplicate ack SMS failed: %s", str(sms_err))
        return {"lead_id": None, "status": "duplicate_acknowledged", "response_ms": timer.elapsed_ms}

    if not client:
        logger.error("Client not found: %s", envelope.client_id)
        return {"lead_id": None, "status": "client_not_found", "response_ms": timer.elapsed_ms}

    config = ClientConfig(**client.config) if client.config else ClientConfig()

    # Enforce monthly lead limit based on plan tier
    monthly_limit = get_monthly_lead_limit(client.tier)
    if monthly_limit is not None:
        from datetime import timezone as tz
        month_start = datetime.now(tz.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        leads_this_month = (await db.execute(
            select(func.count(Lead.id)).where(
                and_(Lead.client_id == client.id, Lead.created_at >= month_start)
            )
        )).scalar() or 0
        if leads_this_month >= monthly_limit:
            logger.warning(
                "Client %s hit monthly lead limit (%d/%d, tier=%s)",
                str(client.id)[:8], leads_this_month, monthly_limit, client.tier,
            )
            return {
                "lead_id": None,
                "status": "monthly_lead_limit_reached",
                "response_ms": timer.elapsed_ms,
            }

    # Create consent record
    consent = ConsentRecord(
        phone=phone,
        client_id=client.id,
        consent_type=envelope.consent_type,
        consent_method=envelope.consent_method,
        consent_text=f"Lead submitted via {envelope.source}",
        raw_consent_data=envelope.metadata.model_dump() if envelope.metadata else {},
    )
    db.add(consent)
    await db.flush()

    # Create lead record
    lead = Lead(
        client_id=client.id,
        phone=phone,
        first_name=envelope.lead.first_name,
        last_name=envelope.lead.last_name,
        email=envelope.lead.email,
        address=envelope.lead.address,
        zip_code=envelope.lead.zip_code,
        city=envelope.lead.city,
        state_code=envelope.lead.state_code,
        source=envelope.source,
        source_lead_id=envelope.metadata.source_lead_id if envelope.metadata else None,
        state="new",
        service_type=envelope.lead.service_type,
        urgency=envelope.lead.urgency,
        property_type=envelope.lead.property_type,
        problem_description=envelope.lead.problem_description,
        consent_id=consent.id,
        raw_payload=envelope.metadata.raw_payload if envelope.metadata else None,
        current_agent="intake",
    )

    # Check for emergency in the message
    message_text = envelope.lead.problem_description or envelope.inbound_message or ""
    emergency = detect_emergency(message_text, config.emergency_keywords)
    if emergency["is_emergency"]:
        lead.is_emergency = True
        lead.emergency_type = emergency["emergency_type"]
        lead.urgency = "emergency"
        lead.score = 95

    db.add(lead)
    await db.flush()

    # Log lead creation
    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action="lead_created",
        message=f"New lead from {envelope.source}",
        data={"source": envelope.source, "is_emergency": lead.is_emergency},
    ))

    # Record inbound message if present
    if envelope.inbound_message:
        inbound_conv = Conversation(
            lead_id=lead.id,
            client_id=client.id,
            direction="inbound",
            content=envelope.inbound_message,
            from_phone=phone,
            to_phone=client.twilio_phone or "",
            delivery_status="received",
        )
        db.add(inbound_conv)
        lead.total_messages_received = 1
        lead.last_inbound_at = datetime.now(timezone.utc)

    # SPLIT COMMIT: Persist lead + consent + inbound conversation immediately
    # so the record survives even if SMS send fails or process crashes
    await db.commit()

    # Check for prior opt-out on this phone+client before responding
    prior_optout_result = await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.phone == phone,
            ConsentRecord.client_id == client.id,
            ConsentRecord.opted_out == True,
            ConsentRecord.id != consent.id,  # Exclude the just-created record
        ).limit(1)
    )
    prior_optout = prior_optout_result.scalar_one_or_none()

    # Run compliance check before responding
    compliance = full_compliance_check(
        has_consent=True,
        consent_type=consent.consent_type,
        is_opted_out=prior_optout is not None,
        state_code=lead.state_code,
        is_emergency=lead.is_emergency,
        message="",  # Content checked after template generation (line ~198)
        is_first_message=False,  # Skip content check here; real check is post-generation
        business_name=client.business_name,
    )

    if not compliance:
        logger.warning(
            "Compliance blocked new lead response: %s (lead=%s)",
            compliance.reason, str(lead.id)[:8],
        )
        lead.state = "new"
        await db.commit()
        return {
            "lead_id": str(lead.id),
            "status": f"compliance_blocked:{compliance.rule}",
            "response_ms": timer.elapsed_ms,
        }

    # Generate intake response (template-based, <2ms)
    intake_response = await process_intake(
        first_name=lead.first_name,
        service_type=lead.service_type,
        source=envelope.source,
        business_name=client.business_name,
        rep_name=config.persona.rep_name,
        message_text=message_text,
        custom_emergency_keywords=config.emergency_keywords,
    )

    # Content compliance check on the actual message
    from src.services.compliance import check_content_compliance
    content_check = check_content_compliance(
        intake_response.message, is_first_message=True, business_name=client.business_name
    )
    if not content_check:
        logger.error("Template failed content compliance: %s", content_check.reason)
        await db.commit()
        return {
            "lead_id": str(lead.id),
            "status": "template_compliance_error",
            "response_ms": timer.elapsed_ms,
        }

    # California SB 1001: Prepend AI disclosure on first message to CA numbers
    sms_body = intake_response.message
    if needs_ai_disclosure(phone, state_code=lead.state_code, ai_disclosure_sent=lead.ai_disclosure_sent):
        disclosure = get_ai_disclosure(client.business_name)
        sms_body = disclosure + sms_body
        lead.ai_disclosure_sent = True
        lead.ai_disclosure_sent_at = datetime.now(timezone.utc)
        logger.info("CA SB 1001: AI disclosure prepended for lead %s", str(lead.id)[:8])

    # SEND THE SMS - critical path, no retries to avoid blocking webhook
    logger.info("Pre-SMS overhead: %dms (lead=%s)", timer.elapsed_ms, str(lead.id)[:8])
    sms_result = await send_sms(
        to=phone,
        body=sms_body,
        from_phone=client.twilio_phone,
        messaging_service_sid=client.twilio_messaging_service_sid,
        no_retry=True,
    )

    # On transient failure, enqueue background retry instead of blocking
    if sms_result.get("status") == "transient_failure":
        from src.services.task_dispatch import enqueue_task
        await enqueue_task("sms_retry", payload={
            "lead_id": str(lead.id),
            "to": phone,
            "body": sms_body,
            "from_phone": client.twilio_phone,
            "messaging_service_sid": client.twilio_messaging_service_sid,
        }, priority=10, delay_seconds=5)
        logger.warning(
            "Lead %s: Twilio transient failure, SMS retry enqueued (code=%s)",
            str(lead.id)[:8], sms_result.get("error_code"),
        )

    response_ms = timer.stop()

    # Record outbound message
    outbound_conv = Conversation(
        lead_id=lead.id,
        client_id=client.id,
        direction="outbound",
        content=sms_body,
        from_phone=client.twilio_phone or "",
        to_phone=phone,
        agent_id="intake",
        sms_provider=sms_result.get("provider"),
        sms_sid=sms_result.get("sid"),
        delivery_status=sms_result.get("status", "sent"),
        segment_count=sms_result.get("segments", 1),
        sms_cost_usd=sms_result.get("cost_usd", 0.0),
    )
    db.add(outbound_conv)

    # Update lead state — even on transient failure, advance state
    # since the background retry will handle delivery
    lead.state = "intake_sent"
    lead.current_agent = "qualify"
    lead.first_response_ms = response_ms
    lead.total_messages_sent = 1
    lead.total_sms_cost_usd = sms_result.get("cost_usd", 0.0)
    lead.last_outbound_at = datetime.now(timezone.utc)

    # Log response event
    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action="intake_response_sent",
        duration_ms=response_ms,
        cost_usd=sms_result.get("cost_usd", 0.0),
        message=f"First response in {response_ms}ms via {sms_result.get('provider')}",
        data={
            "template": intake_response.template_id,
            "provider": sms_result.get("provider"),
            "segments": sms_result.get("segments"),
            "is_emergency": intake_response.is_emergency,
            "retry_enqueued": sms_result.get("status") == "transient_failure",
        },
    ))

    await db.commit()

    logger.info(
        "Lead %s: intake sent in %dms via %s (emergency=%s, retry=%s)",
        str(lead.id)[:8], response_ms, sms_result.get("provider"),
        lead.is_emergency, sms_result.get("status") == "transient_failure",
    )

    return {
        "lead_id": str(lead.id),
        "status": "intake_sent",
        "response_ms": response_ms,
    }


async def handle_inbound_reply(
    db: AsyncSession,
    lead: Lead,
    client: Client,
    message_text: str,
) -> dict:
    """
    Process an inbound SMS reply from an existing lead.
    Routes to the appropriate agent based on lead state.
    Uses Redis lock to prevent race conditions from simultaneous webhooks.
    """
    timer = Timer().start()
    config = ClientConfig(**client.config) if client.config else ClientConfig()

    # Check for opt-out FIRST - this overrides everything (no lock needed)
    if is_stop_keyword(message_text):
        return await _handle_opt_out(db, lead, client, message_text, timer)

    # Acquire lead lock to prevent concurrent processing
    try:
        async with lead_lock(str(lead.id)):
            return await _process_reply_locked(db, lead, client, config, message_text, timer)
    except LockTimeoutError:
        logger.warning(
            "Lead %s lock timeout - another webhook is processing this lead",
            str(lead.id)[:8],
        )
        return {"lead_id": str(lead.id), "status": "lock_timeout", "response_ms": timer.elapsed_ms}


async def _process_reply_locked(
    db: AsyncSession,
    lead: Lead,
    client: Client,
    config: ClientConfig,
    message_text: str,
    timer: Timer,
) -> dict:
    """Process a reply while holding the lead lock."""

    # Check for emergency
    emergency = detect_emergency(message_text, config.emergency_keywords)
    if emergency["is_emergency"]:
        lead.is_emergency = True
        lead.emergency_type = emergency["emergency_type"]
        lead.urgency = "emergency"
        lead.score = max(lead.score, 90)

    # Record inbound message
    inbound_conv = Conversation(
        lead_id=lead.id,
        client_id=client.id,
        direction="inbound",
        content=message_text,
        from_phone=lead.phone,
        to_phone=client.twilio_phone or "",
        delivery_status="received",
    )
    db.add(inbound_conv)
    lead.total_messages_received += 1
    lead.last_inbound_at = datetime.now(timezone.utc)
    lead.conversation_turn += 1

    # Re-engage cold leads
    if lead.state in ("cold", "dead"):
        previous = lead.state
        lead.state = "qualifying"
        lead.current_agent = "qualify"
        lead.score = max(lead.score, 50)

        # Learning signal: lead re-engaged from cold/dead
        from src.services.learning import record_lead_signal
        asyncio.ensure_future(record_lead_signal(
            lead_id=str(lead.id),
            signal_type="lead_reengaged",
            metadata={
                "previous_state": previous,
                "source": lead.source,
                "trade": client.trade_type,
            },
        ))

    # Enforce conversation turn limit (max 10 turns of AI conversation)
    from src.config import get_settings
    max_turns = get_settings().max_conversation_turns
    if lead.conversation_turn > max_turns and lead.state in ("qualifying", "booking"):
        logger.warning(
            "Lead %s hit conversation turn limit (%d). Escalating to human.",
            str(lead.id)[:8], max_turns,
        )
        lead.state = "booking" if lead.state == "qualifying" else lead.state
        db.add(EventLog(
            lead_id=lead.id,
            client_id=client.id,
            action="turn_limit_reached",
            message=f"Conversation hit {max_turns} turn limit - needs human follow-up",
            data={"turns": lead.conversation_turn, "limit": max_turns},
        ))
        response = {
            "message": f"Thanks for your patience! Let me get our team lead to help you directly. Someone will reach out to you shortly.",
            "agent_id": "system",
            "ai_cost": 0.0,
        }
    # Route to appropriate agent
    elif lead.state in ("intake_sent", "qualifying"):
        response = await _route_to_qualify(db, lead, client, config, message_text)
    elif lead.state in ("qualified", "booking"):
        response = await _route_to_book(db, lead, client, config, message_text)
    else:
        # Default: qualify
        response = await _route_to_qualify(db, lead, client, config, message_text)

    response_ms = timer.stop()

    if response and response.get("message"):
        # Check actual consent opt-out status from DB
        reply_opted_out = False
        if lead.consent_id:
            reply_consent = await db.get(ConsentRecord, lead.consent_id)
            reply_opted_out = reply_consent.opted_out if reply_consent else False

        # Compliance check before sending
        compliance = full_compliance_check(
            has_consent=True,
            consent_type="pec",
            is_opted_out=reply_opted_out,
            state_code=lead.state_code,
            is_emergency=lead.is_emergency,
            is_reply_to_inbound=True,
            message=response["message"],
            is_first_message=False,
            business_name=client.business_name,
        )

        if compliance:
            sms_result = await send_sms(
                to=lead.phone,
                body=response["message"],
                from_phone=client.twilio_phone,
                messaging_service_sid=client.twilio_messaging_service_sid,
            )

            outbound_conv = Conversation(
                lead_id=lead.id,
                client_id=client.id,
                direction="outbound",
                content=response["message"],
                from_phone=client.twilio_phone or "",
                to_phone=lead.phone,
                agent_id=response.get("agent_id", "qualify"),
                sms_provider=sms_result.get("provider"),
                sms_sid=sms_result.get("sid"),
                delivery_status=sms_result.get("status", "sent"),
                segment_count=sms_result.get("segments", 1),
                sms_cost_usd=sms_result.get("cost_usd", 0.0),
                ai_cost_usd=response.get("ai_cost", 0.0),
                ai_latency_ms=response.get("ai_latency_ms"),
            )
            db.add(outbound_conv)

            lead.total_messages_sent += 1
            lead.total_sms_cost_usd += sms_result.get("cost_usd", 0.0)
            lead.total_ai_cost_usd += response.get("ai_cost", 0.0)
            lead.last_outbound_at = datetime.now(timezone.utc)
            lead.last_agent_response = response["message"]
        else:
            logger.warning("Compliance blocked reply: %s", compliance.reason)

    await db.commit()
    return {"lead_id": str(lead.id), "status": lead.state, "response_ms": response_ms}


async def _route_to_qualify(
    db: AsyncSession, lead: Lead, client: Client, config: ClientConfig, message: str
) -> dict:
    """Route lead to the qualify agent."""
    # Assign qualify variant if not yet set (deterministic per lead)
    if not lead.qualify_variant:
        from src.agents.qualify import select_variant
        lead.qualify_variant = select_variant(str(lead.id))

    # Build conversation history
    conversations = []
    for conv in lead.conversations:
        conversations.append({
            "direction": conv.direction,
            "content": conv.content,
        })

    result = await process_qualify(
        lead_message=message,
        conversation_history=conversations,
        current_qualification=lead.qualification_data or {},
        business_name=client.business_name,
        rep_name=config.persona.rep_name,
        trade_type=client.trade_type,
        services=config.services.model_dump() if config.services else {},
        conversation_turn=lead.conversation_turn,
        variant=lead.qualify_variant,
    )

    # Update lead with qualification data
    if result.qualification:
        qual_data = lead.qualification_data or {}
        if result.qualification.service_type:
            qual_data["service_type"] = result.qualification.service_type
            lead.service_type = result.qualification.service_type
        if result.qualification.urgency:
            qual_data["urgency"] = result.qualification.urgency
            lead.urgency = result.qualification.urgency
        if result.qualification.property_type:
            qual_data["property_type"] = result.qualification.property_type
            lead.property_type = result.qualification.property_type
        if result.qualification.preferred_date:
            qual_data["preferred_date"] = result.qualification.preferred_date
        lead.qualification_data = qual_data

    # Apply score adjustment
    lead.score = max(0, min(100, lead.score + result.score_adjustment))

    # State transition based on agent's recommendation
    if result.next_action == "ready_to_book":
        lead.state = "qualified"
        lead.current_agent = "book"
        # Learning signal: lead qualified
        from src.services.learning import record_lead_signal
        asyncio.ensure_future(record_lead_signal(
            lead_id=str(lead.id),
            signal_type="lead_qualified",
            metadata={
                "qualify_variant": getattr(lead, "qualify_variant", None),
                "response_count": lead.conversation_turn,
                "source": lead.source,
                "trade": client.trade_type,
            },
        ))
    elif result.next_action == "mark_cold":
        lead.state = "cold"
        lead.current_agent = "followup"
        # Learning signal: lead went cold
        from src.services.learning import record_lead_signal
        asyncio.ensure_future(record_lead_signal(
            lead_id=str(lead.id),
            signal_type="lead_went_cold",
            metadata={
                "qualify_variant": getattr(lead, "qualify_variant", None),
                "response_count": lead.conversation_turn,
                "source": lead.source,
                "trade": client.trade_type,
            },
        ))
    elif result.next_action == "escalate_emergency":
        lead.is_emergency = True
        lead.urgency = "emergency"
    else:
        lead.state = "qualifying"

    return {
        "message": result.message,
        "agent_id": "qualify",
        "ai_cost": getattr(result, "ai_cost_usd", 0.0),
        "ai_latency_ms": getattr(result, "ai_latency_ms", None),
    }


async def _route_to_book(
    db: AsyncSession, lead: Lead, client: Client, config: ClientConfig, message: str
) -> dict:
    """Route lead to the booking agent."""
    conversations = [
        {"direction": c.direction, "content": c.content}
        for c in lead.conversations
    ]

    # Resolve booking_url: ClientConfig first, then SalesEngineConfig fallback
    booking_url = config.booking_url
    if not booking_url:
        try:
            from src.services.config_cache import get_sales_config
            sales_config = await get_sales_config(tenant_id=client.id)
            if sales_config:
                booking_url = sales_config.get("booking_url")
        except (KeyError, TypeError, ValueError, OSError):
            pass  # Non-critical — proceed without booking URL

    result = await process_booking(
        lead_message=message,
        first_name=lead.first_name or "there",
        service_type=lead.service_type or "service",
        preferred_date=(lead.qualification_data or {}).get("preferred_date"),
        business_name=client.business_name,
        rep_name=config.persona.rep_name,
        scheduling_config=config.scheduling.model_dump() if config.scheduling else {},
        team_members=[t.model_dump() for t in config.team] if config.team else [],
        hours_config=config.hours.model_dump() if config.hours else {},
        conversation_history=conversations,
        booking_url=booking_url,
    )

    if result.booking_confirmed:
        lead.state = "booked"
        lead.current_agent = None

        # Create booking record (CRM sync happens asynchronously)
        from src.models.booking import Booking
        parsed_date = None
        if result.appointment_date:
            try:
                parsed_date = datetime.strptime(result.appointment_date, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(
                    "AI returned unparseable appointment_date '%s' for lead %s",
                    result.appointment_date, str(lead.id)[:8],
                )
        # Parse time window from "HH:MM" strings
        from datetime import time as time_type
        parsed_start = None
        parsed_end = None
        for raw_val, label in [(result.time_window_start, "start"), (result.time_window_end, "end")]:
            if raw_val:
                try:
                    parts = raw_val.split(":")
                    parsed_time = time_type(int(parts[0]), int(parts[1]))
                    if label == "start":
                        parsed_start = parsed_time
                    else:
                        parsed_end = parsed_time
                except (ValueError, IndexError):
                    logger.warning(
                        "AI returned unparseable time_window_%s '%s' for lead %s",
                        label, raw_val, str(lead.id)[:8],
                    )

        booking = Booking(
            lead_id=lead.id,
            client_id=client.id,
            appointment_date=parsed_date or datetime.now(timezone.utc).date(),
            time_window_start=parsed_start,
            time_window_end=parsed_end,
            service_type=lead.service_type or "service",
            tech_name=result.tech_name,
            crm_sync_status="pending",
        )
        db.add(booking)

        db.add(EventLog(
            lead_id=lead.id,
            client_id=client.id,
            action="booking_confirmed",
            message=f"Appointment booked for {result.appointment_date}",
        ))

        # Learning signal: lead booked
        from src.services.learning import record_lead_signal
        asyncio.ensure_future(record_lead_signal(
            lead_id=str(lead.id),
            signal_type="lead_booked",
            metadata={
                "qualify_variant": getattr(lead, "qualify_variant", None),
                "response_count": lead.conversation_turn,
                "source": lead.source,
                "trade": client.trade_type,
            },
        ))
    elif result.needs_human_handoff:
        lead.state = "booking"
        db.add(EventLog(
            lead_id=lead.id,
            client_id=client.id,
            action="human_handoff_needed",
            message="Booking agent needs human assistance",
        ))
    else:
        lead.state = "booking"

    return {
        "message": result.message,
        "agent_id": "book",
        "ai_cost": getattr(result, "ai_cost_usd", 0.0),
        "ai_latency_ms": getattr(result, "ai_latency_ms", None),
    }


async def _handle_opt_out(
    db: AsyncSession, lead: Lead, client: Client, message: str, timer: Timer
) -> dict:
    """Process STOP/opt-out. Immediately cease all messaging."""
    lead.previous_state = lead.state
    lead.state = "opted_out"
    lead.current_agent = None

    # Update consent record
    if lead.consent_id:
        consent = await db.get(ConsentRecord, lead.consent_id)
        if consent:
            consent.opted_out = True
            consent.opted_out_at = datetime.now(timezone.utc)
            consent.opt_out_method = "sms_stop"
            consent.is_active = False

    # Record the inbound STOP message
    db.add(Conversation(
        lead_id=lead.id,
        client_id=client.id,
        direction="inbound",
        content=message,
        from_phone=lead.phone,
        to_phone=client.twilio_phone or "",
        delivery_status="received",
    ))

    db.add(EventLog(
        lead_id=lead.id,
        client_id=client.id,
        action="opt_out",
        message=f"Lead opted out via SMS: '{message}'",
    ))

    # Cancel any pending followups
    from src.models.followup import FollowupTask
    from sqlalchemy import update
    await db.execute(
        update(FollowupTask)
        .where(FollowupTask.lead_id == lead.id, FollowupTask.status == "pending")
        .values(status="cancelled", skip_reason="Lead opted out")
    )

    await db.commit()

    logger.info("Lead %s opted out via '%s'", str(lead.id)[:8], message)
    return {
        "lead_id": str(lead.id),
        "status": "opted_out",
        "response_ms": timer.elapsed_ms,
    }
