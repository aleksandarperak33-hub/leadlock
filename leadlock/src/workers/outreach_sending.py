"""
Outreach email sending — generate and send a single outreach email for a prospect.
Extracted from outreach_sequencer.py for file size compliance.
"""
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote
from typing import Optional
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outreach import Outreach
from src.models.outreach_email import OutreachEmail
from src.models.email_blacklist import EmailBlacklist
from src.models.email_template import EmailTemplate
from src.models.campaign import Campaign
from src.models.sales_config import SalesEngineConfig
from src.agents.sales_outreach import generate_outreach_email
from src.services.cold_email import send_cold_email
from src.services.sender_mailboxes import get_active_sender_mailboxes
from src.services.outreach_timing import followup_readiness
from src.utils.email_validation import validate_email

logger = logging.getLogger(__name__)


def sanitize_dashes(text: str) -> str:
    """Replace em dashes, en dashes, and other unicode dashes with regular hyphens."""
    if not text:
        return text
    return (
        text
        .replace("\u2014", "-")   # em dash
        .replace("\u2013", "-")   # en dash
        .replace("\u2012", "-")   # figure dash
        .replace("\u2015", "-")   # horizontal bar
        .replace("\u2010", "-")   # hyphen
        .replace("\u2011", "-")   # non-breaking hyphen
    )


def normalize_email(raw_email: str) -> str:
    """Normalize noisy email strings from scraping/enrichment sources."""
    if not raw_email:
        return ""

    email = unquote(raw_email).strip().strip("\"\'<>")
    if email.lower().startswith("mailto:"):
        email = email[7:]

    # Strip whitespace that can be URL-encoded as %20 or copied from HTML.
    email = "".join(email.split())
    return email.lower()


async def _verify_or_find_working_email(prospect: Outreach) -> Optional[str]:
    """
    Discover a real email for a pattern-guessed prospect using deep web
    scraping and Brave Search (replaces broken SMTP verification —
    port 25 blocked on VPS).

    Returns:
        Discovered email address, or None if no real email found.
    """
    from src.services.email_discovery import discover_email

    try:
        discovery = await discover_email(
            website=prospect.website or "",
            company_name=prospect.prospect_company or prospect.prospect_name,
            enrichment_data=prospect.enrichment_data,
        )
    except Exception as e:
        logger.warning(
            "Email discovery failed for prospect %s: %s",
            str(prospect.id)[:8], str(e),
        )
        return None

    email = discovery.get("email")
    source = discovery.get("source")
    confidence = discovery.get("confidence")

    if not email:
        logger.info(
            "No email found for prospect %s via discovery",
            str(prospect.id)[:8],
        )
        return None

    # Only accept non-pattern-guess results
    if source == "pattern_guess":
        logger.info(
            "Only pattern guess available for prospect %s, skipping",
            str(prospect.id)[:8],
        )
        return None

    # Update source metadata on the prospect
    prospect.email_source = source
    prospect.email_verified = confidence == "high"
    cost = discovery.get("cost_usd", 0.0)
    if cost > 0:
        prospect.total_cost_usd = (prospect.total_cost_usd or 0) + cost

    return email


async def _pre_send_checks(
    db: AsyncSession,
    prospect: Outreach,
) -> Optional[str]:
    """
    Run pre-send validation: email format, pattern-guess verification,
    blacklist, and dedup checks.

    Returns:
        None if all checks pass, or a skip reason string.
    """
    # Normalize and validate email format
    normalized_email = normalize_email(prospect.prospect_email or "")
    if normalized_email != (prospect.prospect_email or ""):
        logger.info(
            "Normalized prospect email for %s: %s -> %s",
            str(prospect.id)[:8],
            (prospect.prospect_email or "")[:32],
            normalized_email[:32],
        )
    prospect.prospect_email = normalized_email

    # Lifecycle safety: never send to unsubscribed/replied/terminal leads.
    if prospect.email_unsubscribed:
        return "unsubscribed"
    if prospect.last_email_replied_at is not None:
        return "already replied"
    current_status = (prospect.status or "").strip().lower()
    if current_status and current_status not in {"cold", "contacted"}:
        return f"status not send-eligible ({current_status})"

    email_check = await validate_email(prospect.prospect_email)
    if not email_check["valid"]:
        return f"invalid email ({email_check['reason']})"

    # Gate: on first touch, always attempt to replace pattern-guessed emails
    # with a discovered real address (higher deliverability).
    # Follow-ups can proceed without rediscovery because initial send already passed.
    if prospect.email_source == "pattern_guess" and prospect.outreach_sequence_step <= 0:
        verified_email = await _verify_or_find_working_email(prospect)
        if verified_email is None:
            prospect.status = "no_verified_email"
            return "no verified email found"
        # Update prospect with the (possibly different) verified email
        if verified_email != prospect.prospect_email:
            logger.info(
                "Prospect %s: swapped email from %s*** to %s***",
                str(prospect.id)[:8],
                prospect.prospect_email[:12],
                verified_email[:12],
            )
        prospect.prospect_email = normalize_email(verified_email)
        prospect.email_verified = True

    # Check blacklist (email and domain)
    email_lower = prospect.prospect_email.lower().strip()
    domain = email_lower.split("@")[1] if "@" in email_lower else ""
    blacklist_check = await db.execute(
        select(EmailBlacklist).where(
            EmailBlacklist.value.in_([email_lower, domain])
        ).limit(1)
    )
    if blacklist_check.scalar_one_or_none():
        return "blacklisted"

    # Temporary domain cooldown after repeated bounce events.
    if domain:
        try:
            from src.utils.dedup import get_redis
            redis = await get_redis()
            cooldown_key = f"leadlock:email_domain_cooldown:{domain}"
            ttl = await redis.ttl(cooldown_key)
            if ttl and ttl > 0:
                return f"domain cooldown active ({ttl}s remaining)"
        except Exception as e:
            logger.debug("Domain cooldown check unavailable: %s", str(e))

    # Dedup: skip if another record with same email was already contacted
    if prospect.prospect_email:
        dupe_check = await db.execute(
            select(Outreach).where(
                and_(
                    Outreach.prospect_email == email_lower,
                    Outreach.id != prospect.id,
                    Outreach.total_emails_sent > 0,
                )
            ).limit(1)
        )
        if dupe_check.scalar_one_or_none():
            prospect.status = "duplicate_email"
            return "email already contacted via another record"

    return None


async def _generate_email_with_template(
    prospect: Outreach,
    next_step: int,
    template: Optional[EmailTemplate] = None,
    sender_name: str = "Alek",
    enrichment_data: Optional[dict] = None,
    booking_url: Optional[str] = None,
) -> dict:
    """
    Generate an outreach email, optionally using a template.
    Checks for active A/B experiments and injects variant instructions.
    """
    from src.agents.sales_outreach import _extract_first_name
    first_name = _extract_first_name(prospect.prospect_name or "")

    if template and not template.is_ai_generated and template.body_template:
        # Static template with variable substitution
        company_fallback = prospect.prospect_company or prospect.prospect_name or ""
        substitutions = {
            "{prospect_name}": prospect.prospect_name or "",
            "{first_name}": first_name or f"{company_fallback} team",
            "{company}": company_fallback,
            "{city}": prospect.city or "",
            "{trade}": prospect.prospect_trade_type or "home services",
            "{sender_name}": sender_name,
        }

        body_text = template.body_template
        subject = template.subject_template or f"Quick question for {prospect.prospect_company or prospect.prospect_name}"

        for key, value in substitutions.items():
            body_text = body_text.replace(key, value)
            subject = subject.replace(key, value)

        body_html = body_text.replace("\n", "<br>")

        return {
            "subject": sanitize_dashes(subject),
            "body_html": sanitize_dashes(body_html),
            "body_text": sanitize_dashes(body_text),
            "ai_cost_usd": 0.0,
        }

    # Check for active A/B experiment for this step
    ab_variant = None
    ab_extra_instruction = None
    try:
        from src.services.ab_testing import get_active_experiment, assign_variant

        experiment = await get_active_experiment(
            sequence_step=next_step,
            trade_type=prospect.prospect_trade_type,
        )
        if experiment and experiment.get("variants"):
            ab_variant = assign_variant(experiment["variants"])
            if ab_variant and ab_variant.get("instruction"):
                ab_extra_instruction = (
                    f"SUBJECT LINE INSTRUCTION (A/B test): {ab_variant['instruction']}"
                )
    except Exception as e:
        logger.debug("A/B experiment lookup failed (proceeding without): %s", str(e))

    # AI-generated email (with optional extra instructions from template + A/B variant)
    extra_instructions = None
    if template and template.is_ai_generated and template.ai_instructions:
        extra_instructions = template.ai_instructions

    # Combine template instructions with A/B variant instruction
    if ab_extra_instruction:
        extra_instructions = (
            f"{extra_instructions}\n\n{ab_extra_instruction}"
            if extra_instructions
            else ab_extra_instruction
        )

    # If no AB experiment and no template instructions, inject winning patterns
    if not ab_extra_instruction and not extra_instructions:
        try:
            from src.services.winning_patterns import format_patterns_for_prompt

            patterns = await format_patterns_for_prompt(
                trade=prospect.prospect_trade_type,
                step=next_step,
            )
            if patterns:
                extra_instructions = patterns
        except Exception as e:
            logger.debug("Winning patterns lookup failed: %s", str(e))

    result = await generate_outreach_email(
        prospect_name=prospect.prospect_name,
        company_name=prospect.prospect_company or prospect.prospect_name,
        trade_type=prospect.prospect_trade_type or "general",
        city=prospect.city or "",
        state=prospect.state_code or "",
        rating=prospect.google_rating,
        review_count=prospect.review_count,
        website=prospect.website,
        sequence_step=next_step,
        extra_instructions=extra_instructions,
        sender_name=sender_name,
        enrichment_data=enrichment_data,
        prospect_email=prospect.prospect_email,
        booking_url=booking_url,
    )

    # Attach A/B variant info for tracking
    if ab_variant:
        result["ab_variant_id"] = ab_variant.get("id")

    return result


async def send_sequence_email(
    db: AsyncSession,
    config: SalesEngineConfig,
    settings,
    prospect: Outreach,
    template_id: Optional[str] = None,
    campaign: Optional[Campaign] = None,
):
    """Generate and send a single outreach email for a prospect."""
    next_step = prospect.outreach_sequence_step + 1

    # Hard cap: never exceed max_sequence_steps regardless of campaign definition.
    if next_step > config.max_sequence_steps:
        logger.info(
            "Prospect %s at max touches (%d/%d) — skipping",
            str(prospect.id)[:8], prospect.outreach_sequence_step, config.max_sequence_steps,
        )
        return

    # Cadence guardrail - never send follow-ups too soon.
    if next_step > 1:
        is_due, required_delay, remaining_seconds = followup_readiness(
            prospect, base_delay_hours=config.sequence_delay_hours
        )
        if not is_due:
            logger.info(
                "Skipping prospect %s - follow-up not due (required=%dh remaining=%ds)",
                str(prospect.id)[:8], required_delay, remaining_seconds,
            )
            return

    # Pre-send validation (email, blacklist, dedup)
    skip_reason = await _pre_send_checks(db, prospect)
    if skip_reason:
        logger.info(
            "Skipping prospect %s - %s",
            str(prospect.id)[:8], skip_reason,
        )
        return

    # Load template if specified
    template = None
    if template_id:
        try:
            template_uuid = uuid.UUID(template_id)
            template_result = await db.execute(
                select(EmailTemplate).where(
                    and_(
                        EmailTemplate.id == template_uuid,
                        or_(
                            EmailTemplate.tenant_id == prospect.tenant_id,
                            EmailTemplate.tenant_id.is_(None),
                        ),
                    )
                ).limit(1)
            )
            template = template_result.scalar_one_or_none()
        except Exception as e:
            logger.warning(
                "Template %s not found for prospect %s",
                template_id, str(prospect.id)[:8],
            )

    sender_profile = await _choose_sender_profile(db, config, prospect, next_step)
    if not sender_profile:
        logger.warning(
            "No active sender mailbox for prospect %s",
            str(prospect.id)[:8],
        )
        return

    # CTA A/B split: deterministic 50/50 based on prospect ID
    # "calendar" = includes booking link, "question" = question-based CTA
    cta_variant = "calendar" if hash(str(prospect.id)) % 2 == 0 else "question"
    effective_booking_url = config.booking_url if cta_variant == "calendar" else None

    # Generate personalized email
    email_result = await _generate_email_with_template(
        prospect=prospect,
        next_step=next_step,
        template=template,
        sender_name=sender_profile["sender_name"],
        enrichment_data=prospect.enrichment_data,
        booking_url=effective_booking_url,
    )

    if email_result.get("error"):
        logger.warning(
            "Email generation failed for prospect %s: %s",
            str(prospect.id)[:8], email_result["error"],
        )
        prospect.generation_failures = (prospect.generation_failures or 0) + 1
        if prospect.generation_failures >= 3:
            prospect.status = "generation_failed"
            logger.warning(
                "Prospect %s marked generation_failed after %d failures",
                str(prospect.id)[:8], prospect.generation_failures,
            )
        return

    # Sanitize dashes from AI-generated content and attach CTA variant for tracking
    email_result = {
        **email_result,
        "subject": sanitize_dashes(email_result.get("subject", "")),
        "body_html": sanitize_dashes(email_result.get("body_html", "")),
        "body_text": sanitize_dashes(email_result.get("body_text", "")),
        "cta_variant": cta_variant,
    }

    # Quality gate
    email_result = await _run_quality_gate(
        email_result, prospect, next_step, template, config,
    )

    # Build unsubscribe URL
    base_url = settings.app_base_url.rstrip("/")
    unsubscribe_url = f"{base_url}/api/v1/sales/unsubscribe/{prospect.id}"

    # Threading headers for follow-ups
    in_reply_to, references, send_subject = await _resolve_threading(
        db, prospect, next_step, email_result["subject"],
    )

    # Send email
    send_result = await send_cold_email(
        to_email=prospect.prospect_email,
        to_name=prospect.prospect_name,
        subject=send_subject,
        body_html=email_result["body_html"],
        from_email=sender_profile["from_email"],
        from_name=sender_profile["from_name"] or "LeadLock",
        reply_to=sender_profile["reply_to_email"] or sender_profile["from_email"],
        unsubscribe_url=unsubscribe_url,
        company_address=config.company_address or "",
        custom_args={
            "outreach_id": str(prospect.id),
            "step": str(next_step),
        },
        in_reply_to=in_reply_to,
        references=references,
        body_text=email_result.get("body_text", ""),
        company_name="LeadLock",
    )

    if send_result.get("error"):
        logger.warning(
            "Email send failed for prospect %s: %s",
            str(prospect.id)[:8], send_result["error"],
        )
        return

    # Record send and update prospect
    await _record_send(
        db, prospect, config, campaign, next_step,
        send_subject, email_result, send_result, sender_profile,
    )


async def _choose_sender_profile(
    db: AsyncSession,
    config: SalesEngineConfig,
    prospect: Outreach,
    next_step: int,
) -> Optional[dict]:
    """
    Pick a mailbox for this send using deterministic round-robin.
    Respects optional per-mailbox daily_limit when configured.
    """
    profiles = get_active_sender_mailboxes(config)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    seed = uuid.UUID(str(prospect.id)).int + int(next_step)
    start_index = seed % len(profiles)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for offset in range(len(profiles)):
        profile = profiles[(start_index + offset) % len(profiles)]
        mailbox_limit = profile.get("daily_limit")
        if not mailbox_limit:
            return profile

        sent_today_query = (
            select(func.count())
            .select_from(OutreachEmail)
            .join(Outreach, OutreachEmail.outreach_id == Outreach.id)
            .where(
                and_(
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.from_email == profile["from_email"],
                    OutreachEmail.sent_at >= today_start,
                    Outreach.tenant_id == prospect.tenant_id if prospect.tenant_id else True,
                )
            )
        )
        sent_today_result = await db.execute(sent_today_query)
        sent_today = sent_today_result.scalar() or 0
        if sent_today < mailbox_limit:
            return profile

    return profiles[start_index]


async def _run_quality_gate(
    email_result: dict,
    prospect: Outreach,
    next_step: int,
    template: Optional[EmailTemplate],
    config: SalesEngineConfig,
) -> dict:
    """Run quality gate on generated email, regenerate once if it fails.

    On 2nd failure, falls back to the deterministic template which always
    passes quality checks — never sends a bad AI-generated email.
    """
    try:
        from src.services.email_quality_gate import check_email_quality
        from src.agents.sales_outreach import _build_fallback_outreach_email, _extract_first_name

        qg_kwargs = dict(
            prospect_name=prospect.prospect_name,
            company_name=prospect.prospect_company,
            city=prospect.city,
            trade_type=prospect.prospect_trade_type,
            sequence_step=next_step,
        )
        quality = check_email_quality(
            subject=email_result["subject"],
            body_text=email_result["body_text"],
            **qg_kwargs,
        )
        if not quality["passed"]:
            logger.info(
                "Quality gate failed for %s (step %d): %s - regenerating",
                str(prospect.id)[:8], next_step, "; ".join(quality["issues"]),
            )
            retry_result = await _generate_email_with_template(
                prospect=prospect,
                next_step=next_step,
                template=template,
                sender_name=config.sender_name or "Alek",
                enrichment_data=prospect.enrichment_data,
                booking_url=config.booking_url,
            )
            if not retry_result.get("error"):
                retry_result = {
                    **retry_result,
                    "subject": sanitize_dashes(retry_result.get("subject", "")),
                    "body_html": sanitize_dashes(retry_result.get("body_html", "")),
                    "body_text": sanitize_dashes(retry_result.get("body_text", "")),
                }
                retry_quality = check_email_quality(
                    subject=retry_result["subject"],
                    body_text=retry_result["body_text"],
                    **qg_kwargs,
                )
                if retry_quality["passed"]:
                    return retry_result

            # 2nd failure (or retry error): use deterministic fallback
            logger.warning(
                "Quality gate still failing for %s after retry - using fallback template",
                str(prospect.id)[:8],
            )
            fallback = _build_fallback_outreach_email(
                prospect_name=prospect.prospect_name or "",
                company_name=prospect.prospect_company or prospect.prospect_name or "",
                trade_type=prospect.prospect_trade_type or "general",
                city=prospect.city or "",
                state=prospect.state_code or "",
                sequence_step=next_step,
                sender_name=config.sender_name or "Alek",
                rating=prospect.google_rating,
                review_count=prospect.review_count,
            )
            result = {
                **fallback,
                "subject": sanitize_dashes(fallback["subject"]),
                "body_html": sanitize_dashes(fallback["body_html"]),
                "body_text": sanitize_dashes(fallback["body_text"]),
            }
            # Preserve A/B variant ID so tracking isn't silently lost
            if email_result.get("ab_variant_id"):
                result["ab_variant_id"] = email_result["ab_variant_id"]
            return result
    except Exception as qg_err:
        logger.debug("Quality gate check failed: %s", str(qg_err))

    return email_result


async def _resolve_threading(
    db: AsyncSession,
    prospect: Outreach,
    next_step: int,
    subject: str,
) -> tuple[Optional[str], Optional[str], str]:
    """
    Resolve email threading headers for follow-up emails.
    Returns (in_reply_to, references, send_subject).
    """
    in_reply_to = None
    references = None
    send_subject = subject

    if next_step > 1:
        prev_email_result = await db.execute(
            select(OutreachEmail).where(
                and_(
                    OutreachEmail.outreach_id == prospect.id,
                    OutreachEmail.direction == "outbound",
                    OutreachEmail.sendgrid_message_id.isnot(None),
                )
            ).order_by(OutreachEmail.sequence_step.desc()).limit(1)
        )
        prev_email = prev_email_result.scalar_one_or_none()
        if prev_email and prev_email.sendgrid_message_id:
            in_reply_to = prev_email.sendgrid_message_id
            references = f"<{prev_email.sendgrid_message_id}>"

        # Reuse step 1 subject with "Re:" for Gmail threading
        if in_reply_to:
            step1_result = await db.execute(
                select(OutreachEmail.subject).where(
                    and_(
                        OutreachEmail.outreach_id == prospect.id,
                        OutreachEmail.direction == "outbound",
                        OutreachEmail.sequence_step == 1,
                    )
                ).limit(1)
            )
            step1_subject = step1_result.scalar()
            if step1_subject:
                send_subject = f"Re: {step1_subject}"

    return in_reply_to, references, send_subject


async def _record_send(
    db: AsyncSession,
    prospect: Outreach,
    config: SalesEngineConfig,
    campaign: Optional[Campaign],
    next_step: int,
    send_subject: str,
    email_result: dict,
    send_result: dict,
    sender_profile: dict,
) -> None:
    """Record the sent email and update prospect state."""
    # Record email reputation event
    try:
        from src.utils.dedup import get_redis
        from src.services.deliverability import record_email_event
        redis = await get_redis()
        await record_email_event(redis, "sent")
    except Exception as rep_err:
        logger.debug("Failed to record email send event: %s", str(rep_err))

    now = datetime.now(timezone.utc)

    # Parse A/B variant UUID
    ab_variant_id_str = email_result.get("ab_variant_id")
    ab_variant_uuid = None
    if ab_variant_id_str:
        try:
            ab_variant_uuid = uuid.UUID(ab_variant_id_str)
        except (ValueError, TypeError):
            pass

    email_record = OutreachEmail(
        outreach_id=prospect.id,
        direction="outbound",
        subject=send_subject,
        body_html=email_result["body_html"],
        body_text=email_result["body_text"],
        from_email=sender_profile["from_email"],
        to_email=prospect.prospect_email,
        sendgrid_message_id=send_result.get("message_id"),
        sequence_step=next_step,
        sent_at=now,
        ai_cost_usd=email_result.get("ai_cost_usd", 0.0),
        fallback_used=email_result.get("fallback_used", False),
        ab_variant_id=ab_variant_uuid,
        cta_variant=email_result.get("cta_variant"),
    )
    db.add(email_record)

    # Track A/B variant send event
    if ab_variant_id_str:
        try:
            from src.services.ab_testing import record_event
            await record_event(ab_variant_id_str, "sent")
        except Exception as ab_err:
            logger.debug("A/B send tracking failed: %s", str(ab_err))

    # Update prospect
    total_email_cost = email_result.get("ai_cost_usd", 0.0) + send_result.get("cost_usd", 0.0)
    prospect.outreach_sequence_step = next_step
    prospect.last_email_sent_at = now
    prospect.total_emails_sent = (prospect.total_emails_sent or 0) + 1
    prospect.total_cost_usd = (prospect.total_cost_usd or 0.0) + total_email_cost
    prospect.updated_at = now

    if prospect.status == "cold":
        prospect.status = "contacted"

    logger.info(
        "Outreach email sent: prospect=%s step=%d to=%s campaign=%s",
        str(prospect.id)[:8], next_step, prospect.prospect_email[:20] + "***",
        str(campaign.id)[:8] if campaign else "none",
    )
