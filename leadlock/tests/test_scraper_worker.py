"""
Scraper worker tests - comprehensive coverage for lead discovery pipeline.
Tests query rotation, dedup, enrichment, round-robin, heartbeat, and the
main scrape_cycle / scrape_location_trade flows.

All external services (Redis, Brave API, enrichment, phone validation) are mocked.
DB tests use the shared SQLite in-memory fixture from conftest.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from sqlalchemy import select

from src.models.scrape_job import ScrapeJob
from src.models.outreach import Outreach
from src.models.sales_config import SalesEngineConfig
from src.workers.scraper import (
    TRADE_QUERY_VARIANTS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_VARIANT_COOLDOWN_DAYS,
    get_query_variants,
    get_next_variant_and_offset,
    scrape_location_trade,
    scrape_cycle,
    run_scraper,
    _heartbeat,
    _get_poll_interval,
    _get_round_robin_position,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _make_config(
    is_active: bool = True,
    target_locations=_SENTINEL,
    target_trade_types=_SENTINEL,
    daily_scrape_limit: int = 100,
    scraper_paused: bool = False,
    scraper_interval_minutes: int = 15,
    variant_cooldown_days: int = 7,
) -> SalesEngineConfig:
    """Create a SalesEngineConfig model instance for testing."""
    if target_locations is _SENTINEL:
        target_locations = [{"city": "Austin", "state": "TX"}]
    if target_trade_types is _SENTINEL:
        target_trade_types = ["hvac"]
    return SalesEngineConfig(
        is_active=is_active,
        target_locations=target_locations,
        target_trade_types=target_trade_types,
        daily_scrape_limit=daily_scrape_limit,
        scraper_paused=scraper_paused,
        scraper_interval_minutes=scraper_interval_minutes,
        variant_cooldown_days=variant_cooldown_days,
    )


def _make_settings(brave_api_key: str = "test-brave-key"):
    """Create a mock settings object."""
    settings = MagicMock()
    settings.brave_api_key = brave_api_key
    return settings


def _make_biz(
    name: str = "Cool HVAC Co",
    place_id: str = "place_123",
    phone: str = "+15125551234",
    website: str = "https://coolhvac.com",
    rating: float = 4.5,
    reviews: int = 100,
    address: str = "123 Main St, Austin, TX 78701",
) -> dict:
    """Create a mock business result from Brave Search."""
    return {
        "name": name,
        "place_id": place_id,
        "phone": phone,
        "website": website,
        "rating": rating,
        "reviews": reviews,
        "address": address,
    }


# ---------------------------------------------------------------------------
# TRADE_QUERY_VARIANTS constant
# ---------------------------------------------------------------------------

class TestTradeQueryVariants:
    """Verify the trade query variant constant is correctly structured."""

    def test_all_expected_trades_present(self):
        expected_trades = {"hvac", "plumbing", "roofing", "electrical", "solar", "general"}
        assert set(TRADE_QUERY_VARIANTS.keys()) == expected_trades

    def test_each_trade_has_six_variants(self):
        for trade, variants in TRADE_QUERY_VARIANTS.items():
            assert len(variants) == 6, f"{trade} should have 6 variants"

    def test_variants_are_nonempty_strings(self):
        for trade, variants in TRADE_QUERY_VARIANTS.items():
            for v in variants:
                assert isinstance(v, str) and len(v) > 0


# ---------------------------------------------------------------------------
# get_query_variants
# ---------------------------------------------------------------------------

class TestGetQueryVariants:
    """Test query variant lookup function."""

    def test_known_trade_returns_list(self):
        result = get_query_variants("hvac")
        assert result == TRADE_QUERY_VARIANTS["hvac"]

    def test_unknown_trade_returns_fallback(self):
        result = get_query_variants("landscaping")
        assert result == ["landscaping contractors"]

    def test_all_standard_trades(self):
        for trade in TRADE_QUERY_VARIANTS:
            variants = get_query_variants(trade)
            assert len(variants) == 6


# ---------------------------------------------------------------------------
# get_next_variant_and_offset
# ---------------------------------------------------------------------------

class TestGetNextVariantAndOffset:
    """Test variant rotation with DB-backed tracking."""

    async def test_first_scrape_returns_variant_zero(self, db):
        """No previous jobs should return variant 0."""
        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == 0
        assert offset == 0

    async def test_skips_used_variants(self, db):
        """Used variants within cooldown should be skipped."""
        # Mark variants 0 and 1 as completed recently
        for v in [0, 1]:
            job = ScrapeJob(
                platform="brave",
                trade_type="hvac",
                location_query=f"query in Austin, TX",
                city="Austin",
                state_code="TX",
                query_variant=v,
                status="completed",
                completed_at=datetime.now(timezone.utc),
            )
            db.add(job)
        await db.flush()

        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == 2
        assert offset == 0

    async def test_all_variants_exhausted_returns_negative(self, db):
        """When all variants used within cooldown, returns (-1, -1)."""
        now = datetime.now(timezone.utc)
        for v in range(6):
            job = ScrapeJob(
                platform="brave",
                trade_type="hvac",
                location_query="query in Austin, TX",
                city="Austin",
                state_code="TX",
                query_variant=v,
                status="completed",
                completed_at=now,
            )
            db.add(job)
        await db.flush()

        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == -1
        assert offset == -1

    async def test_old_variants_are_recycled(self, db):
        """Variants older than cooldown should be available again."""
        old_date = datetime.now(timezone.utc) - timedelta(days=8)
        for v in range(6):
            job = ScrapeJob(
                platform="brave",
                trade_type="hvac",
                location_query="query in Austin, TX",
                city="Austin",
                state_code="TX",
                query_variant=v,
                status="completed",
                completed_at=old_date,
            )
            db.add(job)
        await db.flush()

        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == 0
        assert offset == 0

    async def test_different_location_is_independent(self, db):
        """Variant tracking is per-location."""
        job = ScrapeJob(
            platform="brave",
            trade_type="hvac",
            location_query="query in Dallas, TX",
            city="Dallas",
            state_code="TX",
            query_variant=0,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()

        # Austin should still be at variant 0
        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == 0

    async def test_different_trade_is_independent(self, db):
        """Variant tracking is per-trade."""
        job = ScrapeJob(
            platform="brave",
            trade_type="plumbing",
            location_query="query in Austin, TX",
            city="Austin",
            state_code="TX",
            query_variant=0,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()

        # hvac should still be at variant 0
        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == 0

    async def test_failed_jobs_not_counted(self, db):
        """Only 'completed' jobs should block variants."""
        job = ScrapeJob(
            platform="brave",
            trade_type="hvac",
            location_query="query in Austin, TX",
            city="Austin",
            state_code="TX",
            query_variant=0,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()

        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == 0

    async def test_unknown_trade_with_zero_variants(self, db):
        """Edge case: a trade whose fallback returns one variant."""
        # "landscaping" is not in TRADE_QUERY_VARIANTS so get_query_variants
        # returns ["landscaping contractors"] - 1 variant
        idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "landscaping")
        assert idx == 0
        assert offset == 0

    async def test_zero_variants_returns_negative(self, db):
        """When get_query_variants returns empty list, should return (-1, -1)."""
        with patch("src.workers.scraper.get_query_variants", return_value=[]):
            idx, offset = await get_next_variant_and_offset(db, "Austin", "TX", "hvac")
        assert idx == -1
        assert offset == -1

    async def test_custom_cooldown_days(self, db):
        """Custom cooldown should be respected."""
        # completed 3 days ago - default 7-day cooldown: should be blocked
        completed_at = datetime.now(timezone.utc) - timedelta(days=3)
        job = ScrapeJob(
            platform="brave",
            trade_type="hvac",
            location_query="query in Austin, TX",
            city="Austin",
            state_code="TX",
            query_variant=0,
            status="completed",
            completed_at=completed_at,
        )
        db.add(job)
        await db.flush()

        # With 2-day cooldown, variant 0 is already past cooldown
        idx, offset = await get_next_variant_and_offset(
            db, "Austin", "TX", "hvac", cooldown_days=2
        )
        assert idx == 0


# ---------------------------------------------------------------------------
# _heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    """Test Redis heartbeat."""

    async def test_heartbeat_success(self):
        """Heartbeat stores ISO timestamp in Redis."""
        mock_redis = AsyncMock()
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await _heartbeat()
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "leadlock:worker_health:scraper"
        assert call_args[1]["ex"] == 7200

    async def test_heartbeat_redis_failure_does_not_raise(self):
        """Heartbeat failure should be silently swallowed."""
        with patch("src.utils.dedup.get_redis", side_effect=Exception("Redis down")):
            await _heartbeat()  # should not raise


# ---------------------------------------------------------------------------
# _get_round_robin_position
# ---------------------------------------------------------------------------

class TestGetRoundRobinPosition:
    """Test round-robin position via Redis."""

    async def test_returns_modulo_position(self):
        """Position should be (incr - 1) % total_combos."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=5)
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            pos = await _get_round_robin_position(3)
        assert pos == (5 - 1) % 3  # 1

    async def test_redis_failure_returns_zero(self):
        """On Redis failure, default to position 0."""
        with patch("src.utils.dedup.get_redis", side_effect=Exception("Redis down")):
            pos = await _get_round_robin_position(5)
        assert pos == 0

    async def test_wraps_around(self):
        """Position wraps correctly."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=10)
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            pos = await _get_round_robin_position(4)
        assert pos == (10 - 1) % 4  # 1


# ---------------------------------------------------------------------------
# _get_poll_interval
# ---------------------------------------------------------------------------

class TestGetPollInterval:
    """Test configurable poll interval."""

    async def test_returns_config_value(self):
        """Should return interval from DB config."""
        mock_config = MagicMock()
        mock_config.scraper_interval_minutes = 30

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("src.workers.scraper.async_session_factory", return_value=mock_factory):
            interval = await _get_poll_interval()
        assert interval == 30 * 60

    async def test_returns_default_on_no_config(self):
        """Should return default when no config row exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("src.workers.scraper.async_session_factory", return_value=mock_factory):
            interval = await _get_poll_interval()
        assert interval == DEFAULT_POLL_INTERVAL_SECONDS

    async def test_returns_default_on_db_error(self):
        """Should fallback to default on DB error."""
        with patch("src.workers.scraper.async_session_factory", side_effect=Exception("DB down")):
            interval = await _get_poll_interval()
        assert interval == DEFAULT_POLL_INTERVAL_SECONDS

    async def test_returns_default_when_config_has_no_interval(self):
        """Config exists but scraper_interval_minutes is falsy."""
        mock_config = MagicMock()
        mock_config.scraper_interval_minutes = 0

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("src.workers.scraper.async_session_factory", return_value=mock_factory):
            interval = await _get_poll_interval()
        assert interval == DEFAULT_POLL_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# scrape_location_trade
# ---------------------------------------------------------------------------

class TestScrapeLocationTrade:
    """Test the core scraping function for a single location+trade."""

    async def test_creates_scrape_job_and_prospect(self, db):
        """Happy path: creates a ScrapeJob and Outreach records."""
        config = _make_config()
        db.add(config)
        await db.flush()

        settings = _make_settings()
        biz = _make_biz()

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch(
                "src.workers.scraper.normalize_phone",
                return_value="+15125551234",
            ),
            patch(
                "src.workers.scraper.parse_address_components",
                return_value={"city": "Austin", "state": "TX", "zip": "78701"},
            ),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": "info@coolhvac.com", "source": "website_scrape", "verified": True},
            ),
            patch(
                "src.workers.scraper.validate_email",
                new_callable=AsyncMock,
                return_value={"valid": True, "reason": None},
            ),
        ):
            await scrape_location_trade(
                db, config, settings, "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        # Verify ScrapeJob
        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].status == "completed"
        assert jobs[0].new_prospects_created == 1
        assert jobs[0].duplicates_skipped == 0
        assert jobs[0].results_found == 1
        assert jobs[0].api_cost_usd == 0.005

        # Verify Outreach
        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        assert prospects[0].prospect_name == "Cool HVAC Co"
        assert prospects[0].prospect_email == "info@coolhvac.com"
        assert prospects[0].prospect_phone == "+15125551234"
        assert prospects[0].email_verified is True
        assert prospects[0].email_source == "website_scrape"
        assert prospects[0].city == "Austin"
        assert prospects[0].state_code == "TX"
        assert prospects[0].zip_code == "78701"
        assert prospects[0].outreach_sequence_step == 0
        assert prospects[0].status == "cold"
        assert prospects[0].source == "brave"

    async def test_skips_biz_without_place_id_and_phone(self, db):
        """Businesses with no place_id and no phone should be skipped."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz(place_id="", phone="")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value=""),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert jobs[0].new_prospects_created == 0

    async def test_dedup_by_place_id(self, db):
        """Duplicate place_id should be skipped."""
        config = _make_config()
        db.add(config)

        # Pre-existing prospect with the same place_id
        existing = Outreach(
            prospect_name="Existing Co",
            source_place_id="place_123",
            status="cold",
        )
        db.add(existing)
        await db.flush()

        biz = _make_biz(place_id="place_123")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch("src.workers.scraper.parse_address_components", return_value={}),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert jobs[0].duplicates_skipped == 1
        assert jobs[0].new_prospects_created == 0

    async def test_dedup_by_phone(self, db):
        """Duplicate phone number should be skipped."""
        config = _make_config()
        db.add(config)

        existing = Outreach(
            prospect_name="Existing Co",
            prospect_phone="+15125551234",
            status="cold",
        )
        db.add(existing)
        await db.flush()

        # No place_id but has phone
        biz = _make_biz(place_id="", phone="+15125551234")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch("src.workers.scraper.parse_address_components", return_value={}),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert jobs[0].duplicates_skipped == 1
        assert jobs[0].new_prospects_created == 0

    async def test_no_website_no_email(self, db):
        """Business with no website should get no email enrichment."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz(website="")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch(
                "src.workers.scraper.parse_address_components",
                return_value={"city": "Austin", "state": "TX", "zip": "78701"},
            ),
            patch("src.workers.scraper.extract_domain", return_value=None),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        assert prospects[0].prospect_email is None

    async def test_invalid_email_skipped(self, db):
        """Email that fails validation should be set to None."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz()

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch(
                "src.workers.scraper.parse_address_components",
                return_value={"city": "Austin", "state": "TX", "zip": "78701"},
            ),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": "bad-email@@invalid", "source": "website_scrape"},
            ),
            patch(
                "src.workers.scraper.validate_email",
                new_callable=AsyncMock,
                return_value={"valid": False, "reason": "invalid_format"},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        assert prospects[0].prospect_email is None
        assert prospects[0].email_verified is False
        assert prospects[0].email_source is None

    async def test_enrichment_returns_no_email(self, db):
        """Enrichment may not find an email."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz()

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch(
                "src.workers.scraper.parse_address_components",
                return_value={},
            ),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": None, "source": None},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        assert prospects[0].prospect_email is None

    async def test_search_api_failure_marks_job_failed(self, db):
        """If Brave API call raises, job should be marked 'failed'."""
        config = _make_config()
        db.add(config)
        await db.flush()

        with patch(
            "src.workers.scraper.search_local_businesses",
            new_callable=AsyncMock,
            side_effect=Exception("Brave API timeout"),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].status == "failed"
        assert "Brave API timeout" in jobs[0].error_message
        assert jobs[0].completed_at is not None

    async def test_multiple_businesses_mixed_dupes(self, db):
        """Mix of new and duplicate businesses."""
        config = _make_config()
        db.add(config)

        existing = Outreach(
            prospect_name="Existing Co",
            source_place_id="dupe_place",
            status="cold",
        )
        db.add(existing)
        await db.flush()

        biz_new = _make_biz(name="New Biz", place_id="new_place", phone="+15125559999")
        biz_dupe = _make_biz(name="Dupe Biz", place_id="dupe_place", phone="+15125558888")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz_new, biz_dupe], "cost_usd": 0.01},
            ),
            patch("src.workers.scraper.normalize_phone", side_effect=lambda p: p),
            patch("src.workers.scraper.parse_address_components", return_value={}),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": None, "source": None},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert jobs[0].new_prospects_created == 1
        assert jobs[0].duplicates_skipped == 1
        assert jobs[0].results_found == 2

    async def test_no_place_id_but_has_phone_creates_prospect(self, db):
        """Business with no place_id but valid phone should create prospect."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz(place_id="", phone="+15125559999")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125559999"),
            patch("src.workers.scraper.parse_address_components", return_value={}),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": None, "source": None},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        assert prospects[0].source_place_id is None

    async def test_address_parts_fallback_to_location(self, db):
        """When parse_address_components returns empty, use city/state args."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz()

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch(
                "src.workers.scraper.parse_address_components",
                return_value={"city": None, "state": None, "zip": None},
            ),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": None, "source": None},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert prospects[0].city == "Austin"
        assert prospects[0].state_code == "TX"

    async def test_raw_phone_empty_string_normalized_to_empty(self, db):
        """Empty phone in biz result should produce empty string after normalize."""
        config = _make_config()
        db.add(config)
        await db.flush()

        # No phone at all - should skip if also no place_id
        biz = _make_biz(place_id="place_abc", phone="")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.parse_address_components", return_value={}),
            patch(
                "src.workers.scraper.enrich_prospect_email",
                new_callable=AsyncMock,
                return_value={"email": None, "source": None},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        # Phone is empty, no normalization call
        assert prospects[0].prospect_phone == ""

    async def test_website_no_email_but_extract_domain_returns_domain(self, db):
        """
        When website is falsy AND extract_domain somehow returns a domain,
        the elif branch for pattern-guessing should trigger.

        In the source code, the elif checks `extract_domain(website)` when
        `website` is falsy. This is technically unreachable (extract_domain
        returns None for empty strings). But we test the branch by mocking
        extract_domain to return a domain when website is empty.
        """
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz(website="")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch("src.workers.scraper.parse_address_components", return_value={}),
            patch("src.workers.scraper.extract_domain", return_value="coolhvac.com"),
            patch(
                "src.services.enrichment.guess_email_patterns",
                return_value=["info@coolhvac.com"],
            ),
            patch(
                "src.workers.scraper.validate_email",
                new_callable=AsyncMock,
                return_value={"valid": True, "reason": None},
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert len(prospects) == 1
        assert prospects[0].prospect_email == "info@coolhvac.com"
        assert prospects[0].email_source == "pattern_guess"

    async def test_pattern_guess_empty_list(self, db):
        """When pattern guessing returns empty list, no email set."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz(website="")

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch("src.workers.scraper.normalize_phone", return_value="+15125551234"),
            patch("src.workers.scraper.parse_address_components", return_value={}),
            patch("src.workers.scraper.extract_domain", return_value="coolhvac.com"),
            patch(
                "src.services.enrichment.guess_email_patterns",
                return_value=[],
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        prospects = (await db.execute(select(Outreach))).scalars().all()
        assert prospects[0].prospect_email is None

    async def test_cost_accumulation(self, db):
        """API cost should be recorded on job even with zero results."""
        config = _make_config()
        db.add(config)
        await db.flush()

        with patch(
            "src.workers.scraper.search_local_businesses",
            new_callable=AsyncMock,
            return_value={"results": [], "cost_usd": 0.005},
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert jobs[0].api_cost_usd == 0.005
        assert jobs[0].results_found == 0

    async def test_error_cost_preserved(self, db):
        """If search succeeds but processing fails, cost recorded on failed job."""
        config = _make_config()
        db.add(config)
        await db.flush()

        biz = _make_biz()

        with (
            patch(
                "src.workers.scraper.search_local_businesses",
                new_callable=AsyncMock,
                return_value={"results": [biz], "cost_usd": 0.005},
            ),
            patch(
                "src.workers.scraper.normalize_phone",
                side_effect=Exception("phone exploded"),
            ),
        ):
            await scrape_location_trade(
                db, config, _make_settings(), "Austin", "TX", "Austin, TX",
                "hvac", "HVAC contractors", 0, 0,
            )
            await db.flush()

        jobs = (await db.execute(select(ScrapeJob))).scalars().all()
        assert jobs[0].status == "failed"
        assert jobs[0].api_cost_usd == 0.005
        assert "phone exploded" in jobs[0].error_message


# ---------------------------------------------------------------------------
# scrape_cycle
# ---------------------------------------------------------------------------

class TestScrapeCycle:
    """Test the orchestrating scrape_cycle function."""

    async def _setup_active_config(self, db, **kwargs):
        """Insert an active SalesEngineConfig and return it."""
        config = _make_config(**kwargs)
        db.add(config)
        await db.flush()
        return config

    async def test_disabled_engine_skips(self, db):
        """Inactive sales engine should skip scraping."""
        await self._setup_active_config(db, is_active=False)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_no_brave_key_skips(self, db):
        """Missing Brave API key should skip scraping."""
        await self._setup_active_config(db)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        mock_settings = _make_settings(brave_api_key="")

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=mock_settings),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_no_locations_skips(self, db):
        """Empty target_locations should skip."""
        await self._setup_active_config(db, target_locations=[])

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_no_trades_skips(self, db):
        """Empty target_trade_types should skip."""
        await self._setup_active_config(db, target_trade_types=[])

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_daily_limit_reached_skips(self, db):
        """Exceeding daily scrape limit should skip."""
        config = await self._setup_active_config(db, daily_scrape_limit=1)

        # Create a ScrapeJob from today
        job = ScrapeJob(
            platform="brave",
            trade_type="hvac",
            location_query="test",
            city="Austin",
            state_code="TX",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_all_variants_exhausted_skips(self, db):
        """All variants in cooldown should skip scraping."""
        config = await self._setup_active_config(db)

        # Exhaust all 6 HVAC variants
        now = datetime.now(timezone.utc)
        for v in range(6):
            job = ScrapeJob(
                platform="brave",
                trade_type="hvac",
                location_query=f"query in Austin, TX",
                city="Austin",
                state_code="TX",
                query_variant=v,
                status="completed",
                completed_at=now,
            )
            db.add(job)
        await db.flush()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper._get_round_robin_position", new_callable=AsyncMock, return_value=0),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_successful_cycle_calls_scrape_location_trade(self, db):
        """A valid cycle should call scrape_location_trade."""
        config = await self._setup_active_config(db)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper._get_round_robin_position", new_callable=AsyncMock, return_value=0),
            patch("src.workers.scraper.scrape_location_trade", new_callable=AsyncMock) as mock_slt,
        ):
            await scrape_cycle()

        mock_slt.assert_called_once()
        call_args = mock_slt.call_args
        assert call_args[0][3] == "Austin"  # city
        assert call_args[0][4] == "TX"  # state
        assert call_args[0][6] == "hvac"  # trade

    async def test_no_config_row_skips(self, db):
        """No SalesEngineConfig row should skip."""
        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_none_locations_skips(self, db):
        """None target_locations should skip."""
        await self._setup_active_config(db, target_locations=None)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        # SalesEngineConfig with target_locations=None goes through.
        # The code does `config.target_locations or []` so None becomes [].
        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper.search_local_businesses", new_callable=AsyncMock) as mock_search,
        ):
            await scrape_cycle()
        mock_search.assert_not_called()

    async def test_multiple_combos_uses_round_robin(self, db):
        """Multiple location+trade combos should pick one via round-robin."""
        await self._setup_active_config(
            db,
            target_locations=[
                {"city": "Austin", "state": "TX"},
                {"city": "Dallas", "state": "TX"},
            ],
            target_trade_types=["hvac", "plumbing"],
        )

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=db)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        # Round-robin position 2 -> combos[2] = (Dallas, TX, hvac)
        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper.get_settings", return_value=_make_settings()),
            patch("src.workers.scraper._get_round_robin_position", new_callable=AsyncMock, return_value=2),
            patch("src.workers.scraper.scrape_location_trade", new_callable=AsyncMock) as mock_slt,
        ):
            await scrape_cycle()

        mock_slt.assert_called_once()
        call_args = mock_slt.call_args
        assert call_args[0][3] == "Dallas"  # city
        assert call_args[0][6] == "hvac"  # trade


# ---------------------------------------------------------------------------
# run_scraper
# ---------------------------------------------------------------------------

class TestRunScraper:
    """Test the main loop (only a single iteration)."""

    async def test_run_scraper_calls_scrape_cycle(self):
        """The main loop should call scrape_cycle and heartbeat."""
        call_count = 0

        async def _mock_scrape_cycle():
            nonlocal call_count
            call_count += 1

        async def _break_loop(*args, **kwargs):
            """Break the infinite loop after first iteration."""
            raise KeyboardInterrupt("stop")

        mock_config = MagicMock()
        mock_config.scraper_paused = False

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper._get_poll_interval", new_callable=AsyncMock, return_value=1),
            patch("src.workers.scraper.scrape_cycle", side_effect=_mock_scrape_cycle),
            patch("src.workers.scraper._heartbeat", new_callable=AsyncMock, side_effect=_break_loop),
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_scraper()

        assert call_count == 1

    async def test_run_scraper_paused_skips_cycle(self):
        """When scraper_paused is True, scrape_cycle should not be called."""
        mock_config = MagicMock()
        mock_config.scraper_paused = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        async def _break_loop(*args, **kwargs):
            raise KeyboardInterrupt("stop")

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper._get_poll_interval", new_callable=AsyncMock, return_value=1),
            patch("src.workers.scraper.scrape_cycle", new_callable=AsyncMock) as mock_cycle,
            patch("src.workers.scraper._heartbeat", new_callable=AsyncMock, side_effect=_break_loop),
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_scraper()

        mock_cycle.assert_not_called()

    async def test_run_scraper_cycle_error_continues(self):
        """Errors in scrape_cycle should be caught and the loop continues."""
        iteration = 0

        async def _heartbeat_counter():
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise KeyboardInterrupt("stop")

        mock_config = MagicMock()
        mock_config.scraper_paused = False

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper._get_poll_interval", new_callable=AsyncMock, return_value=1),
            patch("src.workers.scraper.scrape_cycle", new_callable=AsyncMock, side_effect=Exception("boom")),
            patch("src.workers.scraper._heartbeat", new_callable=AsyncMock, side_effect=_heartbeat_counter),
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_scraper()

        # Heartbeat was reached despite cycle error
        assert iteration >= 1

    async def test_run_scraper_sleep_with_jitter(self):
        """The main loop should sleep with jitter after each cycle."""
        mock_config = MagicMock()
        mock_config.scraper_paused = False

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper._get_poll_interval", new_callable=AsyncMock, return_value=60),
            patch("src.workers.scraper.scrape_cycle", new_callable=AsyncMock),
            patch("src.workers.scraper._heartbeat", new_callable=AsyncMock),
            patch("src.workers.scraper.random") as mock_random,
            patch("src.workers.scraper.asyncio") as mock_asyncio,
        ):
            mock_random.randint.return_value = 100
            mock_asyncio.sleep = AsyncMock(side_effect=KeyboardInterrupt("stop"))

            with pytest.raises(KeyboardInterrupt):
                await run_scraper()

            mock_asyncio.sleep.assert_called_once_with(60 + 100)
            mock_random.randint.assert_called_once_with(0, 300)

    async def test_run_scraper_no_config_calls_cycle(self):
        """When no config row exists, scrape_cycle should still be called."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        async def _break_loop(*args, **kwargs):
            raise KeyboardInterrupt("stop")

        with (
            patch("src.workers.scraper.async_session_factory", return_value=mock_factory),
            patch("src.workers.scraper._get_poll_interval", new_callable=AsyncMock, return_value=1),
            patch("src.workers.scraper.scrape_cycle", new_callable=AsyncMock) as mock_cycle,
            patch("src.workers.scraper._heartbeat", new_callable=AsyncMock, side_effect=_break_loop),
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_scraper()

        mock_cycle.assert_called_once()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants."""

    def test_default_poll_interval(self):
        assert DEFAULT_POLL_INTERVAL_SECONDS == 15 * 60

    def test_default_variant_cooldown(self):
        assert DEFAULT_VARIANT_COOLDOWN_DAYS == 7
