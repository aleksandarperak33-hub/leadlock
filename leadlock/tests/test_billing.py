"""
Tests for src/services/billing.py — Stripe billing: customer creation, checkout,
webhook processing, and subscription lifecycle.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.services.billing import (
    create_customer,
    create_checkout_session,
    handle_webhook,
    _handle_checkout_completed,
    _handle_payment_failed,
    _price_id_to_plan,
    PLAN_NAMES,
    PLAN_AMOUNTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_settings(**overrides):
    """Build a mock Settings object with Stripe config."""
    defaults = {
        "stripe_secret_key": "sk_test_xxx",
        "stripe_webhook_secret": "whsec_test_xxx",
        "stripe_price_starter": "price_starter_123",
        "stripe_price_pro": "price_pro_456",
        "stripe_price_business": "price_biz_789",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _mock_async_session_factory():
    """Return a patched async_session_factory that yields a mock db session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            pass

    return _FakeCtx, mock_db


# ---------------------------------------------------------------------------
# _price_id_to_plan
# ---------------------------------------------------------------------------

class TestPriceIdToPlan:
    def test_starter(self):
        with patch("src.services.billing.get_settings", return_value=_make_mock_settings()):
            assert _price_id_to_plan("price_starter_123") == "starter"

    def test_pro(self):
        with patch("src.services.billing.get_settings", return_value=_make_mock_settings()):
            assert _price_id_to_plan("price_pro_456") == "pro"

    def test_business(self):
        with patch("src.services.billing.get_settings", return_value=_make_mock_settings()):
            assert _price_id_to_plan("price_biz_789") == "business"

    def test_unknown_price(self):
        with patch("src.services.billing.get_settings", return_value=_make_mock_settings()):
            assert _price_id_to_plan("price_unknown_999") == "unknown"


# ---------------------------------------------------------------------------
# create_customer
# ---------------------------------------------------------------------------

class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_success(self):
        """Successful Stripe customer creation returns customer_id."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()
        mock_customer = MagicMock()
        mock_customer.id = "cus_test_abc"
        mock_stripe.Customer.create = MagicMock(return_value=mock_customer)

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = mock_customer
            result = await create_customer("client-id-123", "test@example.com", "HVAC Co")

        assert result["customer_id"] == "cus_test_abc"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_stripe_not_configured(self):
        """When Stripe key is missing, _get_stripe raises ValueError."""
        with patch(
            "src.services.billing._get_stripe",
            side_effect=ValueError("Stripe secret key not configured"),
        ):
            result = await create_customer("cid", "test@ex.com", "Biz")

        assert result["customer_id"] is None
        assert "Stripe secret key not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_stripe_api_error(self):
        """Generic API error returns error in result dict."""
        mock_stripe = MagicMock()

        with (
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch(
                "src.services.billing._run_sync",
                new_callable=AsyncMock,
                side_effect=Exception("Connection timeout"),
            ),
        ):
            result = await create_customer("cid", "test@ex.com", "Biz")

        assert result["customer_id"] is None
        assert "Connection timeout" in result["error"]


# ---------------------------------------------------------------------------
# create_checkout_session
# ---------------------------------------------------------------------------

class TestCreateCheckoutSession:
    @pytest.mark.asyncio
    async def test_success_returns_url(self):
        """Successful checkout session returns session URL."""
        mock_stripe = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_session.id = "cs_test_123"

        with (
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_session),
        ):
            result = await create_checkout_session(
                "client-id", "cus_123", "price_pro_456",
                "https://app.leadlock.io/success",
                "https://app.leadlock.io/cancel",
            )

        assert result["session_url"] == "https://checkout.stripe.com/test"
        assert result["session_id"] == "cs_test_123"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_failure_returns_error(self):
        """When Stripe API fails, return error dict."""
        mock_stripe = MagicMock()

        with (
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch(
                "src.services.billing._run_sync",
                new_callable=AsyncMock,
                side_effect=Exception("Rate limited"),
            ),
        ):
            result = await create_checkout_session(
                "cid", "cus_123", "price_x",
                "https://app.leadlock.io/success",
                "https://app.leadlock.io/cancel",
            )

        assert result["session_url"] is None
        assert "Rate limited" in result["error"]


# ---------------------------------------------------------------------------
# handle_webhook
# ---------------------------------------------------------------------------

class TestHandleWebhook:
    @pytest.mark.asyncio
    async def test_valid_signature_routes_event(self):
        """Valid signature + known event type dispatches to handler."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        fake_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"leadlock_client_id": str(uuid.uuid4())},
                    "subscription": "sub_123",
                    "customer": "cus_123",
                }
            },
        }
        mock_stripe.Webhook.construct_event = MagicMock(return_value=fake_event)
        # Prevent SignatureVerificationError from being raised
        mock_stripe.error.SignatureVerificationError = type("SigError", (Exception,), {})

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=fake_event),
            patch("src.services.billing._handle_checkout_completed", new_callable=AsyncMock) as mock_handler,
        ):
            result = await handle_webhook(b"payload", "sig_header")

        assert result["event_type"] == "checkout.session.completed"
        assert result["handled"] is True
        assert result["error"] is None
        mock_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_error(self):
        """Invalid webhook signature returns error without processing."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        sig_error = type("SignatureVerificationError", (Exception,), {})
        mock_stripe.error.SignatureVerificationError = sig_error
        mock_stripe.Webhook.construct_event = MagicMock(side_effect=sig_error("bad sig"))

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch(
                "src.services.billing._run_sync",
                new_callable=AsyncMock,
                side_effect=sig_error("bad sig"),
            ),
        ):
            result = await handle_webhook(b"payload", "bad_sig")

        assert result["handled"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_unhandled_event_type(self):
        """Unknown event types are acknowledged but not handled."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        fake_event = {
            "type": "some.unknown.event",
            "data": {"object": {}},
        }
        mock_stripe.error.SignatureVerificationError = type("SigError", (Exception,), {})

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=fake_event),
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["event_type"] == "some.unknown.event"
        assert result["handled"] is False
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_stripe_not_configured(self):
        """If Stripe is not configured, return error immediately."""
        with patch(
            "src.services.billing._get_stripe",
            side_effect=ValueError("Stripe secret key not configured"),
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["handled"] is False
        assert "Stripe secret key not configured" in result["error"]


# ---------------------------------------------------------------------------
# _handle_checkout_completed
# ---------------------------------------------------------------------------

class TestHandleCheckoutCompleted:
    @pytest.mark.asyncio
    async def test_updates_client_plan_tier(self):
        """checkout.session.completed should set client's tier and billing_status."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_test_123",
            "customer": "cus_test_456",
        }

        mock_client = MagicMock()
        mock_client.id = uuid.UUID(client_id)
        mock_client.dashboard_email = "owner@hvac.com"
        mock_client.business_name = "HVAC Pro"
        mock_client.tier = "starter"
        mock_client.billing_status = "pending"
        mock_client.stripe_customer_id = None
        mock_client.stripe_subscription_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *args):
                pass

        # Mock Stripe subscription retrieval for tier sync
        mock_sub = {
            "items": {"data": [{"price": {"id": "price_pro_456"}}]},
        }

        mock_stripe = MagicMock()

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=_FakeCtx()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
            patch("src.services.billing._price_id_to_plan", return_value="pro"),
            patch("src.services.transactional_email.send_subscription_confirmation", new_callable=AsyncMock),
        ):
            await _handle_checkout_completed(session_data)

        assert mock_client.stripe_customer_id == "cus_test_456"
        assert mock_client.stripe_subscription_id == "sub_test_123"
        assert mock_client.billing_status == "active"
        assert mock_client.tier == "pro"

    @pytest.mark.asyncio
    async def test_no_client_id_in_metadata(self):
        """Missing client_id in metadata should log warning and return."""
        session_data = {"metadata": {}, "subscription": "sub_x", "customer": "cus_x"}

        # Should not raise — just returns early
        await _handle_checkout_completed(session_data)


# ---------------------------------------------------------------------------
# _handle_payment_failed
# ---------------------------------------------------------------------------

class TestHandlePaymentFailed:
    @pytest.mark.asyncio
    async def test_sends_failure_email(self):
        """Payment failure should mark past_due and send email."""
        mock_client = MagicMock()
        mock_client.id = uuid.uuid4()
        mock_client.dashboard_email = "owner@hvac.com"
        mock_client.business_name = "HVAC Pro"
        mock_client.billing_status = "active"
        mock_client.stripe_customer_id = "cus_123"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        class _FakeCtx:
            async def __aenter__(self):
                return mock_db
            async def __aexit__(self, *args):
                pass

        invoice_data = {"customer": "cus_123"}

        with (
            patch("src.database.async_session_factory", return_value=_FakeCtx()),
            patch("src.services.transactional_email.send_payment_failed", new_callable=AsyncMock) as mock_email,
            patch("src.utils.alerting.send_alert", new_callable=AsyncMock),
        ):
            await _handle_payment_failed(invoice_data)

        assert mock_client.billing_status == "past_due"
        mock_email.assert_awaited_once_with("owner@hvac.com", "HVAC Pro")

    @pytest.mark.asyncio
    async def test_no_customer_id_returns_early(self):
        """Missing customer ID in invoice should return without error."""
        await _handle_payment_failed({"customer": None})
        # No exception = pass
