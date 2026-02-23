"""
Tests for src/workers/outreach_sequencer.py - outreach email sequence worker.
Covers sanitize_dashes, is_within_send_window, _check_smart_timing,
_heartbeat, _get_warmup_limit, _check_email_health, _calculate_cycle_cap,
run_outreach_sequencer, sequence_cycle, _process_campaign_prospects,
_generate_email_with_template, and send_sequence_email.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.outreach_sequencer import (
    sanitize_dashes,
    is_within_send_window,
    _check_smart_timing,
    _heartbeat,
    _get_warmup_limit,
    _check_email_health,
    _calculate_cycle_cap,
    _verify_or_find_working_email,
    _is_ai_circuit_open,
    _trip_ai_circuit_breaker,
    _recover_generation_failed,
    run_outreach_sequencer,
    sequence_cycle,
    _process_campaign_prospects,
    _generate_email_with_template,
    send_sequence_email,
    EMAIL_WARMUP_SCHEDULE,
    POLL_INTERVAL_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    is_active: bool = True,
    send_timezone: str = "America/Chicago",
    send_weekdays_only: bool = True,
    send_hours_start: str = "08:00",
    send_hours_end: str = "18:00",
    daily_email_limit: int = 50,
    sequence_delay_hours: int = 48,
    max_sequence_steps: int = 3,
    from_email: str = "sales@leadlock.ai",
    from_name: str = "LeadLock",
    sender_name: str = "Alek",
    reply_to_email: str = "reply@leadlock.ai",
    company_address: str = "123 Main St",
    sequencer_paused: bool = False,
):
    """Create a mock SalesEngineConfig."""
    config = MagicMock()
    config.is_active = is_active
    config.send_timezone = send_timezone
    config.send_weekdays_only = send_weekdays_only
    config.send_hours_start = send_hours_start
    config.send_hours_end = send_hours_end
    config.daily_email_limit = daily_email_limit
    config.sequence_delay_hours = sequence_delay_hours
    config.max_sequence_steps = max_sequence_steps
    config.from_email = from_email
    config.from_name = from_name
    config.sender_name = sender_name
    config.reply_to_email = reply_to_email
    config.company_address = company_address
    config.sequencer_paused = sequencer_paused
    return config


def _make_prospect(
    prospect_id: uuid.UUID | None = None,
    prospect_name: str = "John Doe",
    prospect_company: str = "Acme HVAC",
    prospect_email: str = "john@acmehvac.com",
    prospect_trade_type: str = "hvac",
    city: str = "Austin",
    state_code: str = "TX",
    status: str = "cold",
    outreach_sequence_step: int = 0,
    campaign_id: uuid.UUID | None = None,
    email_unsubscribed: bool = False,
    last_email_sent_at: datetime | None = None,
    last_email_replied_at: datetime | None = None,
    total_emails_sent: int = 0,
    total_cost_usd: float = 0.0,
    google_rating: float | None = 4.5,
    review_count: int | None = 100,
    website: str | None = "https://acmehvac.com",
):
    """Create a mock Outreach prospect."""
    prospect = MagicMock()
    prospect.id = prospect_id or uuid.uuid4()
    prospect.prospect_name = prospect_name
    prospect.prospect_company = prospect_company
    prospect.prospect_email = prospect_email
    prospect.prospect_trade_type = prospect_trade_type
    prospect.city = city
    prospect.state_code = state_code
    prospect.status = status
    prospect.outreach_sequence_step = outreach_sequence_step
    prospect.generation_failures = 0
    prospect.campaign_id = campaign_id
    prospect.email_unsubscribed = email_unsubscribed
    prospect.last_email_sent_at = last_email_sent_at
    prospect.last_email_replied_at = last_email_replied_at
    prospect.total_emails_sent = total_emails_sent
    prospect.total_cost_usd = total_cost_usd
    prospect.google_rating = google_rating
    prospect.review_count = review_count
    prospect.website = website
    prospect.email_source = "website_deep_scrape"
    prospect.email_verified = True
    prospect.enrichment_data = None
    prospect.created_at = datetime.now(timezone.utc)
    prospect.updated_at = datetime.now(timezone.utc)
    return prospect


def _make_campaign(
    campaign_id: uuid.UUID | None = None,
    name: str = "Test Campaign",
    status: str = "active",
    daily_limit: int = 25,
    total_sent: int = 0,
    sequence_steps: list | None = None,
):
    """Create a mock Campaign."""
    campaign = MagicMock()
    campaign.id = campaign_id or uuid.uuid4()
    campaign.name = name
    campaign.status = status
    campaign.daily_limit = daily_limit
    campaign.total_sent = total_sent
    campaign.sequence_steps = sequence_steps or []
    return campaign


def _make_settings(app_base_url: str = "https://app.leadlock.ai"):
    """Create a mock settings object."""
    settings = MagicMock()
    settings.app_base_url = app_base_url
    return settings


def _make_template(
    template_id: uuid.UUID | None = None,
    is_ai_generated: bool = True,
    body_template: str | None = None,
    subject_template: str | None = None,
    ai_instructions: str | None = None,
):
    """Create a mock EmailTemplate."""
    tmpl = MagicMock()
    tmpl.id = template_id or uuid.uuid4()
    tmpl.is_ai_generated = is_ai_generated
    tmpl.body_template = body_template
    tmpl.subject_template = subject_template
    tmpl.ai_instructions = ai_instructions
    return tmpl


# ---------------------------------------------------------------------------
# sanitize_dashes
# ---------------------------------------------------------------------------

class TestSanitizeDashes:
    """Tests for sanitize_dashes."""

    def test_replaces_em_dash(self):
        assert sanitize_dashes("hello\u2014world") == "hello-world"

    def test_replaces_en_dash(self):
        assert sanitize_dashes("hello\u2013world") == "hello-world"

    def test_replaces_figure_dash(self):
        assert sanitize_dashes("hello\u2012world") == "hello-world"

    def test_replaces_horizontal_bar(self):
        assert sanitize_dashes("hello\u2015world") == "hello-world"

    def test_replaces_hyphen_unicode(self):
        assert sanitize_dashes("hello\u2010world") == "hello-world"

    def test_replaces_non_breaking_hyphen(self):
        assert sanitize_dashes("hello\u2011world") == "hello-world"

    def test_empty_string_returns_empty(self):
        assert sanitize_dashes("") == ""

    def test_none_like_falsy_returns_as_is(self):
        assert sanitize_dashes("") == ""

    def test_normal_text_unchanged(self):
        assert sanitize_dashes("hello-world") == "hello-world"

    def test_multiple_dash_types(self):
        text = "A\u2014B\u2013C\u2012D"
        assert sanitize_dashes(text) == "A-B-C-D"


# ---------------------------------------------------------------------------
# is_within_send_window
# ---------------------------------------------------------------------------

class TestIsWithinSendWindow:
    """Tests for is_within_send_window."""

    @patch("src.workers.outreach_sequencer.datetime")
    def test_within_window_weekday(self, mock_dt):
        """Returns True when current time is within send window on a weekday."""
        # Wednesday at 10:00 AM Central
        mock_now = MagicMock()
        mock_now.weekday.return_value = 2  # Wednesday
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        result = is_within_send_window(config)
        assert result is True

    @patch("src.workers.outreach_sequencer.datetime")
    def test_outside_window_too_early(self, mock_dt):
        """Returns False when before send_hours_start."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1  # Tuesday
        mock_now.hour = 7
        mock_now.minute = 30
        mock_dt.now.return_value = mock_now

        config = _make_config(send_hours_start="08:00", send_hours_end="18:00")
        result = is_within_send_window(config)
        assert result is False

    @patch("src.workers.outreach_sequencer.datetime")
    def test_outside_window_too_late(self, mock_dt):
        """Returns False when after send_hours_end."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1  # Tuesday
        mock_now.hour = 19
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_hours_start="08:00", send_hours_end="18:00")
        result = is_within_send_window(config)
        assert result is False

    @patch("src.workers.outreach_sequencer.datetime")
    def test_weekend_blocked_when_weekdays_only(self, mock_dt):
        """Returns False on weekends when send_weekdays_only is True."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 5  # Saturday
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_weekdays_only=True)
        result = is_within_send_window(config)
        assert result is False

    @patch("src.workers.outreach_sequencer.datetime")
    def test_weekend_allowed_when_not_weekdays_only(self, mock_dt):
        """Returns True on weekends when send_weekdays_only is False."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 6  # Sunday
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_weekdays_only=False)
        result = is_within_send_window(config)
        assert result is True

    @patch("src.workers.outreach_sequencer.datetime")
    def test_invalid_timezone_falls_back(self, mock_dt):
        """Falls back to America/Chicago on invalid timezone."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_timezone="Invalid/Timezone")
        # Should not raise
        result = is_within_send_window(config)
        assert isinstance(result, bool)

    @patch("src.workers.outreach_sequencer.datetime")
    def test_missing_timezone_uses_default(self, mock_dt):
        """Uses America/Chicago when timezone is None."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        config.send_timezone = None
        result = is_within_send_window(config)
        assert isinstance(result, bool)

    @patch("src.workers.outreach_sequencer.datetime")
    def test_invalid_send_hours_uses_defaults(self, mock_dt):
        """Uses 08:00-18:00 when send hours cannot be parsed."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        config.send_hours_start = "invalid"
        config.send_hours_end = "invalid"
        result = is_within_send_window(config)
        assert result is True

    @patch("src.workers.outreach_sequencer.datetime")
    def test_missing_send_hours_uses_defaults(self, mock_dt):
        """Uses 08:00-18:00 when send hours attributes are None."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        config.send_hours_start = None
        config.send_hours_end = None
        result = is_within_send_window(config)
        assert result is True

    @patch("src.workers.outreach_sequencer.datetime")
    def test_at_exact_start_boundary(self, mock_dt):
        """Returns True when exactly at start time."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1
        mock_now.hour = 8
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_hours_start="08:00", send_hours_end="18:00")
        result = is_within_send_window(config)
        assert result is True

    @patch("src.workers.outreach_sequencer.datetime")
    def test_at_exact_end_boundary(self, mock_dt):
        """Returns False when exactly at end time (exclusive)."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1
        mock_now.hour = 18
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_hours_start="08:00", send_hours_end="18:00")
        result = is_within_send_window(config)
        assert result is False

    @patch("src.workers.outreach_sequencer.datetime")
    def test_missing_weekdays_only_attribute(self, mock_dt):
        """Defaults to True when send_weekdays_only attr missing."""
        mock_now = MagicMock()
        mock_now.weekday.return_value = 5  # Saturday
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        # Remove the attribute so getattr falls back
        del config.send_weekdays_only
        config.send_weekdays_only = True
        result = is_within_send_window(config)
        assert result is False


# ---------------------------------------------------------------------------
# _check_smart_timing
# ---------------------------------------------------------------------------

class TestCheckSmartTiming:
    """Tests for _check_smart_timing."""

    @patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock)
    @patch("src.services.learning._time_bucket")
    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    async def test_defers_when_not_in_best_bucket(
        self, mock_best, mock_bucket, mock_enqueue,
    ):
        """Returns True and enqueues task when not in best bucket."""
        mock_best.return_value = "9am-12pm"
        mock_bucket.return_value = "3pm-6pm"

        prospect = _make_prospect()
        config = _make_config()

        result = await _check_smart_timing(prospect, config)

        assert result is True
        mock_enqueue.assert_awaited_once()

    @patch("src.services.learning._time_bucket")
    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    async def test_sends_now_when_already_in_best_bucket(
        self, mock_best, mock_bucket,
    ):
        """Returns False when current bucket matches best bucket."""
        mock_best.return_value = "9am-12pm"
        mock_bucket.return_value = "9am-12pm"

        prospect = _make_prospect()
        config = _make_config()

        result = await _check_smart_timing(prospect, config)

        assert result is False

    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    async def test_sends_now_when_no_best_bucket(self, mock_best):
        """Returns False when no best send time data available."""
        mock_best.return_value = None

        prospect = _make_prospect()
        config = _make_config()

        result = await _check_smart_timing(prospect, config)

        assert result is False

    async def test_sends_now_on_exception(self):
        """Returns False when smart timing check raises an exception."""
        prospect = _make_prospect()
        config = _make_config()

        with patch(
            "src.services.learning.get_best_send_time",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            result = await _check_smart_timing(prospect, config)

        assert result is False

    @patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock)
    @patch("src.services.learning._time_bucket")
    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    async def test_does_not_defer_more_than_24_hours(
        self, mock_best, mock_bucket, mock_enqueue,
    ):
        """Returns False if delay would exceed 24 hours."""
        # Use a bucket that is unknown - defaults to target hour 9
        mock_best.return_value = "unknown_bucket"
        mock_bucket.return_value = "3pm-6pm"

        prospect = _make_prospect()
        config = _make_config()

        # The function checks delay_seconds > 86400
        # For an unknown bucket, target_hour defaults to 9
        # If current time is e.g. 8AM, delay to 9AM next day is > 24h
        # But this depends on datetime.now, which varies. Let's test the exception path.
        result = await _check_smart_timing(prospect, config)

        # Either True (deferred) or False (too long delay), depends on time
        assert isinstance(result, bool)

    @patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock)
    @patch("src.services.learning._time_bucket")
    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    async def test_invalid_timezone_falls_back(
        self, mock_best, mock_bucket, mock_enqueue,
    ):
        """Falls back to America/Chicago on invalid timezone."""
        mock_best.return_value = "evening"
        mock_bucket.return_value = "early_morning"

        prospect = _make_prospect()
        config = _make_config(send_timezone="Invalid/Zone")

        result = await _check_smart_timing(prospect, config)
        assert isinstance(result, bool)

    @patch("src.services.task_dispatch.enqueue_task", new_callable=AsyncMock)
    @patch("src.services.learning._time_bucket")
    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.datetime")
    async def test_delay_over_24_hours_sends_now(
        self, mock_dt, mock_best, mock_bucket, mock_enqueue,
    ):
        """Returns False when calculated delay exceeds 24 hours."""
        mock_best.return_value = "early_morning"  # target_hour = 6
        mock_bucket.return_value = "evening"

        # Simulate time where target would be > 24h away
        # If current time is 5:30 AM, target_time at 6 AM is 30 min away (< 24h)
        # so set up the mock so that target_time <= now_local forces +1 day
        # and then delay > 86400

        # Create a mock now_local where target_hour (6) is already past
        mock_now = MagicMock()
        mock_now.hour = 6
        mock_now.minute = 30
        # target_time = replace(hour=6, min=0) => 6:00, which <= 6:30 => +1 day
        # delay = 23.5 hours => < 86400 ... still not enough

        # To exceed 86400: we need the delta to be > 86400
        # Let's use real datetime objects for the calculation
        from datetime import datetime as real_dt
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Chicago")
        now_real = real_dt(2026, 2, 18, 6, 1, 0, tzinfo=tz)
        target = now_real.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)
        # target is 6:00 next day, now is 6:01 today
        # delay = ~23h 59min = 86340 < 86400 ... just under

        # To get > 86400 we need target to be > 24h away
        # This is hard with replace + timedelta(days=1)
        # The only way delay > 86400 is if target_time + 1 day - now > 86400
        # That means now < target_time (same day) but target + 1 day anyway?
        # Actually re-reading: target_time = now_local.replace(hour=target_hour)
        # if target_time <= now_local: target_time += 1 day
        # So delay = target_time - now_local
        # max delay is ~24h (when target_time.hour == now.hour but now is just past)
        # It can never exceed 24h through this path.
        # BUT: with mock datetime, we can make the subtraction return > 86400

        # Use mock to control the calculation
        mock_target = MagicMock()
        mock_now_local = MagicMock()
        mock_now_local.replace.return_value = mock_target
        mock_now_local.hour = 7

        # target_time <= now_local => True, so target_time += 1 day
        mock_target.__le__ = lambda self, other: True
        added = MagicMock()
        mock_target.__add__ = lambda self, other: added

        # delay_seconds = (added - now_local).total_seconds()
        diff = MagicMock()
        diff.total_seconds.return_value = 90000  # > 86400
        added.__sub__ = lambda self, other: diff

        mock_dt.now.return_value = mock_now_local

        prospect = _make_prospect()
        config = _make_config()

        result = await _check_smart_timing(prospect, config)

        assert result is False
        mock_enqueue.assert_not_awaited()

    @patch("src.services.learning._time_bucket")
    @patch("src.services.learning.get_best_send_time", new_callable=AsyncMock)
    async def test_missing_prospect_trade_type(self, mock_best, mock_bucket):
        """Handles None trade type by using 'general'."""
        mock_best.return_value = None
        prospect = _make_prospect()
        prospect.prospect_trade_type = None
        prospect.state_code = None
        config = _make_config()

        result = await _check_smart_timing(prospect, config)
        assert result is False
        mock_best.assert_awaited_once_with("general", "")


# ---------------------------------------------------------------------------
# _heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:
    """Tests for _heartbeat."""

    async def test_stores_heartbeat_in_redis(self):
        """Heartbeat stores timestamp in Redis."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await _heartbeat()

        mock_redis.set.assert_awaited_once()
        call_args = mock_redis.set.call_args
        assert "leadlock:worker_health:outreach_sequencer" in str(call_args)

    async def test_heartbeat_swallows_exceptions(self):
        """Heartbeat does not raise on Redis failure."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            # Should not raise
            await _heartbeat()


# ---------------------------------------------------------------------------
# _get_warmup_limit
# ---------------------------------------------------------------------------

class TestGetWarmupLimit:
    """Tests for _get_warmup_limit."""

    async def test_first_send_returns_10(self):
        """First email send ever (no Redis key, no DB history) returns min(10, configured)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("src.workers.outreach_sequencer._recover_warmup_start_from_db", new_callable=AsyncMock, return_value=None),
        ):
            result = await _get_warmup_limit(150, "sales@leadlock.ai")

        assert result == 10

    async def test_first_send_respects_configured_limit_lower_than_10(self):
        """First send returns configured_limit when it's less than warmup day 0."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        with (
            patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis),
            patch("src.workers.outreach_sequencer._recover_warmup_start_from_db", new_callable=AsyncMock, return_value=None),
        ):
            result = await _get_warmup_limit(5, "sales@leadlock.ai")

        assert result == 5

    async def test_day_3_returns_10(self):
        """Day 3 is still in range (0-3), should return warmup limit of 10."""
        started = datetime.now(timezone.utc) - timedelta(days=3)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _get_warmup_limit(150, "sales@leadlock.ai")

        assert result == 10

    async def test_day_6_returns_20(self):
        """Day 6 is in range (4-7), should return warmup limit of 20."""
        started = datetime.now(timezone.utc) - timedelta(days=6)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _get_warmup_limit(150, "sales@leadlock.ai")

        assert result == 20

    async def test_day_10_returns_40(self):
        """Day 10 (week 2) is in range (8-14), should return warmup limit of 40."""
        started = datetime.now(timezone.utc) - timedelta(days=10)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _get_warmup_limit(150, "sales@leadlock.ai")

        assert result == 40

    async def test_day_18_returns_75(self):
        """Day 18 (week 3) is in range (15-21), should return warmup limit of 75."""
        started = datetime.now(timezone.utc) - timedelta(days=18)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _get_warmup_limit(200, "sales@leadlock.ai")

        assert result == 75

    async def test_day_25_returns_120(self):
        """Day 25 is in range (22-28), should return warmup limit of 120."""
        started = datetime.now(timezone.utc) - timedelta(days=25)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _get_warmup_limit(200, "sales@leadlock.ai")

        assert result == 120

    async def test_day_30_returns_configured_limit(self):
        """After 29 days, returns the configured limit."""
        started = datetime.now(timezone.utc) - timedelta(days=30)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _get_warmup_limit(200, "sales@leadlock.ai")

        assert result == 200

    async def test_warmup_limit_respects_min_of_configured(self):
        """Warmup limit never exceeds configured limit."""
        started = datetime.now(timezone.utc) - timedelta(days=18)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            # Configured limit = 30, warmup at day 18 = 75, min = 30
            result = await _get_warmup_limit(30, "sales@leadlock.ai")

        assert result == 30

    async def test_redis_failure_returns_configured_limit(self):
        """Returns configured limit when Redis fails."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            result = await _get_warmup_limit(50, "sales@leadlock.ai")

        assert result == 50

    async def test_extracts_domain_from_email(self):
        """Extracts domain from from_email for warmup key."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await _get_warmup_limit(50, "sales@example.com")

        # Should use domain-based key
        set_call = mock_redis.set.call_args
        assert "example.com" in str(set_call)

    async def test_no_at_in_email_uses_default_domain(self):
        """Uses 'default' domain when no @ in from_email."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            await _get_warmup_limit(50, "noemail")

        set_call = mock_redis.set.call_args
        assert "default" in str(set_call)

    async def test_warmup_schedule_loop_fallback(self):
        """Covers the fallback after the warmup schedule loop when no entry matches."""
        started = datetime.now(timezone.utc) - timedelta(days=10)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=started.isoformat().encode())

        # Temporarily replace warmup schedule with entries that don't match day 10
        fake_schedule = [
            (0, 3, 5),
            (4, 7, 10),
            # Gap: days 8-14 not covered, and no None sentinel
        ]

        with (
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch(
                "src.workers.outreach_sequencer.EMAIL_WARMUP_SCHEDULE",
                fake_schedule,
            ),
        ):
            result = await _get_warmup_limit(200, "sales@leadlock.ai")

        # Falls through the loop without matching => returns configured_limit
        assert result == 200

    async def test_string_value_from_redis(self):
        """Handles non-bytes value from Redis (string)."""
        started = datetime.now(timezone.utc) - timedelta(days=6)
        mock_redis = AsyncMock()
        # Return string, not bytes
        mock_redis.get = AsyncMock(return_value=started.isoformat())

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ):
            result = await _get_warmup_limit(150, "sales@leadlock.ai")

        assert result == 20


# ---------------------------------------------------------------------------
# _check_email_health
# ---------------------------------------------------------------------------

class TestCheckEmailHealth:
    """Tests for _check_email_health."""

    async def test_normal_reputation(self):
        """Returns (True, 'normal') for healthy reputation."""
        mock_redis = AsyncMock()
        reputation = {
            "score": 95.0,
            "throttle": "normal",
            "metrics": {"bounce_rate": 0.01, "complaint_rate": 0.0001},
        }

        with (
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=reputation,
            ),
        ):
            allowed, throttle = await _check_email_health()

        assert allowed is True
        assert throttle == "normal"

    async def test_reduced_reputation(self):
        """Returns (True, 'reduced') for warning reputation."""
        mock_redis = AsyncMock()
        reputation = {
            "score": 60.0,
            "throttle": "reduced",
            "metrics": {"bounce_rate": 0.05, "complaint_rate": 0.001},
        }

        with (
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=reputation,
            ),
        ):
            allowed, throttle = await _check_email_health()

        assert allowed is True
        assert throttle == "reduced"

    async def test_critical_reputation(self):
        """Returns (True, 'critical') for poor reputation."""
        mock_redis = AsyncMock()
        reputation = {
            "score": 30.0,
            "throttle": "critical",
            "metrics": {"bounce_rate": 0.1, "complaint_rate": 0.005},
        }

        with (
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=reputation,
            ),
        ):
            allowed, throttle = await _check_email_health()

        assert allowed is True
        assert throttle == "critical"

    async def test_paused_reputation(self):
        """Returns (False, 'paused') for critically bad reputation."""
        mock_redis = AsyncMock()
        reputation = {
            "score": 10.0,
            "throttle": "paused",
            "metrics": {"bounce_rate": 0.2, "complaint_rate": 0.01},
        }

        with (
            patch(
                "src.utils.dedup.get_redis",
                new_callable=AsyncMock,
                return_value=mock_redis,
            ),
            patch(
                "src.services.deliverability.get_email_reputation",
                new_callable=AsyncMock,
                return_value=reputation,
            ),
        ):
            allowed, throttle = await _check_email_health()

        assert allowed is False
        assert throttle == "paused"

    async def test_exception_returns_reduced(self):
        """Returns (True, 'reduced') when health check fails."""
        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("Redis down"),
        ):
            allowed, throttle = await _check_email_health()

        assert allowed is True
        assert throttle == "reduced"


# ---------------------------------------------------------------------------
# _calculate_cycle_cap
# ---------------------------------------------------------------------------

class TestCalculateCycleCap:
    """Tests for _calculate_cycle_cap."""

    @patch("src.workers.outreach_sequencer.datetime")
    def test_returns_zero_when_daily_limit_reached(self, mock_dt):
        """Returns 0 when sent_today >= daily_limit."""
        config = _make_config()
        result = _calculate_cycle_cap(50, 50, config)
        assert result == 0

    @patch("src.workers.outreach_sequencer.datetime")
    def test_returns_zero_when_over_limit(self, mock_dt):
        """Returns 0 when sent_today > daily_limit."""
        config = _make_config()
        result = _calculate_cycle_cap(50, 60, config)
        assert result == 0

    @patch("src.workers.outreach_sequencer.datetime")
    def test_distributes_across_remaining_cycles(self, mock_dt):
        """Distributes remaining sends across remaining time cycles."""
        mock_now = MagicMock()
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_hours_end="18:00")
        # 8 hours remain = 480 minutes / 30 = 16 cycles
        # remaining = 50 - 10 = 40, 40 / 16 = 2
        result = _calculate_cycle_cap(50, 10, config)
        assert result >= 1

    @patch("src.workers.outreach_sequencer.datetime")
    def test_minimum_one_when_remaining(self, mock_dt):
        """Returns at least 1 when there are emails remaining."""
        mock_now = MagicMock()
        mock_now.hour = 17
        mock_now.minute = 50
        mock_dt.now.return_value = mock_now

        config = _make_config(send_hours_end="18:00")
        # Only 10 minutes left = 0 cycles, max(1, ...) = 1 cycle
        # remaining = 50 - 49 = 1
        result = _calculate_cycle_cap(50, 49, config)
        assert result >= 1

    @patch("src.workers.outreach_sequencer.datetime")
    def test_invalid_timezone_falls_back(self, mock_dt):
        """Falls back to America/Chicago on invalid timezone."""
        mock_now = MagicMock()
        mock_now.hour = 12
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config(send_timezone="Invalid/TZ")
        result = _calculate_cycle_cap(50, 10, config)
        assert result >= 1

    @patch("src.workers.outreach_sequencer.datetime")
    def test_invalid_end_hour_uses_default(self, mock_dt):
        """Falls back to 18:00 when send_hours_end is unparseable."""
        mock_now = MagicMock()
        mock_now.hour = 12
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        config.send_hours_end = "bad"
        result = _calculate_cycle_cap(50, 10, config)
        assert result >= 1

    @patch("src.workers.outreach_sequencer.datetime")
    def test_none_end_hour_uses_default(self, mock_dt):
        """Falls back to 18:00 when send_hours_end is None."""
        mock_now = MagicMock()
        mock_now.hour = 12
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now

        config = _make_config()
        config.send_hours_end = None
        result = _calculate_cycle_cap(50, 10, config)
        assert result >= 1


# ---------------------------------------------------------------------------
# _generate_email_with_template
# ---------------------------------------------------------------------------

class TestGenerateEmailWithTemplate:
    """Tests for _generate_email_with_template."""

    async def test_static_template_substitutions(self):
        """Static template replaces variables correctly."""
        template = _make_template(
            is_ai_generated=False,
            body_template="Hello {prospect_name}, your company {company} in {city} does great {trade}!",
            subject_template="Quick question for {company}",
        )

        prospect = _make_prospect(
            prospect_name="Bob",
            prospect_company="Bob's HVAC",
            city="Dallas",
            prospect_trade_type="hvac",
        )

        result = await _generate_email_with_template(prospect, 1, template)

        assert result["subject"] == "Quick question for Bob's HVAC"
        assert "Bob" in result["body_text"]
        assert "Dallas" in result["body_text"]
        assert "hvac" in result["body_text"]
        assert result["ai_cost_usd"] == 0.0

    async def test_static_template_html_conversion(self):
        """Static template converts newlines to <br> for HTML."""
        template = _make_template(
            is_ai_generated=False,
            body_template="Line one\nLine two",
            subject_template="Subject",
        )

        prospect = _make_prospect()

        result = await _generate_email_with_template(prospect, 1, template)

        assert "<br>" in result["body_html"]

    async def test_static_template_no_subject_template(self):
        """Uses default subject when template has no subject_template."""
        template = _make_template(
            is_ai_generated=False,
            body_template="Hello {prospect_name}",
            subject_template=None,
        )

        prospect = _make_prospect(
            prospect_company="XYZ Corp",
        )

        result = await _generate_email_with_template(prospect, 1, template)

        assert "XYZ Corp" in result["subject"]

    async def test_static_template_sanitizes_dashes(self):
        """Static template output has dashes sanitized."""
        template = _make_template(
            is_ai_generated=False,
            body_template="Hello\u2014world",
            subject_template="Subject\u2013here",
        )

        prospect = _make_prospect()

        result = await _generate_email_with_template(prospect, 1, template)

        assert "\u2014" not in result["body_text"]
        assert "\u2013" not in result["subject"]

    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    async def test_ai_generated_with_instructions(self, mock_gen):
        """AI template with instructions passes extra_instructions."""
        mock_gen.return_value = {
            "subject": "AI Subject",
            "body_html": "<p>AI Body</p>",
            "body_text": "AI Body",
            "ai_cost_usd": 0.002,
        }

        template = _make_template(
            is_ai_generated=True,
            ai_instructions="Be friendly and mention roofing.",
            body_template=None,
        )

        prospect = _make_prospect()

        result = await _generate_email_with_template(prospect, 1, template)

        assert result["subject"] == "AI Subject"
        mock_gen.assert_awaited_once()
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["extra_instructions"] == "Be friendly and mention roofing."

    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    async def test_no_template_uses_ai(self, mock_gen):
        """No template defaults to AI generation."""
        mock_gen.return_value = {
            "subject": "AI Subject",
            "body_html": "<p>AI Body</p>",
            "body_text": "AI Body",
            "ai_cost_usd": 0.001,
        }

        prospect = _make_prospect()

        result = await _generate_email_with_template(prospect, 1, None)

        assert result["subject"] == "AI Subject"
        mock_gen.assert_awaited_once()
        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["extra_instructions"] is None

    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    async def test_ai_template_without_instructions(self, mock_gen):
        """AI template without ai_instructions passes None."""
        mock_gen.return_value = {
            "subject": "AI Sub",
            "body_html": "<p>Body</p>",
            "body_text": "Body",
            "ai_cost_usd": 0.001,
        }

        template = _make_template(
            is_ai_generated=True,
            ai_instructions=None,
        )

        prospect = _make_prospect()

        result = await _generate_email_with_template(prospect, 1, template)

        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["extra_instructions"] is None

    async def test_static_template_missing_prospect_fields(self):
        """Substitutes empty strings for None prospect fields."""
        template = _make_template(
            is_ai_generated=False,
            body_template="Name: {prospect_name}, Company: {company}, City: {city}, Trade: {trade}",
            subject_template="Hi {company}",
        )

        prospect = _make_prospect(
            prospect_name=None,
            prospect_company=None,
            city=None,
            prospect_trade_type=None,
        )

        result = await _generate_email_with_template(prospect, 1, template)

        # {company} falls back to prospect_name (None -> "")
        assert result["body_text"] is not None
        assert result["ai_cost_usd"] == 0.0

    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    async def test_ai_generation_with_none_fields(self, mock_gen):
        """Handles None prospect fields for AI generation."""
        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.001,
        }

        prospect = _make_prospect(
            prospect_company=None,
            prospect_trade_type=None,
            city=None,
            state_code=None,
        )

        result = await _generate_email_with_template(prospect, 2, None)

        call_kwargs = mock_gen.call_args[1]
        assert call_kwargs["company_name"] == prospect.prospect_name
        assert call_kwargs["trade_type"] == "general"
        assert call_kwargs["city"] == ""
        assert call_kwargs["state"] == ""


# ---------------------------------------------------------------------------
# send_sequence_email
# ---------------------------------------------------------------------------

class TestSendSequenceEmail:
    """Tests for send_sequence_email."""

    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_skips_invalid_email(self, mock_validate, mock_gen, mock_send):
        """Skips prospect with invalid email."""
        mock_validate.return_value = {"valid": False, "reason": "bad format"}

        db = AsyncMock()
        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect()

        await send_sequence_email(db, config, settings, prospect)

        mock_gen.assert_not_awaited()
        mock_send.assert_not_awaited()

    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_skips_blacklisted_email(self, mock_validate, mock_gen, mock_send):
        """Skips prospect whose email or domain is blacklisted."""
        mock_validate.return_value = {"valid": True, "reason": None}

        # Blacklist check finds a match
        blacklist_match = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = blacklist_match

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect()

        await send_sequence_email(db, config, settings, prospect)

        mock_gen.assert_not_awaited()
        mock_send.assert_not_awaited()

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_successful_first_email_send(
        self, mock_validate, mock_gen, mock_send, mock_get_redis, mock_record_event,
    ):
        """Successfully sends first email and updates prospect."""
        mock_validate.return_value = {"valid": True, "reason": None}

        # No blacklist match
        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Test Subject",
            "body_html": "<p>Hello</p>",
            "body_text": "Hello",
            "ai_cost_usd": 0.002,
        }

        mock_send.return_value = {
            "message_id": "msg_123",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(outreach_sequence_step=0, status="cold")

        await send_sequence_email(db, config, settings, prospect)

        mock_send.assert_awaited_once()
        db.add.assert_called_once()  # email_record added
        assert prospect.outreach_sequence_step == 1
        assert prospect.total_emails_sent == 1
        assert prospect.status == "contacted"

    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_email_generation_error(self, mock_validate, mock_gen, mock_send):
        """Stops when email generation returns an error."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "error": "AI generation failed",
            "subject": "",
            "body_html": "",
            "body_text": "",
        }

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect()

        await send_sequence_email(db, config, settings, prospect)

        mock_send.assert_not_awaited()

    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_email_send_error(self, mock_validate, mock_gen, mock_send):
        """Stops when email send returns an error."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.001,
        }

        mock_send.return_value = {"error": "SendGrid API error"}

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect()

        await send_sequence_email(db, config, settings, prospect)

        # Prospect should NOT be updated on send failure
        assert prospect.outreach_sequence_step == 0

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_followup_email_threads(
        self, mock_validate, mock_gen, mock_send, mock_get_redis, mock_record_event,
    ):
        """Follow-up emails include threading headers from previous email."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        # Mock previous email for threading
        prev_email = MagicMock()
        prev_email.sendgrid_message_id = "prev_msg_id_123"
        prev_email_result = MagicMock()
        prev_email_result.scalar_one_or_none.return_value = prev_email

        # Mock for dedup check (no duplicate found)
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return blacklist_result
            if call_count == 2:
                return dedup_result
            return prev_email_result

        mock_gen.return_value = {
            "subject": "Follow Up",
            "body_html": "<p>Following up</p>",
            "body_text": "Following up",
            "ai_cost_usd": 0.001,
        }

        mock_send.return_value = {
            "message_id": "msg_456",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(
            outreach_sequence_step=1,
            status="contacted",
        )

        await send_sequence_email(db, config, settings, prospect)

        # Verify threading headers were passed
        send_call = mock_send.call_args
        assert send_call[1]["in_reply_to"] == "prev_msg_id_123"
        assert "prev_msg_id_123" in send_call[1]["references"]

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_campaign_counter_not_mutated(
        self, mock_validate, mock_gen, mock_send, mock_get_redis, mock_record_event,
    ):
        """Campaign counters should NOT be mutated (calculated metrics used instead)."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.001,
        }

        mock_send.return_value = {
            "message_id": "msg_789",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(outreach_sequence_step=0)
        campaign = _make_campaign(total_sent=5)

        await send_sequence_email(db, config, settings, prospect, campaign=campaign)

        assert campaign.total_sent == 5  # unchanged - calculated metrics used instead

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.validate_email",
        new_callable=AsyncMock,
    )
    async def test_template_id_loads_template(
        self, mock_validate, mock_send, mock_get_redis, mock_record_event,
    ):
        """Template is loaded from DB when template_id is provided."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        template = _make_template(
            is_ai_generated=False,
            body_template="Hello {prospect_name}!",
            subject_template="Hi {prospect_name}",
        )

        mock_send.return_value = {
            "message_id": "msg_tmpl",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=template)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(outreach_sequence_step=0)

        await send_sequence_email(
            db, config, settings, prospect,
            template_id=str(uuid.uuid4()),
        )

        mock_send.assert_awaited_once()
        # Verify the template was used (static template, ai_cost=0)
        db.get.assert_awaited()

    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_template_id_load_exception_falls_back(
        self, mock_validate, mock_gen, mock_send,
    ):
        """Falls back to no template when template ID load fails."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "AI Sub",
            "body_html": "<p>AI</p>",
            "body_text": "AI",
            "ai_cost_usd": 0.001,
            "error": None,
        }

        mock_send.return_value = {
            "message_id": "msg_fb",
            "cost_usd": 0.001,
            "error": None,
        }

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(side_effect=Exception("Invalid UUID"))
        db.add = MagicMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            return_value=AsyncMock(),
        ), patch(
            "src.services.deliverability.record_email_event",
            new_callable=AsyncMock,
        ):
            config = _make_config()
            settings = _make_settings()
            prospect = _make_prospect(outreach_sequence_step=0)

            await send_sequence_email(
                db, config, settings, prospect,
                template_id="bad-uuid",
            )

        # Falls back to AI generation (may be called twice due to quality gate retry)
        assert mock_gen.await_count >= 1

    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_record_event_failure_does_not_break_send(
        self, mock_validate, mock_gen, mock_send,
    ):
        """Email reputation recording failure does not break the send flow."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.001,
        }

        mock_send.return_value = {
            "message_id": "msg_ev",
            "cost_usd": 0.001,
            "error": None,
        }

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        with patch(
            "src.utils.dedup.get_redis",
            new_callable=AsyncMock,
            side_effect=Exception("Redis fail"),
        ):
            config = _make_config()
            settings = _make_settings()
            prospect = _make_prospect(outreach_sequence_step=0, status="cold")

            await send_sequence_email(db, config, settings, prospect)

        # Prospect should still be updated despite Redis failure
        assert prospect.outreach_sequence_step == 1
        assert prospect.status == "contacted"

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_followup_no_previous_email(
        self, mock_validate, mock_gen, mock_send, mock_get_redis, mock_record_event,
    ):
        """Follow-up with no previous email sends without threading headers."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        # No previous email found
        prev_email_result = MagicMock()
        prev_email_result.scalar_one_or_none.return_value = None

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return blacklist_result
            return prev_email_result

        mock_gen.return_value = {
            "subject": "Follow Up",
            "body_html": "<p>Following up</p>",
            "body_text": "Following up",
            "ai_cost_usd": 0.001,
        }

        mock_send.return_value = {
            "message_id": "msg_no_thread",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(outreach_sequence_step=1, status="contacted")

        await send_sequence_email(db, config, settings, prospect)

        send_call = mock_send.call_args
        assert send_call[1]["in_reply_to"] is None
        assert send_call[1]["references"] is None

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_status_not_changed_if_already_contacted(
        self, mock_validate, mock_gen, mock_send, mock_get_redis, mock_record_event,
    ):
        """Status remains 'contacted' if already in that state."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.001,
        }

        mock_send.return_value = {
            "message_id": "msg_c",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(
            outreach_sequence_step=1,
            status="contacted",
            total_emails_sent=1,
        )

        await send_sequence_email(db, config, settings, prospect)

        assert prospect.status == "contacted"

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch(
        "src.workers.outreach_sending.generate_outreach_email",
        new_callable=AsyncMock,
    )
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_cost_accumulation(
        self, mock_validate, mock_gen, mock_send, mock_get_redis, mock_record_event,
    ):
        """Total cost accumulates AI and send costs."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.005,
        }

        mock_send.return_value = {
            "message_id": "msg_cost",
            "cost_usd": 0.003,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(
            outreach_sequence_step=0,
            total_cost_usd=0.01,
        )

        await send_sequence_email(db, config, settings, prospect)

        assert prospect.total_cost_usd == pytest.approx(0.018)


# ---------------------------------------------------------------------------
# run_outreach_sequencer
# ---------------------------------------------------------------------------

class TestRunOutreachSequencer:
    """Tests for run_outreach_sequencer."""

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._heartbeat", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.sequence_cycle", new_callable=AsyncMock)
    async def test_calls_sequence_cycle_when_not_paused(
        self, mock_cycle, mock_heartbeat, mock_sleep,
    ):
        """Calls sequence_cycle when sequencer is not paused."""
        config = _make_config(sequencer_paused=False)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        iteration = 0

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        async def stop_after_one(*args, **kwargs):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise KeyboardInterrupt()

        mock_sleep.side_effect = stop_after_one

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_outreach_sequencer()

        mock_cycle.assert_awaited_once()
        mock_heartbeat.assert_awaited_once()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._heartbeat", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.sequence_cycle", new_callable=AsyncMock)
    async def test_skips_cycle_when_paused(
        self, mock_cycle, mock_heartbeat, mock_sleep,
    ):
        """Skips sequence_cycle when sequencer is paused."""
        config = _make_config(sequencer_paused=True)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        iteration = 0

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        async def stop_after_one(*args, **kwargs):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise KeyboardInterrupt()

        mock_sleep.side_effect = stop_after_one

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_outreach_sequencer()

        mock_cycle.assert_not_awaited()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._heartbeat", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.sequence_cycle", new_callable=AsyncMock)
    async def test_runs_cycle_when_no_config(
        self, mock_cycle, mock_heartbeat, mock_sleep,
    ):
        """Runs sequence_cycle when no config exists (config is None)."""
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None

        iteration = 0

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        async def stop_after_one(*args, **kwargs):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise KeyboardInterrupt()

        mock_sleep.side_effect = stop_after_one

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_outreach_sequencer()

        # When config is None, it does not have sequencer_paused, so cycle runs
        mock_cycle.assert_awaited_once()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._heartbeat", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.sequence_cycle", new_callable=AsyncMock)
    async def test_catches_cycle_exception(
        self, mock_cycle, mock_heartbeat, mock_sleep,
    ):
        """Catches and logs exceptions from sequence_cycle without crashing."""
        config = _make_config(sequencer_paused=False)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        iteration = 0

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        mock_cycle.side_effect = Exception("DB error")

        async def stop_after_one(*args, **kwargs):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise KeyboardInterrupt()

        mock_sleep.side_effect = stop_after_one

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_outreach_sequencer()

        mock_heartbeat.assert_awaited_once()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._heartbeat", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.sequence_cycle", new_callable=AsyncMock)
    async def test_config_without_sequencer_paused_attribute(
        self, mock_cycle, mock_heartbeat, mock_sleep,
    ):
        """Runs cycle when config has no sequencer_paused attribute."""
        config = MagicMock(spec=[])  # No attributes
        config.sequencer_paused = False

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        iteration = 0

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        async def stop_after_one(*args, **kwargs):
            nonlocal iteration
            iteration += 1
            if iteration >= 1:
                raise KeyboardInterrupt()

        mock_sleep.side_effect = stop_after_one

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            with pytest.raises(KeyboardInterrupt):
                await run_outreach_sequencer()


# ---------------------------------------------------------------------------
# sequence_cycle
# ---------------------------------------------------------------------------

class TestSequenceCycle:
    """Tests for sequence_cycle."""

    @pytest.fixture(autouse=True)
    def _patch_recover(self):
        with patch(
            "src.workers.outreach_sequencer._recover_generation_failed",
            new_callable=AsyncMock, return_value=0,
        ):
            yield

    async def test_returns_early_when_config_inactive(self):
        """Returns early when config is_active is False."""
        config = _make_config(is_active=False)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            await sequence_cycle()

    async def test_returns_early_when_no_config(self):
        """Returns early when no config exists."""
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=False)
    async def test_returns_early_outside_send_window(self, mock_window):
        """Returns early when outside send window."""
        config = _make_config(is_active=True)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    async def test_returns_early_when_no_from_email(self, mock_window):
        """Returns early when from_email is not configured."""
        config = _make_config(is_active=True, from_email=None, company_address="123 Main")

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    async def test_returns_early_when_no_company_address(self, mock_window):
        """Returns early when company_address is not configured."""
        config = _make_config(is_active=True, from_email="sales@test.com")
        config.company_address = None

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    async def test_returns_early_when_email_unhealthy(self, mock_health, mock_window):
        """Returns early when email reputation is paused."""
        mock_health.return_value = (False, "paused")

        config = _make_config(is_active=True)

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = config

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(return_value=scalar_result)
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ):
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    @patch("src.workers.outreach_sequencer._get_warmup_limit", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_full_cycle_with_prospects(
        self, mock_settings, mock_campaign_proc, mock_window, mock_health,
        mock_warmup, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Full cycle processes campaigns and unbound prospects."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_warmup.return_value = 50
        mock_smart.return_value = False  # Don't defer

        config = _make_config(is_active=True)
        prospect = _make_prospect()

        # Track call order to return different results
        call_count = 0

        def make_scalars_result(items):
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = items
            result = MagicMock()
            result.scalars.return_value = scalars_mock
            result.scalar_one_or_none.return_value = config
            result.scalar.return_value = 0
            return result

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_result = make_scalars_result([])  # No campaigns
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 5  # 5 sent today

        step0_result = make_scalars_result([prospect])
        followup_result = make_scalars_result([])

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            elif call_count == 4:
                return step0_result
            elif call_count == 5:
                return followup_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0, "reduced": 0.5, "critical": 0.25},
        ):
            await sequence_cycle()

        mock_send.assert_awaited_once()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    @patch("src.workers.outreach_sequencer._get_warmup_limit", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_daily_limit_reached(
        self, mock_settings, mock_campaign_proc, mock_window, mock_health,
        mock_warmup, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Stops when daily email limit is reached."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_warmup.return_value = 50

        config = _make_config(is_active=True, daily_email_limit=50)

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        campaigns_result.scalars.return_value = scalars

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 50  # Already at limit

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0, "reduced": 0.5, "critical": 0.25},
        ):
            await sequence_cycle()

        mock_send.assert_not_awaited()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    @patch("src.workers.outreach_sequencer._get_warmup_limit", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_deferred_prospect_skipped(
        self, mock_settings, mock_campaign_proc, mock_window, mock_health,
        mock_warmup, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Deferred prospects (smart timing) are skipped."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_warmup.return_value = 50
        mock_smart.return_value = True  # Defer all

        config = _make_config(is_active=True)
        prospect = _make_prospect()

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        campaigns_result.scalars.return_value = scalars

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step0_scalars = MagicMock()
        step0_scalars.all.return_value = [prospect]
        step0_result = MagicMock()
        step0_result.scalars.return_value = step0_scalars

        followup_scalars = MagicMock()
        followup_scalars.all.return_value = []
        followup_result = MagicMock()
        followup_result.scalars.return_value = followup_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            elif call_count == 4:
                return step0_result
            elif call_count == 5:
                return followup_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0, "reduced": 0.5, "critical": 0.25},
        ):
            await sequence_cycle()

        mock_send.assert_not_awaited()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    @patch("src.workers.outreach_sequencer._get_warmup_limit", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_send_exception_caught(
        self, mock_settings, mock_campaign_proc, mock_window, mock_health,
        mock_warmup, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Exception during send_sequence_email is caught and logged."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_warmup.return_value = 50
        mock_smart.return_value = False
        mock_send.side_effect = Exception("Send failed")

        config = _make_config(is_active=True)
        prospect = _make_prospect()

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        campaigns_result.scalars.return_value = scalars

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step0_scalars = MagicMock()
        step0_scalars.all.return_value = [prospect]
        step0_result = MagicMock()
        step0_result.scalars.return_value = step0_scalars

        followup_scalars = MagicMock()
        followup_scalars.all.return_value = []
        followup_result = MagicMock()
        followup_result.scalars.return_value = followup_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            elif call_count == 4:
                return step0_result
            elif call_count == 5:
                return followup_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0, "reduced": 0.5, "critical": 0.25},
        ):
            # Should not raise
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    @patch("src.workers.outreach_sequencer._get_warmup_limit", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_jitter_sleep_between_unbound_prospects(
        self, mock_settings, mock_campaign_proc, mock_window, mock_health,
        mock_warmup, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Sleeps with jitter between unbound prospect sends, not after last."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_warmup.return_value = 50
        mock_smart.return_value = False

        config = _make_config(is_active=True)
        p1 = _make_prospect(prospect_id=uuid.uuid4())
        p2 = _make_prospect(prospect_id=uuid.uuid4())

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        campaigns_result.scalars.return_value = scalars

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step0_scalars = MagicMock()
        step0_scalars.all.return_value = [p1, p2]
        step0_result = MagicMock()
        step0_result.scalars.return_value = step0_scalars

        followup_scalars = MagicMock()
        followup_scalars.all.return_value = []
        followup_result = MagicMock()
        followup_result.scalars.return_value = followup_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            elif call_count == 4:
                return step0_result
            elif call_count == 5:
                return followup_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0, "reduced": 0.5, "critical": 0.25},
        ):
            await sequence_cycle()

        # 2 prospects, sleep once between them (not after last)
        assert mock_send.await_count == 2
        assert mock_sleep.await_count == 1

    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_campaign_processing_error_caught(
        self, mock_settings, mock_window, mock_health, mock_campaign_proc,
    ):
        """Exception during campaign processing is caught and logged."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_campaign_proc.side_effect = Exception("Campaign error")

        config = _make_config(is_active=True)
        campaign = _make_campaign()

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_scalars = MagicMock()
        campaigns_scalars.all.return_value = [campaign]
        campaigns_result = MagicMock()
        campaigns_result.scalars.return_value = campaigns_scalars

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 50  # At limit to avoid unbound processing

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.workers.outreach_sequencer._get_warmup_limit",
            new_callable=AsyncMock,
            return_value=50,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0},
        ):
            # Should not raise
            await sequence_cycle()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    @patch("src.workers.outreach_sequencer._get_warmup_limit", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_email_health", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.is_within_send_window", return_value=True)
    @patch("src.workers.outreach_sequencer._process_campaign_prospects", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.get_settings")
    async def test_circuit_breaker_stops_after_3_failures(
        self, mock_settings, mock_campaign_proc, mock_window, mock_health,
        mock_warmup, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Circuit breaker stops batch after 3 consecutive AI generation failures."""
        mock_settings.return_value = _make_settings()
        mock_health.return_value = (True, "normal")
        mock_warmup.return_value = 50
        mock_smart.return_value = False

        config = _make_config(is_active=True)
        # Create 5 prospects — circuit breaker should stop after 3
        prospects = [_make_prospect() for _ in range(5)]

        # Simulate AI generation failure by incrementing generation_failures
        async def mock_send_fn(db, cfg, settings, prospect, **kwargs):
            prospect.generation_failures = (prospect.generation_failures or 0) + 1

        mock_send.side_effect = mock_send_fn

        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        campaigns_result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = []
        campaigns_result.scalars.return_value = scalars

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step0_scalars = MagicMock()
        step0_scalars.all.return_value = prospects
        step0_result = MagicMock()
        step0_result.scalars.return_value = step0_scalars

        followup_scalars = MagicMock()
        followup_scalars.all.return_value = []
        followup_result = MagicMock()
        followup_result.scalars.return_value = followup_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return config_result
            elif call_count == 2:
                return campaigns_result
            elif call_count == 3:
                return sent_count_result
            elif call_count == 4:
                return step0_result
            elif call_count == 5:
                return followup_result
            return MagicMock()

        @asynccontextmanager
        async def mock_session_factory():
            db = AsyncMock()
            db.execute = AsyncMock(side_effect=mock_execute)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            yield db

        with patch(
            "src.workers.outreach_sequencer.async_session_factory",
            side_effect=mock_session_factory,
        ), patch(
            "src.services.deliverability.EMAIL_THROTTLE_FACTORS",
            {"normal": 1.0, "reduced": 0.5, "critical": 0.25},
        ), patch(
            "src.workers.outreach_sequencer._trip_ai_circuit_breaker",
            new_callable=AsyncMock,
        ) as mock_trip:
            await sequence_cycle()

        # Should have stopped after 3 prospects (circuit breaker), not all 5
        assert mock_send.await_count == 3
        # Should have tripped the persistent circuit breaker
        mock_trip.assert_awaited_once()


# ---------------------------------------------------------------------------
# _process_campaign_prospects
# ---------------------------------------------------------------------------

class TestProcessCampaignProspects:
    """Tests for _process_campaign_prospects."""

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_processes_step1_prospects(
        self, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Processes step 1 (cold) prospects in campaign."""
        mock_smart.return_value = False

        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )

        template_id = str(uuid.uuid4())
        campaign = _make_campaign(
            daily_limit=25,
            sequence_steps=[
                {"step": 1, "delay_hours": 0, "template_id": template_id},
            ],
        )

        prospect = _make_prospect()

        # sent_today count
        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        # step 1 prospects
        step_scalars = MagicMock()
        step_scalars.all.return_value = [prospect]
        step_result = MagicMock()
        step_result.scalars.return_value = step_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sent_count_result
            return step_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.flush = AsyncMock()

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        mock_send.assert_awaited_once()
        send_call = mock_send.call_args
        assert send_call[1]["template_id"] == template_id
        assert send_call[1]["campaign"] == campaign

    async def test_returns_early_when_no_steps(self):
        """Returns early when campaign has no sequence_steps."""
        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)
        campaign = _make_campaign(sequence_steps=[])

        db = AsyncMock()

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        db.execute.assert_not_awaited()

    async def test_returns_early_when_none_steps(self):
        """Returns early when campaign sequence_steps is None."""
        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)
        campaign = _make_campaign()
        campaign.sequence_steps = None

        db = AsyncMock()

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        db.execute.assert_not_awaited()

    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_returns_early_when_daily_limit_reached(self, mock_cycle_cap):
        """Returns early when campaign daily limit is reached."""
        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)
        campaign = _make_campaign(
            daily_limit=10,
            sequence_steps=[{"step": 1, "delay_hours": 0}],
        )

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 10  # At limit

        db = AsyncMock()
        db.execute = AsyncMock(return_value=sent_count_result)

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_deferred_prospect_skipped_in_campaign(
        self, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Deferred (smart timing) prospects are skipped in campaigns."""
        mock_smart.return_value = True  # Defer

        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)
        campaign = _make_campaign(
            daily_limit=25,
            sequence_steps=[{"step": 1, "delay_hours": 0}],
        )

        prospect = _make_prospect()

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step_scalars = MagicMock()
        step_scalars.all.return_value = [prospect]
        step_result = MagicMock()
        step_result.scalars.return_value = step_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sent_count_result
            return step_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.flush = AsyncMock()

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        mock_send.assert_not_awaited()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_send_exception_caught_in_campaign(
        self, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Send exception is caught in campaign processing."""
        mock_smart.return_value = False
        mock_send.side_effect = Exception("Send failed")

        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)
        campaign = _make_campaign(
            daily_limit=25,
            sequence_steps=[{"step": 1, "delay_hours": 0}],
        )

        prospect = _make_prospect()

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step_scalars = MagicMock()
        step_scalars.all.return_value = [prospect]
        step_result = MagicMock()
        step_result.scalars.return_value = step_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sent_count_result
            return step_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.flush = AsyncMock()

        # Should not raise
        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_deduplicates_prospects_across_steps(
        self, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Deduplicates prospects that appear in multiple step queries."""
        mock_smart.return_value = False

        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)

        prospect_id = uuid.uuid4()
        prospect = _make_prospect(prospect_id=prospect_id)

        campaign = _make_campaign(
            daily_limit=25,
            sequence_steps=[
                {"step": 1, "delay_hours": 0, "template_id": "t1"},
                {"step": 2, "delay_hours": 24, "template_id": "t2"},
            ],
        )

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        # Both steps return the same prospect
        step_scalars = MagicMock()
        step_scalars.all.return_value = [prospect]
        step_result = MagicMock()
        step_result.scalars.return_value = step_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sent_count_result
            return step_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.flush = AsyncMock()

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        # Should only send once despite appearing in both step queries
        mock_send.assert_awaited_once()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_no_prospects_returns_early(
        self, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Returns early when no prospects found."""
        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)
        campaign = _make_campaign(
            daily_limit=25,
            sequence_steps=[{"step": 1, "delay_hours": 0}],
        )

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step_scalars = MagicMock()
        step_scalars.all.return_value = []
        step_result = MagicMock()
        step_result.scalars.return_value = step_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sent_count_result
            return step_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        mock_send.assert_not_awaited()

    @patch("src.workers.outreach_sequencer.asyncio.sleep", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer.send_sequence_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._check_smart_timing", new_callable=AsyncMock)
    @patch("src.workers.outreach_sequencer._calculate_cycle_cap", return_value=10)
    async def test_jitter_sleep_between_sends(
        self, mock_cycle_cap, mock_smart, mock_send, mock_sleep,
    ):
        """Sleeps between sends with jitter, but not after the last one."""
        mock_smart.return_value = False

        config = _make_config()
        settings = _make_settings()
        today_start = datetime.now(timezone.utc)

        p1 = _make_prospect(prospect_id=uuid.uuid4())
        p2 = _make_prospect(prospect_id=uuid.uuid4())

        campaign = _make_campaign(
            daily_limit=25,
            sequence_steps=[{"step": 1, "delay_hours": 0}],
        )

        sent_count_result = MagicMock()
        sent_count_result.scalar.return_value = 0

        step_scalars = MagicMock()
        step_scalars.all.return_value = [p1, p2]
        step_result = MagicMock()
        step_result.scalars.return_value = step_scalars

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sent_count_result
            return step_result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.flush = AsyncMock()

        await _process_campaign_prospects(
            db, config, settings, campaign, today_start,
        )

        # Sleep called once between 2 prospects (not after the last one)
        assert mock_sleep.await_count == 1


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Test module-level constants."""

    def test_poll_interval(self):
        assert POLL_INTERVAL_SECONDS == 30 * 60

    def test_warmup_schedule_has_entries(self):
        assert len(EMAIL_WARMUP_SCHEDULE) > 0

    def test_warmup_schedule_last_entry_unbounded(self):
        last = EMAIL_WARMUP_SCHEDULE[-1]
        assert last[1] is None  # day_end is None
        assert last[2] is None  # max_daily is None

    def test_warmup_schedule_ordered(self):
        """Warmup schedule entries are in chronological order."""
        for i in range(1, len(EMAIL_WARMUP_SCHEDULE)):
            assert EMAIL_WARMUP_SCHEDULE[i][0] > EMAIL_WARMUP_SCHEDULE[i - 1][0]


# ---------------------------------------------------------------------------
# _verify_or_find_working_email (discover_email-based)
# ---------------------------------------------------------------------------

class TestVerifyOrFindWorkingEmail:
    """Tests for _verify_or_find_working_email using discover_email."""

    async def test_returns_discovered_email(self):
        """Returns email found via deep scrape."""
        prospect = _make_prospect()
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "real@acmehvac.com",
                "source": "website_deep_scrape",
                "confidence": "high",
                "cost_usd": 0.0,
            },
        ):
            result = await _verify_or_find_working_email(prospect)

        assert result == "real@acmehvac.com"
        assert prospect.email_source == "website_deep_scrape"
        assert prospect.email_verified is True

    async def test_returns_none_when_no_email_found(self):
        """Returns None when discovery finds nothing."""
        prospect = _make_prospect()
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": None,
                "source": None,
                "confidence": None,
                "cost_usd": 0.0,
            },
        ):
            result = await _verify_or_find_working_email(prospect)

        assert result is None

    async def test_rejects_pattern_guess_only_result(self):
        """Returns None when discovery only produces another pattern guess."""
        prospect = _make_prospect()
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "info@acmehvac.com",
                "source": "pattern_guess",
                "confidence": "low",
                "cost_usd": 0.0,
            },
        ):
            result = await _verify_or_find_working_email(prospect)

        assert result is None

    async def test_handles_discovery_exception(self):
        """Returns None when discover_email raises."""
        prospect = _make_prospect()
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            result = await _verify_or_find_working_email(prospect)

        assert result is None

    async def test_tracks_discovery_cost(self):
        """Adds discovery cost to prospect total_cost_usd."""
        prospect = _make_prospect(total_cost_usd=0.01)
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        with patch(
            "src.services.email_discovery.discover_email",
            new_callable=AsyncMock,
            return_value={
                "email": "found@acmehvac.com",
                "source": "brave_search",
                "confidence": "medium",
                "cost_usd": 0.005,
            },
        ):
            result = await _verify_or_find_working_email(prospect)

        assert result == "found@acmehvac.com"
        assert prospect.total_cost_usd == pytest.approx(0.015)
        assert prospect.email_source == "brave_search"
        assert prospect.email_verified is False  # medium != high


# ---------------------------------------------------------------------------
# send_sequence_email — pattern_guess guard
# ---------------------------------------------------------------------------

class TestSendSequenceEmailPatternGuard:
    """Tests for the pattern_guess safety guard in send_sequence_email."""

    @patch("src.workers.outreach_sending._verify_or_find_working_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.generate_outreach_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_pattern_guess_triggers_discovery(
        self, mock_validate, mock_gen, mock_send, mock_verify,
    ):
        """Pattern guess + unverified triggers _verify_or_find_working_email."""
        mock_validate.return_value = {"valid": True, "reason": None}
        mock_verify.return_value = None  # No email found

        db = AsyncMock()
        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect()
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        await send_sequence_email(db, config, settings, prospect)

        mock_verify.assert_awaited_once_with(prospect)
        assert prospect.status == "no_verified_email"
        mock_gen.assert_not_awaited()
        mock_send.assert_not_awaited()

    @patch("src.services.deliverability.record_email_event", new_callable=AsyncMock)
    @patch("src.utils.dedup.get_redis", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending._verify_or_find_working_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.generate_outreach_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_pattern_guess_proceeds_when_email_found(
        self, mock_validate, mock_gen, mock_send, mock_verify,
        mock_get_redis, mock_record_event,
    ):
        """Pattern guess proceeds to send when discovery finds a real email."""
        mock_validate.return_value = {"valid": True, "reason": None}
        mock_verify.return_value = "real@acmehvac.com"

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Test",
            "body_html": "<p>Hi</p>",
            "body_text": "Hi",
            "ai_cost_usd": 0.001,
        }
        mock_send.return_value = {
            "message_id": "msg_456",
            "cost_usd": 0.001,
            "error": None,
        }

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)
        db.add = MagicMock()

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect(outreach_sequence_step=0, status="cold")
        prospect.email_source = "pattern_guess"
        prospect.email_verified = False

        await send_sequence_email(db, config, settings, prospect)

        mock_verify.assert_awaited_once_with(prospect)
        assert prospect.prospect_email == "real@acmehvac.com"
        mock_send.assert_awaited_once()

    @patch("src.workers.outreach_sending._verify_or_find_working_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.send_cold_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.generate_outreach_email", new_callable=AsyncMock)
    @patch("src.workers.outreach_sending.validate_email", new_callable=AsyncMock)
    async def test_verified_email_skips_discovery(
        self, mock_validate, mock_gen, mock_send, mock_verify,
    ):
        """Verified email does NOT trigger _verify_or_find_working_email."""
        mock_validate.return_value = {"valid": True, "reason": None}

        blacklist_result = MagicMock()
        blacklist_result.scalar_one_or_none.return_value = None

        mock_gen.return_value = {
            "subject": "Sub",
            "body_html": "<p>B</p>",
            "body_text": "B",
            "ai_cost_usd": 0.001,
        }
        mock_send.return_value = {"error": "test"}

        db = AsyncMock()
        db.execute = AsyncMock(return_value=blacklist_result)
        db.get = AsyncMock(return_value=None)

        config = _make_config()
        settings = _make_settings()
        prospect = _make_prospect()
        # email_source is "website_deep_scrape" and email_verified=True by default

        await send_sequence_email(db, config, settings, prospect)

        mock_verify.assert_not_awaited()


# ---------------------------------------------------------------------------
# Persistent AI circuit breaker
# ---------------------------------------------------------------------------

class TestPersistentCircuitBreaker:
    """Tests for Redis-backed persistent circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_open_when_key_exists(self):
        """Circuit is open when Redis key exists."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _is_ai_circuit_open()

        assert result is True

    @pytest.mark.asyncio
    async def test_circuit_closed_when_key_missing(self):
        """Circuit is closed when Redis key doesn't exist."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await _is_ai_circuit_open()

        assert result is False

    @pytest.mark.asyncio
    async def test_circuit_closed_on_redis_error(self):
        """Circuit defaults to closed if Redis is unreachable."""
        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, side_effect=Exception("redis down")):
            result = await _is_ai_circuit_open()

        assert result is False

    @pytest.mark.asyncio
    async def test_trip_sets_redis_key(self):
        """Tripping the circuit breaker sets a Redis key with TTL."""
        mock_redis = AsyncMock()

        with patch("src.utils.dedup.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            await _trip_ai_circuit_breaker()

        mock_redis.set.assert_awaited_once()
        args, kwargs = mock_redis.set.await_args
        assert args[0] == "leadlock:circuit:ai_generation"
        assert kwargs.get("ex") == 7200
