"""
Test configuration and fixtures.
Uses SQLite in-memory for fast tests. Mocks all external services.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from src.database import Base


# Register JSONB as JSON for SQLite compatibility in tests
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
async def db():
    """In-memory SQLite database for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def mock_sms():
    """Mock for async send_sms — prevents real Twilio calls in tests."""
    with patch("src.services.sms.send_sms", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "sid": "SM_test_123",
            "status": "sent",
            "provider": "twilio",
            "segments": 1,
            "cost_usd": 0.0079,
            "error": None,
        }
        yield mock


@pytest.fixture
def mock_ai():
    """Mock for async generate_response — prevents real AI API calls in tests."""
    with patch("src.services.ai.generate_response", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "content": '{"message": "Test response", "qualification": {}, "internal_notes": "", "next_action": "continue_qualifying", "score_adjustment": 0}',
            "provider": "anthropic",
            "model": "claude-haiku",
            "latency_ms": 500,
            "cost_usd": 0.001,
            "input_tokens": 100,
            "output_tokens": 50,
            "error": None,
        }
        yield mock


@pytest.fixture
def mock_redis():
    """Mock for async Redis — prevents real Redis calls in tests."""
    with patch("src.utils.dedup.get_redis") as mock:
        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)
        redis_mock.ping = AsyncMock(return_value=True)
        mock.return_value = redis_mock
        yield redis_mock


@pytest.fixture
def sample_client_config():
    """A complete sample client configuration for testing."""
    return {
        "service_area": {
            "center": {"lat": 30.2672, "lng": -97.7431},
            "radius_miles": 35,
            "valid_zips": ["78701", "78702", "78703"],
        },
        "hours": {
            "business": {
                "start": "07:00",
                "end": "18:00",
                "days": ["mon", "tue", "wed", "thu", "fri"],
            },
            "saturday": {"start": "08:00", "end": "14:00", "days": ["sat"]},
            "after_hours_handling": "ai_responds_books_next_available",
            "emergency_handling": "ai_responds_plus_owner_alert",
        },
        "team": [
            {
                "name": "Mike",
                "specialty": ["hvac_repair", "hvac_install"],
                "active": True,
            }
        ],
        "persona": {
            "rep_name": "Sarah",
            "tone": "friendly_professional",
            "languages": ["en"],
            "emergency_contact_phone": "+15121234567",
        },
        "services": {
            "primary": ["AC Repair", "Heating Repair", "AC Installation"],
            "secondary": ["Duct Cleaning"],
            "do_not_quote": [],
        },
        "emergency_keywords": ["gas leak", "no heat", "no ac", "flooding"],
        "lead_sources": {},
        "scheduling": {
            "slot_duration_minutes": 120,
            "buffer_minutes": 30,
            "max_daily_bookings": 8,
        },
    }


@pytest.fixture
def sample_client_id():
    return str(uuid.UUID("11111111-1111-1111-1111-111111111111"))
