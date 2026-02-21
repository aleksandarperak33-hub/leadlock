"""
Extended tests for src/services/billing.py - covers all lines missing from
test_billing.py: _get_stripe, _run_sync, create_billing_portal_session,
webhook signature/parsing errors, _handle_invoice_paid,
_handle_subscription_updated, _handle_subscription_deleted, and additional
branch paths in _handle_checkout_completed and _handle_payment_failed.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.billing import (
    _get_stripe,
    _run_sync,
    _price_id_to_plan,
    create_billing_portal_session,
    handle_webhook,
    _handle_checkout_completed,
    _handle_invoice_paid,
    _handle_payment_failed,
    _handle_subscription_updated,
    _handle_subscription_deleted,
    PLAN_NAMES,
    PLAN_AMOUNTS,
    STRIPE_API_TIMEOUT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_settings(**overrides):
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


def _mock_async_session_factory(mock_client=None):
    """Return a fake async_session_factory context and its mock db session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_client

    mock_db.execute = AsyncMock(return_value=mock_result)

    class _FakeCtx:
        async def __aenter__(self):
            return mock_db
        async def __aexit__(self, *args):
            pass

    return _FakeCtx, mock_db


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_plan_names_mapping(self):
        assert PLAN_NAMES == {
            "starter": "Starter",
            "pro": "Professional",
            "business": "Business",
        }

    def test_plan_amounts_mapping(self):
        assert PLAN_AMOUNTS == {
            "starter": "$297",
            "pro": "$597",
            "business": "$1,497",
        }

    def test_stripe_api_timeout(self):
        assert STRIPE_API_TIMEOUT == 10


# ---------------------------------------------------------------------------
# _get_stripe
# ---------------------------------------------------------------------------

class TestGetStripe:
    def test_returns_stripe_module_with_key(self):
        """_get_stripe configures stripe and returns the module."""
        mock_settings = _make_mock_settings()
        with patch("src.services.billing.get_settings", return_value=mock_settings):
            with patch.dict("sys.modules", {"stripe": MagicMock()}) as _:
                import stripe as stripe_mod
                with patch("src.services.billing.get_settings", return_value=mock_settings):
                    # We need to patch the import inside _get_stripe
                    mock_stripe_module = MagicMock()
                    with patch("builtins.__import__", side_effect=lambda name, *a, **kw: mock_stripe_module if name == "stripe" else __import__(name, *a, **kw)):
                        result = _get_stripe()
                        assert result is mock_stripe_module
                        assert mock_stripe_module.api_key == "sk_test_xxx"
                        assert mock_stripe_module.max_network_retries == 1

    def test_raises_when_key_not_configured(self):
        """_get_stripe raises ValueError when stripe_secret_key is empty."""
        mock_settings = _make_mock_settings(stripe_secret_key="")
        with patch("src.services.billing.get_settings", return_value=mock_settings):
            mock_stripe_module = MagicMock()
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: mock_stripe_module if name == "stripe" else __import__(name, *a, **kw)):
                with pytest.raises(ValueError, match="Stripe secret key not configured"):
                    _get_stripe()


# ---------------------------------------------------------------------------
# _run_sync
# ---------------------------------------------------------------------------

class TestRunSync:
    async def test_executes_function_in_executor(self):
        """_run_sync runs a synchronous function in the event loop executor."""
        def sync_fn(x, y):
            return x + y

        result = await _run_sync(sync_fn, 3, 7)
        assert result == 10

    async def test_passes_kwargs(self):
        """_run_sync passes keyword arguments correctly."""
        def sync_fn(a, b=0):
            return a * b

        result = await _run_sync(sync_fn, 5, b=3)
        assert result == 15


# ---------------------------------------------------------------------------
# create_billing_portal_session
# ---------------------------------------------------------------------------

class TestCreateBillingPortalSession:
    async def test_success(self):
        """Successful portal session returns URL."""
        mock_stripe = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/session/test_portal"

        with (
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_session),
        ):
            result = await create_billing_portal_session("cus_123", "https://app.leadlock.io/billing")

        assert result["portal_url"] == "https://billing.stripe.com/session/test_portal"
        assert result["error"] is None

    async def test_failure(self):
        """Portal session failure returns error."""
        mock_stripe = MagicMock()

        with (
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch(
                "src.services.billing._run_sync",
                new_callable=AsyncMock,
                side_effect=Exception("Stripe unavailable"),
            ),
        ):
            result = await create_billing_portal_session("cus_123", "https://app.leadlock.io/billing")

        assert result["portal_url"] is None
        assert "Stripe unavailable" in result["error"]


# ---------------------------------------------------------------------------
# handle_webhook - additional branches
# ---------------------------------------------------------------------------

class TestHandleWebhookExtended:
    async def test_signature_verification_error(self):
        """SignatureVerificationError returns invalid signature error."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        sig_error_cls = type("SignatureVerificationError", (Exception,), {})
        mock_stripe.error.SignatureVerificationError = sig_error_cls

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch(
                "src.services.billing._run_sync",
                new_callable=AsyncMock,
                side_effect=sig_error_cls("bad"),
            ),
        ):
            result = await handle_webhook(b"payload", "bad_sig")

        assert result["handled"] is False
        assert result["error"] == "Invalid signature"

    async def test_general_parsing_error(self):
        """Non-signature parsing error is returned."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        sig_error_cls = type("SignatureVerificationError", (Exception,), {})
        mock_stripe.error.SignatureVerificationError = sig_error_cls

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch(
                "src.services.billing._run_sync",
                new_callable=AsyncMock,
                side_effect=RuntimeError("JSON decode error"),
            ),
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["handled"] is False
        assert "JSON decode error" in result["error"]

    async def test_invoice_paid_event(self):
        """invoice.paid event is dispatched correctly."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        fake_event = {
            "type": "invoice.paid",
            "data": {"object": {"customer": "cus_123"}},
        }
        mock_stripe.error.SignatureVerificationError = type("SigError", (Exception,), {})

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=fake_event),
            patch("src.services.billing._handle_invoice_paid", new_callable=AsyncMock) as mock_handler,
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["event_type"] == "invoice.paid"
        assert result["handled"] is True
        mock_handler.assert_awaited_once()

    async def test_invoice_payment_failed_event(self):
        """invoice.payment_failed event is dispatched correctly."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        fake_event = {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_fail"}},
        }
        mock_stripe.error.SignatureVerificationError = type("SigError", (Exception,), {})

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=fake_event),
            patch("src.services.billing._handle_payment_failed", new_callable=AsyncMock) as mock_handler,
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["event_type"] == "invoice.payment_failed"
        assert result["handled"] is True
        mock_handler.assert_awaited_once()

    async def test_subscription_updated_event(self):
        """customer.subscription.updated event is dispatched correctly."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        fake_event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": "cus_up"}},
        }
        mock_stripe.error.SignatureVerificationError = type("SigError", (Exception,), {})

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=fake_event),
            patch("src.services.billing._handle_subscription_updated", new_callable=AsyncMock) as mock_handler,
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["event_type"] == "customer.subscription.updated"
        assert result["handled"] is True
        mock_handler.assert_awaited_once()

    async def test_subscription_deleted_event(self):
        """customer.subscription.deleted event is dispatched correctly."""
        mock_settings = _make_mock_settings()
        mock_stripe = MagicMock()

        fake_event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_del"}},
        }
        mock_stripe.error.SignatureVerificationError = type("SigError", (Exception,), {})

        with (
            patch("src.services.billing.get_settings", return_value=mock_settings),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=fake_event),
            patch("src.services.billing._handle_subscription_deleted", new_callable=AsyncMock) as mock_handler,
        ):
            result = await handle_webhook(b"payload", "sig")

        assert result["event_type"] == "customer.subscription.deleted"
        assert result["handled"] is True
        mock_handler.assert_awaited_once()


# ---------------------------------------------------------------------------
# _handle_checkout_completed - additional branches
# ---------------------------------------------------------------------------

class TestHandleCheckoutCompletedExtended:
    async def test_invalid_uuid_returns_early(self):
        """Invalid UUID in metadata logs error and returns."""
        session_data = {
            "metadata": {"leadlock_client_id": "not-a-uuid"},
            "subscription": "sub_x",
            "customer": "cus_x",
        }
        mock_stripe = MagicMock()
        mock_sub = {"items": {"data": [{"price": {"id": "price_pro_456"}}]}}

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
            patch("src.services.billing._price_id_to_plan", return_value="pro"),
        ):
            # Should not raise
            await _handle_checkout_completed(session_data)

    async def test_unknown_client_returns_early(self):
        """When client is not found in the DB, returns without crashing."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_x",
            "customer": "cus_x",
        }

        factory_cls, mock_db = _mock_async_session_factory(mock_client=None)
        mock_stripe = MagicMock()
        mock_sub = {"items": {"data": [{"price": {"id": "price_pro_456"}}]}}

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
            patch("src.services.billing._price_id_to_plan", return_value="pro"),
        ):
            await _handle_checkout_completed(session_data)

    async def test_stripe_subscription_retrieval_fails_gracefully(self):
        """If Stripe subscription retrieval fails, proceed without tier sync."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_fail",
            "customer": "cus_fail",
        }

        mock_client = MagicMock()
        mock_client.id = uuid.UUID(client_id)
        mock_client.dashboard_email = None
        mock_client.business_name = "Test Biz"
        mock_client.tier = "starter"
        mock_client.billing_status = "pending"
        mock_client.stripe_customer_id = None
        mock_client.stripe_subscription_id = None

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)
        mock_stripe = MagicMock()

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, side_effect=Exception("Stripe down")),
        ):
            await _handle_checkout_completed(session_data)

        # Client should still have billing_status set but tier unchanged
        assert mock_client.billing_status == "active"
        assert mock_client.stripe_customer_id == "cus_fail"

    async def test_unknown_plan_does_not_set_tier(self):
        """When plan_slug is 'unknown', tier should not be changed."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_x",
            "customer": "cus_x",
        }

        mock_client = MagicMock()
        mock_client.id = uuid.UUID(client_id)
        mock_client.dashboard_email = None
        mock_client.business_name = "Test Biz"
        mock_client.tier = "starter"
        mock_client.billing_status = "pending"
        mock_client.stripe_customer_id = None
        mock_client.stripe_subscription_id = None

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)
        mock_stripe = MagicMock()
        mock_sub = {"items": {"data": [{"price": {"id": "price_unknown"}}]}}

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
            patch("src.services.billing._price_id_to_plan", return_value="unknown"),
        ):
            await _handle_checkout_completed(session_data)

        # tier unchanged, no email sent
        assert mock_client.billing_status == "active"
        assert mock_client.tier == "starter"

    async def test_sends_confirmation_email_when_plan_known(self):
        """Sends subscription confirmation email when plan and email are present."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_ok",
            "customer": "cus_ok",
        }

        mock_client = MagicMock()
        mock_client.id = uuid.UUID(client_id)
        mock_client.dashboard_email = "owner@hvac.com"
        mock_client.business_name = "HVAC Pro"
        mock_client.tier = "starter"
        mock_client.billing_status = "pending"
        mock_client.stripe_customer_id = None
        mock_client.stripe_subscription_id = None

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)
        mock_stripe = MagicMock()
        mock_sub = {"items": {"data": [{"price": {"id": "price_pro_456"}}]}}

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
            patch("src.services.billing._price_id_to_plan", return_value="pro"),
            patch(
                "src.services.transactional_email.send_subscription_confirmation",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _handle_checkout_completed(session_data)

        mock_email.assert_awaited_once_with("owner@hvac.com", "Professional", "$597")

    async def test_no_email_when_dashboard_email_missing(self):
        """No confirmation email when dashboard_email is None."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_no_email",
            "customer": "cus_no_email",
        }

        mock_client = MagicMock()
        mock_client.id = uuid.UUID(client_id)
        mock_client.dashboard_email = None
        mock_client.business_name = "No Email Biz"
        mock_client.tier = "starter"
        mock_client.billing_status = "pending"
        mock_client.stripe_customer_id = None
        mock_client.stripe_subscription_id = None

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)
        mock_stripe = MagicMock()
        mock_sub = {"items": {"data": [{"price": {"id": "price_starter_123"}}]}}

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
            patch("src.services.billing._price_id_to_plan", return_value="starter"),
            patch(
                "src.services.transactional_email.send_subscription_confirmation",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await _handle_checkout_completed(session_data)

        mock_email.assert_not_awaited()

    async def test_empty_subscription_items(self):
        """When Stripe subscription has empty items data, plan_slug defaults to unknown."""
        client_id = str(uuid.uuid4())
        session_data = {
            "metadata": {"leadlock_client_id": client_id},
            "subscription": "sub_empty",
            "customer": "cus_empty",
        }

        mock_client = MagicMock()
        mock_client.id = uuid.UUID(client_id)
        mock_client.dashboard_email = None
        mock_client.business_name = "Empty Items Biz"
        mock_client.tier = "pro"
        mock_client.billing_status = "pending"
        mock_client.stripe_customer_id = None
        mock_client.stripe_subscription_id = None

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)
        mock_stripe = MagicMock()
        # items.data is empty list
        mock_sub = {"items": {"data": []}}

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._get_stripe", return_value=mock_stripe),
            patch("src.services.billing._run_sync", new_callable=AsyncMock, return_value=mock_sub),
        ):
            await _handle_checkout_completed(session_data)

        # tier should not change since plan_slug would be "unknown" (empty price_id)
        assert mock_client.billing_status == "active"


# ---------------------------------------------------------------------------
# _handle_invoice_paid
# ---------------------------------------------------------------------------

class TestHandleInvoicePaid:
    async def test_no_customer_id_returns_early(self):
        """Missing customer_id returns early."""
        await _handle_invoice_paid({"customer": None})

    async def test_activates_non_active_client(self):
        """Sets billing_status to active when currently not active."""
        mock_client = MagicMock()
        mock_client.billing_status = "past_due"
        mock_client.business_name = "Reactivated Biz"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with patch("src.database.async_session_factory", return_value=factory_cls()):
            await _handle_invoice_paid({"customer": "cus_reactivate"})

        assert mock_client.billing_status == "active"
        mock_db.commit.assert_awaited_once()

    async def test_no_change_when_already_active(self):
        """Does not commit when billing_status is already active."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with patch("src.database.async_session_factory", return_value=factory_cls()):
            await _handle_invoice_paid({"customer": "cus_active"})

        mock_db.commit.assert_not_awaited()

    async def test_no_client_found(self):
        """When client is not found, does nothing."""
        factory_cls, mock_db = _mock_async_session_factory(mock_client=None)

        with patch("src.database.async_session_factory", return_value=factory_cls()):
            await _handle_invoice_paid({"customer": "cus_notfound"})

        mock_db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_payment_failed - extended
# ---------------------------------------------------------------------------

class TestHandlePaymentFailedExtended:
    async def test_no_client_found_returns_early(self):
        """Missing client in DB returns early without sending email."""
        factory_cls, mock_db = _mock_async_session_factory(mock_client=None)

        with (
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_payment_failed({"customer": "cus_ghost"})

        mock_db.commit.assert_not_awaited()

    async def test_no_dashboard_email_skips_notification(self):
        """When dashboard_email is None, no failure email is sent."""
        mock_client = MagicMock()
        mock_client.id = uuid.uuid4()
        mock_client.dashboard_email = None
        mock_client.business_name = "No Email Biz"
        mock_client.billing_status = "active"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch(
                "src.services.transactional_email.send_payment_failed",
                new_callable=AsyncMock,
            ) as mock_email,
            patch("src.utils.alerting.send_alert", new_callable=AsyncMock),
        ):
            await _handle_payment_failed({"customer": "cus_no_email"})

        assert mock_client.billing_status == "past_due"
        mock_email.assert_not_awaited()

    async def test_sends_alert_on_failure(self):
        """Payment failure sends an ops alert."""
        mock_client = MagicMock()
        mock_client.id = uuid.uuid4()
        mock_client.dashboard_email = "owner@test.com"
        mock_client.business_name = "Alert Biz"
        mock_client.billing_status = "active"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch(
                "src.services.transactional_email.send_payment_failed",
                new_callable=AsyncMock,
            ),
            patch("src.utils.alerting.send_alert", new_callable=AsyncMock) as mock_alert,
        ):
            await _handle_payment_failed({"customer": "cus_alert"})

        mock_alert.assert_awaited_once()
        call_args = mock_alert.call_args
        assert call_args[0][0] == "payment_failed"
        assert "Alert Biz" in call_args[0][1]


# ---------------------------------------------------------------------------
# _handle_subscription_updated
# ---------------------------------------------------------------------------

class TestHandleSubscriptionUpdated:
    async def test_no_customer_id_returns_early(self):
        """Missing customer_id returns early."""
        await _handle_subscription_updated({"customer": None, "status": "active"})

    async def test_updates_billing_status(self):
        """Subscription update changes billing_status per mapping."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Updated Biz"
        mock_client.tier = "starter"
        mock_client.stripe_subscription_id = "sub_old"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_subscription_updated({
                "customer": "cus_update",
                "status": "past_due",
                "id": "sub_new",
                "items": {"data": []},
            })

        assert mock_client.billing_status == "past_due"
        assert mock_client.stripe_subscription_id == "sub_new"

    async def test_trialing_status_maps_to_trial(self):
        """Stripe 'trialing' maps to billing_status 'trial'."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Trial Biz"
        mock_client.tier = "starter"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_subscription_updated({
                "customer": "cus_trial",
                "status": "trialing",
                "id": "sub_trial",
                "items": {"data": []},
            })

        assert mock_client.billing_status == "trial"

    async def test_canceled_status(self):
        """Stripe 'canceled' maps to billing_status 'canceled'."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Cancel Biz"
        mock_client.tier = "pro"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_subscription_updated({
                "customer": "cus_cancel",
                "status": "canceled",
                "id": "sub_cancel",
                "items": {"data": []},
            })

        assert mock_client.billing_status == "canceled"

    async def test_unpaid_status_maps_to_past_due(self):
        """Stripe 'unpaid' maps to billing_status 'past_due'."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Unpaid Biz"
        mock_client.tier = "starter"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_subscription_updated({
                "customer": "cus_unpaid",
                "status": "unpaid",
                "id": "sub_unpaid",
                "items": {"data": []},
            })

        assert mock_client.billing_status == "past_due"

    async def test_unknown_status_keeps_current(self):
        """Unknown Stripe status keeps existing billing_status."""
        mock_client = MagicMock()
        mock_client.billing_status = "pilot"
        mock_client.business_name = "Pilot Biz"
        mock_client.tier = "pro"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_subscription_updated({
                "customer": "cus_unknown_status",
                "status": "some_unknown_status",
                "id": "sub_unk",
                "items": {"data": []},
            })

        assert mock_client.billing_status == "pilot"

    async def test_tier_change_on_upgrade(self):
        """Subscription upgrade changes client tier."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Upgrade Biz"
        mock_client.tier = "starter"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._price_id_to_plan", return_value="business"),
        ):
            await _handle_subscription_updated({
                "customer": "cus_upgrade",
                "status": "active",
                "id": "sub_upgrade",
                "items": {"data": [{"price": {"id": "price_biz_789"}}]},
            })

        assert mock_client.tier == "business"

    async def test_unknown_plan_does_not_change_tier(self):
        """When price maps to 'unknown', tier stays the same."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "No Change Biz"
        mock_client.tier = "pro"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._price_id_to_plan", return_value="unknown"),
        ):
            await _handle_subscription_updated({
                "customer": "cus_no_plan",
                "status": "active",
                "id": "sub_no_plan",
                "items": {"data": [{"price": {"id": "price_xxx"}}]},
            })

        assert mock_client.tier == "pro"

    async def test_same_tier_no_log(self):
        """When tier does not change, no tier change log."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Same Tier Biz"
        mock_client.tier = "pro"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
            patch("src.services.billing._price_id_to_plan", return_value="pro"),
        ):
            await _handle_subscription_updated({
                "customer": "cus_same",
                "status": "active",
                "id": "sub_same",
                "items": {"data": [{"price": {"id": "price_pro_456"}}]},
            })

        assert mock_client.tier == "pro"

    async def test_no_client_found(self):
        """When client is not found, does nothing."""
        factory_cls, mock_db = _mock_async_session_factory(mock_client=None)

        with (
            patch("src.services.billing.get_settings", return_value=_make_mock_settings()),
            patch("src.database.async_session_factory", return_value=factory_cls()),
        ):
            await _handle_subscription_updated({
                "customer": "cus_ghost",
                "status": "active",
                "id": "sub_ghost",
                "items": {"data": []},
            })

        mock_db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# _handle_subscription_deleted
# ---------------------------------------------------------------------------

class TestHandleSubscriptionDeleted:
    async def test_no_customer_id_returns_early(self):
        """Missing customer_id returns early."""
        await _handle_subscription_deleted({"customer": None})

    async def test_cancels_subscription(self):
        """Deleting subscription sets canceled and clears subscription_id."""
        mock_client = MagicMock()
        mock_client.billing_status = "active"
        mock_client.business_name = "Deleted Sub Biz"
        mock_client.stripe_subscription_id = "sub_old"

        factory_cls, mock_db = _mock_async_session_factory(mock_client=mock_client)

        with patch("src.database.async_session_factory", return_value=factory_cls()):
            await _handle_subscription_deleted({"customer": "cus_del"})

        assert mock_client.billing_status == "canceled"
        assert mock_client.stripe_subscription_id is None
        mock_db.commit.assert_awaited_once()

    async def test_no_client_found(self):
        """When client is not found, does nothing."""
        factory_cls, mock_db = _mock_async_session_factory(mock_client=None)

        with patch("src.database.async_session_factory", return_value=factory_cls()):
            await _handle_subscription_deleted({"customer": "cus_ghost"})

        mock_db.commit.assert_not_awaited()
