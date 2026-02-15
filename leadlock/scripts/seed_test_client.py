"""
Seed a test client (Austin Comfort HVAC) into the database.

Usage:
    python scripts/seed_test_client.py
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.models.client import Client

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
            return

        client = Client(
            business_name="Austin Comfort HVAC",
            trade_type="hvac",
            tier="growth",
            monthly_fee=997.00,
            owner_name="David Chen",
            owner_email="david@austincomforthvac.com",
            owner_phone="+15125550100",
            twilio_phone="+15125550199",
            twilio_phone_sid="PN_TEST_000000000000000000000000",
            crm_type="google_sheets",
            crm_config={"spreadsheet_id": "test_spreadsheet_id_abc123"},
            config=TEST_CLIENT_CONFIG,
            billing_status="active",
            onboarding_status="live",
            is_active=True,
            dashboard_email="david@austincomforthvac.com",
            dashboard_password_hash="$2b$12$test_hash_not_real_bcrypt_placeholder",
        )
        session.add(client)
        await session.commit()
        logger.info(
            "Seeded test client: %s (id=%s)", client.business_name, client.id
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
