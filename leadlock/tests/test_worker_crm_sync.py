"""
Tests for src/workers/crm_sync.py — CRM synchronization worker.
"""
import uuid
from contextlib import asynccontextmanager
from datetime import date, time, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_booking(
    booking_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    crm_sync_status: str = "pending",
    extra_data: dict | None = None,
):
    """Create a mock Booking object."""
    booking = MagicMock()
    booking.id = booking_id or uuid.uuid4()
    booking.lead_id = lead_id or uuid.uuid4()
    booking.client_id = client_id or uuid.uuid4()
    booking.appointment_date = date(2026, 3, 15)
    booking.time_window_start = time(9, 0)
    booking.time_window_end = time(11, 0)
    booking.service_type = "AC Repair"
    booking.tech_id = "tech_001"
    booking.crm_sync_status = crm_sync_status
    booking.crm_sync_error = None
    booking.crm_customer_id = None
    booking.crm_job_id = None
    booking.crm_synced_at = None
    booking.extra_data = extra_data
    return booking


def _make_lead(
    lead_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
):
    """Create a mock Lead object."""
    lead = MagicMock()
    lead.id = lead_id or uuid.uuid4()
    lead.client_id = client_id or uuid.uuid4()
    lead.first_name = "John"
    lead.last_name = "Doe"
    lead.phone = "+15125551234"
    lead.email = "john@example.com"
    lead.address = "123 Main St"
    return lead


def _make_client(
    client_id: uuid.UUID | None = None,
    crm_type: str = "servicetitan",
    crm_config: dict | None = None,
    crm_tenant_id: str | None = "tenant_123",
):
    """Create a mock Client object."""
    client = MagicMock()
    client.id = client_id or uuid.uuid4()
    client.crm_type = crm_type
    client.crm_config = crm_config or {
        "client_id": "crm_client",
        "client_secret": "crm_secret",
        "app_key": "crm_app_key",
    }
    client.crm_tenant_id = crm_tenant_id
    return client


@asynccontextmanager
async def mock_session():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    db.add = MagicMock()
    yield db


# ---------------------------------------------------------------------------
# sync_booking — success path
# ---------------------------------------------------------------------------

class TestSyncBookingSuccess:
    """Tests for sync_booking success scenarios."""

    async def test_success_path_updates_status_to_synced(self):
        """Successful CRM sync sets status to synced with job and customer IDs."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        booking = _make_booking(lead_id=lead_id, client_id=client_id)
        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            lead_id: lead,
            client_id: client,
        }.get(pk))
        db.add = MagicMock()

        mock_crm = AsyncMock()
        mock_crm.create_customer = AsyncMock(
            return_value={"success": True, "customer_id": "cust_123"}
        )
        mock_crm.create_booking = AsyncMock(
            return_value={"success": True, "job_id": "job_456"}
        )

        with (
            patch(
                "src.workers.crm_sync.get_crm_for_client",
                return_value=mock_crm,
            ),
            patch("src.models.event_log.EventLog") as mock_event_cls,
        ):
            mock_event_cls.return_value = MagicMock()

            from src.workers.crm_sync import sync_booking

            await sync_booking(db, booking)

            assert booking.crm_sync_status == "synced"
            assert booking.crm_customer_id == "cust_123"
            assert booking.crm_job_id == "job_456"
            assert booking.crm_synced_at is not None
            db.add.assert_called_once()


# ---------------------------------------------------------------------------
# sync_booking — CRM error / retry
# ---------------------------------------------------------------------------

class TestSyncBookingCRMError:
    """Tests for sync_booking CRM error handling."""

    async def test_customer_creation_failure_sets_status_failed(self):
        """Failed customer creation sets booking to failed."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        booking = _make_booking(lead_id=lead_id, client_id=client_id)
        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            lead_id: lead,
            client_id: client,
        }.get(pk))
        db.add = MagicMock()

        mock_crm = AsyncMock()
        mock_crm.create_customer = AsyncMock(
            return_value={"success": False, "error": "API rate limit"}
        )

        with patch(
            "src.workers.crm_sync.get_crm_for_client",
            return_value=mock_crm,
        ):
            from src.workers.crm_sync import sync_booking

            await sync_booking(db, booking)

            assert booking.crm_sync_status == "failed"
            assert "Customer creation failed" in booking.crm_sync_error

    async def test_booking_creation_failure_sets_status_failed(self):
        """Customer succeeds but booking creation fails."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        booking = _make_booking(lead_id=lead_id, client_id=client_id)
        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            lead_id: lead,
            client_id: client,
        }.get(pk))
        db.add = MagicMock()

        mock_crm = AsyncMock()
        mock_crm.create_customer = AsyncMock(
            return_value={"success": True, "customer_id": "cust_789"}
        )
        mock_crm.create_booking = AsyncMock(
            return_value={"success": False, "error": "Slot unavailable"}
        )

        with patch(
            "src.workers.crm_sync.get_crm_for_client",
            return_value=mock_crm,
        ):
            from src.workers.crm_sync import sync_booking

            await sync_booking(db, booking)

            assert booking.crm_sync_status == "failed"
            assert booking.crm_sync_error == "Slot unavailable"


# ---------------------------------------------------------------------------
# sync_booking — missing lead/client
# ---------------------------------------------------------------------------

class TestSyncBookingMissingEntities:
    """Tests for sync_booking when lead or client is not found."""

    async def test_missing_lead_sets_status_failed(self):
        """Missing lead sets booking to failed."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        booking = _make_booking(lead_id=lead_id, client_id=client_id)

        db = MagicMock()
        db.get = AsyncMock(return_value=None)

        from src.workers.crm_sync import sync_booking

        await sync_booking(db, booking)

        assert booking.crm_sync_status == "failed"
        assert "not found" in booking.crm_sync_error

    async def test_missing_client_sets_status_failed(self):
        """Missing client sets booking to failed."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        booking = _make_booking(lead_id=lead_id, client_id=client_id)
        lead = _make_lead(lead_id=lead_id)

        db = MagicMock()
        # Return lead for first get, None for client
        db.get = AsyncMock(side_effect=lambda model, pk: lead if pk == lead_id else None)

        from src.workers.crm_sync import sync_booking

        await sync_booking(db, booking)

        assert booking.crm_sync_status == "failed"
        assert "not found" in booking.crm_sync_error

    async def test_no_crm_integration_sets_not_applicable(self):
        """Client with no matching CRM sets status to not_applicable."""
        lead_id = uuid.uuid4()
        client_id = uuid.uuid4()
        booking = _make_booking(lead_id=lead_id, client_id=client_id)
        lead = _make_lead(lead_id=lead_id, client_id=client_id)
        client = _make_client(client_id=client_id, crm_type="unknown_crm")

        db = MagicMock()
        db.get = AsyncMock(side_effect=lambda model, pk: {
            lead_id: lead,
            client_id: client,
        }.get(pk))

        with patch(
            "src.workers.crm_sync.get_crm_for_client",
            return_value=None,
        ):
            from src.workers.crm_sync import sync_booking

            await sync_booking(db, booking)

            assert booking.crm_sync_status == "not_applicable"


# ---------------------------------------------------------------------------
# sync_pending_bookings — retry and max retries
# ---------------------------------------------------------------------------

class TestSyncPendingBookingsRetry:
    """Tests for retry logic in sync_pending_bookings."""

    async def test_crm_error_increments_retry_and_schedules_backoff(self):
        """CRM exception increments retry count and schedules next retry."""
        booking = _make_booking(extra_data={"crm_retry_count": 1})

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [booking]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=result_mock)
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "src.workers.crm_sync.async_session_factory",
                side_effect=session_factory,
            ),
            patch(
                "src.workers.crm_sync.sync_booking",
                new_callable=AsyncMock,
                side_effect=RuntimeError("CRM connection failed"),
            ),
        ):
            from src.workers.crm_sync import sync_pending_bookings

            await sync_pending_bookings()

            assert booking.crm_sync_status == "retrying"
            assert booking.extra_data["crm_retry_count"] == 2
            assert "crm_next_retry_at" in booking.extra_data

    async def test_max_retries_sets_failed_and_sends_alert(self):
        """After max retries, booking is marked failed and alert is sent."""
        booking = _make_booking(extra_data={"crm_retry_count": 5})

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [booking]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock

        @asynccontextmanager
        async def session_factory():
            db = MagicMock()
            db.execute = AsyncMock(return_value=result_mock)
            db.commit = AsyncMock()
            yield db

        with (
            patch(
                "src.workers.crm_sync.async_session_factory",
                side_effect=session_factory,
            ),
            patch(
                "src.workers.crm_sync.sync_booking",
                new_callable=AsyncMock,
                side_effect=RuntimeError("CRM permanently down"),
            ),
            patch(
                "src.utils.alerting.send_alert",
                new_callable=AsyncMock,
            ) as mock_alert,
        ):
            from src.workers.crm_sync import sync_pending_bookings

            await sync_pending_bookings()

            assert booking.crm_sync_status == "failed"
            assert "Max retries" in booking.crm_sync_error
            mock_alert.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_crm_for_client
# ---------------------------------------------------------------------------

class TestGetCRMForClient:
    """Tests for get_crm_for_client."""

    def test_servicetitan_returns_servicetitan_crm(self):
        """ServiceTitan client gets ServiceTitanCRM instance."""
        client = _make_client(crm_type="servicetitan")

        with patch("src.workers.crm_sync.ServiceTitanCRM") as mock_st:
            mock_st.return_value = MagicMock()

            from src.workers.crm_sync import get_crm_for_client

            crm = get_crm_for_client(client)

            assert crm is not None
            mock_st.assert_called_once()

    def test_google_sheets_returns_google_sheets_crm(self):
        """Google Sheets client gets GoogleSheetsCRM instance."""
        client = _make_client(
            crm_type="google_sheets",
            crm_config={"spreadsheet_id": "sheet_abc"},
        )

        with patch("src.workers.crm_sync.GoogleSheetsCRM") as mock_gs:
            mock_gs.return_value = MagicMock()

            from src.workers.crm_sync import get_crm_for_client

            crm = get_crm_for_client(client)

            assert crm is not None
            mock_gs.assert_called_once_with(spreadsheet_id="sheet_abc")

    def test_unknown_crm_type_returns_none(self):
        """Unknown CRM type returns None."""
        client = _make_client(crm_type="salesforce")

        from src.workers.crm_sync import get_crm_for_client

        crm = get_crm_for_client(client)

        assert crm is None
