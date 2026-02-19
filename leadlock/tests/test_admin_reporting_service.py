"""
Tests for src/services/admin_reporting.py — system-wide admin dashboard metrics.

Uses the shared db fixture (SQLite in-memory) with real model inserts.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.models.client import Client
from src.models.lead import Lead
from src.services.admin_reporting import (
    get_system_overview,
    get_client_list_with_metrics,
    get_revenue_breakdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(db_session, **kwargs):
    """Create a Client record with minimal required fields."""
    defaults = {
        "id": uuid.uuid4(),
        "business_name": "Test HVAC",
        "trade_type": "hvac",
        "tier": "starter",
        "monthly_fee": 497.0,
        "config": {},
        "is_admin": False,
        "is_active": True,
        "billing_status": "active",
        "onboarding_status": "live",
        "owner_name": "John Doe",
        "owner_email": f"john+{uuid.uuid4().hex[:6]}@example.com",
        "twilio_phone": None,
        "crm_type": "google_sheets",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    client = Client(**defaults)
    db_session.add(client)
    return client


def _make_lead(db_session, client_id, **kwargs):
    """Create a Lead record."""
    defaults = {
        "id": uuid.uuid4(),
        "client_id": client_id,
        "phone": "+15125551234",
        "source": "google_lsa",
        "state": "new",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    lead = Lead(**defaults)
    db_session.add(lead)
    return lead


# ---------------------------------------------------------------------------
# get_system_overview
# ---------------------------------------------------------------------------

class TestGetSystemOverview:
    async def test_empty_database(self, db):
        """Returns zeros when database is empty."""
        result = await get_system_overview(db)

        assert result["active_clients"] == 0
        assert result["mrr"] == 0.0
        assert result["total_leads_30d"] == 0
        assert result["total_leads_7d"] == 0
        assert result["avg_response_time_ms"] == 0
        assert result["total_booked_30d"] == 0
        assert result["conversion_rate"] == 0.0
        assert result["clients_by_tier"] == {}
        assert result["clients_by_billing"] == {}

    async def test_counts_active_non_admin_clients(self, db):
        """Counts only active, non-admin clients."""
        _make_client(db, is_active=True, is_admin=False)
        _make_client(db, is_active=True, is_admin=False)
        _make_client(db, is_active=False, is_admin=False)  # inactive
        _make_client(db, is_active=True, is_admin=True)  # admin
        await db.commit()

        result = await get_system_overview(db)
        assert result["active_clients"] == 2

    async def test_mrr_calculation(self, db):
        """MRR sums monthly_fee for active, non-admin, billable clients."""
        _make_client(db, monthly_fee=497.0, billing_status="active")
        _make_client(db, monthly_fee=997.0, billing_status="pilot")
        _make_client(db, monthly_fee=1497.0, billing_status="trial")
        _make_client(db, monthly_fee=497.0, billing_status="churned")  # excluded
        _make_client(db, monthly_fee=497.0, is_admin=True, billing_status="active")  # admin excluded
        await db.commit()

        result = await get_system_overview(db)
        assert result["mrr"] == pytest.approx(2991.0)

    async def test_lead_counts_by_period(self, db):
        """Counts leads in 30d and 7d windows."""
        client = _make_client(db)
        await db.flush()

        now = datetime.now(timezone.utc)
        _make_lead(db, client.id, created_at=now - timedelta(days=3))  # both 7d and 30d
        _make_lead(db, client.id, created_at=now - timedelta(days=15))  # 30d only
        _make_lead(db, client.id, created_at=now - timedelta(days=45))  # neither
        await db.commit()

        result = await get_system_overview(db)
        assert result["total_leads_7d"] == 1
        assert result["total_leads_30d"] == 2

    async def test_avg_response_time(self, db):
        """Calculates average response time across all leads."""
        client = _make_client(db)
        await db.flush()

        now = datetime.now(timezone.utc)
        _make_lead(db, client.id, first_response_ms=5000, created_at=now - timedelta(days=5))
        _make_lead(db, client.id, first_response_ms=15000, created_at=now - timedelta(days=5))
        _make_lead(db, client.id, first_response_ms=None, created_at=now - timedelta(days=5))
        await db.commit()

        result = await get_system_overview(db)
        assert result["avg_response_time_ms"] == 10000

    async def test_booked_count_and_conversion(self, db):
        """Counts booked/completed leads and calculates conversion rate."""
        client = _make_client(db)
        await db.flush()

        now = datetime.now(timezone.utc)
        _make_lead(db, client.id, state="booked", created_at=now - timedelta(days=5))
        _make_lead(db, client.id, state="completed", created_at=now - timedelta(days=5))
        _make_lead(db, client.id, state="new", created_at=now - timedelta(days=5))
        _make_lead(db, client.id, state="qualifying", created_at=now - timedelta(days=5))
        await db.commit()

        result = await get_system_overview(db)
        assert result["total_booked_30d"] == 2
        assert result["conversion_rate"] == pytest.approx(0.5)

    async def test_clients_by_tier(self, db):
        """Groups active non-admin clients by tier."""
        _make_client(db, tier="starter")
        _make_client(db, tier="starter")
        _make_client(db, tier="pro")
        _make_client(db, tier="business")
        _make_client(db, tier="starter", is_admin=True)  # excluded
        await db.commit()

        result = await get_system_overview(db)
        assert result["clients_by_tier"]["starter"] == 2
        assert result["clients_by_tier"]["pro"] == 1
        assert result["clients_by_tier"]["business"] == 1

    async def test_clients_by_billing_status(self, db):
        """Groups non-admin clients by billing_status."""
        _make_client(db, billing_status="active")
        _make_client(db, billing_status="active")
        _make_client(db, billing_status="trial")
        _make_client(db, billing_status="churned")
        _make_client(db, billing_status="active", is_admin=True)  # excluded
        await db.commit()

        result = await get_system_overview(db)
        assert result["clients_by_billing"]["active"] == 2
        assert result["clients_by_billing"]["trial"] == 1
        assert result["clients_by_billing"]["churned"] == 1


# ---------------------------------------------------------------------------
# get_client_list_with_metrics
# ---------------------------------------------------------------------------

class TestGetClientListWithMetrics:
    async def test_empty_database(self, db):
        """Returns empty list when no clients exist."""
        result = await get_client_list_with_metrics(db)

        assert result["clients"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["pages"] == 1

    async def test_excludes_admin_clients(self, db):
        """Admin clients are excluded from the list."""
        _make_client(db, business_name="Regular Biz", is_admin=False)
        _make_client(db, business_name="Admin Biz", is_admin=True)
        await db.commit()

        result = await get_client_list_with_metrics(db)
        assert result["total"] == 1
        assert result["clients"][0]["business_name"] == "Regular Biz"

    async def test_per_client_lead_metrics(self, db):
        """Each client has leads_30d, booked_30d, and conversion_rate."""
        client = _make_client(db, business_name="Metrics Biz")
        await db.flush()

        now = datetime.now(timezone.utc)
        _make_lead(db, client.id, state="booked", created_at=now - timedelta(days=5))
        _make_lead(db, client.id, state="new", created_at=now - timedelta(days=5))
        _make_lead(db, client.id, state="completed", created_at=now - timedelta(days=5))
        # Old lead outside 30d
        _make_lead(db, client.id, state="booked", created_at=now - timedelta(days=45))
        await db.commit()

        result = await get_client_list_with_metrics(db)
        cd = result["clients"][0]
        assert cd["leads_30d"] == 3
        assert cd["booked_30d"] == 2
        assert cd["conversion_rate"] == pytest.approx(2 / 3, rel=0.01)

    async def test_zero_leads_conversion_rate(self, db):
        """Conversion rate is 0.0 when no leads."""
        _make_client(db, business_name="No Leads Biz")
        await db.commit()

        result = await get_client_list_with_metrics(db)
        cd = result["clients"][0]
        assert cd["leads_30d"] == 0
        assert cd["conversion_rate"] == 0.0

    async def test_search_filter(self, db):
        """Filters by business_name, owner_email, or owner_name."""
        _make_client(
            db,
            business_name="Alpha HVAC",
            owner_name="Alice",
            owner_email="alice@alpha.com",
        )
        _make_client(
            db,
            business_name="Beta Plumbing",
            owner_name="Bob",
            owner_email="bob@beta.com",
        )
        await db.commit()

        result = await get_client_list_with_metrics(db, search="Alpha")
        assert result["total"] == 1
        assert result["clients"][0]["business_name"] == "Alpha HVAC"

        result2 = await get_client_list_with_metrics(db, search="bob@beta")
        assert result2["total"] == 1
        assert result2["clients"][0]["business_name"] == "Beta Plumbing"

        result3 = await get_client_list_with_metrics(db, search="Alice")
        assert result3["total"] == 1

    async def test_tier_filter(self, db):
        """Filters by tier."""
        _make_client(db, business_name="Starter Biz", tier="starter")
        _make_client(db, business_name="Pro Biz", tier="pro")
        await db.commit()

        result = await get_client_list_with_metrics(db, tier="pro")
        assert result["total"] == 1
        assert result["clients"][0]["business_name"] == "Pro Biz"

    async def test_billing_status_filter(self, db):
        """Filters by billing_status."""
        _make_client(db, business_name="Active Biz", billing_status="active")
        _make_client(db, business_name="Trial Biz", billing_status="trial")
        await db.commit()

        result = await get_client_list_with_metrics(db, billing_status="trial")
        assert result["total"] == 1
        assert result["clients"][0]["business_name"] == "Trial Biz"

    async def test_pagination(self, db):
        """Pagination works correctly."""
        for i in range(5):
            _make_client(
                db,
                business_name=f"Biz {i}",
                created_at=datetime.now(timezone.utc) - timedelta(hours=i),
            )
        await db.commit()

        result = await get_client_list_with_metrics(db, page=1, per_page=2)
        assert len(result["clients"]) == 2
        assert result["total"] == 5
        assert result["pages"] == 3
        assert result["page"] == 1

        result2 = await get_client_list_with_metrics(db, page=3, per_page=2)
        assert len(result2["clients"]) == 1

    async def test_client_data_fields(self, db):
        """All expected fields are present in client data dict."""
        now = datetime.now(timezone.utc)
        client = _make_client(
            db,
            business_name="Full Fields Biz",
            trade_type="plumbing",
            tier="pro",
            monthly_fee=597.0,
            billing_status="active",
            onboarding_status="live",
            owner_name="Jane",
            owner_email="jane@fullfields.com",
            twilio_phone="+15125559876",
            crm_type="servicetitan",
            is_active=True,
            created_at=now,
        )
        await db.commit()

        result = await get_client_list_with_metrics(db)
        cd = result["clients"][0]

        assert cd["id"] == str(client.id)
        assert cd["business_name"] == "Full Fields Biz"
        assert cd["trade_type"] == "plumbing"
        assert cd["tier"] == "pro"
        assert cd["monthly_fee"] == 597.0
        assert cd["billing_status"] == "active"
        assert cd["onboarding_status"] == "live"
        assert cd["owner_name"] == "Jane"
        assert cd["owner_email"] == "jane@fullfields.com"
        assert cd["twilio_phone"] == "+15125559876"
        assert cd["crm_type"] == "servicetitan"
        assert cd["is_active"] is True
        assert cd["created_at"] is not None

    async def test_created_at_isoformat(self, db):
        """created_at is serialized as isoformat string."""
        fixed_time = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        _make_client(db, business_name="Dated Biz", created_at=fixed_time)
        await db.commit()

        result = await get_client_list_with_metrics(db)
        cd = result["clients"][0]
        assert cd["created_at"] is not None
        assert "2026-01-15" in cd["created_at"]


# ---------------------------------------------------------------------------
# get_revenue_breakdown
# ---------------------------------------------------------------------------

class TestGetRevenueBreakdown:
    async def test_empty_database(self, db):
        """Returns empty breakdown when no clients."""
        result = await get_revenue_breakdown(db)

        assert result["total_mrr"] == 0
        assert result["mrr_by_tier"] == {}
        assert result["top_clients"] == []
        assert result["total_paying_clients"] == 0

    async def test_mrr_by_tier(self, db):
        """Groups MRR by tier for active/pilot/trial clients."""
        _make_client(db, tier="starter", monthly_fee=297.0, billing_status="active")
        _make_client(db, tier="starter", monthly_fee=297.0, billing_status="active")
        _make_client(db, tier="pro", monthly_fee=597.0, billing_status="pilot")
        _make_client(db, tier="business", monthly_fee=1497.0, billing_status="trial")
        # Excluded: churned
        _make_client(db, tier="pro", monthly_fee=597.0, billing_status="churned")
        # Excluded: admin
        _make_client(db, tier="starter", monthly_fee=297.0, billing_status="active", is_admin=True)
        await db.commit()

        result = await get_revenue_breakdown(db)
        assert result["mrr_by_tier"]["starter"] == pytest.approx(594.0)
        assert result["mrr_by_tier"]["pro"] == pytest.approx(597.0)
        assert result["mrr_by_tier"]["business"] == pytest.approx(1497.0)
        assert result["total_mrr"] == pytest.approx(2688.0)

    async def test_top_clients(self, db):
        """Returns top clients ordered by monthly_fee descending."""
        for i in range(12):
            _make_client(
                db,
                business_name=f"Client {i}",
                monthly_fee=100.0 * (i + 1),
                billing_status="active",
                trade_type="hvac",
                tier="starter",
            )
        await db.commit()

        result = await get_revenue_breakdown(db)
        assert len(result["top_clients"]) == 10
        assert result["top_clients"][0]["mrr"] == pytest.approx(1200.0)
        assert result["top_clients"][9]["mrr"] == pytest.approx(300.0)

    async def test_top_client_fields(self, db):
        """Top client dict contains expected fields."""
        client = _make_client(
            db,
            business_name="Top Biz",
            monthly_fee=1500.0,
            billing_status="active",
            trade_type="solar",
            tier="business",
        )
        await db.commit()

        result = await get_revenue_breakdown(db)
        tc = result["top_clients"][0]
        assert tc["id"] == str(client.id)
        assert tc["business_name"] == "Top Biz"
        assert tc["mrr"] == pytest.approx(1500.0)
        assert tc["tier"] == "business"
        assert tc["trade_type"] == "solar"

    async def test_total_paying_clients(self, db):
        """Counts total paying (active/pilot/trial) non-admin clients."""
        _make_client(db, billing_status="active")
        _make_client(db, billing_status="pilot")
        _make_client(db, billing_status="trial")
        _make_client(db, billing_status="churned")  # excluded
        _make_client(db, billing_status="active", is_admin=True)  # excluded
        await db.commit()

        result = await get_revenue_breakdown(db)
        assert result["total_paying_clients"] == 3

    async def test_inactive_clients_excluded(self, db):
        """Inactive clients are excluded from MRR and top clients."""
        _make_client(db, monthly_fee=1000.0, billing_status="active", is_active=True)
        _make_client(db, monthly_fee=500.0, billing_status="active", is_active=False)
        await db.commit()

        result = await get_revenue_breakdown(db)
        assert result["total_mrr"] == pytest.approx(1000.0)
        assert len(result["top_clients"]) == 1
