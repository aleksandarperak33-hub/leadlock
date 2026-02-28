"""
Seed a fully populated demo account for sales call demos.

Idempotent: deletes existing demo data first, recreates fresh with
timestamps relative to now so the dashboard always looks lively.

Usage:
    python scripts/seed_demo_account.py
"""
import asyncio
import logging
import random
import uuid
from datetime import datetime, time, timedelta, timezone

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.models.booking import Booking
from src.models.client import Client
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.event_log import EventLog
from src.models.followup import FollowupTask
from src.models.lead import Lead

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEMO_EMAIL = "demo@leadlock.org"
DEMO_PASSWORD = "DemoPass123!"
BUSINESS_NAME = "Premier Plumbing & HVAC"
BUSINESS_PHONE_PREFIX = "+1602555"  # Arizona 555 range — no real numbers
NOW = datetime.now(timezone.utc)

SOURCES = ["website", "google_lsa", "missed_call", "text_in", "angi"]
SOURCE_WEIGHTS = [30, 25, 20, 15, 10]

SERVICES = [
    "Water Heater Repair",
    "Drain Cleaning",
    "Leak Repair",
    "AC Repair",
    "Pipe Repair",
    "Sewer Line Inspection",
]
SERVICE_WEIGHTS = [25, 20, 20, 15, 10, 10]

TEAM = ["Mike Torres", "James Wilson", "Carlos Rivera", "David Park"]

FIRST_NAMES = [
    "Sarah", "Michael", "Jennifer", "David", "Emily", "Robert", "Jessica",
    "Daniel", "Amanda", "Christopher", "Ashley", "Matthew", "Stephanie",
    "Andrew", "Nicole", "Joshua", "Elizabeth", "James", "Melissa", "Ryan",
    "Maria", "Brandon", "Angela", "Justin", "Linda", "Kevin", "Sandra",
    "Tyler", "Patricia", "Mark", "Lisa", "Alex", "Karen", "Thomas", "Susan",
    "Brian",
]

LAST_NAMES = [
    "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson",
    "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee",
    "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
    "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright",
    "Scott", "Torres",
]

PHOENIX_ZIPS = [
    "85001", "85003", "85004", "85006", "85007", "85008", "85009",
    "85012", "85013", "85014", "85015", "85016", "85017", "85018",
    "85019", "85020", "85021", "85022", "85023", "85024", "85028",
    "85029", "85031", "85032", "85033", "85034", "85035", "85040",
    "85041", "85042", "85043", "85044", "85048", "85050", "85051",
]

PHOENIX_STREETS = [
    "123 E Camelback Rd", "456 N Central Ave", "789 W Indian School Rd",
    "1010 S 7th St", "2345 E Thomas Rd", "678 N 32nd St",
    "9101 W Glendale Ave", "1234 E McDowell Rd", "5678 N 19th Ave",
    "3456 S 48th St", "7890 W Bethany Home Rd", "2345 E Osborn Rd",
    "111 N 44th St", "222 W Thunderbird Rd", "333 E Bell Rd",
    "444 S Mill Ave", "555 W Baseline Rd", "666 N Scottsdale Rd",
    "777 E Greenway Pkwy", "888 W Peoria Ave", "999 N Tatum Blvd",
    "1111 E Shea Blvd", "2222 W Dunlap Ave", "3333 N 7th Ave",
    "4444 E Cactus Rd", "5555 W Northern Ave", "6666 S 24th St",
    "7777 E Camelback Rd", "8888 N Cave Creek Rd", "9999 W Happy Valley Rd",
    "1212 E Roosevelt St", "3434 N 16th St", "5656 W Olive Ave",
    "7878 E Indian Bend Rd", "2020 S Priest Dr", "4040 N 40th St",
]

CONSENT_METHODS = {
    "website": "web_form",
    "google_lsa": "google_lsa",
    "missed_call": "missed_call",
    "text_in": "text_in",
    "angi": "angi",
}

DEMO_CLIENT_CONFIG = {
    "service_area": {
        "center": {"lat": 33.4484, "lng": -112.0740},
        "radius_miles": 30,
        "valid_zips": PHOENIX_ZIPS[:15],
    },
    "hours": {
        "business": {
            "start": "07:00",
            "end": "19:00",
            "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        },
        "saturday": {"start": "08:00", "end": "14:00", "days": ["sat"]},
        "after_hours_handling": "ai_responds_books_next_available",
        "emergency_handling": "ai_responds_plus_owner_alert",
    },
    "persona": {
        "rep_name": "Rachel",
        "tone": "friendly_professional",
        "languages": ["en"],
        "emergency_contact_phone": "+16025550100",
    },
    "services": {
        "primary": [
            "Water Heater Repair", "Drain Cleaning", "Leak Repair",
            "AC Repair", "Pipe Repair", "Sewer Line Inspection",
        ],
        "secondary": ["Garbage Disposal", "Faucet Install", "Toilet Repair"],
        "do_not_quote": [],
    },
    "team": [
        {"name": "Mike Torres", "specialty": ["water_heater", "pipe_repair"], "active": True},
        {"name": "James Wilson", "specialty": ["drain_cleaning", "sewer"], "active": True},
        {"name": "Carlos Rivera", "specialty": ["leak_repair", "ac_repair"], "active": True},
        {"name": "David Park", "specialty": ["ac_repair", "water_heater"], "active": True},
    ],
    "emergency_keywords": [
        "flooding", "gas leak", "pipe burst", "no hot water",
        "sewage backup", "water everywhere", "emergency",
    ],
    "scheduling": {
        "slot_duration_minutes": 120,
        "buffer_minutes": 30,
        "max_daily_bookings": 10,
        "advance_booking_days": 14,
    },
}


# ---------------------------------------------------------------------------
# Lead state definitions
# ---------------------------------------------------------------------------
LEAD_SPECS = [
    # (state, count, score_range, msg_range, urgency_pool)
    ("new", 2, (45, 55), (0, 0), ["today", "this_week", "flexible"]),
    ("intake_sent", 3, (45, 55), (1, 1), ["today", "this_week"]),
    ("qualifying", 4, (40, 65), (3, 4), ["today", "this_week", "flexible"]),
    ("qualified", 2, (65, 75), (4, 5), ["today", "this_week"]),
    ("booking", 1, (70, 80), (5, 5), ["today"]),
    ("booked", 10, (75, 90), (6, 8), ["today", "this_week"]),
    ("completed", 5, (85, 95), (6, 8), ["today", "this_week"]),
    ("cold", 5, (20, 40), (2, 3), ["flexible", "just_quote"]),
    ("opted_out", 3, (30, 50), (2, 3), ["this_week", "flexible"]),
    ("dead", 1, (10, 20), (1, 1), ["just_quote"]),
]


# ---------------------------------------------------------------------------
# Conversation templates — realistic SMS exchanges
# ---------------------------------------------------------------------------
def _build_conversation_templates() -> list[dict]:
    """Return message templates keyed by lead scenario."""
    biz = BUSINESS_NAME
    return [
        {
            "service": "Water Heater Repair",
            "states": ["booked", "completed"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. Thanks for reaching out about your water heater issue! I'd love to help. Can you tell me a bit more about what's going on? Reply STOP to opt out."),
                ("inbound", None, "Yeah our water heater isn't making hot water anymore. It's about 10 years old."),
                ("outbound", "qualify", f"Oh no, that's frustrating! A 10-year-old water heater could need a simple repair or might be time for a replacement. Are you experiencing any leaking around the unit?"),
                ("inbound", None, "No leaking just no hot water at all"),
                ("outbound", "qualify", "Got it! That's actually good news — no leaking means we might be able to get it fixed quickly. Would you prefer morning or afternoon for a technician visit?"),
                ("inbound", None, "Morning works best before noon if possible"),
                ("outbound", "book", "I've got Mike Torres available tomorrow morning 8-10 AM. He's our water heater specialist. Does that work for you?"),
                ("inbound", None, "That's perfect see you then"),
            ],
        },
        {
            "service": "Drain Cleaning",
            "states": ["booked", "completed"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. We got your request about a drain issue. We'd love to help! What's going on with your drain? Reply STOP to opt out."),
                ("inbound", None, "Kitchen sink is draining super slow and making gurgling sounds"),
                ("outbound", "qualify", "Slow draining with gurgling usually means a partial clog. Is it just the kitchen sink or are other drains affected too?"),
                ("inbound", None, "Just the kitchen sink the rest are fine"),
                ("outbound", "qualify", "Good news — that's likely an isolated clog. We can usually clear those in one visit. James Wilson is available Friday afternoon 1-3 PM. Would that work?"),
                ("inbound", None, "Yes Friday works"),
            ],
        },
        {
            "service": "Leak Repair",
            "states": ["booked"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel from {biz}. Thanks for contacting us about a leak. We want to get that taken care of right away! Where is the leak located? Reply STOP to opt out."),
                ("inbound", None, "There's water dripping under our bathroom sink pretty fast"),
                ("outbound", "qualify", "Under the bathroom sink — that can get worse quickly. Is the water clear or discolored? And can you see where it's coming from?"),
                ("inbound", None, "It's clear water coming from one of the pipes under there"),
                ("outbound", "qualify", "Sounds like a supply line or P-trap connection issue. These are usually straightforward repairs. How soon do you need someone out?"),
                ("inbound", None, "As soon as possible we've got a bucket under it now"),
            ],
        },
        {
            "service": "AC Repair",
            "states": ["booked", "completed"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. We received your AC repair request. It's hot out there — let's get your cooling back! What's happening with your AC? Reply STOP to opt out."),
                ("inbound", None, "AC is blowing warm air. It was working fine yesterday"),
                ("outbound", "qualify", "Warm air suddenly could be a few things — refrigerant, compressor, or thermostat. Is the outdoor unit running? Can you hear the fan?"),
                ("inbound", None, "I can hear the fan outside but it's definitely not cooling"),
                ("outbound", "qualify", "Good that the fan is running! This might be a refrigerant or capacitor issue. Carlos Rivera can come check it out. He's available Monday 9-11 AM — does that work?"),
                ("inbound", None, "Monday works great thank you!"),
                ("outbound", "book", "You're all set! Carlos will be there Monday between 9-11 AM. He'll diagnose the issue and give you options before any work is done. See you then!"),
            ],
        },
        {
            "service": "Sewer Line Inspection",
            "states": ["qualifying"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. Thanks for reaching out about your sewer concern. We can definitely help investigate! What symptoms are you seeing? Reply STOP to opt out."),
                ("inbound", None, "Multiple drains are slow and there's a weird smell coming from the basement"),
                ("outbound", "qualify", "Multiple slow drains plus odor from the basement could indicate a main sewer line issue. Have you noticed any water backing up into the tub or toilet?"),
                ("inbound", None, "Not yet but I'm worried it might get to that point"),
            ],
        },
        {
            "service": "Pipe Repair",
            "states": ["cold"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. We got your inquiry about a pipe issue. We'd be happy to help! Can you describe what's going on? Reply STOP to opt out."),
                ("inbound", None, "Just getting quotes for now not urgent"),
            ],
        },
        {
            "service": "Drain Cleaning",
            "states": ["opted_out"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. Thanks for reaching out! We'd love to help with your drain issue. What can we help with? Reply STOP to opt out."),
                ("inbound", None, "Actually I already found someone. STOP"),
                ("outbound", "followup", f"We've removed you from our messages. If you ever need plumbing or HVAC help in the future, don't hesitate to reach out. Take care!"),
            ],
        },
        {
            "service": "Water Heater Repair",
            "states": ["intake_sent"],
            "messages": [
                ("outbound", "intake", f"Hi! This is Rachel with {biz}. Thanks for your water heater inquiry! We'd love to help. Can you tell me what's going on? Reply STOP to opt out."),
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _random_phone(index: int) -> str:
    """Generate a unique +1602555XXXX phone number."""
    return f"{BUSINESS_PHONE_PREFIX}{index:04d}"


def _random_ts(hours_ago_min: float, hours_ago_max: float) -> datetime:
    """Random timestamp between hours_ago_max and hours_ago_min before now."""
    delta_seconds = random.uniform(hours_ago_min * 3600, hours_ago_max * 3600)
    return NOW - timedelta(seconds=delta_seconds)


def _pick_source() -> str:
    return random.choices(SOURCES, weights=SOURCE_WEIGHTS, k=1)[0]


def _pick_service() -> str:
    return random.choices(SERVICES, weights=SERVICE_WEIGHTS, k=1)[0]


def _sms_sid() -> str:
    return f"SM_DEMO_{uuid.uuid4().hex[:24]}"


def _response_time_ms() -> int:
    """Realistic response time: mostly 4-12s, occasional up to 45s."""
    if random.random() < 0.92:
        return random.randint(4000, 12000)
    return random.randint(12000, 45000)


# ---------------------------------------------------------------------------
# Deletion (FK-safe order)
# ---------------------------------------------------------------------------
async def _delete_demo_data(session: AsyncSession, client_id: uuid.UUID) -> None:
    """Remove all demo data in FK-safe order."""
    cid = str(client_id)
    tables_and_fk = [
        ("event_logs", "client_id"),
        ("followup_tasks", "client_id"),
        ("bookings", "client_id"),
        ("conversations", "client_id"),
    ]
    for table, col in tables_and_fk:
        await session.execute(
            text(f"DELETE FROM {table} WHERE {col} = :cid"),  # noqa: S608
            {"cid": cid},
        )

    # Null out consent_id before deleting consent records
    await session.execute(
        text("UPDATE leads SET consent_id = NULL WHERE client_id = :cid"),
        {"cid": cid},
    )
    await session.execute(
        text("DELETE FROM consent_records WHERE client_id = :cid"),
        {"cid": cid},
    )
    await session.execute(
        text("DELETE FROM leads WHERE client_id = :cid"),
        {"cid": cid},
    )
    await session.execute(
        text("DELETE FROM clients WHERE id = :cid"),
        {"cid": cid},
    )
    await session.commit()
    logger.info("Deleted existing demo data for client %s", cid)


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------
def _create_client() -> Client:
    """Build the demo Client object."""
    pw_hash = bcrypt.hashpw(
        DEMO_PASSWORD.encode(), bcrypt.gensalt()
    ).decode()
    return Client(
        business_name=BUSINESS_NAME,
        trade_type="plumbing",
        tier="pro",
        monthly_fee=1497.00,
        owner_name="Rachel Torres",
        owner_email="rachel@premierplumbinghvac.com",
        owner_phone="+16025550100",
        twilio_phone=None,
        crm_type="servicetitan",
        crm_config={"tenant_id": "demo_tenant"},
        config=DEMO_CLIENT_CONFIG,
        billing_status="active",
        onboarding_status="live",
        is_active=True,
        email_verified=True,
        dashboard_email=DEMO_EMAIL,
        dashboard_password_hash=pw_hash,
    )


def _create_leads_and_related(
    client_id: uuid.UUID,
) -> tuple[list[Lead], list[ConsentRecord], list[Conversation], list[Booking], list[EventLog], list[FollowupTask]]:
    """Build all leads, consent records, conversations, bookings, events, and followup tasks."""
    leads: list[Lead] = []
    consents: list[ConsentRecord] = []
    conversations: list[Conversation] = []
    bookings: list[Booking] = []
    events: list[EventLog] = []
    followups: list[FollowupTask] = []

    templates = _build_conversation_templates()
    template_idx = 0
    lead_index = 0

    for state, count, score_range, msg_range, urgency_pool in LEAD_SPECS:
        for _ in range(count):
            lead_index += 1
            lead_id = uuid.uuid4()
            phone = _random_phone(lead_index)
            first_name = FIRST_NAMES[lead_index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[lead_index % len(LAST_NAMES)]
            source = _pick_source()

            # Bias timestamps toward recent
            if state in ("new", "intake_sent"):
                created = _random_ts(0.5, 4)
            elif state in ("qualifying", "booking"):
                created = _random_ts(2, 24)
            elif state in ("booked",):
                created = _random_ts(12, 96)
            elif state in ("completed",):
                created = _random_ts(48, 168)
            elif state in ("cold", "dead"):
                created = _random_ts(72, 168)
            else:  # opted_out
                created = _random_ts(24, 120)

            score = random.randint(*score_range)
            service = _pick_service()
            urgency = random.choice(urgency_pool)
            response_ms = _response_time_ms()
            n_msgs = random.randint(*msg_range)
            n_out = max(1, n_msgs // 2) if n_msgs > 0 else 0
            n_in = n_msgs - n_out

            # Pick a conversation template that fits this state
            matching = [
                t for t in templates if state in t["states"]
            ]
            if matching:
                tpl = matching[template_idx % len(matching)]
                template_idx += 1
            else:
                tpl = None

            # If using a template, override msg counts to match actual messages
            if tpl and tpl["messages"]:
                tpl_msgs = tpl["messages"]
                n_msgs = len(tpl_msgs)
                n_out = sum(1 for d, _, _ in tpl_msgs if d == "outbound")
                n_in = sum(1 for d, _, _ in tpl_msgs if d == "inbound")

            # Determine current agent based on state
            agent_map = {
                "new": None,
                "intake_sent": "intake",
                "qualifying": "qualify",
                "qualified": "qualify",
                "booking": "book",
                "booked": "book",
                "completed": "book",
                "cold": "followup",
                "opted_out": None,
                "dead": None,
            }

            # Consent record (all except dead)
            consent_id = None
            if state != "dead":
                consent = ConsentRecord(
                    id=uuid.uuid4(),
                    phone=phone,
                    client_id=client_id,
                    consent_type="pec",
                    consent_method=CONSENT_METHODS.get(source, "text_in"),
                    is_active=state != "opted_out",
                    opted_out=state == "opted_out",
                    opted_out_at=NOW - timedelta(hours=random.randint(1, 48)) if state == "opted_out" else None,
                    opt_out_method="sms_stop" if state == "opted_out" else None,
                    consent_text=f"Customer initiated contact via {source}",
                    created_at=created,
                    updated_at=created,
                )
                consents.append(consent)
                consent_id = consent.id

            lead = Lead(
                id=lead_id,
                client_id=client_id,
                phone=phone,
                phone_national=f"(602) 555-{phone[-4:]}" if lead_index < 10 else None,
                first_name=first_name,
                last_name=last_name,
                email=f"{first_name.lower()}.{last_name.lower()}@email.com" if random.random() > 0.3 else None,
                address=random.choice(PHOENIX_STREETS),
                zip_code=random.choice(PHOENIX_ZIPS),
                city="Phoenix",
                state_code="AZ",
                source=source,
                state=state,
                previous_state=_previous_state(state),
                score=score,
                service_type=service if tpl is None else tpl["service"],
                urgency=urgency,
                property_type=random.choice(["residential", "residential", "commercial"]),
                problem_description=_problem_desc(service if tpl is None else tpl["service"]),
                current_agent=agent_map.get(state),
                conversation_turn=n_msgs,
                consent_id=consent_id,
                is_emergency=urgency == "today" and random.random() < 0.15,
                ai_disclosure_sent=n_out > 0,
                ai_disclosure_sent_at=created + timedelta(seconds=8) if n_out > 0 else None,
                first_response_ms=response_ms if n_out > 0 else None,
                total_messages_sent=n_out,
                total_messages_received=n_in,
                total_ai_cost_usd=round(n_out * 0.003, 4),
                total_sms_cost_usd=round(n_msgs * 0.0079, 4),
                cold_outreach_count=min(n_out, 3) if state in ("cold", "dead") else 0,
                last_outbound_at=created + timedelta(minutes=n_msgs * 3) if n_out > 0 else None,
                last_inbound_at=created + timedelta(minutes=n_msgs * 3 + 1) if n_in > 0 else None,
                created_at=created,
                updated_at=created + timedelta(minutes=n_msgs * 5),
            )
            leads.append(lead)

            # --- Conversations ---
            if tpl and tpl["messages"]:
                _add_template_conversations(
                    conversations, tpl["messages"], lead, client_id, phone, created,
                )
            elif n_msgs > 0:
                _add_generic_conversations(
                    conversations, lead, client_id, phone, created, n_out, n_in,
                    service if tpl is None else tpl["service"],
                )

            # --- Bookings ---
            if state in ("booked", "completed"):
                booking = _create_booking(lead, client_id, created, state)
                bookings.append(booking)

            # --- Events ---
            _add_events(events, lead, client_id, created, state, n_out, n_in)

            # --- Followup tasks ---
            _add_followup_tasks(followups, lead, client_id, created, state)

    return leads, consents, conversations, bookings, events, followups


def _previous_state(state: str) -> str | None:
    """Return the likely previous state for a given current state."""
    chain = {
        "new": None,
        "intake_sent": "new",
        "qualifying": "intake_sent",
        "qualified": "qualifying",
        "booking": "qualified",
        "booked": "booking",
        "completed": "booked",
        "cold": "qualifying",
        "opted_out": "intake_sent",
        "dead": "cold",
    }
    return chain.get(state)


def _problem_desc(service: str) -> str:
    """Generate a realistic problem description."""
    descs = {
        "Water Heater Repair": "Water heater stopped producing hot water. Unit is approximately 10 years old.",
        "Drain Cleaning": "Kitchen sink draining very slowly with gurgling sounds.",
        "Leak Repair": "Water dripping under bathroom sink, clear water from pipe connection.",
        "AC Repair": "AC unit blowing warm air, outdoor fan is running but no cooling.",
        "Pipe Repair": "Visible pipe corrosion in basement, requesting inspection and quote.",
        "Sewer Line Inspection": "Multiple slow drains and odor from basement area.",
    }
    return descs.get(service, "General plumbing service request.")


def _add_template_conversations(
    conversations: list[Conversation],
    messages: list[tuple[str, str | None, str]],
    lead: Lead,
    client_id: uuid.UUID,
    phone: str,
    base_time: datetime,
) -> None:
    """Add conversation messages from a template."""
    biz_phone = "+16025550000"
    for i, (direction, agent, content) in enumerate(messages):
        msg_time = base_time + timedelta(minutes=i * 3, seconds=random.randint(0, 60))
        is_outbound = direction == "outbound"
        conversations.append(
            Conversation(
                id=uuid.uuid4(),
                lead_id=lead.id,
                client_id=client_id,
                direction=direction,
                content=content,
                from_phone=biz_phone if is_outbound else phone,
                to_phone=phone if is_outbound else biz_phone,
                agent_id=agent,
                agent_model="claude-haiku-4-5" if agent in ("intake", "book", "followup") else (
                    "claude-sonnet-4-5" if agent == "qualify" else None
                ),
                sms_provider="twilio" if is_outbound else None,
                sms_sid=_sms_sid() if is_outbound else None,
                delivery_status="delivered" if is_outbound else "received",
                segment_count=1,
                sms_cost_usd=0.0079 if is_outbound else 0.0075,
                ai_cost_usd=round(random.uniform(0.001, 0.005), 4) if is_outbound else 0.0,
                ai_latency_ms=random.randint(800, 3500) if is_outbound else None,
                ai_input_tokens=random.randint(200, 800) if is_outbound else None,
                ai_output_tokens=random.randint(30, 120) if is_outbound else None,
                created_at=msg_time,
                delivered_at=msg_time + timedelta(seconds=random.randint(1, 5)) if is_outbound else None,
            )
        )


def _add_generic_conversations(
    conversations: list[Conversation],
    lead: Lead,
    client_id: uuid.UUID,
    phone: str,
    base_time: datetime,
    n_out: int,
    n_in: int,
    service: str,
) -> None:
    """Add generic conversation messages for leads without a template match."""
    biz_phone = "+16025550000"
    biz = BUSINESS_NAME
    total = n_out + n_in

    # First message is always outbound intake with TCPA
    generic_first = (
        f"Hi! This is Rachel with {biz}. Thanks for reaching out about "
        f"{service.lower()}! We'd love to help get that taken care of. "
        f"Can you tell me more about what's going on? Reply STOP to opt out."
    )
    generic_replies = [
        "Yeah it's been going on for a couple days now",
        "Can you come out this week?",
        "How much does that usually cost?",
        "Ok that works for me",
        "Thanks for the help",
    ]
    generic_outbound = [
        f"We can definitely help with that! Let me get some details to find the best time for a technician visit.",
        "Got it — is this a residential or commercial property?",
        "Thanks for that info! We have availability this week. Would morning or afternoon work better?",
        "We'll get that scheduled for you. You'll receive a confirmation shortly!",
    ]

    out_remaining = n_out
    in_remaining = n_in
    reply_idx = 0
    outbound_idx = 0

    for i in range(total):
        msg_time = base_time + timedelta(minutes=i * 4, seconds=random.randint(0, 90))
        if i == 0:
            direction, agent, content = "outbound", "intake", generic_first
            out_remaining -= 1
        elif i % 2 == 1 and in_remaining > 0:
            direction, agent = "inbound", None
            content = generic_replies[min(reply_idx, len(generic_replies) - 1)]
            reply_idx += 1
            in_remaining -= 1
        elif out_remaining > 0:
            direction, agent = "outbound", "qualify"
            content = generic_outbound[min(outbound_idx, len(generic_outbound) - 1)]
            outbound_idx += 1
            out_remaining -= 1
        elif in_remaining > 0:
            direction, agent = "inbound", None
            content = generic_replies[min(reply_idx, len(generic_replies) - 1)]
            reply_idx += 1
            in_remaining -= 1
        else:
            break

        is_outbound = direction == "outbound"
        conversations.append(
            Conversation(
                id=uuid.uuid4(),
                lead_id=lead.id,
                client_id=client_id,
                direction=direction,
                content=content,
                from_phone=biz_phone if is_outbound else phone,
                to_phone=phone if is_outbound else biz_phone,
                agent_id=agent,
                agent_model="claude-haiku-4-5" if agent == "intake" else (
                    "claude-sonnet-4-5" if agent == "qualify" else None
                ),
                sms_provider="twilio" if is_outbound else None,
                sms_sid=_sms_sid() if is_outbound else None,
                delivery_status="delivered" if is_outbound else "received",
                segment_count=1,
                sms_cost_usd=0.0079 if is_outbound else 0.0075,
                ai_cost_usd=round(random.uniform(0.001, 0.004), 4) if is_outbound else 0.0,
                ai_latency_ms=random.randint(900, 3000) if is_outbound else None,
                created_at=msg_time,
                delivered_at=msg_time + timedelta(seconds=2) if is_outbound else None,
            )
        )


def _create_booking(
    lead: Lead, client_id: uuid.UUID, lead_created: datetime, state: str,
) -> Booking:
    """Create a booking for booked/completed leads."""
    is_completed = state == "completed"

    if is_completed:
        # Past appointment: 1-3 days ago
        appt_date = (NOW - timedelta(days=random.randint(1, 3))).date()
    else:
        # Future appointment: 1-5 days from now
        appt_date = (NOW + timedelta(days=random.randint(1, 5))).date()

    hour = random.choice([8, 9, 10, 11, 13, 14, 15])
    tech = random.choice(TEAM)

    return Booking(
        id=uuid.uuid4(),
        lead_id=lead.id,
        client_id=client_id,
        appointment_date=appt_date,
        time_window_start=time(hour, 0),
        time_window_end=time(hour + 2, 0),
        service_type=lead.service_type or "General Service",
        service_description=lead.problem_description,
        service_address=lead.address,
        service_zip=lead.zip_code,
        tech_name=tech,
        crm_sync_status="synced" if random.random() > 0.2 else "pending",
        status="completed" if is_completed else "confirmed",
        reminder_sent=is_completed or random.random() > 0.3,
        reminder_sent_at=(
            datetime.combine(appt_date - timedelta(days=1), time(10, 0), tzinfo=timezone.utc)
            if is_completed else None
        ),
        review_score=random.choice([4, 5, 5, 5]) if is_completed and random.random() > 0.3 else None,
        created_at=lead_created + timedelta(minutes=30),
        updated_at=lead_created + timedelta(hours=1),
    )


def _add_events(
    events: list[EventLog],
    lead: Lead,
    client_id: uuid.UUID,
    created: datetime,
    state: str,
    n_out: int,
    n_in: int,
) -> None:
    """Generate event log entries for a lead."""
    # lead_created event
    events.append(EventLog(
        id=uuid.uuid4(),
        lead_id=lead.id,
        client_id=client_id,
        action="lead_created",
        status="success",
        message=f"New lead from {lead.source}: {lead.first_name} {lead.last_name}",
        data={"source": lead.source, "service": lead.service_type},
        created_at=created,
    ))

    # sms_sent events
    for i in range(min(n_out, 2)):
        events.append(EventLog(
            id=uuid.uuid4(),
            lead_id=lead.id,
            client_id=client_id,
            action="sms_sent",
            status="success",
            agent_id="intake" if i == 0 else "qualify",
            duration_ms=random.randint(800, 3000),
            cost_usd=0.0079,
            message=f"SMS delivered to {lead.phone[:6]}***",
            created_at=created + timedelta(minutes=i * 5 + 1),
        ))

    # sms_received events
    for i in range(min(n_in, 2)):
        events.append(EventLog(
            id=uuid.uuid4(),
            lead_id=lead.id,
            client_id=client_id,
            action="sms_received",
            status="success",
            message=f"Inbound SMS from {lead.phone[:6]}***",
            created_at=created + timedelta(minutes=i * 5 + 3),
        ))

    # State-specific events
    if state in ("booked", "completed"):
        events.append(EventLog(
            id=uuid.uuid4(),
            lead_id=lead.id,
            client_id=client_id,
            action="booking_confirmed",
            status="success",
            agent_id="book",
            message=f"Appointment booked for {lead.service_type}",
            data={"tech": random.choice(TEAM)},
            created_at=created + timedelta(minutes=25),
        ))

    if state == "opted_out":
        events.append(EventLog(
            id=uuid.uuid4(),
            lead_id=lead.id,
            client_id=client_id,
            action="opt_out_processed",
            status="success",
            message=f"STOP received — opt-out processed for {lead.phone[:6]}***",
            created_at=created + timedelta(minutes=10),
        ))


def _add_followup_tasks(
    followups: list[FollowupTask],
    lead: Lead,
    client_id: uuid.UUID,
    created: datetime,
    state: str,
) -> None:
    """Generate followup tasks for cold and booked leads."""
    if state == "cold":
        # Cold leads get 1-3 nurture tasks (some sent, some pending)
        for seq in range(1, random.randint(2, 4)):
            scheduled = created + timedelta(hours=seq * 24)
            is_sent = scheduled < NOW
            followups.append(FollowupTask(
                id=uuid.uuid4(),
                lead_id=lead.id,
                client_id=client_id,
                task_type="cold_nurture",
                scheduled_at=scheduled,
                sequence_number=seq,
                status="sent" if is_sent else "pending",
                sent_at=scheduled + timedelta(minutes=5) if is_sent else None,
                message_template="cold_nurture_v1",
                created_at=created,
                updated_at=scheduled if is_sent else created,
            ))
    elif state == "booked":
        # Booked leads get a day-before reminder
        followups.append(FollowupTask(
            id=uuid.uuid4(),
            lead_id=lead.id,
            client_id=client_id,
            task_type="day_before_reminder",
            scheduled_at=NOW + timedelta(hours=random.randint(12, 72)),
            sequence_number=1,
            status="pending",
            message_template="reminder_day_before",
            created_at=created + timedelta(minutes=35),
            updated_at=created + timedelta(minutes=35),
        ))
    elif state == "completed":
        # Completed leads get a sent review request
        review_time = created + timedelta(days=1)
        followups.append(FollowupTask(
            id=uuid.uuid4(),
            lead_id=lead.id,
            client_id=client_id,
            task_type="review_request",
            scheduled_at=review_time,
            sequence_number=1,
            status="sent",
            sent_at=review_time + timedelta(minutes=2),
            message_template="review_request_v1",
            created_at=created + timedelta(hours=2),
            updated_at=review_time + timedelta(minutes=2),
        ))


# ---------------------------------------------------------------------------
# Main seed routine
# ---------------------------------------------------------------------------
async def seed() -> None:
    """Seed the demo account."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check for existing demo client
        result = await session.execute(
            text("SELECT id FROM clients WHERE dashboard_email = :email"),
            {"email": DEMO_EMAIL},
        )
        existing_id = result.scalar_one_or_none()

        if existing_id:
            logger.info("Existing demo client found (id=%s). Deleting...", existing_id)
            await _delete_demo_data(session, existing_id)

    # Create fresh demo data
    async with async_session() as session:
        # 1. Client
        client = _create_client()
        session.add(client)
        await session.flush()
        client_id = client.id
        logger.info("Created demo client: %s (id=%s)", BUSINESS_NAME, client_id)

        # 2. Leads + related data
        leads, consents, conversations, bookings, events, followups = _create_leads_and_related(client_id)

        # 3. Insert consent records first (leads FK to them)
        for c in consents:
            session.add(c)
        await session.flush()
        logger.info("Created %d consent records", len(consents))

        # 4. Insert leads
        for lead in leads:
            session.add(lead)
        await session.flush()
        logger.info("Created %d leads", len(leads))

        # 5. Insert conversations
        for conv in conversations:
            session.add(conv)
        await session.flush()
        logger.info("Created %d conversation messages", len(conversations))

        # 6. Insert bookings
        for b in bookings:
            session.add(b)
        await session.flush()
        logger.info("Created %d bookings", len(bookings))

        # 7. Insert events
        for e in events:
            session.add(e)
        await session.flush()
        logger.info("Created %d event log entries", len(events))

        # 8. Insert followup tasks
        for f in followups:
            session.add(f)
        await session.flush()
        logger.info("Created %d followup tasks", len(followups))

        await session.commit()

    await engine.dispose()

    # Summary
    logger.info("=" * 60)
    logger.info("Demo account seeded successfully!")
    logger.info("  Login:    %s / %s", DEMO_EMAIL, DEMO_PASSWORD)
    logger.info("  Leads:    %d", len(leads))
    logger.info("  Messages: %d", len(conversations))
    logger.info("  Bookings: %d", len(bookings))
    logger.info("  Events:   %d", len(events))
    logger.info("  Consents: %d", len(consents))
    logger.info("  Followups:%d", len(followups))
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed())
