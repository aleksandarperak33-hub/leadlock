"""
Seed a test client (Austin Comfort HVAC) into the database.

Usage:
    python scripts/seed_test_client.py
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

import bcrypt
from src.config import get_settings
from src.models.client import Client
from src.models.outreach import Outreach

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_CLIENT_CONFIG = {
    "service_area": {
        "center": {"lat": 30.2672, "lng": -97.7431},  # Austin, TX
        "radius_miles": 30,
        "valid_zips": [],
    },
    "hours": {
        "business": {"start": "07:00", "end": "19:00", "days": ["mon", "tue", "wed", "thu", "fri", "sat"]},
        "saturday": {"start": "08:00", "end": "14:00", "days": ["sat"]},
        "after_hours_handling": "ai_responds_books_next_available",
        "emergency_handling": "ai_responds_plus_owner_alert",
    },
    "persona": {
        "rep_name": "Sarah",
        "tone": "friendly_professional",
        "languages": ["en"],
        "emergency_contact_phone": "+15125550100",
    },
    "services": {
        "primary": ["AC Repair", "AC Installation", "Heating Repair", "Heating Installation"],
        "secondary": ["Duct Cleaning", "Maintenance Plans"],
        "do_not_quote": [],
    },
    "team": [
        {"name": "Mike Rodriguez", "specialty": ["ac_repair", "ac_install"], "active": True},
        {"name": "Carlos Martinez", "specialty": ["heating_repair", "heating_install"], "active": True},
        {"name": "Jake Thompson", "specialty": ["maintenance"], "active": True},
    ],
    "emergency_keywords": ["no heat", "gas leak", "carbon monoxide", "pipe burst", "flooding", "no ac", "fire"],
    "scheduling": {
        "slot_duration_minutes": 120,
        "buffer_minutes": 30,
        "max_daily_bookings": 8,
        "advance_booking_days": 14,
    },
}


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check if test client already exists
        result = await session.execute(
            text("SELECT id FROM clients WHERE business_name = :name"),
            {"name": "Austin Comfort HVAC"},
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info("Test client already exists (id=%s). Skipping.", existing)
        else:
            client = Client(
                business_name="Austin Comfort HVAC",
                trade_type="hvac",
                tier="growth",
                monthly_fee=997.00,
                owner_name="David Chen",
                owner_email="david@austincomforthvac.com",
                owner_phone="+15125550100",
                twilio_phone=settings.twilio_phone_number or "+15125550199",
                twilio_phone_sid="PN_TEST_000000000000000000000000",
                crm_type="google_sheets",
                crm_config={"spreadsheet_id": "test_spreadsheet_id_abc123"},
                config=TEST_CLIENT_CONFIG,
                billing_status="active",
                onboarding_status="live",
                is_active=True,
                dashboard_email="david@austincomforthvac.com",
                dashboard_password_hash=bcrypt.hashpw(b"LeadLock2026!", bcrypt.gensalt()).decode(),
            )
            session.add(client)
            await session.commit()
            logger.info(
                "Seeded test client: %s (id=%s)", client.business_name, client.id
            )

    # Seed admin user
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id FROM clients WHERE dashboard_email = :email"),
            {"email": "aleksandar.perak33@gmail.com"},
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            logger.info("Admin user already exists (id=%s). Skipping.", existing_admin)
        else:
            admin = Client(
                business_name="LeadLock Admin",
                trade_type="general",
                tier="enterprise",
                monthly_fee=0.0,
                owner_name="Aleksandar Perak",
                owner_email="aleksandar.perak33@gmail.com",
                owner_phone="+10000000000",
                crm_type="google_sheets",
                config={},
                billing_status="active",
                onboarding_status="live",
                is_active=True,
                is_admin=True,
                dashboard_email="aleksandar.perak33@gmail.com",
                dashboard_password_hash=bcrypt.hashpw(b"Aleksandar2004$", bcrypt.gensalt()).decode(),
            )
            session.add(admin)
            await session.commit()
            logger.info("Seeded admin user: %s (id=%s)", admin.business_name, admin.id)

    # Seed sample outreach records
    async with async_session() as session:
        result = await session.execute(text("SELECT count(*) FROM outreach"))
        outreach_count = result.scalar() or 0

        if outreach_count > 0:
            logger.info("Outreach records already exist (%d). Skipping.", outreach_count)
        else:
            sample_prospects = [
                Outreach(
                    prospect_name="Mike Johnson",
                    prospect_company="Johnson Plumbing Co",
                    prospect_email="mike@johnsonplumbing.com",
                    prospect_phone="+15125559001",
                    prospect_trade_type="plumbing",
                    status="demo_scheduled",
                    estimated_mrr=997.0,
                    demo_date=date(2026, 2, 20),
                    notes="Referred by Austin Comfort HVAC. 15 trucks, ServiceTitan user.",
                ),
                Outreach(
                    prospect_name="Sarah Williams",
                    prospect_company="Williams Roofing",
                    prospect_email="sarah@williamsroofing.com",
                    prospect_phone="+15125559002",
                    prospect_trade_type="roofing",
                    status="contacted",
                    estimated_mrr=1497.0,
                    notes="Met at home services expo. Interested in growth tier.",
                ),
                Outreach(
                    prospect_name="Carlos Rivera",
                    prospect_company="Rivera Electric",
                    prospect_email="carlos@riveraelectric.com",
                    prospect_phone="+15125559003",
                    prospect_trade_type="electrical",
                    status="cold",
                    estimated_mrr=497.0,
                    notes="Found on Google. 5-person shop in south Austin.",
                ),
                Outreach(
                    prospect_name="Tom Bradley",
                    prospect_company="Bradley Solar Solutions",
                    prospect_email="tom@bradleysolar.com",
                    prospect_phone="+15125559004",
                    prospect_trade_type="solar",
                    status="proposal_sent",
                    estimated_mrr=2497.0,
                    notes="Enterprise tier prospect. 50+ installers. Wants full CRM integration.",
                ),
                Outreach(
                    prospect_name="Lisa Park",
                    prospect_company="Park HVAC Services",
                    prospect_email="lisa@parkhvac.com",
                    prospect_phone="+15125559005",
                    prospect_trade_type="hvac",
                    status="demo_completed",
                    estimated_mrr=997.0,
                    demo_date=date(2026, 2, 12),
                    notes="Demo went well. Following up with proposal this week.",
                ),
            ]
            for p in sample_prospects:
                session.add(p)
            await session.commit()
            logger.info("Seeded %d sample outreach records.", len(sample_prospects))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
