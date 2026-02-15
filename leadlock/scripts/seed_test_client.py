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
    "business_name": "Austin Comfort HVAC",
    "industry": "hvac",
    "service_area": {
        "cities": ["Austin", "Round Rock", "Cedar Park", "Pflugerville", "Georgetown"],
        "state": "TX",
        "radius_miles": 30,
    },
    "services": [
        "AC Repair",
        "AC Installation",
        "Heating Repair",
        "Heating Installation",
        "Duct Cleaning",
        "Maintenance Plans",
    ],
    "business_hours": {"start": "07:00", "end": "19:00", "days": [0, 1, 2, 3, 4, 5]},
    "saturday_hours": {"start": "08:00", "end": "14:00"},
    "emergency_after_hours": True,
    "persona": {
        "rep_name": "Sarah",
        "tone": "warm_professional",
        "greeting_style": "friendly",
    },
    "team": [
        {"name": "Mike Rodriguez", "role": "Senior Tech", "active": True},
        {"name": "Carlos Martinez", "role": "Tech", "active": True},
        {"name": "Jake Thompson", "role": "Apprentice", "active": True},
    ],
    "scheduling": {
        "slot_duration_minutes": 120,
        "buffer_minutes": 30,
        "max_daily_bookings": 8,
        "days_ahead": 14,
    },
    "qualification": {
        "required_fields": ["service_type", "urgency"],
        "max_qualify_messages": 4,
    },
    "followup": {
        "cold_nurture_enabled": True,
        "cold_nurture_max": 3,
        "cold_nurture_delays_hours": [24, 72, 168],
        "review_request_enabled": True,
        "review_request_delay_days": 3,
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
