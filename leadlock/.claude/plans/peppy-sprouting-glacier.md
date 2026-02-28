# Outreach Engine Scaling Plan — Path to $10M MRR

## Context

LeadLock sells to home services contractors (HVAC, plumbing, roofing, electrical, solar) across the entire US — TAM is ~2.8M businesses. At $497–$3,500/month, $10M MRR needs 2,800–20,000 clients. That requires aggressive, high-volume outbound with sustained deliverability.

**Current bottlenecks:**
1. **Email reputation is global** — one bad domain poisons ALL sending
2. **Prospects are terminal** — after 3 emails + 1 winback, prospects are dead forever
3. **Step 3 wastes sends** — fires even when prospect never opened steps 1-2
4. **Fixed timing** — misses engagement windows

**5 features, single consolidated migration, phased rollout.**

---

## Phase 1: Per-Domain + Per-Mailbox Email Reputation (Foundation)

Without domain-level isolation, scaling to 1,500+ emails/day across multiple domains will inevitably tank all sending when a single domain degrades.

### 1a. Extend `src/services/deliverability.py`

**Extract shared scoring logic:**
- Refactor `get_email_reputation()` lines 338-448 into a pure function `_compute_email_score(metrics: dict) -> dict` that takes `{sent, delivered, bounced, complained, opened, clicked}` and returns `{score, status, throttle, metrics}`
- `get_email_reputation()` calls it (backward compatible, no behavior change)

**New function: `record_email_event_scoped(redis, event_type, domain="", from_email="")`**
- Records to 3 scopes in a single `redis.pipeline()`:
  - Global: `email:reputation:{event_type}` (existing key, backward compatible)
  - Per-domain: `email:reputation:domain:{domain}:{event_type}`
  - Per-mailbox: `email:reputation:mailbox:{from_email}:{event_type}`
- All keys get `EMAIL_REPUTATION_TTL` (86400s)
- Skips domain/mailbox keys if params are empty

**New function: `get_email_reputation_scoped(redis, scope="global", scope_key="")`**
- `scope` is `"global"` | `"domain"` | `"mailbox"`
- Reads from `email:reputation:{scope}:{scope_key}:{metric}` keys
- Calls shared `_compute_email_score()` — same scoring algorithm
- Returns same shape as `get_email_reputation()` plus `scope`/`scope_key`

**New function: `get_domain_health_map(redis) -> dict[str, dict]`**
- `SCAN` for `email:reputation:domain:*:sent` keys, extract domain names
- Call `get_email_reputation_scoped("domain", domain)` for each
- Returns `{domain: {score, status, throttle, metrics}}`

**New function: `get_mailbox_health_map(redis) -> dict[str, dict]`**
- Same pattern, scans `email:reputation:mailbox:*:sent`

### 1b. Update `src/api/sales_webhooks.py` — email event recording

At each `record_email_event(redis, ...)` call site (~5 locations in `email_events_webhook`):
- Extract `domain` from `email_record.from_email.split("@")[1]`
- Replace with `record_email_event_scoped(redis, event_type, domain=domain, from_email=email_record.from_email)`

### 1c. Update `src/workers/outreach_sending.py` — domain-health-aware mailbox selection

In `_choose_sender_profile()`:
- Fetch `domain_health_map` and `mailbox_health_map` once at function start
- After existing daily-limit check, add domain+mailbox health check:
  - If domain throttle == `"paused"` → skip mailbox
  - If mailbox throttle == `"paused"` → skip mailbox
- `_record_send()`: replace `record_email_event(redis, "sent")` with scoped version

### 1d. Update `src/models/sales_config.py`

Add: `mailbox_health_threshold` (Integer, default=40) — score below this auto-skips mailbox

### 1e. Tests: `tests/test_deliverability_scoped.py`

- `record_email_event_scoped` records to all 3 scopes
- `get_email_reputation_scoped` returns correct score per scope
- `get_domain_health_map` with multiple domains
- Domain-unhealthy mailbox is skipped in `_choose_sender_profile`
- Fallback when all mailboxes for a domain are unhealthy

---

## Phase 2: Engagement-Gated Step 3 (Quick Win)

Sending step 3 to prospects who never opened steps 1-2 is net negative — burns deliverability for ~10% of replies.

### 2a. Update `src/models/sales_config.py`

Add: `require_engagement_for_final_step` (Boolean, default=True)

### 2b. Update `src/workers/outreach_sequencer.py`

In both `_process_unbound_prospects()` follow-up query (~line 665) and `_process_campaign_prospects()` follow-up query (~line 839):

When `config.require_engagement_for_final_step` is True, add to WHERE clause:
```python
or_(
    Outreach.outreach_sequence_step < config.max_sequence_steps - 1,
    Outreach.last_email_opened_at.isnot(None),
    Outreach.last_email_clicked_at.isnot(None),
)
```

This only gates the FINAL step. Steps 1-2 are unaffected.

### 2c. Tests

- Step 3 prospect WITHOUT opens/clicks → excluded
- Step 3 prospect WITH opens → included
- Step 2 prospect without opens → included (gate only on final)
- Config flag disabled → sends step 3 regardless

---

## Phase 3: Adaptive Send Cadence

Refine timing to capitalize on engagement signals.

### 3a. Update `src/models/outreach.py`

Add: `email_open_count` (Integer, default=0) — tracks ALL opens including re-opens

### 3b. Update `src/api/sales_webhooks.py`

In `open` event handler: increment `prospect.email_open_count` on EVERY open event (not just first). Existing `opened_at` timestamp still only records first open.

### 3c. Refine `src/services/outreach_timing.py` — `required_followup_delay_hours()`

Replace the 3-branch logic with 5-priority tiers:

| Priority | Signal | Effective Delay |
|----------|--------|----------------|
| 1 | Re-opened 3+ times | base - 18h (→ ~30h) |
| 2 | Clicked | base - 12h (→ ~36h) — existing |
| 3 | Opened within 1h of receipt | base - 12h (→ ~36h) |
| 4 | Opened (not clicked) | base (→ 48h) — existing |
| 5 | Never opened | base + 24h (→ 72h) — existing, +24h more if step ≥2 |

All respect `MIN_FOLLOWUP_DELAY_HOURS` (36h) floor.

### 3d. Tests

- Re-open count >= 3 gets fastest delay
- Opened within 1h of receipt gets priority 3 delay
- Backward compatible when `email_open_count` attribute missing

---

## Phase 4: 90-Day Re-Contact Cycle

The big one. Turns a finite, burn-through pipeline into a compounding one.

### 4a. Update `src/models/outreach.py`

Add columns:
- `re_contact_cycle` (Integer, default=0)
- `cycle_reset_at` (DateTime(tz), nullable)

Add index: `ix_outreach_recontact` on `(tenant_id, status, re_contact_cycle, last_email_sent_at)`

### 4b. Update `src/models/sales_config.py`

Add columns:
- `max_recontact_cycles` (Integer, default=4) — ~1 year of coverage
- `recontact_cooldown_days` (Integer, default=90)

### 4c. New worker: `src/workers/recontact_worker.py` (~150 lines)

Runs daily. Finds prospects where:
- `status == "contacted"` (completed sequence)
- `last_email_sent_at <= NOW() - cooldown_days`
- `last_email_replied_at IS NULL`
- `email_unsubscribed == False`
- `re_contact_cycle < max_recontact_cycles`
- Has valid email

For eligible prospects, reset:
- `outreach_sequence_step = 0`
- `re_contact_cycle += 1`
- `cycle_reset_at = now`
- `status = "cold"`
- Clear engagement fields: `last_email_opened_at`, `last_email_clicked_at`, `email_open_count`
- Clear `generation_failures`

The worker ONLY resets. The existing outreach_sequencer picks up `cold` + `step 0` prospects on its next 30-min cycle. This inherits ALL existing guardrails (warmup, domain health, engagement gate, smart timing).

### 4d. Update `src/workers/outreach_sending.py` — cycle-aware mailbox rotation

In `_choose_sender_profile()`, include cycle in the seed:
```python
cycle = getattr(prospect, "re_contact_cycle", 0)
seed = uuid.UUID(str(prospect.id)).int + int(next_step) + (cycle * 7)
```

Guarantees different mailbox per cycle.

### 4e. Update `src/agents/sales_outreach.py` — cycle-aware angle rotation

In `generate_outreach_email()`:
- Accept `re_contact_cycle: int = 0` parameter
- When cycle > 0, prepend instruction: "This is re-contact cycle N. Use a COMPLETELY DIFFERENT angle. Cycle suggestions: 1=industry trends, 2=competitor insight, 3=seasonal opportunity, 4=case study."

In `src/workers/outreach_sending.py`, pass cycle to generation:
```python
re_contact_cycle=getattr(prospect, "re_contact_cycle", 0)
```

### 4f. Register worker in `src/main.py`

Feature-flagged like winback:
```python
"recontact_agent": (settings.agent_recontact_agent, "src.workers.recontact_worker", "run_recontact_worker"),
```

Add `agent_recontact_agent: bool = True` to `src/config.py` Settings.

### 4g. Tests: `tests/test_recontact_worker.py`

- Eligible prospects are reset (status, step, cycle incremented)
- Max cycles cap respected
- Unsubscribed/replied prospects excluded
- Cooldown period enforced
- Engagement fields cleared on reset
- Different mailbox seed per cycle

---

## Phase 5: Dashboard Visibility

### 5a. New endpoint in `src/api/sales_dashboard.py`

`GET /email-health` → returns:
```json
{
  "global": {score, status, throttle, metrics},
  "domains": [{domain, score, status, throttle, metrics}, ...],
  "mailboxes": [{from_email, score, status, throttle, metrics}, ...]
}
```

### 5b. Extend command-center response

Add `recontact_stats`: `{total_eligible, total_recycled_30d, cycle_distribution}`

### 5c. Dashboard components

- `DomainHealthGrid.tsx` — per-domain score/status/throttle
- `MailboxHealthGrid.tsx` — per-mailbox health with auto-deactivation indicator
- `RecontactStats.tsx` — cycle distribution, eligible count

---

## Single Consolidated Migration

`alembic revision --autogenerate -m "outreach_scaling_v1"`

All additive (zero-downtime):

**`outreach` table:**
- `email_open_count` (Integer, default=0)
- `re_contact_cycle` (Integer, default=0)
- `cycle_reset_at` (DateTime(tz), nullable)
- Index: `ix_outreach_recontact` on `(tenant_id, status, re_contact_cycle, last_email_sent_at)`

**`sales_engine_config` table:**
- `mailbox_health_threshold` (Integer, default=40)
- `require_engagement_for_final_step` (Boolean, default=True)
- `max_recontact_cycles` (Integer, default=4)
- `recontact_cooldown_days` (Integer, default=90)

**`config.py` Settings:**
- `agent_recontact_agent: bool = True`

---

## Verification

1. **Per-domain reputation**: Send test emails from 2 domains, trigger bounce on domain A → verify domain A paused, domain B continues
2. **Engagement gate**: Create prospect at step 2 with no opens → verify step 3 is NOT sent
3. **Adaptive timing**: Create prospect with 3+ opens → verify shortened delay
4. **Re-contact**: Create prospect at step 3, last_email_sent_at 91 days ago → verify reset to cold/step 0/cycle 1
5. **Cycle angle rotation**: Verify AI prompt includes cycle number on re-contact
6. **Full suite**: `pytest tests/test_deliverability_scoped.py tests/test_outreach_sequencer.py tests/test_outreach_timing.py tests/test_recontact_worker.py -v`

---

## Key Files

| File | Phases | Change |
|------|--------|--------|
| `src/services/deliverability.py` | 1 | Per-domain/mailbox reputation scoring |
| `src/api/sales_webhooks.py` | 1, 3 | Scoped event recording, open count tracking |
| `src/workers/outreach_sending.py` | 1, 4 | Health-aware mailbox selection, cycle-aware seed |
| `src/workers/outreach_sequencer.py` | 2 | Engagement gate on final step query |
| `src/services/outreach_timing.py` | 3 | 5-tier adaptive delay calculation |
| `src/models/outreach.py` | 3, 4 | New columns: email_open_count, re_contact_cycle, cycle_reset_at |
| `src/models/sales_config.py` | 1, 2, 4 | New config fields |
| `src/agents/sales_outreach.py` | 4 | Cycle-aware angle rotation in AI prompt |
| `src/workers/recontact_worker.py` | 4 | **NEW** — daily cycle reset worker |
| `src/main.py` | 4 | Register recontact worker (feature-flagged) |
| `src/config.py` | 4 | Add agent_recontact_agent setting |
| `src/api/sales_dashboard.py` | 5 | Email health + recontact stats endpoints |
