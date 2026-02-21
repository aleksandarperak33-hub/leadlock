"""
Tests for src/api/admin_dashboard.py - admin overview, client CRUD, lead listing,
revenue, health, and outreach pipeline endpoints.
All database calls are mocked to avoid SQLite/JSONB incompatibility.
"""
import uuid
from datetime import datetime, timezone, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch
from collections import namedtuple

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_MOCK = MagicMock()


def _mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


def _scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _make_client(
    business_name="Acme HVAC",
    trade_type="hvac",
    tier="starter",
    **overrides,
):
    """Build a mock Client object."""
    c = MagicMock()
    c.id = overrides.get("id", uuid.uuid4())
    c.business_name = business_name
    c.trade_type = trade_type
    c.tier = tier
    c.monthly_fee = overrides.get("monthly_fee", 497.00)
    c.billing_status = overrides.get("billing_status", "trial")
    c.onboarding_status = overrides.get("onboarding_status", "pending")
    c.is_active = overrides.get("is_active", True)
    c.is_admin = overrides.get("is_admin", False)
    c.ten_dlc_status = overrides.get("ten_dlc_status", "pending")
    c.crm_type = overrides.get("crm_type", "google_sheets")
    c.config = overrides.get("config", {})
    c.owner_name = overrides.get("owner_name", "John Doe")
    c.owner_email = overrides.get("owner_email", "john@acme.com")
    c.owner_phone = overrides.get("owner_phone", "+15125551234")
    c.twilio_phone = overrides.get("twilio_phone", None)
    c.dashboard_email = overrides.get("dashboard_email", None)
    c.dashboard_password_hash = overrides.get("dashboard_password_hash", None)
    c.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    c.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return c


def _make_lead(client_id, **overrides):
    """Build a mock Lead object."""
    l = MagicMock()
    l.id = overrides.get("id", uuid.uuid4())
    l.client_id = client_id
    l.phone = overrides.get("phone", "+15125559876")
    l.first_name = overrides.get("first_name", "Jane")
    l.last_name = overrides.get("last_name", "Smith")
    l.source = overrides.get("source", "website")
    l.state = overrides.get("state", "new")
    l.score = overrides.get("score", 50)
    l.service_type = overrides.get("service_type", "AC Repair")
    l.urgency = overrides.get("urgency", "today")
    l.first_response_ms = overrides.get("first_response_ms", 3500)
    l.total_messages_sent = overrides.get("total_messages_sent", 2)
    l.total_messages_received = overrides.get("total_messages_received", 1)
    l.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return l


def _make_outreach(name="Prospect One", **overrides):
    """Build a mock Outreach object."""
    o = MagicMock()
    o.id = overrides.get("id", uuid.uuid4())
    o.prospect_name = name
    o.prospect_company = overrides.get("prospect_company", "Cool Plumbing")
    o.prospect_email = overrides.get("prospect_email", "prospect@example.com")
    o.prospect_phone = overrides.get("prospect_phone", "+15125559999")
    o.prospect_trade_type = overrides.get("prospect_trade_type", "plumbing")
    o.status = overrides.get("status", "cold")
    o.notes = overrides.get("notes", None)
    o.estimated_mrr = overrides.get("estimated_mrr", 497.0)
    o.campaign_id = overrides.get("campaign_id", None)
    o.converted_client_id = overrides.get("converted_client_id", None)
    o.demo_date = overrides.get("demo_date", None)
    o.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    o.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return o


def _make_event_log(status="error", action="sms_send", **overrides):
    """Build a mock EventLog object."""
    e = MagicMock()
    e.id = overrides.get("id", uuid.uuid4())
    e.action = action
    e.status = status
    e.message = overrides.get("message", "Something went wrong")
    e.lead_id = overrides.get("lead_id", None)
    e.client_id = overrides.get("client_id", None)
    e.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return e


# ---------------------------------------------------------------------------
# GET /admin/overview
# ---------------------------------------------------------------------------


class TestAdminOverview:
    """Tests for the admin_overview endpoint."""

    @patch("src.api.admin_dashboard.get_system_overview", new_callable=AsyncMock)
    async def test_returns_system_overview(self, mock_overview):
        from src.api.admin_dashboard import admin_overview

        db = _mock_db()
        mock_overview.return_value = {
            "active_clients": 5,
            "total_leads_30d": 120,
            "avg_response_ms": 4200,
        }

        result = await admin_overview(db=db, admin=ADMIN_MOCK)

        mock_overview.assert_called_once_with(db)
        assert result["active_clients"] == 5
        assert result["total_leads_30d"] == 120

    @patch("src.api.admin_dashboard.get_system_overview", new_callable=AsyncMock)
    async def test_delegates_to_service(self, mock_overview):
        from src.api.admin_dashboard import admin_overview

        db = _mock_db()
        mock_overview.return_value = {}

        await admin_overview(db=db, admin=ADMIN_MOCK)
        mock_overview.assert_called_once()


# ---------------------------------------------------------------------------
# GET /admin/clients
# ---------------------------------------------------------------------------


class TestAdminClients:
    """Tests for the admin_clients endpoint."""

    @patch("src.api.admin_dashboard.get_client_list_with_metrics", new_callable=AsyncMock)
    async def test_returns_client_list(self, mock_clients):
        from src.api.admin_dashboard import admin_clients

        db = _mock_db()
        mock_clients.return_value = {
            "clients": [{"id": "abc", "business_name": "Test"}],
            "total": 1,
            "page": 1,
            "pages": 1,
        }

        result = await admin_clients(page=1, per_page=20, db=db, admin=ADMIN_MOCK)

        mock_clients.assert_called_once_with(
            db,
            search=None,
            tier=None,
            billing_status=None,
            page=1,
            per_page=20,
        )
        assert result["total"] == 1

    @patch("src.api.admin_dashboard.get_client_list_with_metrics", new_callable=AsyncMock)
    async def test_passes_filters(self, mock_clients):
        from src.api.admin_dashboard import admin_clients

        db = _mock_db()
        mock_clients.return_value = {"clients": [], "total": 0, "page": 2, "pages": 1}

        await admin_clients(
            search="acme",
            tier="pro",
            billing_status="active",
            page=2,
            per_page=10,
            db=db,
            admin=ADMIN_MOCK,
        )

        mock_clients.assert_called_once_with(
            db,
            search="acme",
            tier="pro",
            billing_status="active",
            page=2,
            per_page=10,
        )


# ---------------------------------------------------------------------------
# POST /admin/clients
# ---------------------------------------------------------------------------


class TestCreateClient:
    """Tests for the create_client endpoint."""

    async def test_missing_business_name_returns_400(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await create_client(
                payload={"trade_type": "hvac"},
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400
        assert "business_name" in exc.value.detail

    async def test_empty_business_name_returns_400(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await create_client(
                payload={"business_name": "  ", "trade_type": "hvac"},
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400

    async def test_missing_trade_type_returns_400(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await create_client(
                payload={"business_name": "Test HVAC"},
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400
        assert "trade_type" in exc.value.detail

    async def test_empty_trade_type_returns_400(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await create_client(
                payload={"business_name": "Test", "trade_type": "  "},
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400

    async def test_invalid_tier_returns_400(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await create_client(
                payload={
                    "business_name": "Test",
                    "trade_type": "hvac",
                    "tier": "enterprise",
                },
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400
        assert "tier" in exc.value.detail

    async def test_successful_creation(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        # After commit+refresh, the client will have an id
        created_id = uuid.uuid4()

        async def fake_refresh(obj):
            obj.id = created_id
            obj.business_name = obj.business_name

        db.refresh.side_effect = fake_refresh

        result = await create_client(
            payload={
                "business_name": "Cool HVAC",
                "trade_type": "hvac",
            },
            db=db,
            admin=ADMIN_MOCK,
        )

        assert result["id"] == str(created_id)
        assert result["business_name"] == "Cool HVAC"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    async def test_default_values_applied(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        created_id = uuid.uuid4()

        captured_client = {}

        def capture_add(obj):
            captured_client["obj"] = obj

        db.add.side_effect = capture_add

        async def fake_refresh(obj):
            obj.id = created_id

        db.refresh.side_effect = fake_refresh

        await create_client(
            payload={
                "business_name": "Default Test",
                "trade_type": "plumbing",
            },
            db=db,
            admin=ADMIN_MOCK,
        )

        client = captured_client["obj"]
        assert client.tier == "starter"
        assert client.monthly_fee == 497.00
        assert client.crm_type == "google_sheets"
        assert client.billing_status == "trial"

    @patch("bcrypt.hashpw", return_value=b"$2b$12$hashed")
    @patch("bcrypt.gensalt", return_value=b"$2b$12$salt")
    async def test_password_hashed(self, _salt, _hash):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        created_id = uuid.uuid4()
        captured_client = {}

        def capture_add(obj):
            captured_client["obj"] = obj

        db.add.side_effect = capture_add

        async def fake_refresh(obj):
            obj.id = created_id

        db.refresh.side_effect = fake_refresh

        await create_client(
            payload={
                "business_name": "Pwd Test",
                "trade_type": "hvac",
                "dashboard_password": "secret",
            },
            db=db,
            admin=ADMIN_MOCK,
        )

        client = captured_client["obj"]
        assert client.dashboard_password_hash == "$2b$12$hashed"

    async def test_all_fields_passed(self):
        from src.api.admin_dashboard import create_client

        db = _mock_db()
        created_id = uuid.uuid4()
        captured_client = {}

        def capture_add(obj):
            captured_client["obj"] = obj

        db.add.side_effect = capture_add

        async def fake_refresh(obj):
            obj.id = created_id

        db.refresh.side_effect = fake_refresh

        await create_client(
            payload={
                "business_name": "Premium",
                "trade_type": "plumbing",
                "tier": "pro",
                "monthly_fee": 1500.00,
                "twilio_phone": "+15125550001",
                "crm_type": "servicetitan",
                "owner_name": "Bob",
                "owner_email": "bob@premium.com",
                "owner_phone": "+15125550002",
                "dashboard_email": "bob@premium.com",
                "billing_status": "active",
                "config": {"custom": True},
            },
            db=db,
            admin=ADMIN_MOCK,
        )

        client = captured_client["obj"]
        assert client.tier == "pro"
        assert client.monthly_fee == 1500.00
        assert client.crm_type == "servicetitan"
        assert client.billing_status == "active"
        assert client.owner_name == "Bob"


# ---------------------------------------------------------------------------
# GET /admin/clients/{client_id}
# ---------------------------------------------------------------------------


class TestAdminClientDetail:
    """Tests for the admin_client_detail endpoint."""

    async def test_invalid_client_id(self):
        from src.api.admin_dashboard import admin_client_detail

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await admin_client_detail("not-a-uuid", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400
        assert "Invalid client ID" in exc.value.detail

    async def test_missing_client(self):
        from src.api.admin_dashboard import admin_client_detail

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await admin_client_detail(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    @patch("src.services.reporting.get_dashboard_metrics", new_callable=AsyncMock)
    async def test_success_with_leads(self, mock_metrics):
        from src.api.admin_dashboard import admin_client_detail

        db = _mock_db()
        client = _make_client(
            business_name="Detail Client",
            trade_type="plumbing",
            tier="pro",
            owner_name="Alice",
        )
        db.get.return_value = client

        mock_metric_obj = MagicMock()
        mock_metric_obj.model_dump.return_value = {
            "total_leads": 10,
            "avg_response_ms": 5000,
        }
        mock_metrics.return_value = mock_metric_obj

        lead = _make_lead(client.id, first_name="Bob", last_name="Builder", phone="+15125551111")
        db.execute.return_value = _scalars_result([lead])

        result = await admin_client_detail(str(client.id), db=db, admin=ADMIN_MOCK)

        assert result["client"]["business_name"] == "Detail Client"
        assert result["client"]["trade_type"] == "plumbing"
        assert result["client"]["tier"] == "pro"
        assert result["client"]["owner_name"] == "Alice"
        assert result["metrics"]["total_leads"] == 10
        assert len(result["recent_leads"]) == 1
        assert result["recent_leads"][0]["first_name"] == "Bob"
        assert "***" in result["recent_leads"][0]["phone_masked"]

    @patch("src.services.reporting.get_dashboard_metrics", new_callable=AsyncMock)
    async def test_no_leads_returns_empty(self, mock_metrics):
        from src.api.admin_dashboard import admin_client_detail

        db = _mock_db()
        client = _make_client()
        db.get.return_value = client
        mock_metrics.return_value = None

        db.execute.return_value = _scalars_result([])

        result = await admin_client_detail(str(client.id), db=db, admin=ADMIN_MOCK)
        assert result["recent_leads"] == []
        assert result["metrics"] == {}

    @patch("src.services.reporting.get_dashboard_metrics", new_callable=AsyncMock)
    async def test_client_fields_serialized(self, mock_metrics):
        from src.api.admin_dashboard import admin_client_detail

        db = _mock_db()
        client = _make_client(
            business_name="Full Client",
            ten_dlc_status="approved",
        )
        db.get.return_value = client
        mock_metrics.return_value = None

        db.execute.return_value = _scalars_result([])

        result = await admin_client_detail(str(client.id), db=db, admin=ADMIN_MOCK)
        c = result["client"]
        assert c["id"] == str(client.id)
        assert c["ten_dlc_status"] == "approved"
        assert c["crm_type"] == "google_sheets"
        assert c["created_at"] is not None

    @patch("src.services.reporting.get_dashboard_metrics", new_callable=AsyncMock)
    async def test_lead_phone_empty(self, mock_metrics):
        from src.api.admin_dashboard import admin_client_detail

        db = _mock_db()
        client = _make_client()
        db.get.return_value = client
        mock_metrics.return_value = None

        lead = _make_lead(client.id, phone="")
        db.execute.return_value = _scalars_result([lead])

        result = await admin_client_detail(str(client.id), db=db, admin=ADMIN_MOCK)
        assert result["recent_leads"][0]["phone_masked"] == ""


# ---------------------------------------------------------------------------
# GET /admin/leads
# ---------------------------------------------------------------------------


class TestAdminLeads:
    """Tests for the admin_leads endpoint."""

    async def test_empty_results(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        db.execute.side_effect = [
            _scalar_result(0),       # count
            _scalars_result([]),     # leads
        ]

        result = await admin_leads(page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["leads"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["pages"] == 1

    async def test_returns_leads_with_client_names(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        cid = uuid.uuid4()
        lead = _make_lead(cid, first_name="Lead1")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(cid, "HVAC Pro")]),  # client name lookup
        ]

        result = await admin_leads(page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 1
        assert result["leads"][0]["client_name"] == "HVAC Pro"
        assert result["leads"][0]["first_name"] == "Lead1"

    async def test_invalid_client_id_filter(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await admin_leads(client_id="bad-uuid", page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_state_filter(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4(), state="qualifying")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(lead.client_id, "Test")]),
        ]

        result = await admin_leads(state="qualifying", page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 1

    async def test_source_filter(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4(), source="google_lsa")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(lead.client_id, "Test")]),
        ]

        result = await admin_leads(source="google_lsa", page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 1

    async def test_client_id_filter(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        cid = uuid.uuid4()
        lead = _make_lead(cid)

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(cid, "Test")]),
        ]

        result = await admin_leads(client_id=str(cid), page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 1

    async def test_search_filter(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4(), first_name="Alice")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(lead.client_id, "Test")]),
        ]

        result = await admin_leads(search="Alice", page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 1

    async def test_pagination(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        leads = [_make_lead(uuid.uuid4()) for _ in range(2)]

        db.execute.side_effect = [
            _scalar_result(5),
            _scalars_result(leads),
            _rows_result([(leads[0].client_id, "A"), (leads[1].client_id, "B")]),
        ]

        result = await admin_leads(page=2, per_page=2, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 5
        assert result["page"] == 2
        assert result["pages"] == 3
        assert len(result["leads"]) == 2

    async def test_phone_masking(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4(), phone="+15125559876")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(lead.client_id, "Test")]),
        ]

        result = await admin_leads(page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["leads"][0]["phone_masked"] == "+15125***"

    async def test_empty_phone(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4(), phone="")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(lead.client_id, "Test")]),
        ]

        result = await admin_leads(page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["leads"][0]["phone_masked"] == ""

    async def test_total_messages(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4(), total_messages_sent=5, total_messages_received=3)

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([(lead.client_id, "Test")]),
        ]

        result = await admin_leads(page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["leads"][0]["total_messages"] == 8

    async def test_no_client_name_shows_unknown(self):
        from src.api.admin_dashboard import admin_leads

        db = _mock_db()
        lead = _make_lead(uuid.uuid4())

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([lead]),
            _rows_result([]),  # no matching client names
        ]

        result = await admin_leads(page=1, per_page=20, db=db, admin=ADMIN_MOCK)
        assert result["leads"][0]["client_name"] == "Unknown"


# ---------------------------------------------------------------------------
# GET /admin/revenue
# ---------------------------------------------------------------------------


class TestAdminRevenue:
    """Tests for the admin_revenue endpoint."""

    @patch("src.api.admin_dashboard.get_revenue_breakdown", new_callable=AsyncMock)
    async def test_returns_revenue_data(self, mock_rev):
        from src.api.admin_dashboard import admin_revenue

        db = _mock_db()
        mock_rev.return_value = {
            "mrr_total": 12000,
            "by_tier": {"starter": 5000, "pro": 7000},
        }

        result = await admin_revenue(period="30d", db=db, admin=ADMIN_MOCK)

        mock_rev.assert_called_once_with(db, "30d")
        assert result["mrr_total"] == 12000

    @patch("src.api.admin_dashboard.get_revenue_breakdown", new_callable=AsyncMock)
    async def test_passes_7d_period(self, mock_rev):
        from src.api.admin_dashboard import admin_revenue

        db = _mock_db()
        mock_rev.return_value = {}

        await admin_revenue(period="7d", db=db, admin=ADMIN_MOCK)
        mock_rev.assert_called_once_with(db, "7d")

    @patch("src.api.admin_dashboard.get_revenue_breakdown", new_callable=AsyncMock)
    async def test_passes_90d_period(self, mock_rev):
        from src.api.admin_dashboard import admin_revenue

        db = _mock_db()
        mock_rev.return_value = {}

        await admin_revenue(period="90d", db=db, admin=ADMIN_MOCK)
        mock_rev.assert_called_once_with(db, "90d")


# ---------------------------------------------------------------------------
# GET /admin/health
# ---------------------------------------------------------------------------


class TestAdminHealth:
    """Tests for the admin_health endpoint."""

    async def test_empty_health(self):
        from src.api.admin_dashboard import admin_health

        db = _mock_db()
        db.execute.side_effect = [
            _scalars_result([]),  # errors
            _scalars_result([]),  # pending clients
        ]

        result = await admin_health(db=db, admin=ADMIN_MOCK)

        assert result["recent_errors"] == []
        assert result["error_count_24h"] == 0
        assert result["pending_integrations"] == []

    async def test_recent_errors(self):
        from src.api.admin_dashboard import admin_health

        db = _mock_db()
        error = _make_event_log(
            status="error",
            action="sms_send",
            message="Twilio timeout",
        )
        db.execute.side_effect = [
            _scalars_result([error]),
            _scalars_result([]),
        ]

        result = await admin_health(db=db, admin=ADMIN_MOCK)
        assert result["error_count_24h"] == 1
        assert result["recent_errors"][0]["action"] == "sms_send"
        assert result["recent_errors"][0]["message"] == "Twilio timeout"

    async def test_pending_integrations(self):
        from src.api.admin_dashboard import admin_health

        db = _mock_db()
        client = _make_client(
            business_name="Pending Co",
            ten_dlc_status="pending",
            onboarding_status="in_progress",
        )
        db.execute.side_effect = [
            _scalars_result([]),
            _scalars_result([client]),
        ]

        result = await admin_health(db=db, admin=ADMIN_MOCK)
        assert len(result["pending_integrations"]) == 1
        assert result["pending_integrations"][0]["business_name"] == "Pending Co"
        assert result["pending_integrations"][0]["ten_dlc_status"] == "pending"
        assert result["pending_integrations"][0]["onboarding_status"] == "in_progress"

    async def test_error_with_lead_and_client_ids(self):
        from src.api.admin_dashboard import admin_health

        db = _mock_db()
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        error = _make_event_log(
            status="error",
            action="crm_sync",
            message="CRM error",
            lead_id=lead_id,
            client_id=client_id,
        )
        db.execute.side_effect = [
            _scalars_result([error]),
            _scalars_result([]),
        ]

        result = await admin_health(db=db, admin=ADMIN_MOCK)
        e = result["recent_errors"][0]
        assert e["lead_id"] == str(lead_id)
        assert e["client_id"] == str(client_id)

    async def test_error_without_lead_id(self):
        from src.api.admin_dashboard import admin_health

        db = _mock_db()
        error = _make_event_log(lead_id=None, client_id=None)
        db.execute.side_effect = [
            _scalars_result([error]),
            _scalars_result([]),
        ]

        result = await admin_health(db=db, admin=ADMIN_MOCK)
        assert result["recent_errors"][0]["lead_id"] is None
        assert result["recent_errors"][0]["client_id"] is None


# ---------------------------------------------------------------------------
# GET /admin/outreach
# ---------------------------------------------------------------------------


class TestAdminOutreach:
    """Tests for the admin_outreach endpoint."""

    async def test_empty_outreach(self):
        from src.api.admin_dashboard import admin_outreach

        db = _mock_db()
        db.execute.side_effect = [
            _scalar_result(0),
            _scalars_result([]),
        ]

        result = await admin_outreach(page=1, per_page=50, db=db, admin=ADMIN_MOCK)
        assert result["prospects"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["pages"] == 1

    async def test_returns_prospects(self):
        from src.api.admin_dashboard import admin_outreach

        db = _mock_db()
        p1 = _make_outreach(name="Lead One", status="cold")
        p2 = _make_outreach(name="Lead Two", status="contacted")

        db.execute.side_effect = [
            _scalar_result(2),
            _scalars_result([p1, p2]),
        ]

        result = await admin_outreach(page=1, per_page=50, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 2
        assert len(result["prospects"]) == 2

    async def test_status_filter(self):
        from src.api.admin_dashboard import admin_outreach

        db = _mock_db()
        p = _make_outreach(name="Cold", status="cold")

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([p]),
        ]

        result = await admin_outreach(status="cold", page=1, per_page=50, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 1
        assert result["prospects"][0]["status"] == "cold"

    async def test_pagination(self):
        from src.api.admin_dashboard import admin_outreach

        db = _mock_db()
        prospects = [_make_outreach(name=f"P{i}") for i in range(3)]

        db.execute.side_effect = [
            _scalar_result(7),
            _scalars_result(prospects),
        ]

        result = await admin_outreach(page=2, per_page=3, db=db, admin=ADMIN_MOCK)
        assert result["total"] == 7
        assert result["page"] == 2
        assert result["pages"] == 3

    async def test_prospect_serialization(self):
        from src.api.admin_dashboard import admin_outreach

        db = _mock_db()
        p = _make_outreach(
            name="Full Data",
            prospect_company="Full Co",
            prospect_email="full@co.com",
            status="demo_scheduled",
            estimated_mrr=1500.0,
            demo_date=date(2026, 3, 15),
            notes="Great prospect",
        )

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([p]),
        ]

        result = await admin_outreach(page=1, per_page=50, db=db, admin=ADMIN_MOCK)
        prospect = result["prospects"][0]
        assert prospect["prospect_name"] == "Full Data"
        assert prospect["prospect_company"] == "Full Co"
        assert prospect["status"] == "demo_scheduled"
        assert prospect["estimated_mrr"] == 1500.0
        assert prospect["demo_date"] == "2026-03-15"
        assert prospect["notes"] == "Great prospect"

    async def test_prospect_without_demo_date(self):
        from src.api.admin_dashboard import admin_outreach

        db = _mock_db()
        p = _make_outreach(name="No Demo", demo_date=None)

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([p]),
        ]

        result = await admin_outreach(page=1, per_page=50, db=db, admin=ADMIN_MOCK)
        assert result["prospects"][0]["demo_date"] is None


# ---------------------------------------------------------------------------
# POST /admin/outreach
# ---------------------------------------------------------------------------


class TestCreateOutreach:
    """Tests for the create_outreach endpoint."""

    async def test_minimal_creation(self):
        from src.api.admin_dashboard import create_outreach

        db = _mock_db()
        captured = {}

        def capture_add(obj):
            captured["obj"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        result = await create_outreach(
            payload={"prospect_name": "New Prospect"},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert result["status"] == "created"
        assert "id" in result
        db.flush.assert_called_once()

    async def test_creation_with_demo_date(self):
        from src.api.admin_dashboard import create_outreach

        db = _mock_db()
        captured = {}

        def capture_add(obj):
            captured["obj"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        result = await create_outreach(
            payload={
                "prospect_name": "With Demo",
                "demo_date": "2026-04-01",
            },
            db=db,
            admin=ADMIN_MOCK,
        )

        assert result["status"] == "created"
        obj = captured["obj"]
        assert obj.demo_date == date(2026, 4, 1)

    async def test_creation_without_demo_date(self):
        from src.api.admin_dashboard import create_outreach

        db = _mock_db()
        captured = {}

        def capture_add(obj):
            captured["obj"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        await create_outreach(
            payload={"prospect_name": "No Demo"},
            db=db,
            admin=ADMIN_MOCK,
        )

        obj = captured["obj"]
        assert obj.demo_date is None

    async def test_default_status_is_cold(self):
        from src.api.admin_dashboard import create_outreach

        db = _mock_db()
        captured = {}

        def capture_add(obj):
            captured["obj"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        await create_outreach(
            payload={"prospect_name": "Default"},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert captured["obj"].status == "cold"

    async def test_custom_status(self):
        from src.api.admin_dashboard import create_outreach

        db = _mock_db()
        captured = {}

        def capture_add(obj):
            captured["obj"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        await create_outreach(
            payload={"prospect_name": "Custom", "status": "contacted"},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert captured["obj"].status == "contacted"


# ---------------------------------------------------------------------------
# PUT /admin/outreach/{prospect_id}
# ---------------------------------------------------------------------------


class TestUpdateOutreach:
    """Tests for the update_outreach endpoint."""

    async def test_invalid_prospect_id(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await update_outreach("bad-uuid", payload={}, db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_prospect(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await update_outreach(str(uuid.uuid4()), payload={}, db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_update_fields(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Original", status="cold")
        db.get.return_value = prospect

        result = await update_outreach(
            str(prospect.id),
            payload={
                "prospect_name": "Updated Name",
                "status": "contacted",
                "notes": "Called them",
                "estimated_mrr": 999.0,
            },
            db=db,
            admin=ADMIN_MOCK,
        )

        assert result["status"] == "updated"
        db.flush.assert_called_once()

    async def test_update_demo_date(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Demo")
        db.get.return_value = prospect

        await update_outreach(
            str(prospect.id),
            payload={"demo_date": "2026-05-01"},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert prospect.demo_date == date(2026, 5, 1)

    async def test_clear_demo_date(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Clear Demo", demo_date=date(2026, 3, 1))
        db.get.return_value = prospect

        await update_outreach(
            str(prospect.id),
            payload={"demo_date": None},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert prospect.demo_date is None

    async def test_update_converted_client_id(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Convert Link")
        db.get.return_value = prospect

        new_cid = uuid.uuid4()
        await update_outreach(
            str(prospect.id),
            payload={"converted_client_id": str(new_cid)},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert prospect.converted_client_id == new_cid

    async def test_clear_converted_client_id(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Unlink", converted_client_id=uuid.uuid4())
        db.get.return_value = prospect

        await update_outreach(
            str(prospect.id),
            payload={"converted_client_id": None},
            db=db,
            admin=ADMIN_MOCK,
        )

        assert prospect.converted_client_id is None

    async def test_invalid_converted_client_id(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Bad Link")
        db.get.return_value = prospect

        with pytest.raises(HTTPException) as exc:
            await update_outreach(
                str(prospect.id),
                payload={"converted_client_id": "not-uuid"},
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400
        assert "converted_client_id" in exc.value.detail

    async def test_updated_at_set(self):
        from src.api.admin_dashboard import update_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Timestamp")
        old_updated = prospect.updated_at
        db.get.return_value = prospect

        await update_outreach(
            str(prospect.id),
            payload={"status": "contacted"},
            db=db,
            admin=ADMIN_MOCK,
        )

        # updated_at should be modified (set to a new datetime)
        assert prospect.updated_at is not None


# ---------------------------------------------------------------------------
# DELETE /admin/outreach/{prospect_id}
# ---------------------------------------------------------------------------


class TestDeleteOutreach:
    """Tests for the delete_outreach endpoint."""

    async def test_invalid_prospect_id(self):
        from src.api.admin_dashboard import delete_outreach

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await delete_outreach("bad", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_prospect(self):
        from src.api.admin_dashboard import delete_outreach

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await delete_outreach(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_successful_deletion(self):
        from src.api.admin_dashboard import delete_outreach

        db = _mock_db()
        prospect = _make_outreach(name="Delete Me")
        db.get.return_value = prospect

        result = await delete_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)
        assert result["status"] == "deleted"
        db.delete.assert_called_once_with(prospect)
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# POST /admin/outreach/{prospect_id}/convert
# ---------------------------------------------------------------------------


class TestConvertOutreach:
    """Tests for the convert_outreach endpoint."""

    async def test_invalid_prospect_id(self):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await convert_outreach("bad", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_prospect(self):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await convert_outreach(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_already_converted(self):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        prospect = _make_outreach(
            name="Already Won",
            converted_client_id=uuid.uuid4(),
        )
        db.get.return_value = prospect

        with pytest.raises(HTTPException) as exc:
            await convert_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400
        assert "already converted" in exc.value.detail

    @patch("bcrypt.hashpw", return_value=b"$2b$12$hashed")
    @patch("bcrypt.gensalt", return_value=b"$2b$12$salt")
    async def test_successful_conversion_with_email(self, _salt, _hash):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        prospect = _make_outreach(
            name="Convert Lead",
            prospect_company="Convert Co",
            prospect_email="convert@co.com",
            prospect_phone="+15125550003",
            prospect_trade_type="roofing",
            estimated_mrr=1500.0,
            converted_client_id=None,
        )
        db.get.return_value = prospect

        captured = {}

        def capture_add(obj):
            captured["client"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        result = await convert_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)

        assert result["status"] == "converted"
        assert "client_id" in result
        assert result["business_name"] == "Convert Co"
        assert "temp_password" in result

        # Verify prospect was updated
        assert prospect.status == "won"
        assert prospect.converted_client_id is not None

        # Verify client was created with correct data
        client = captured["client"]
        assert client.business_name == "Convert Co"
        assert client.trade_type == "roofing"
        assert client.monthly_fee == 1500.0
        assert client.tier == "starter"
        assert client.billing_status == "trial"
        assert client.onboarding_status == "pending"

    @patch("bcrypt.hashpw", return_value=b"$2b$12$hashed")
    @patch("bcrypt.gensalt", return_value=b"$2b$12$salt")
    async def test_conversion_without_email_no_temp_password(self, _salt, _hash):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        prospect = _make_outreach(
            name="No Email Lead",
            prospect_company="No Email Co",
            prospect_email=None,
            converted_client_id=None,
        )
        db.get.return_value = prospect

        def capture_add(obj):
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        result = await convert_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)

        assert result["status"] == "converted"
        assert "temp_password" not in result

    @patch("bcrypt.hashpw", return_value=b"$2b$12$hashed")
    @patch("bcrypt.gensalt", return_value=b"$2b$12$salt")
    async def test_uses_name_when_no_company(self, _salt, _hash):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        prospect = _make_outreach(
            name="Solo Person",
            prospect_company=None,
            prospect_email="solo@test.com",
            converted_client_id=None,
        )
        db.get.return_value = prospect

        captured = {}

        def capture_add(obj):
            captured["client"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        result = await convert_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)
        assert result["business_name"] == "Solo Person"

    @patch("bcrypt.hashpw", return_value=b"$2b$12$hashed")
    @patch("bcrypt.gensalt", return_value=b"$2b$12$salt")
    async def test_defaults_trade_type_to_general(self, _salt, _hash):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        prospect = _make_outreach(
            name="No Trade",
            prospect_trade_type=None,
            prospect_email="gen@test.com",
            converted_client_id=None,
        )
        db.get.return_value = prospect

        captured = {}

        def capture_add(obj):
            captured["client"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        await convert_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)
        assert captured["client"].trade_type == "general"

    @patch("bcrypt.hashpw", return_value=b"$2b$12$hashed")
    @patch("bcrypt.gensalt", return_value=b"$2b$12$salt")
    async def test_defaults_mrr_to_497(self, _salt, _hash):
        from src.api.admin_dashboard import convert_outreach

        db = _mock_db()
        prospect = _make_outreach(
            name="Default MRR",
            estimated_mrr=None,
            prospect_email="mrr@test.com",
            converted_client_id=None,
        )
        db.get.return_value = prospect

        captured = {}

        def capture_add(obj):
            captured["client"] = obj
            obj.id = uuid.uuid4()

        db.add.side_effect = capture_add

        await convert_outreach(str(prospect.id), db=db, admin=ADMIN_MOCK)
        assert captured["client"].monthly_fee == 497.00
