"""
Tests for src/api/campaign_detail.py — campaign detail, prospect management,
inbox, and email thread viewer endpoints.
All database calls are mocked to avoid SQLite/JSONB incompatibility.
"""
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from collections import namedtuple

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_MOCK = MagicMock()


def _make_campaign(
    name="Test Campaign",
    status="draft",
    target_trades=None,
    target_locations=None,
    sequence_steps=None,
    daily_limit=25,
    **overrides,
):
    """Build a mock Campaign object."""
    c = MagicMock()
    c.id = overrides.get("id", uuid.uuid4())
    c.name = name
    c.description = overrides.get("description", "Test description")
    c.status = status
    c.target_trades = target_trades or []
    c.target_locations = target_locations or []
    c.sequence_steps = sequence_steps or []
    c.daily_limit = daily_limit
    c.total_sent = overrides.get("total_sent", 0)
    c.total_opened = overrides.get("total_opened", 0)
    c.total_replied = overrides.get("total_replied", 0)
    c.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    c.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return c


def _make_outreach(
    name="Prospect One",
    email="prospect@example.com",
    status="cold",
    campaign_id=None,
    **overrides,
):
    """Build a mock Outreach object."""
    o = MagicMock()
    o.id = overrides.get("id", uuid.uuid4())
    o.prospect_name = name
    o.prospect_company = overrides.get("prospect_company", "ACME HVAC")
    o.prospect_email = email
    o.prospect_phone = overrides.get("prospect_phone", "+15125559999")
    o.prospect_trade_type = overrides.get("prospect_trade_type", "hvac")
    o.status = status
    o.campaign_id = campaign_id
    o.email_unsubscribed = overrides.get("email_unsubscribed", False)
    o.city = overrides.get("city", "Austin")
    o.state_code = overrides.get("state_code", "TX")
    o.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    o.updated_at = overrides.get("updated_at", datetime.now(timezone.utc))
    return o


def _make_email(
    outreach_id,
    direction="outbound",
    step=1,
    sent_at=None,
    **overrides,
):
    """Build a mock OutreachEmail object."""
    e = MagicMock()
    e.id = overrides.get("id", uuid.uuid4())
    e.outreach_id = outreach_id
    e.direction = direction
    e.sequence_step = step
    e.subject = overrides.get("subject", "Hello")
    e.body_html = overrides.get("body_html", "<p>Hi</p>")
    e.body_text = overrides.get("body_text", "Hi")
    e.from_email = overrides.get("from_email", "sales@leadlock.ai")
    e.to_email = overrides.get("to_email", "prospect@example.com")
    e.sent_at = sent_at or datetime.now(timezone.utc)
    e.delivered_at = overrides.get("delivered_at", None)
    e.opened_at = overrides.get("opened_at", None)
    e.clicked_at = overrides.get("clicked_at", None)
    e.bounced_at = overrides.get("bounced_at", None)
    e.ai_cost_usd = overrides.get("ai_cost_usd", 0.001)
    e.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return e


def _mock_db():
    """Create a mock AsyncSession with common helpers."""
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
    """Create a mock execute result whose .scalar() returns value."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _scalars_result(items):
    """Create a mock execute result whose .scalars().all() returns items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _rows_result(rows):
    """Create a mock execute result whose .all() returns rows."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _one_result(**kwargs):
    """Create a mock execute result whose .one() returns a named row."""
    result = MagicMock()
    Row = namedtuple("Row", kwargs.keys())
    result.one.return_value = Row(**kwargs)
    return result


def _scalar_one_result(value):
    """Create a mock execute result whose .scalar_one_or_none() returns value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# GET /campaigns/{campaign_id}/detail
# ---------------------------------------------------------------------------


class TestGetCampaignDetail:
    """Tests for the get_campaign_detail endpoint."""

    async def test_invalid_campaign_id_returns_400(self):
        from src.api.campaign_detail import get_campaign_detail

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await get_campaign_detail("not-a-uuid", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400
        assert "Invalid campaign ID" in exc.value.detail

    async def test_nonexistent_campaign_returns_404(self):
        from src.api.campaign_detail import get_campaign_detail

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_campaign_detail(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_success_returns_enriched_detail(self):
        from src.api.campaign_detail import get_campaign_detail

        db = _mock_db()
        campaign = _make_campaign(name="HVAC Q1", status="active")
        db.get.return_value = campaign

        StatusRow = namedtuple("StatusRow", ["status", "count"])
        StepRow = namedtuple("StepRow", ["sequence_step", "sent", "opened", "clicked"])
        StepReplyRow = namedtuple("StepReplyRow", ["sequence_step", "replied"])

        # Configure execute calls in order:
        # 1. status counts, 2. email stats, 3. reply count,
        # 4. step performance, 5. step replies
        db.execute.side_effect = [
            _rows_result([StatusRow("contacted", 5), StatusRow("cold", 3)]),
            _one_result(sent=10, opened=4, clicked=2, bounced=1),
            _scalar_result(3),
            _rows_result([
                StepRow(1, 6, 3, 1),
                StepRow(2, 4, 1, 1),
            ]),
            _rows_result([
                StepReplyRow(1, 2),
                StepReplyRow(2, 1),
            ]),
        ]

        result = await get_campaign_detail(str(campaign.id), db=db, admin=ADMIN_MOCK)

        assert result["id"] == str(campaign.id)
        assert result["name"] == "HVAC Q1"
        assert result["status"] == "active"
        assert result["prospects"]["total"] == 8
        assert result["prospects"]["by_status"]["contacted"] == 5
        assert result["prospects"]["by_status"]["cold"] == 3
        assert result["emails"]["sent"] == 10
        assert result["emails"]["opened"] == 4
        assert result["emails"]["clicked"] == 2
        assert result["emails"]["bounced"] == 1
        assert result["emails"]["replied"] == 3
        assert result["emails"]["open_rate"] == 40.0
        assert result["emails"]["reply_rate"] == 30.0
        assert result["emails"]["bounce_rate"] == 10.0
        assert len(result["step_performance"]) == 2
        assert result["step_performance"][0]["step"] == 1
        assert result["step_performance"][0]["sent"] == 6
        assert result["step_performance"][0]["replied"] == 2
        assert result["step_performance"][1]["step"] == 2

    async def test_empty_campaign_returns_zero_metrics(self):
        from src.api.campaign_detail import get_campaign_detail

        db = _mock_db()
        campaign = _make_campaign(name="Empty")
        db.get.return_value = campaign

        db.execute.side_effect = [
            _rows_result([]),                              # no prospects
            _one_result(sent=0, opened=0, clicked=0, bounced=0),
            _scalar_result(0),                             # 0 replies
            _rows_result([]),                              # no step perf
            _rows_result([]),                              # no step replies
        ]

        result = await get_campaign_detail(str(campaign.id), db=db, admin=ADMIN_MOCK)

        assert result["prospects"]["total"] == 0
        assert result["emails"]["sent"] == 0
        assert result["emails"]["replied"] == 0
        assert result["emails"]["open_rate"] == 0
        assert result["step_performance"] == []

    async def test_rate_helper_zero_denom(self):
        """_rate helper should return 0 when denominator is 0."""
        from src.api.campaign_detail import get_campaign_detail

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        db.execute.side_effect = [
            _rows_result([]),
            _one_result(sent=0, opened=0, clicked=0, bounced=0),
            _scalar_result(0),
            _rows_result([]),
            _rows_result([]),
        ]

        result = await get_campaign_detail(str(campaign.id), db=db, admin=ADMIN_MOCK)
        assert result["emails"]["open_rate"] == 0
        assert result["emails"]["reply_rate"] == 0
        assert result["emails"]["bounce_rate"] == 0


# ---------------------------------------------------------------------------
# GET /campaigns/{campaign_id}/prospects
# ---------------------------------------------------------------------------


class TestGetCampaignProspects:
    """Tests for the get_campaign_prospects endpoint."""

    async def test_invalid_campaign_id_returns_400(self):
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await get_campaign_prospects("bad-id", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_campaign_returns_404(self):
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_campaign_prospects(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    @patch("src.api.sales_engine._serialize_prospect", side_effect=lambda p: {"id": str(p.id)})
    async def test_returns_paginated_prospects(self, _ser):
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        prospects = [_make_outreach(name=f"P{i}") for i in range(3)]

        db.execute.side_effect = [
            _scalar_result(3),       # count
            _scalars_result(prospects),
        ]

        result = await get_campaign_prospects(
            str(campaign.id), page=1, per_page=25, status=None,
            search=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["total"] == 3
        assert result["page"] == 1
        assert result["pages"] == 1
        assert len(result["prospects"]) == 3

    @patch("src.api.sales_engine._serialize_prospect", side_effect=lambda p: {"id": str(p.id)})
    async def test_pagination_page2(self, _ser):
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        prospects = [_make_outreach(name=f"P{i}") for i in range(2)]

        db.execute.side_effect = [
            _scalar_result(5),       # total 5
            _scalars_result(prospects),
        ]

        result = await get_campaign_prospects(
            str(campaign.id), page=2, per_page=2, status=None,
            search=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["total"] == 5
        assert result["page"] == 2
        assert result["pages"] == 3
        assert len(result["prospects"]) == 2

    @patch("src.api.sales_engine._serialize_prospect", side_effect=lambda p: {"id": str(p.id)})
    async def test_status_filter_passed(self, _ser):
        """Verify status filter is accepted (filter logic is in SQL)."""
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([_make_outreach(status="cold")]),
        ]

        result = await get_campaign_prospects(
            str(campaign.id), page=1, per_page=25, status="cold",
            search=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["total"] == 1

    @patch("src.api.sales_engine._serialize_prospect", side_effect=lambda p: {"id": str(p.id)})
    async def test_search_filter_passed(self, _ser):
        """Verify search filter is accepted."""
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        db.execute.side_effect = [
            _scalar_result(1),
            _scalars_result([_make_outreach(name="Alice Smith")]),
        ]

        result = await get_campaign_prospects(
            str(campaign.id), page=1, per_page=25, status=None,
            search="Alice", db=db, admin=ADMIN_MOCK,
        )
        assert result["total"] == 1

    @patch("src.api.sales_engine._serialize_prospect", side_effect=lambda p: {"id": str(p.id)})
    async def test_empty_results(self, _ser):
        from src.api.campaign_detail import get_campaign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        db.execute.side_effect = [
            _scalar_result(0),
            _scalars_result([]),
        ]

        result = await get_campaign_prospects(
            str(campaign.id), page=1, per_page=25, status=None,
            search=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["total"] == 0
        assert result["pages"] == 1
        assert result["prospects"] == []


# ---------------------------------------------------------------------------
# POST /campaigns/{campaign_id}/activate
# ---------------------------------------------------------------------------


class TestActivateCampaign:
    """Tests for the activate_campaign endpoint."""

    async def test_invalid_id_returns_400(self):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await activate_campaign("invalid", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_campaign_returns_404(self):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await activate_campaign(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_cannot_activate_already_active(self):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        campaign = _make_campaign(status="active", sequence_steps=[{"step": 1}])
        db.get.return_value = campaign

        with pytest.raises(HTTPException) as exc:
            await activate_campaign(str(campaign.id), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400
        assert "Cannot activate" in exc.value.detail

    async def test_cannot_activate_completed(self):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        campaign = _make_campaign(status="completed", sequence_steps=[{"step": 1}])
        db.get.return_value = campaign

        with pytest.raises(HTTPException) as exc:
            await activate_campaign(str(campaign.id), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_no_steps_returns_400(self):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        campaign = _make_campaign(status="draft", sequence_steps=[])
        db.get.return_value = campaign

        with pytest.raises(HTTPException) as exc:
            await activate_campaign(str(campaign.id), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400
        assert "at least 1 sequence step" in exc.value.detail

    async def test_none_steps_returns_400(self):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        campaign = _make_campaign(status="draft", sequence_steps=None)
        campaign.sequence_steps = None
        db.get.return_value = campaign

        with pytest.raises(HTTPException) as exc:
            await activate_campaign(str(campaign.id), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    @patch("src.api.campaign_detail._auto_assign_prospects", new_callable=AsyncMock)
    async def test_successful_activation_from_draft(self, mock_assign):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        campaign = _make_campaign(
            status="draft",
            sequence_steps=[{"step": 1, "channel": "email"}],
        )
        db.get.return_value = campaign
        mock_assign.return_value = 5

        result = await activate_campaign(str(campaign.id), db=db, admin=ADMIN_MOCK)

        assert result["status"] == "activated"
        assert result["prospects_assigned"] == 5
        assert campaign.status == "active"
        mock_assign.assert_called_once()

    @patch("src.api.campaign_detail._auto_assign_prospects", new_callable=AsyncMock)
    async def test_activation_from_paused(self, mock_assign):
        from src.api.campaign_detail import activate_campaign

        db = _mock_db()
        campaign = _make_campaign(status="paused", sequence_steps=[{"step": 1}])
        db.get.return_value = campaign
        mock_assign.return_value = 0

        result = await activate_campaign(str(campaign.id), db=db, admin=ADMIN_MOCK)
        assert result["status"] == "activated"
        assert campaign.status == "active"


# ---------------------------------------------------------------------------
# _auto_assign_prospects helper
# ---------------------------------------------------------------------------


class TestAutoAssignProspects:
    """Tests for the _auto_assign_prospects internal helper."""

    async def test_assigns_matching_prospects(self):
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(status="active", target_trades=["plumbing"])

        p1 = _make_outreach(name="Plumber", prospect_trade_type="plumbing")
        p2 = _make_outreach(name="HVAC", prospect_trade_type="hvac")

        db.execute.return_value = _scalars_result([p1])

        assigned = await _auto_assign_prospects(db, campaign)
        assert assigned == 1
        assert p1.campaign_id == campaign.id

    async def test_assigns_zero_when_no_matches(self):
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(status="active")
        db.execute.return_value = _scalars_result([])

        assigned = await _auto_assign_prospects(db, campaign)
        assert assigned == 0

    async def test_sets_updated_at_on_assigned_prospects(self):
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(status="active")
        p1 = _make_outreach(name="Test")
        db.execute.return_value = _scalars_result([p1])

        await _auto_assign_prospects(db, campaign)
        assert p1.updated_at is not None

    async def test_location_dict_filter(self):
        """Verifies location dict filter builds correctly (no exception)."""
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(
            status="active",
            target_locations=[{"city": "Austin", "state": "TX"}],
        )
        db.execute.return_value = _scalars_result([])

        assigned = await _auto_assign_prospects(db, campaign)
        assert assigned == 0
        db.execute.assert_called_once()

    async def test_location_string_filter(self):
        """Verifies location string filter builds correctly (no exception)."""
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(
            status="active",
            target_locations=["Houston, TX"],
        )
        db.execute.return_value = _scalars_result([])

        assigned = await _auto_assign_prospects(db, campaign)
        assert assigned == 0
        db.execute.assert_called_once()

    async def test_no_target_trades_skips_trade_filter(self):
        """When target_trades is empty, no trade filter applied."""
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(status="active", target_trades=[])
        p = _make_outreach(name="Any Trade")
        db.execute.return_value = _scalars_result([p])

        assigned = await _auto_assign_prospects(db, campaign)
        assert assigned == 1

    async def test_no_target_locations_skips_location_filter(self):
        """When target_locations is empty, no location filter applied."""
        from src.api.campaign_detail import _auto_assign_prospects

        db = _mock_db()
        campaign = _make_campaign(status="active", target_locations=[])
        p = _make_outreach(name="Any Location")
        db.execute.return_value = _scalars_result([p])

        assigned = await _auto_assign_prospects(db, campaign)
        assert assigned == 1


# ---------------------------------------------------------------------------
# POST /campaigns/{campaign_id}/assign-prospects
# ---------------------------------------------------------------------------


class TestAssignProspects:
    """Tests for the assign_prospects endpoint."""

    async def test_invalid_campaign_id(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await assign_prospects("xyz", payload={}, db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_campaign(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await assign_prospects(
                str(uuid.uuid4()),
                payload={"prospect_ids": ["abc"]},
                db=db,
                admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 404

    async def test_no_ids_no_filters_returns_400(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        with pytest.raises(HTTPException) as exc:
            await assign_prospects(
                str(campaign.id), payload={}, db=db, admin=ADMIN_MOCK
            )
        assert exc.value.status_code == 400
        assert "Either prospect_ids or filters required" in exc.value.detail

    async def test_assign_by_prospect_ids(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()

        p1 = _make_outreach(name="P1")
        p1.campaign_id = None
        p2 = _make_outreach(name="P2")
        p2.campaign_id = None

        # First call is db.get(Campaign), then db.get(Outreach) for each
        db.get.side_effect = [campaign, p1, p2]

        result = await assign_prospects(
            str(campaign.id),
            payload={"prospect_ids": [str(p1.id), str(p2.id)]},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["status"] == "assigned"
        assert result["count"] == 2
        assert p1.campaign_id == campaign.id
        assert p2.campaign_id == campaign.id

    async def test_assign_by_ids_skips_already_assigned(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        p1 = _make_outreach(name="Taken")
        p1.campaign_id = uuid.uuid4()  # already assigned

        db.get.side_effect = [campaign, p1]

        result = await assign_prospects(
            str(campaign.id),
            payload={"prospect_ids": [str(p1.id)]},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 0

    async def test_assign_by_ids_handles_invalid_uuid(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.side_effect = [campaign]

        result = await assign_prospects(
            str(campaign.id),
            payload={"prospect_ids": ["not-a-uuid"]},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 0

    async def test_assign_by_ids_handles_missing_prospect(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        db.get.side_effect = [campaign, None]  # prospect not found

        result = await assign_prospects(
            str(campaign.id),
            payload={"prospect_ids": [str(uuid.uuid4())]},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 0

    async def test_assign_by_filters(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()

        p1 = _make_outreach(name="Plumber")
        p1.campaign_id = None

        db.get.return_value = campaign
        db.execute.return_value = _scalars_result([p1])

        result = await assign_prospects(
            str(campaign.id),
            payload={"filters": {"trade_type": "plumbing"}},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 1
        assert p1.campaign_id == campaign.id

    async def test_assign_by_filters_city_state(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        p1 = _make_outreach(name="Austin P")
        p1.campaign_id = None

        db.get.return_value = campaign
        db.execute.return_value = _scalars_result([p1])

        result = await assign_prospects(
            str(campaign.id),
            payload={"filters": {"city": "Austin", "state": "TX"}},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 1

    async def test_assign_by_filters_status(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()
        p1 = _make_outreach(name="Contacted", status="contacted")
        p1.campaign_id = None

        db.get.return_value = campaign
        db.execute.return_value = _scalars_result([p1])

        result = await assign_prospects(
            str(campaign.id),
            payload={"filters": {"status": "contacted"}},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 1

    async def test_assign_by_filters_empty_results(self):
        from src.api.campaign_detail import assign_prospects

        db = _mock_db()
        campaign = _make_campaign()

        db.get.return_value = campaign
        db.execute.return_value = _scalars_result([])

        result = await assign_prospects(
            str(campaign.id),
            payload={"filters": {"trade_type": "solar"}},
            db=db,
            admin=ADMIN_MOCK,
        )
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# GET /campaigns/{campaign_id}/metrics
# ---------------------------------------------------------------------------


class TestGetCampaignMetrics:
    """Tests for the get_campaign_metrics endpoint."""

    async def test_invalid_campaign_id(self):
        from src.api.campaign_detail import get_campaign_metrics

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await get_campaign_metrics("bad", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_campaign(self):
        from src.api.campaign_detail import get_campaign_metrics

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_campaign_metrics(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_empty_campaign_returns_empty_metrics(self):
        from src.api.campaign_detail import get_campaign_metrics

        db = _mock_db()
        campaign = _make_campaign()
        db.get.return_value = campaign

        db.execute.side_effect = [
            _rows_result([]),   # step performance
            _rows_result([]),   # step replies
            _rows_result([]),   # daily sends
            _rows_result([]),   # funnel
        ]

        result = await get_campaign_metrics(str(campaign.id), db=db, admin=ADMIN_MOCK)

        assert result["step_performance"] == []
        assert result["daily_sends"] == []
        assert result["funnel"]["cold"] == 0
        assert result["funnel"]["contacted"] == 0
        assert result["funnel"]["won"] == 0
        assert result["funnel"]["lost"] == 0
        assert result["funnel"]["demo_scheduled"] == 0

    async def test_metrics_with_step_data(self):
        from src.api.campaign_detail import get_campaign_metrics

        db = _mock_db()
        campaign = _make_campaign(status="active")
        db.get.return_value = campaign

        StepRow = namedtuple("StepRow", ["sequence_step", "sent", "opened", "clicked"])
        StepReplyRow = namedtuple("StepReplyRow", ["sequence_step", "replied"])
        DayRow = namedtuple("DayRow", ["day", "sent"])
        FunnelRow = namedtuple("FunnelRow", ["status", "count"])

        db.execute.side_effect = [
            _rows_result([StepRow(1, 10, 5, 2), StepRow(2, 8, 3, 1)]),
            _rows_result([StepReplyRow(1, 3), StepReplyRow(2, 1)]),
            _rows_result([DayRow(datetime(2026, 2, 15, tzinfo=timezone.utc), 5)]),
            _rows_result([
                FunnelRow("cold", 10),
                FunnelRow("contacted", 5),
                FunnelRow("won", 2),
            ]),
        ]

        result = await get_campaign_metrics(str(campaign.id), db=db, admin=ADMIN_MOCK)

        assert len(result["step_performance"]) == 2
        step1 = result["step_performance"][0]
        assert step1["step"] == 1
        assert step1["sent"] == 10
        assert step1["opened"] == 5
        assert step1["clicked"] == 2
        assert step1["replied"] == 3
        assert step1["open_rate"] == 50.0
        assert step1["click_rate"] == 20.0
        assert step1["reply_rate"] == 30.0

        step2 = result["step_performance"][1]
        assert step2["step"] == 2
        assert step2["replied"] == 1

        assert len(result["daily_sends"]) == 1
        assert result["daily_sends"][0]["sent"] == 5

        assert result["funnel"]["cold"] == 10
        assert result["funnel"]["contacted"] == 5
        assert result["funnel"]["won"] == 2
        assert result["funnel"]["lost"] == 0


# ---------------------------------------------------------------------------
# GET /inbox
# ---------------------------------------------------------------------------


class TestGetInbox:
    """Tests for the get_inbox endpoint."""

    async def test_empty_inbox(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        db.execute.side_effect = [
            _scalar_result(0),   # count
            _rows_result([]),    # page rows
        ]

        result = await get_inbox(
            page=1, per_page=25, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["conversations"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["pages"] == 1

    async def test_inbox_invalid_campaign_filter(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await get_inbox(
                page=1, per_page=25, campaign_id="not-uuid",
                classification=None, db=db, admin=ADMIN_MOCK,
            )
        assert exc.value.status_code == 400

    async def test_inbox_with_conversations(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        prospect = _make_outreach(name="John Doe", campaign_id=uuid.uuid4())
        now = datetime.now(timezone.utc)
        campaign_obj = _make_campaign(name="Test Campaign")

        last_email = MagicMock()
        last_email.body_text = "I am interested in your services"
        last_email.body_html = None

        # count, page rows, last_email query, campaign lookup
        db.execute.side_effect = [
            _scalar_result(1),
            _rows_result([(prospect, now, 2)]),
            _scalar_one_result(last_email),
        ]
        db.get.return_value = campaign_obj

        result = await get_inbox(
            page=1, per_page=25, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["total"] == 1
        assert len(result["conversations"]) == 1
        convo = result["conversations"][0]
        assert convo["prospect_name"] == "John Doe"
        assert convo["reply_count"] == 2
        assert convo["campaign_name"] == "Test Campaign"

    async def test_inbox_prospect_without_campaign(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        prospect = _make_outreach(name="Orphan", campaign_id=None)
        now = datetime.now(timezone.utc)

        last_email = MagicMock()
        last_email.body_text = "reply text"
        last_email.body_html = None

        db.execute.side_effect = [
            _scalar_result(1),
            _rows_result([(prospect, now, 1)]),
            _scalar_one_result(last_email),
        ]

        result = await get_inbox(
            page=1, per_page=25, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["conversations"][0]["campaign_name"] is None
        assert result["conversations"][0]["campaign_id"] is None

    async def test_inbox_pagination(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        db.execute.side_effect = [
            _scalar_result(5),
            _rows_result([]),
        ]

        result = await get_inbox(
            page=2, per_page=2, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["page"] == 2
        assert result["pages"] == 3

    async def test_inbox_snippet_truncated_at_80_chars(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        prospect = _make_outreach(name="Long Reply", campaign_id=None)
        now = datetime.now(timezone.utc)

        last_email = MagicMock()
        last_email.body_text = "A" * 200
        last_email.body_html = None

        db.execute.side_effect = [
            _scalar_result(1),
            _rows_result([(prospect, now, 1)]),
            _scalar_one_result(last_email),
        ]

        result = await get_inbox(
            page=1, per_page=25, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert len(result["conversations"][0]["last_reply_snippet"]) <= 80

    async def test_inbox_html_fallback_when_no_text(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        prospect = _make_outreach(name="HTML Only", campaign_id=None)
        now = datetime.now(timezone.utc)

        last_email = MagicMock()
        last_email.body_text = None
        last_email.body_html = "<p>HTML content</p>"

        db.execute.side_effect = [
            _scalar_result(1),
            _rows_result([(prospect, now, 1)]),
            _scalar_one_result(last_email),
        ]

        result = await get_inbox(
            page=1, per_page=25, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert "<p>HTML content</p>" in result["conversations"][0]["last_reply_snippet"]

    async def test_inbox_no_last_email(self):
        from src.api.campaign_detail import get_inbox

        db = _mock_db()
        prospect = _make_outreach(name="No Email", campaign_id=None)
        now = datetime.now(timezone.utc)

        db.execute.side_effect = [
            _scalar_result(1),
            _rows_result([(prospect, now, 1)]),
            _scalar_one_result(None),
        ]

        result = await get_inbox(
            page=1, per_page=25, campaign_id=None,
            classification=None, db=db, admin=ADMIN_MOCK,
        )
        assert result["conversations"][0]["last_reply_snippet"] == ""


# ---------------------------------------------------------------------------
# GET /inbox/{prospect_id}/thread
# ---------------------------------------------------------------------------


class TestGetInboxThread:
    """Tests for the get_inbox_thread endpoint."""

    async def test_invalid_prospect_id(self):
        from src.api.campaign_detail import get_inbox_thread

        db = _mock_db()
        with pytest.raises(HTTPException) as exc:
            await get_inbox_thread("bad-id", db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 400

    async def test_missing_prospect(self):
        from src.api.campaign_detail import get_inbox_thread

        db = _mock_db()
        db.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_inbox_thread(str(uuid.uuid4()), db=db, admin=ADMIN_MOCK)
        assert exc.value.status_code == 404

    async def test_thread_with_emails(self):
        from src.api.campaign_detail import get_inbox_thread

        db = _mock_db()
        campaign = _make_campaign(name="Thread Campaign")
        prospect = _make_outreach(
            name="Jane Smith",
            email="jane@example.com",
            prospect_phone="+15125551234",
            prospect_trade_type="plumbing",
            campaign_id=campaign.id,
        )

        now = datetime.now(timezone.utc)
        email1 = _make_email(
            prospect.id, direction="outbound", step=1,
            sent_at=now - timedelta(hours=2),
            subject="Intro",
            body_text="Hello Jane",
        )
        email2 = _make_email(
            prospect.id, direction="inbound", step=1,
            sent_at=now,
            subject="Re: Intro",
            body_text="Interested!",
        )

        # db.get(Outreach) first, then db.get(Campaign)
        db.get.side_effect = [prospect, campaign]
        db.execute.return_value = _scalars_result([email1, email2])

        result = await get_inbox_thread(str(prospect.id), db=db, admin=ADMIN_MOCK)

        assert result["prospect"]["name"] == "Jane Smith"
        assert result["prospect"]["email"] == "jane@example.com"
        assert result["prospect"]["campaign_name"] == "Thread Campaign"
        assert result["total"] == 2
        assert result["emails"][0]["direction"] == "outbound"
        assert result["emails"][1]["direction"] == "inbound"
        assert result["emails"][0]["subject"] == "Intro"

    async def test_thread_without_campaign(self):
        from src.api.campaign_detail import get_inbox_thread

        db = _mock_db()
        prospect = _make_outreach(name="No Campaign", campaign_id=None)

        db.get.return_value = prospect
        db.execute.return_value = _scalars_result([])

        result = await get_inbox_thread(str(prospect.id), db=db, admin=ADMIN_MOCK)
        assert result["prospect"]["campaign_name"] is None
        assert result["prospect"]["campaign_id"] is None
        assert result["total"] == 0
        assert result["emails"] == []

    async def test_thread_email_serialization(self):
        from src.api.campaign_detail import get_inbox_thread

        db = _mock_db()
        prospect = _make_outreach(name="Full Email", campaign_id=None)

        now = datetime.now(timezone.utc)
        email = _make_email(
            prospect.id,
            direction="outbound",
            step=2,
            sent_at=now,
            delivered_at=now + timedelta(seconds=5),
            opened_at=now + timedelta(minutes=10),
            clicked_at=now + timedelta(minutes=15),
            from_email="sales@leadlock.ai",
            to_email="prospect@test.com",
            subject="Follow-up",
            body_html="<p>Follow up</p>",
            body_text="Follow up",
        )

        db.get.return_value = prospect
        db.execute.return_value = _scalars_result([email])

        result = await get_inbox_thread(str(prospect.id), db=db, admin=ADMIN_MOCK)
        e = result["emails"][0]
        assert e["direction"] == "outbound"
        assert e["sequence_step"] == 2
        assert e["from_email"] == "sales@leadlock.ai"
        assert e["to_email"] == "prospect@test.com"
        assert e["subject"] == "Follow-up"
        assert e["sent_at"] is not None
        assert e["delivered_at"] is not None
        assert e["opened_at"] is not None
        assert e["clicked_at"] is not None
        assert e["bounced_at"] is None

    async def test_thread_prospect_fields(self):
        from src.api.campaign_detail import get_inbox_thread

        db = _mock_db()
        cid = uuid.uuid4()
        prospect = _make_outreach(
            name="Full Prospect",
            email="full@example.com",
            prospect_phone="+15125550000",
            prospect_trade_type="roofing",
            campaign_id=cid,
            city="Dallas",
            state_code="TX",
        )
        campaign = _make_campaign(name="Roofing Campaign")

        db.get.side_effect = [prospect, campaign]
        db.execute.return_value = _scalars_result([])

        result = await get_inbox_thread(str(prospect.id), db=db, admin=ADMIN_MOCK)
        p = result["prospect"]
        assert p["id"] == str(prospect.id)
        assert p["name"] == "Full Prospect"
        assert p["company"] == "ACME HVAC"
        assert p["email"] == "full@example.com"
        assert p["phone"] == "+15125550000"
        assert p["trade_type"] == "roofing"
        assert p["city"] == "Dallas"
        assert p["state_code"] == "TX"
        assert p["campaign_id"] == str(cid)
        assert p["campaign_name"] == "Roofing Campaign"
