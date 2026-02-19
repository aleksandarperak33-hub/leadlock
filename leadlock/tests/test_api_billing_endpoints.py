"""
Tests for src/api/billing.py — billing API endpoints (plans, checkout, portal,
status, plan-limits, Stripe webhook).
"""
import pytest
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.api.billing import (
    get_plans,
    create_checkout,
    billing_portal,
    billing_status,
    plan_limits,
    stripe_webhook,
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
        "app_base_url": "https://app.leadlock.io",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _make_mock_client(**overrides):
    """Build a mock Client object."""
    defaults = {
        "id": uuid.uuid4(),
        "business_name": "HVAC Pro",
        "tier": "starter",
        "billing_status": "trial",
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "dashboard_email": "owner@hvac.com",
        "owner_email": "owner@hvac.com",
        "trial_ends_at": None,
    }
    defaults.update(overrides)
    client = MagicMock()
    for k, v in defaults.items():
        setattr(client, k, v)
    return client


def _make_mock_request(json_data=None, body=b"", headers=None):
    """Build a mock Request object."""
    mock_request = AsyncMock()
    if json_data is not None:
        mock_request.json = AsyncMock(return_value=json_data)
    else:
        mock_request.json = AsyncMock(side_effect=Exception("Invalid JSON"))
    mock_request.body = AsyncMock(return_value=body)
    mock_request.headers = headers or {}
    return mock_request


# ---------------------------------------------------------------------------
# GET /api/v1/billing/plans
# ---------------------------------------------------------------------------


class TestGetPlans:
    @pytest.mark.asyncio
    async def test_returns_three_plans(self):
        """Plans endpoint returns starter, pro, and business plans."""
        with patch("src.api.billing.get_settings", return_value=_make_mock_settings()):
            result = await get_plans()

        assert len(result["plans"]) == 3
        slugs = [p["slug"] for p in result["plans"]]
        assert slugs == ["starter", "pro", "business"]

    @pytest.mark.asyncio
    async def test_plans_have_price_ids(self):
        """Each plan includes a Stripe price ID."""
        with patch("src.api.billing.get_settings", return_value=_make_mock_settings()):
            result = await get_plans()

        for plan in result["plans"]:
            assert "price_id" in plan
            assert plan["price_id"]  # not empty

    @pytest.mark.asyncio
    async def test_pro_is_marked_popular(self):
        """Pro plan has popular=True."""
        with patch("src.api.billing.get_settings", return_value=_make_mock_settings()):
            result = await get_plans()

        pro = [p for p in result["plans"] if p["slug"] == "pro"][0]
        assert pro.get("popular") is True

    @pytest.mark.asyncio
    async def test_all_plans_have_features(self):
        """Each plan has a non-empty features list."""
        with patch("src.api.billing.get_settings", return_value=_make_mock_settings()):
            result = await get_plans()

        for plan in result["plans"]:
            assert "features" in plan
            assert len(plan["features"]) > 0

    @pytest.mark.asyncio
    async def test_plans_have_name_and_price(self):
        """Each plan has a name and price string."""
        with patch("src.api.billing.get_settings", return_value=_make_mock_settings()):
            result = await get_plans()

        for plan in result["plans"]:
            assert "name" in plan
            assert "price" in plan
            assert plan["price"].startswith("$")


# ---------------------------------------------------------------------------
# POST /api/v1/billing/create-checkout
# ---------------------------------------------------------------------------


class TestCreateCheckout:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        """Invalid JSON body returns 400."""
        request = _make_mock_request()  # json() will raise
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await create_checkout(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "Invalid JSON" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_price_id_returns_400(self):
        """Missing price_id returns 400."""
        request = _make_mock_request(json_data={"price_id": ""})
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_checkout(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "price_id is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_price_id_returns_400(self):
        """Invalid price_id returns 400."""
        request = _make_mock_request(json_data={"price_id": "price_invalid_999"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_checkout(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "Invalid price_id" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_creates_stripe_customer_when_missing(self):
        """When client has no stripe_customer_id, creates one first."""
        request = _make_mock_request(json_data={"price_id": "price_pro_456"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id=None)

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch(
                "src.api.billing.billing_service.create_customer",
                new_callable=AsyncMock,
                return_value={"customer_id": "cus_new_123", "error": None},
            ) as mock_create,
            patch(
                "src.api.billing.billing_service.create_checkout_session",
                new_callable=AsyncMock,
                return_value={"session_url": "https://checkout.stripe.com/s", "session_id": "cs_1", "error": None},
            ),
        ):
            result = await create_checkout(request=request, db=mock_db, client=mock_client)

        mock_create.assert_awaited_once()
        assert result["url"] == "https://checkout.stripe.com/s"

    @pytest.mark.asyncio
    async def test_customer_creation_failure_returns_502(self):
        """Failure to create Stripe customer returns 502."""
        request = _make_mock_request(json_data={"price_id": "price_pro_456"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id=None)

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch(
                "src.api.billing.billing_service.create_customer",
                new_callable=AsyncMock,
                return_value={"customer_id": None, "error": "Stripe API error"},
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_checkout(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_successful_checkout_with_existing_customer(self):
        """Successful checkout session creation returns URL and session ID."""
        request = _make_mock_request(json_data={"price_id": "price_starter_123"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id="cus_existing_456")

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch(
                "src.api.billing.billing_service.create_checkout_session",
                new_callable=AsyncMock,
                return_value={
                    "session_url": "https://checkout.stripe.com/sess",
                    "session_id": "cs_test_789",
                    "error": None,
                },
            ),
        ):
            result = await create_checkout(request=request, db=mock_db, client=mock_client)

        assert result["url"] == "https://checkout.stripe.com/sess"
        assert result["session_id"] == "cs_test_789"

    @pytest.mark.asyncio
    async def test_checkout_session_failure_returns_502(self):
        """Failure to create checkout session returns 502."""
        request = _make_mock_request(json_data={"price_id": "price_pro_456"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id="cus_existing")

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch(
                "src.api.billing.billing_service.create_checkout_session",
                new_callable=AsyncMock,
                return_value={"session_url": None, "session_id": None, "error": "rate limited"},
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await create_checkout(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# POST /api/v1/billing/portal
# ---------------------------------------------------------------------------


class TestBillingPortal:
    @pytest.mark.asyncio
    async def test_no_stripe_customer_returns_400(self):
        """Client without Stripe customer ID gets 400."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id=None)

        with pytest.raises(HTTPException) as exc_info:
            await billing_portal(db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "No billing account" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_successful_portal_returns_url(self):
        """Successful billing portal creation returns URL."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id="cus_portal_123")

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch(
                "src.api.billing.billing_service.create_billing_portal_session",
                new_callable=AsyncMock,
                return_value={"portal_url": "https://billing.stripe.com/portal", "error": None},
            ),
        ):
            result = await billing_portal(db=mock_db, client=mock_client)

        assert result["url"] == "https://billing.stripe.com/portal"

    @pytest.mark.asyncio
    async def test_portal_failure_returns_502(self):
        """Failure to create billing portal returns 502."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(stripe_customer_id="cus_portal_123")

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch(
                "src.api.billing.billing_service.create_billing_portal_session",
                new_callable=AsyncMock,
                return_value={"portal_url": None, "error": "Stripe error"},
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await billing_portal(db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# GET /api/v1/billing/status
# ---------------------------------------------------------------------------


class TestBillingStatus:
    @pytest.mark.asyncio
    async def test_no_subscription(self):
        """Client without subscription returns plan='none'."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            stripe_subscription_id=None,
            tier="starter",
            billing_status="trial",
        )

        with patch("src.api.billing.get_plan_limits", return_value={"monthly_lead_limit": 200}):
            result = await billing_status(db=mock_db, client=mock_client)

        assert result["plan"] == "none"
        assert result["billing_status"] == "trial"
        assert result["tier"] == "starter"
        assert result["current_period_end"] is None

    @pytest.mark.asyncio
    async def test_with_active_subscription(self):
        """Client with active subscription returns plan details."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            stripe_subscription_id="sub_test_123",
            tier="pro",
            billing_status="active",
            stripe_customer_id="cus_test",
        )

        mock_sub = {
            "items": {"data": [{"price": {"id": "price_pro_456"}}]},
            "current_period_end": 1700000000,
        }

        # Mock the stripe module at the import site to handle lazy import
        mock_stripe_mod = MagicMock()
        mock_stripe_mod.Subscription.retrieve.return_value = mock_sub

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch.dict("sys.modules", {"stripe": mock_stripe_mod}),
            patch("src.api.billing.billing_service._price_id_to_plan", return_value="pro"),
            patch("src.api.billing.get_plan_limits", return_value={"monthly_lead_limit": 1000}),
        ):
            result = await billing_status(db=mock_db, client=mock_client)

        assert result["plan"] == "pro"
        assert result["billing_status"] == "active"
        assert result["current_period_end"] == 1700000000

    @pytest.mark.asyncio
    async def test_subscription_retrieval_failure_defaults_to_none(self):
        """If Stripe subscription retrieval fails, plan defaults to 'none'."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            stripe_subscription_id="sub_broken",
            tier="pro",
            billing_status="active",
        )

        # Mock stripe module with a failing retrieve
        mock_stripe_mod = MagicMock()
        mock_stripe_mod.Subscription.retrieve.side_effect = Exception("Stripe down")

        with (
            patch("src.api.billing.get_settings", return_value=_make_mock_settings()),
            patch.dict("sys.modules", {"stripe": mock_stripe_mod}),
            patch("src.api.billing.get_plan_limits", return_value={"monthly_lead_limit": 1000}),
        ):
            result = await billing_status(db=mock_db, client=mock_client)

        # Falls back to "none" when retrieval fails
        assert result["plan"] == "none"

    @pytest.mark.asyncio
    async def test_includes_plan_limits(self):
        """Billing status includes plan limits based on tier."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            stripe_subscription_id=None,
            tier="business",
        )

        expected_limits = {"monthly_lead_limit": None, "api_access": True}
        with patch("src.api.billing.get_plan_limits", return_value=expected_limits):
            result = await billing_status(db=mock_db, client=mock_client)

        assert result["plan_limits"] == expected_limits

    @pytest.mark.asyncio
    async def test_trial_ends_at_included(self):
        """Billing status includes trial_ends_at when present."""
        from datetime import datetime, timezone
        trial_end = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            stripe_subscription_id=None,
            trial_ends_at=trial_end,
        )

        with patch("src.api.billing.get_plan_limits", return_value={}):
            result = await billing_status(db=mock_db, client=mock_client)

        assert result["trial_ends_at"] == trial_end.isoformat()


# ---------------------------------------------------------------------------
# GET /api/v1/billing/plan-limits
# ---------------------------------------------------------------------------


class TestPlanLimits:
    @pytest.mark.asyncio
    async def test_returns_tier_and_limits(self):
        """Plan limits endpoint returns tier and limit details."""
        mock_client = _make_mock_client(tier="pro")
        expected_limits = {
            "monthly_lead_limit": 1000,
            "crm_integration_limit": None,
            "cold_followup_enabled": True,
        }

        with patch("src.api.billing.get_plan_limits", return_value=expected_limits):
            result = await plan_limits(client=mock_client)

        assert result["tier"] == "pro"
        assert result["plan_limits"] == expected_limits

    @pytest.mark.asyncio
    async def test_starter_tier_limits(self):
        """Starter tier returns appropriate limits."""
        mock_client = _make_mock_client(tier="starter")
        starter_limits = {
            "monthly_lead_limit": 200,
            "crm_integration_limit": 1,
            "cold_followup_enabled": False,
        }

        with patch("src.api.billing.get_plan_limits", return_value=starter_limits):
            result = await plan_limits(client=mock_client)

        assert result["tier"] == "starter"
        assert result["plan_limits"]["monthly_lead_limit"] == 200


# ---------------------------------------------------------------------------
# POST /api/v1/billing/webhook
# ---------------------------------------------------------------------------


class TestStripeWebhook:
    @pytest.mark.asyncio
    async def test_missing_signature_returns_400(self):
        """Missing stripe-signature header returns 400."""
        request = _make_mock_request(body=b"payload", headers={})

        with pytest.raises(HTTPException) as exc_info:
            await stripe_webhook(request=request)

        assert exc_info.value.status_code == 400
        assert "Missing stripe-signature" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_400(self):
        """Invalid signature returns 400."""
        request = _make_mock_request(
            body=b"payload",
            headers={"stripe-signature": "bad_sig"},
        )

        with patch(
            "src.api.billing.billing_service.handle_webhook",
            new_callable=AsyncMock,
            return_value={"error": "Invalid signature", "event_type": None, "handled": False},
        ):
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(request=request)

        assert exc_info.value.status_code == 400
        assert "Invalid webhook signature" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_successful_webhook_returns_event_type(self):
        """Successfully processed webhook returns event type."""
        request = _make_mock_request(
            body=b"payload",
            headers={"stripe-signature": "valid_sig"},
        )

        with patch(
            "src.api.billing.billing_service.handle_webhook",
            new_callable=AsyncMock,
            return_value={
                "error": None,
                "event_type": "checkout.session.completed",
                "handled": True,
            },
        ):
            result = await stripe_webhook(request=request)

        assert result["received"] is True
        assert result["event_type"] == "checkout.session.completed"

    @pytest.mark.asyncio
    async def test_processing_error_returns_200_with_error(self):
        """Processing error returns 200 (to prevent Stripe retries) with error."""
        request = _make_mock_request(
            body=b"payload",
            headers={"stripe-signature": "valid_sig"},
        )

        with patch(
            "src.api.billing.billing_service.handle_webhook",
            new_callable=AsyncMock,
            return_value={
                "error": "DB write failed",
                "event_type": None,
                "handled": False,
            },
        ):
            result = await stripe_webhook(request=request)

        # Returns 200 to prevent Stripe retries
        assert result["received"] is True
        assert result["error"] == "DB write failed"
