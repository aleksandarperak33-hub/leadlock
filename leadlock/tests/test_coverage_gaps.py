"""
Tests targeting specific uncovered lines across the codebase.
Each section covers a single module's coverage gaps.
"""
import uuid
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# 1. src/database.py - lines 23-32, 37-41, 46, 51-60
# =============================================================================

class TestDatabase:
    """Cover engine creation, session factory, async session, and get_db."""

    def setup_method(self):
        """Reset module-level singletons before each test."""
        import src.database as db_mod
        db_mod._engine = None
        db_mod._async_session_factory = None

    def teardown_method(self):
        """Reset module-level singletons after each test."""
        import src.database as db_mod
        db_mod._engine = None
        db_mod._async_session_factory = None

    @patch("src.database.create_async_engine")
    @patch("src.config.get_settings")
    def test_get_engine_creates_engine(self, mock_settings, mock_create):
        """Lines 23-32: engine creation with settings."""
        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://test:test@localhost/testdb"
        settings.database_pool_size = 5
        settings.database_max_overflow = 2
        settings.app_env = "development"
        mock_settings.return_value = settings

        fake_engine = MagicMock()
        mock_create.return_value = fake_engine

        from src.database import _get_engine
        engine = _get_engine()

        assert engine is fake_engine
        mock_create.assert_called_once_with(
            "postgresql+asyncpg://test:test@localhost/testdb",
            pool_size=5,
            max_overflow=2,
            echo=True,
        )

    @patch("src.database.create_async_engine")
    @patch("src.config.get_settings")
    def test_get_engine_production_no_echo(self, mock_settings, mock_create):
        """Lines 23-32: echo=False when not development."""
        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://test:test@localhost/testdb"
        settings.database_pool_size = 5
        settings.database_max_overflow = 2
        settings.app_env = "production"
        mock_settings.return_value = settings
        mock_create.return_value = MagicMock()

        from src.database import _get_engine
        _get_engine()

        mock_create.assert_called_once_with(
            "postgresql+asyncpg://test:test@localhost/testdb",
            pool_size=5,
            max_overflow=2,
            echo=False,
        )

    @patch("src.database.create_async_engine")
    @patch("src.database.async_sessionmaker")
    @patch("src.config.get_settings")
    def test_get_session_factory_creates_factory(self, mock_settings, mock_sessionmaker, mock_create):
        """Lines 37-41: session factory creation."""
        settings = MagicMock()
        settings.database_url = "postgresql+asyncpg://test:test@localhost/testdb"
        settings.database_pool_size = 5
        settings.database_max_overflow = 2
        settings.app_env = "development"
        mock_settings.return_value = settings

        fake_engine = MagicMock()
        mock_create.return_value = fake_engine
        fake_factory = MagicMock()
        mock_sessionmaker.return_value = fake_factory

        from src.database import _get_session_factory
        factory = _get_session_factory()

        assert factory is fake_factory
        from sqlalchemy.ext.asyncio import AsyncSession
        mock_sessionmaker.assert_called_once_with(
            fake_engine, class_=AsyncSession, expire_on_commit=False
        )

    @patch("src.database._get_session_factory")
    def test_async_session_factory_calls_factory(self, mock_get_factory):
        """Line 46: async_session_factory() calls the inner factory."""
        fake_session = MagicMock()
        inner_factory = MagicMock(return_value=fake_session)
        mock_get_factory.return_value = inner_factory

        from src.database import async_session_factory
        result = async_session_factory()

        assert result is fake_session
        inner_factory.assert_called_once()

    @patch("src.database._get_session_factory")
    async def test_get_db_yields_session_and_commits(self, mock_get_factory):
        """Lines 51-60: get_db yields session, commits, and closes."""
        mock_session = AsyncMock()
        # async context manager
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_factory.return_value = mock_factory

        from src.database import get_db
        gen = get_db()
        session = await gen.__anext__()
        assert session is mock_session

        # Finalize the generator (triggers commit + close)
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    @patch("src.database._get_session_factory")
    async def test_get_db_rollback_on_exception(self, mock_get_factory):
        """Lines 56-58: get_db rolls back on exception."""
        mock_session = AsyncMock()
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get_factory.return_value = mock_factory

        from src.database import get_db
        gen = get_db()
        await gen.__anext__()

        # Throw an exception into the generator
        with pytest.raises(ValueError):
            await gen.athrow(ValueError("test error"))

        mock_session.rollback.assert_awaited_once()


# =============================================================================
# 2. src/services/ai.py
# =============================================================================

class TestAIService:
    """Cover return paths for OpenAI-only routing."""

    @patch("src.config.get_settings")
    @patch("src.services.ai._generate_openai")
    async def test_generate_response_openai_success_returns(self, mock_openai, mock_settings):
        """Successful OpenAI call returns generated payload."""
        settings = MagicMock()
        settings.openai_api_key = "sk-test"
        mock_settings.return_value = settings

        expected = {"content": "Hello", "provider": "openai", "error": None}
        mock_openai.return_value = expected

        from src.services.ai import generate_response
        result = await generate_response("system", "user")

        assert result is expected
        assert result["provider"] == "openai"

    @patch("src.config.get_settings")
    @patch("src.services.ai._generate_openai")
    async def test_generate_response_openai_failure_returns_error(self, mock_openai, mock_settings):
        """OpenAI failure returns structured error dict."""
        mock_openai.side_effect = RuntimeError("OpenAI down")
        settings = MagicMock()
        settings.openai_api_key = "sk-test"
        mock_settings.return_value = settings

        from src.services.ai import generate_response
        result = await generate_response("system", "user")

        assert result["provider"] == "none"
        assert result["error"] == "OpenAI request failed"


# =============================================================================
# 3. src/services/cold_email.py - lines 71-72, 75-76
# =============================================================================

class TestColdEmail:
    """Cover CAN-SPAM validation for empty company_address and unsubscribe_url."""

    @patch("src.config.get_settings")
    async def test_empty_company_address_blocked(self, mock_settings):
        """Lines 71-72: empty company_address returns error."""
        settings = MagicMock()
        settings.sendgrid_api_key = "SG.test"
        mock_settings.return_value = settings

        from src.services.cold_email import send_cold_email
        result = await send_cold_email(
            to_email="test@example.com",
            to_name="Test",
            subject="Hello",
            body_html="<p>Hi</p>",
            from_email="from@example.com",
            from_name="Sender",
            reply_to="reply@example.com",
            unsubscribe_url="https://example.com/unsub",
            company_address="",
        )

        assert result["status"] == "error"
        assert "company_address" in result["error"]

    @patch("src.config.get_settings")
    async def test_whitespace_company_address_blocked(self, mock_settings):
        """Lines 70-72: whitespace-only company_address returns error."""
        settings = MagicMock()
        settings.sendgrid_api_key = "SG.test"
        mock_settings.return_value = settings

        from src.services.cold_email import send_cold_email
        result = await send_cold_email(
            to_email="test@example.com",
            to_name="Test",
            subject="Hello",
            body_html="<p>Hi</p>",
            from_email="from@example.com",
            from_name="Sender",
            reply_to="reply@example.com",
            unsubscribe_url="https://example.com/unsub",
            company_address="   ",
        )

        assert result["status"] == "error"
        assert "company_address" in result["error"]

    @patch("src.config.get_settings")
    async def test_empty_unsubscribe_url_blocked(self, mock_settings):
        """Lines 75-76: empty unsubscribe_url returns error."""
        settings = MagicMock()
        settings.sendgrid_api_key = "SG.test"
        mock_settings.return_value = settings

        from src.services.cold_email import send_cold_email
        result = await send_cold_email(
            to_email="test@example.com",
            to_name="Test",
            subject="Hello",
            body_html="<p>Hi</p>",
            from_email="from@example.com",
            from_name="Sender",
            reply_to="reply@example.com",
            unsubscribe_url="",
            company_address="123 Main St",
        )

        assert result["status"] == "error"
        assert "unsubscribe_url" in result["error"]

    @patch("src.config.get_settings")
    async def test_whitespace_unsubscribe_url_blocked(self, mock_settings):
        """Lines 74-76: whitespace-only unsubscribe_url returns error."""
        settings = MagicMock()
        settings.sendgrid_api_key = "SG.test"
        mock_settings.return_value = settings

        from src.services.cold_email import send_cold_email
        result = await send_cold_email(
            to_email="test@example.com",
            to_name="Test",
            subject="Hello",
            body_html="<p>Hi</p>",
            from_email="from@example.com",
            from_name="Sender",
            reply_to="reply@example.com",
            unsubscribe_url="   ",
            company_address="123 Main St",
        )

        assert result["status"] == "error"
        assert "unsubscribe_url" in result["error"]


# =============================================================================
# 4. src/services/compliance.py - lines 81-82, 127, 183, 191, 193, 374
# =============================================================================

class TestComplianceGaps:
    """Cover compliance module gaps."""

    def test_compliance_result_repr_allowed(self):
        """Lines 81-82: ComplianceResult repr for ALLOWED."""
        from src.services.compliance import ComplianceResult
        cr = ComplianceResult(True, "All good")
        assert "ALLOWED" in repr(cr)
        assert "All good" in repr(cr)

    def test_compliance_result_repr_blocked(self):
        """Lines 81-82: ComplianceResult repr for BLOCKED."""
        from src.services.compliance import ComplianceResult
        cr = ComplianceResult(False, "Opted out", "tcpa_opt_out")
        assert "BLOCKED" in repr(cr)
        assert "Opted out" in repr(cr)

    def test_is_stop_keyword_short_message_with_stop_word(self):
        """Line 127: short message (<=4 words) containing a stop keyword as standalone word."""
        from src.services.compliance import is_stop_keyword
        # "stop please now" is 3 words, contains "stop"
        assert is_stop_keyword("stop please now") is True

    def test_is_stop_keyword_long_message_not_triggered(self):
        """Line 127 branch: long message (>4 words) does NOT trigger standalone keyword match."""
        from src.services.compliance import is_stop_keyword
        # 5+ words, should NOT match via Layer 4
        result = is_stop_keyword("please don't stop the service now ok")
        # "stop" is in STOP_KEYWORDS but message is >4 words so Layer 4 skipped
        # Layer 3 phrase matching: "please stop" IS in STOP_PHRASES, so this does match
        # Let's use a message where no phrase matches but has a keyword in >4 words
        result = is_stop_keyword("I want to end this conversation soon enough")
        # "end" is a stop keyword, but >4 words, so Layer 4 won't trigger
        # Layer 3: no stop phrase matches "i want to end this conversation soon enough"
        # Actually "i want out" might match... let's check
        # This msg: "i want to end this conversation soon enough" - no exact phrase match
        assert result is False

    def test_quiet_hours_default_timezone_no_state(self):
        """Line 183 (zone fallback): no state code and no timezone falls back to Eastern."""
        from src.services.compliance import check_quiet_hours
        # 3 AM Eastern - should be blocked
        now = datetime(2025, 6, 15, 3, 0, 0, tzinfo=timezone.utc)
        result = check_quiet_hours(state_code=None, timezone_str=None, now=now)
        # 3 AM UTC = 11 PM EST (previous day) - outside quiet hours
        assert not result.allowed

    def test_quiet_hours_now_is_none_uses_current_time(self):
        """Line 191: now=None uses datetime.now(tz)."""
        from src.services.compliance import check_quiet_hours
        # Just confirm it runs without error when now is not provided
        result = check_quiet_hours(state_code="NY", timezone_str=None)
        # Result depends on current time - just assert it returns a ComplianceResult
        assert hasattr(result, "allowed")

    def test_quiet_hours_naive_datetime_gets_tz(self):
        """Line 193: naive datetime (no tzinfo) gets timezone applied."""
        from src.services.compliance import check_quiet_hours
        # Naive datetime at 3 AM - should be blocked as quiet hours
        naive_now = datetime(2025, 6, 15, 3, 0, 0)
        result = check_quiet_hours(state_code="NY", now=naive_now)
        assert not result.allowed
        assert "quiet" in result.reason.lower() or "TCPA" in result.reason

    def test_is_california_number_non_ca_number(self):
        """Line 374: returns False for non-CA phone."""
        from src.services.compliance import is_california_number
        assert is_california_number("+12125551234") is False

    def test_is_california_number_too_short(self):
        """Line 374: returns False for short phone."""
        from src.services.compliance import is_california_number
        assert is_california_number("+1") is False
        assert is_california_number("") is False


# =============================================================================
# 5. src/utils/templates.py - lines 216, 221-222
# =============================================================================

class TestTemplatesGaps:
    """Cover non-dict template rendering and format_map exception fallback."""

    def test_render_non_dict_template(self):
        """Line 216: template is a plain string (not A/B dict)."""
        from src.utils.templates import render_template
        # "no_availability" in BOOKING_TEMPLATES is a plain string
        result = render_template(
            "no_availability",
            category="booking",
            first_name="John",
            next_date="2025-07-01",
            time_window="9-11 AM",
        )
        assert "John" in result
        assert "2025-07-01" in result

    def test_render_template_format_exception_returns_raw(self):
        """Lines 221-222: format_map raises exception, returns raw template."""
        from src.utils.templates import render_template, SafeDict

        # Monkey-patch SafeDict to raise on format_map
        original_missing = SafeDict.__missing__
        def bad_missing(self, key):
            raise RuntimeError("format error")

        SafeDict.__missing__ = bad_missing
        try:
            # This should catch the exception and return the raw template
            result = render_template(
                "standard",
                category="intake",
                variant="A",
                # Missing required variables will trigger __missing__
            )
            # Since __missing__ raises, format_map fails, returns raw template
            assert isinstance(result, str)
            assert "{first_name}" in result or "Reply STOP" in result
        finally:
            SafeDict.__missing__ = original_missing


# =============================================================================
# 6. src/utils/encryption.py - lines 39-41
# =============================================================================

class TestEncryptionGaps:
    """Cover encrypt_value exception fallback."""

    @patch("src.utils.encryption._get_fernet")
    def test_encrypt_value_exception_returns_plaintext(self, mock_get_fernet):
        """Lines 39-41: encryption failure returns plaintext."""
        mock_fernet = MagicMock()
        mock_fernet.encrypt.side_effect = RuntimeError("encryption error")
        mock_get_fernet.return_value = mock_fernet

        from src.utils.encryption import encrypt_value
        result = encrypt_value("my-secret-value")
        assert result == "my-secret-value"


# =============================================================================
# 7. src/utils/email_validation.py - lines 60-61
# =============================================================================

class TestEmailValidationGaps:
    """Cover MX NoAnswer fallback to A record failure path."""

    async def test_has_mx_no_answer_and_a_record_fails(self):
        """Lines 60-61: NoAnswer on MX, then A record also fails -> returns False."""
        import sys

        # Create mock dns.resolver module with proper exception classes
        mock_dns = MagicMock()
        mock_resolver = MagicMock()

        class MockNoAnswer(Exception):
            pass

        class MockNXDOMAIN(Exception):
            pass

        mock_resolver.NoAnswer = MockNoAnswer
        mock_resolver.NXDOMAIN = MockNXDOMAIN

        def mock_resolve(domain, rtype):
            if rtype == "MX":
                raise MockNoAnswer()
            raise MockNXDOMAIN()

        mock_resolver.resolve = mock_resolve
        mock_dns.resolver = mock_resolver

        with patch.dict(sys.modules, {"dns": mock_dns, "dns.resolver": mock_resolver}):
            # Re-import to pick up mocked module
            import importlib
            import src.utils.email_validation as ev_mod
            importlib.reload(ev_mod)

            result = await ev_mod.has_mx_record("invalid-domain.example")
            assert result is False

            # Reload again to restore normal state
            importlib.reload(ev_mod)


# =============================================================================
# 8. src/integrations/google_sheets.py - lines 32-34
# =============================================================================

class TestGoogleSheetsGaps:
    """Cover _append_row exception path."""

    async def test_append_row_exception_returns_false(self):
        """Lines 32-34: exception in _append_row returns False."""
        from src.integrations.google_sheets import GoogleSheetsCRM

        crm = GoogleSheetsCRM(spreadsheet_id="test-sheet-id")

        # Patch the logger.info to raise, simulating an exception in the try block
        with patch("src.integrations.google_sheets.logger") as mock_logger:
            mock_logger.info.side_effect = RuntimeError("simulated error")
            mock_logger.error = MagicMock()

            result = await crm._append_row("TestSheet", ["val1", "val2"])
            assert result is False
            mock_logger.error.assert_called_once()


# =============================================================================
# 9. src/integrations/jobber.py - lines 124-126
# =============================================================================

class TestJobberGaps:
    """Cover create_lead exception path."""

    async def test_create_lead_exception_returns_error(self):
        """Lines 124-126: exception in create_lead returns error dict."""
        from src.integrations.jobber import JobberCRM

        crm = JobberCRM(api_key="test-key")

        with patch.object(crm, "_graphql", side_effect=RuntimeError("Network error")):
            result = await crm.create_lead(
                customer_id="cust-123",
                source="google_lsa",
                service_type="HVAC repair",
            )

        assert result["success"] is False
        assert result["lead_id"] is None
        assert "Network error" in result["error"]


# =============================================================================
# 10. src/agents/sales_outreach.py - lines 39-57, 118, 123, 126
# =============================================================================

class TestSalesOutreachGaps:
    """Cover _get_learning_context paths and generate_outreach_email branches."""

    @patch("src.agents.sales_outreach.generate_response")
    async def test_get_learning_context_with_data(self, mock_gen):
        """Lines 39-57: _get_learning_context returns insights when data exists."""
        with patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock) as mock_open_rate, \
             patch("src.services.learning.get_best_send_time", new_callable=AsyncMock) as mock_best_time:
            mock_open_rate.return_value = 0.42
            mock_best_time.return_value = "9am-12pm"

            from src.agents.sales_outreach import _get_learning_context
            result = await _get_learning_context("hvac", "TX")

            assert "Performance insights" in result
            assert "42%" in result
            assert "9am-12pm" in result

    async def test_get_learning_context_no_data(self):
        """Lines 39-57: _get_learning_context returns empty when no data."""
        with patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock) as mock_open_rate, \
             patch("src.services.learning.get_best_send_time", new_callable=AsyncMock) as mock_best_time:
            mock_open_rate.return_value = 0
            mock_best_time.return_value = None

            from src.agents.sales_outreach import _get_learning_context
            result = await _get_learning_context("plumbing", "CA")
            assert result == ""

    async def test_get_learning_context_exception_returns_empty(self):
        """Lines 54-55: _get_learning_context catches exceptions."""
        with patch("src.services.learning.get_open_rate_by_dimension", new_callable=AsyncMock) as mock_rate:
            mock_rate.side_effect = RuntimeError("DB down")

            from src.agents.sales_outreach import _get_learning_context
            result = await _get_learning_context("roofing", "FL")
            assert result == ""

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_outreach_email_with_website(self, mock_gen, mock_learning):
        """Line 118: website added to prospect details."""
        mock_learning.return_value = ""
        mock_gen.return_value = {
            "content": '{"subject": "Test", "body_html": "<p>Hi</p>", "body_text": "Hi"}',
            "error": None,
            "cost_usd": 0.001,
        }

        from src.agents.sales_outreach import generate_outreach_email
        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Cool HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
            website="https://coolhvac.com",
        )
        assert result["subject"] == "Test"

        # Verify website was in the user_message
        call_kwargs = mock_gen.call_args
        assert "coolhvac.com" in call_kwargs.kwargs.get("user_message", "") or \
               "coolhvac.com" in (call_kwargs.args[1] if len(call_kwargs.args) > 1 else "")

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_outreach_email_with_learning_context(self, mock_gen, mock_learning):
        """Line 123: learning context appended to prospect details."""
        mock_learning.return_value = "Performance insights:\n- Avg open rate for hvac: 42%"
        mock_gen.return_value = {
            "content": '{"subject": "Test", "body_html": "<p>Hi</p>", "body_text": "Hi"}',
            "error": None,
            "cost_usd": 0.001,
        }

        from src.agents.sales_outreach import generate_outreach_email
        result = await generate_outreach_email(
            prospect_name="John",
            company_name="Cool HVAC",
            trade_type="hvac",
            city="Austin",
            state="TX",
        )
        assert result["subject"] == "Test"

    @patch("src.agents.sales_outreach._get_learning_context", new_callable=AsyncMock)
    @patch("src.agents.sales_outreach.generate_response", new_callable=AsyncMock)
    async def test_generate_outreach_email_with_extra_instructions(self, mock_gen, mock_learning):
        """Line 126: extra_instructions appended to prospect details."""
        mock_learning.return_value = ""
        mock_gen.return_value = {
            "content": '{"subject": "Test", "body_html": "<p>Hi</p>", "body_text": "Hi"}',
            "error": None,
            "cost_usd": 0.001,
        }

        from src.agents.sales_outreach import generate_outreach_email
        result = await generate_outreach_email(
            prospect_name="Jane",
            company_name="ProPlumb",
            trade_type="plumbing",
            city="Dallas",
            state="TX",
            extra_instructions="Mention their recent 5-star review",
        )
        assert result["subject"] == "Test"


# =============================================================================
# 11. Model __repr__ methods
# =============================================================================

class TestModelReprMethods:
    """Cover __repr__ on all model classes with uncovered repr lines.
    Uses MagicMock(spec=Model) + Model.__repr__(mock) to bypass
    SQLAlchemy instrumented attribute descriptors."""

    def test_client_repr(self):
        """client.py:110"""
        from src.models.client import Client
        m = MagicMock(spec=Client)
        m.business_name = "Cool HVAC"
        m.trade_type = "hvac"
        result = Client.__repr__(m)
        assert "Cool HVAC" in result
        assert "hvac" in result

    def test_consent_record_repr(self):
        """consent.py:73-74"""
        from src.models.consent import ConsentRecord
        m = MagicMock(spec=ConsentRecord)
        m.phone = "+15125551234"
        m.consent_type = "pec"
        m.is_active = True
        result = ConsentRecord.__repr__(m)
        assert "+15125" in result
        assert "***" in result
        assert "pec" in result

    def test_consent_record_repr_no_phone(self):
        """consent.py:73-74 - phone is empty string."""
        from src.models.consent import ConsentRecord
        m = MagicMock(spec=ConsentRecord)
        m.phone = ""
        m.consent_type = "pewc"
        m.is_active = False
        result = ConsentRecord.__repr__(m)
        assert "pewc" in result

    def test_conversation_repr(self):
        """conversation.py:82"""
        from src.models.conversation import Conversation
        m = MagicMock(spec=Conversation)
        m.direction = "outbound"
        m.agent_id = "intake"
        result = Conversation.__repr__(m)
        assert "outbound" in result
        assert "intake" in result

    def test_email_blacklist_repr(self):
        """email_blacklist.py:41"""
        from src.models.email_blacklist import EmailBlacklist
        m = MagicMock(spec=EmailBlacklist)
        m.entry_type = "domain"
        m.value = "spam.com"
        result = EmailBlacklist.__repr__(m)
        assert "domain" in result
        assert "spam.com" in result

    def test_event_log_repr(self):
        """event_log.py:64"""
        from src.models.event_log import EventLog
        m = MagicMock(spec=EventLog)
        m.action = "sms_sent"
        m.status = "success"
        result = EventLog.__repr__(m)
        assert "sms_sent" in result
        assert "success" in result

    def test_followup_task_repr(self):
        """followup.py:79"""
        from src.models.followup import FollowupTask
        m = MagicMock(spec=FollowupTask)
        m.task_type = "cold_nurture"
        m.sequence_number = 2
        m.status = "pending"
        result = FollowupTask.__repr__(m)
        assert "cold_nurture" in result
        assert "#2" in result
        assert "pending" in result

    def test_lead_repr(self):
        """lead.py:136-137"""
        from src.models.lead import Lead
        m = MagicMock(spec=Lead)
        m.phone = "+15125559999"
        m.state = "qualifying"
        result = Lead.__repr__(m)
        assert "+15125" in result
        assert "***" in result
        assert "qualifying" in result

    def test_lead_repr_no_phone(self):
        """lead.py:136-137 - phone is empty."""
        from src.models.lead import Lead
        m = MagicMock(spec=Lead)
        m.phone = ""
        m.state = "new"
        result = Lead.__repr__(m)
        assert "unknown" in result

    def test_learning_signal_repr(self):
        """learning_signal.py:48"""
        from src.models.learning_signal import LearningSignal
        m = MagicMock(spec=LearningSignal)
        m.signal_type = "email_opened"
        m.value = 1.0
        result = LearningSignal.__repr__(m)
        assert "email_opened" in result
        assert "1.0" in result

    def test_outreach_repr(self):
        """outreach.py:100"""
        from src.models.outreach import Outreach
        m = MagicMock(spec=Outreach)
        m.prospect_name = "John Doe"
        m.status = "contacted"
        result = Outreach.__repr__(m)
        assert "John Doe" in result
        assert "contacted" in result

    def test_outreach_email_repr(self):
        """outreach_email.py:59"""
        from src.models.outreach_email import OutreachEmail
        m = MagicMock(spec=OutreachEmail)
        m.direction = "outbound"
        m.sequence_step = 2
        result = OutreachEmail.__repr__(m)
        assert "outbound" in result
        assert "step=2" in result

    def test_outreach_sms_repr(self):
        """outreach_sms.py:58"""
        from src.models.outreach_sms import OutreachSMS
        m = MagicMock(spec=OutreachSMS)
        m.direction = "outbound"
        m.to_phone = "+15125551234"
        m.status = "delivered"
        result = OutreachSMS.__repr__(m)
        assert "outbound" in result
        assert "+15125" in result
        assert "***" in result
        assert "delivered" in result

    def test_sales_config_repr(self):
        """sales_config.py:79"""
        from src.models.sales_config import SalesEngineConfig
        m = MagicMock(spec=SalesEngineConfig)
        m.is_active = True
        result = SalesEngineConfig.__repr__(m)
        assert "active=True" in result

    def test_sales_config_repr_inactive(self):
        """sales_config.py:79 - inactive config."""
        from src.models.sales_config import SalesEngineConfig
        m = MagicMock(spec=SalesEngineConfig)
        m.is_active = False
        result = SalesEngineConfig.__repr__(m)
        assert "active=False" in result

    def test_scrape_job_repr(self):
        """scrape_job.py:56"""
        from src.models.scrape_job import ScrapeJob
        m = MagicMock(spec=ScrapeJob)
        m.platform = "google_maps"
        m.location_query = "Austin TX HVAC"
        m.status = "completed"
        result = ScrapeJob.__repr__(m)
        assert "google_maps" in result
        assert "Austin TX HVAC" in result
        assert "completed" in result

    def test_task_queue_repr(self):
        """task_queue.py:58"""
        from src.models.task_queue import TaskQueue
        m = MagicMock(spec=TaskQueue)
        m.task_type = "enrich_email"
        m.status = "pending"
        result = TaskQueue.__repr__(m)
        assert "enrich_email" in result
        assert "pending" in result

    def test_booking_repr(self):
        """booking.py:82"""
        from src.models.booking import Booking
        m = MagicMock(spec=Booking)
        m.appointment_date = date(2025, 7, 15)
        m.service_type = "AC repair"
        m.status = "confirmed"
        result = Booking.__repr__(m)
        assert "2025-07-15" in result
        assert "AC repair" in result
        assert "confirmed" in result

    def test_agency_partner_repr(self):
        """agency_partner.py:49"""
        from src.models.agency_partner import AgencyPartner
        m = MagicMock(spec=AgencyPartner)
        m.company_name = "MarketingCo"
        result = AgencyPartner.__repr__(m)
        assert "MarketingCo" in result
