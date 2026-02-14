# CLAUDE.md — LeadLock AI Speed-to-Lead Platform

## Project Overview

LeadLock is a production-grade AI-powered speed-to-lead platform for home services contractors (HVAC, plumbing, roofing, electrical, solar). The system guarantees sub-60-second SMS response to every inbound lead, qualifies leads through AI conversation, books appointments directly into the client's CRM/calendar, and runs automated follow-up sequences.

**Business model:** B2B SaaS + managed service. Clients pay $497–$3,500/month.

## Tech Stack

- **Backend:** Python 3.12+, FastAPI 0.115+, SQLAlchemy 2.0 async, asyncpg, Alembic
- **Database:** PostgreSQL 16, Redis 7+
- **AI:** Anthropic Claude (primary), OpenAI (fallback)
- **SMS:** Twilio (primary), Telnyx (failover)
- **CRM:** ServiceTitan V2, Housecall Pro, Jobber, GoHighLevel, Google Sheets fallback
- **Dashboard:** React 18 + Vite + Tailwind CSS + shadcn/ui + Recharts
- **Deployment:** Railway (Hobby plan), Docker
- **Testing:** pytest + pytest-asyncio

## Architecture Principles

1. **RESPOND FIRST, SYNC LATER** — SMS response to lead MUST happen in <10 seconds. ALL CRM operations happen asynchronously AFTER the response is sent. NEVER put a CRM API call in the critical SMS response path.
2. **COMPLIANCE IS NON-NEGOTIABLE** — TCPA violations carry $500–$1,500 PER MESSAGE with no cap. Every message must have consent tracking, opt-out processing, and quiet hours enforcement.
3. **RELIABILITY OVER FEATURES** — A system that responds to 100% of leads in 8 seconds beats one that responds to 95% in 2 seconds. No lead can ever be dropped.

## Agent Pipeline

4-agent system orchestrated by a Conductor state machine:
- **Intake Agent** (Claude Haiku 4.5, template-based): First response in <10s
- **Qualify Agent** (Claude Sonnet 4.5, conversational AI): Lead qualification in ≤4 messages
- **Book Agent** (Claude Haiku 4.5): CRM-integrated appointment booking
- **Follow-Up Agent** (Claude Haiku 4.5): Automated nurture sequences (max 3 cold messages)

Lead lifecycle: `new → intake_sent → qualifying → qualified → booking → booked → completed`
Terminal states: `cold → dead`, `opted_out`

## Key Compliance Rules

- TCPA penalties: $500/violation minimum, $1,500 willful, no cap, 4-year SOL
- Consent records retained 5 years (FTC TSR 2024)
- Texas SB 140: Sunday texts only noon–9 PM
- Florida FTSA: 8 AM–8 PM, no state holidays, max 3 calls/person/subject/24hrs
- AI disclosure required (California SB 1001)
- Every first message MUST include "Reply STOP to opt out" and business name
- NEVER use URL shorteners (bit.ly, tinyurl) — carriers filter them
- Emergency messages bypass quiet hours (life safety exception)
- Max 3 cold outreach messages per lead, ever

## Code Standards

- Type hints on ALL functions
- Docstrings on ALL classes and public methods
- Logging: INFO normal ops, WARNING issues, ERROR failures
- Never let an exception crash the system — log it, return safe fallback
- All database operations use async SQLAlchemy
- All external API calls have 10-second timeouts
- All SMS sends go through compliance check first
- Mask PII in logs: phone numbers show first 6 digits + ***
- No `print()` statements — use `logging` module

## Testing Standards

- Every compliance rule has a test
- Every emergency keyword has a test
- Every webhook endpoint has a test
- Every agent fallback path has a test
- Mock all external services (Twilio, AI, CRM) in tests
- Use `pytest-asyncio` with `asyncio_mode = "auto"`

## Common Commands

```bash
# Start development server
uvicorn src.main:app --reload --port 8000

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Run tests
pytest

# Run specific test file
pytest tests/test_compliance.py -v

# Start dashboard dev server
cd dashboard && npm run dev

# Build dashboard for production
cd dashboard && npm run build

# Seed test data
python scripts/seed_test_client.py

# Simulate a lead
python scripts/simulate_lead.py
```

## Project Structure

```
leadlock/
├── src/                    # Backend (FastAPI)
│   ├── main.py            # App entry point
│   ├── config.py          # Environment config (pydantic-settings)
│   ├── database.py        # SQLAlchemy async engine
│   ├── models/            # Database models
│   ├── schemas/           # Pydantic schemas
│   ├── api/               # API routes (webhooks, admin, dashboard)
│   ├── agents/            # AI agent pipeline
│   ├── services/          # Core services (SMS, AI, compliance)
│   ├── integrations/      # CRM integrations
│   ├── workers/           # Background jobs
│   └── utils/             # Utilities (dedup, templates, emergency)
├── dashboard/             # Frontend (React + Vite)
│   └── src/
│       ├── pages/         # Dashboard pages
│       ├── components/    # Reusable components
│       └── hooks/         # Custom React hooks
├── tests/                 # Test suite
├── alembic/               # Database migrations
└── scripts/               # Utility scripts
```

## Environment Variables

See `.env.example` for the complete list. Critical ones:
- `DATABASE_URL` — PostgreSQL connection string (asyncpg)
- `REDIS_URL` — Redis connection string
- `ANTHROPIC_API_KEY` — Claude API key
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` — Twilio credentials
- `APP_SECRET_KEY` — Application secret for JWT/signing

## API Pricing Reference (per-unit costs)

- SMS outbound: ~$0.0079/segment
- SMS inbound: ~$0.0075/segment
- Claude Haiku 4.5: $1.00/$5.00 per MTok (input/output)
- Claude Sonnet 4.5: $3.00/$15.00 per MTok
- Twilio Line Type Lookup: $0.008/lookup
- Per lead engagement cost: ~$0.02–$0.03
