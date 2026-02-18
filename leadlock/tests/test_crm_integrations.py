"""
Comprehensive tests for all CRM integrations.

Covers ServiceTitan, Housecall Pro, Jobber, GoHighLevel, and Google Sheets.
Each integration is tested for:
  - Successful creation (customer, lead, booking)
  - Error handling (HTTP errors, exceptions)
  - Correct HTTP method, URL, headers, and body
  - Edge cases (missing optional fields, default values)

Uses pytest-asyncio with asyncio_mode="auto" (configured in pyproject.toml).
All external HTTP calls are mocked via httpx.AsyncClient.
"""
import time
from datetime import date, time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(json_data: dict) -> MagicMock:
    """Build a mock httpx.Response that returns *json_data*."""
    response = MagicMock()
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    return response


def _make_mock_response_error(exc: Exception) -> MagicMock:
    """Build a mock httpx.Response whose raise_for_status raises *exc*."""
    response = MagicMock()
    response.raise_for_status.side_effect = exc
    return response


def _build_mock_client(
    post_response: MagicMock | None = None,
    get_response: MagicMock | None = None,
    request_response: MagicMock | None = None,
    post_side_effect: Exception | None = None,
    get_side_effect: Exception | None = None,
    request_side_effect: Exception | None = None,
) -> AsyncMock:
    """Return a fully-wired mock httpx.AsyncClient usable as an async ctx mgr."""
    mock_client = AsyncMock()

    if post_side_effect:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    else:
        mock_client.post = AsyncMock(return_value=post_response or _make_mock_response({}))

    if get_side_effect:
        mock_client.get = AsyncMock(side_effect=get_side_effect)
    else:
        mock_client.get = AsyncMock(return_value=get_response or _make_mock_response({}))

    if request_side_effect:
        mock_client.request = AsyncMock(side_effect=request_side_effect)
    else:
        mock_client.request = AsyncMock(return_value=request_response or _make_mock_response({}))

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ===================================================================
# ServiceTitan CRM
# ===================================================================

class TestServiceTitanCRM:
    """Tests for ServiceTitanCRM (src/integrations/servicetitan.py)."""

    def _make_crm(self):
        from src.integrations.servicetitan import ServiceTitanCRM
        return ServiceTitanCRM(
            client_id="test_client_id",
            client_secret="test_client_secret",
            app_key="test_app_key",
            tenant_id="12345",
        )

    # -- __init__ --------------------------------------------------------

    def test_init_stores_credentials(self):
        crm = self._make_crm()
        assert crm.client_id == "test_client_id"
        assert crm.client_secret == "test_client_secret"
        assert crm.app_key == "test_app_key"
        assert crm.tenant_id == "12345"
        assert crm._token is None
        assert crm._token_expires == 0

    # -- _get_token ------------------------------------------------------

    async def test_get_token_fetches_new_token(self):
        crm = self._make_crm()
        token_response = _make_mock_response({
            "access_token": "tok_abc",
            "expires_in": 900,
        })
        mock_client = _build_mock_client(post_response=token_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            token = await crm._get_token()

        assert token == "tok_abc"
        assert crm._token == "tok_abc"
        # Should have called POST to the auth URL
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "auth.servicetitan.io" in call_args.args[0]

    async def test_get_token_returns_cached_when_valid(self):
        crm = self._make_crm()
        crm._token = "cached_tok"
        crm._token_expires = time.time() + 600  # still valid

        mock_client = _build_mock_client()
        with patch("httpx.AsyncClient", return_value=mock_client):
            token = await crm._get_token()

        assert token == "cached_tok"
        # Should NOT have made an HTTP call
        mock_client.post.assert_not_called()

    async def test_get_token_refreshes_when_expired(self):
        crm = self._make_crm()
        crm._token = "old_tok"
        crm._token_expires = time.time() - 10  # expired

        token_response = _make_mock_response({
            "access_token": "new_tok",
            "expires_in": 900,
        })
        mock_client = _build_mock_client(post_response=token_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            token = await crm._get_token()

        assert token == "new_tok"
        mock_client.post.assert_called_once()

    # -- create_customer -------------------------------------------------

    async def test_create_customer_success(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"id": 9001})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234", email="j@d.com")

        assert result["success"] is True
        assert result["customer_id"] == "9001"
        assert result["error"] is None

        # Verify the HTTP call
        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert "/crm/v2/customers" in call_args.args[1]

    async def test_create_customer_with_address(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"id": 9002})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer(
                "Jane", "Smith", "+15125559999",
                address="123 Main St",
            )

        assert result["success"] is True
        # Verify payload contains locations
        call_kwargs = mock_client.request.call_args.kwargs
        payload = call_kwargs["json"]
        assert "locations" in payload
        assert payload["locations"][0]["address"]["street"] == "123 Main St"

    async def test_create_customer_error(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        error_response = _make_mock_response_error(
            httpx.HTTPStatusError("Server Error", request=MagicMock(), response=MagicMock())
        )
        mock_client = _build_mock_client(request_response=error_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234")

        assert result["success"] is False
        assert result["customer_id"] is None
        assert result["error"] is not None

    # -- create_lead -----------------------------------------------------

    async def test_create_lead_success(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"id": 5001})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead("9001", "leadlock", service_type="AC Repair")

        assert result["success"] is True
        assert result["lead_id"] == "5001"

        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert "/crm/v2/booking-provider/bookings" in call_args.args[1]
        payload = call_args.kwargs["json"]
        assert payload["customerId"] == 9001
        assert payload["source"] == "leadlock"

    async def test_create_lead_error(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        mock_client = _build_mock_client(request_side_effect=httpx.ConnectError("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead("9001", "leadlock")

        assert result["success"] is False
        assert result["lead_id"] is None

    # -- create_booking --------------------------------------------------

    async def test_create_booking_success(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"id": 7001})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="9001",
                appointment_date=date(2026, 3, 15),
                time_start=dt_time(9, 0),
                time_end=dt_time(11, 0),
                service_type="HVAC Repair",
                tech_id="42",
                notes="Customer reports AC not cooling",
            )

        assert result["success"] is True
        assert result["job_id"] == "7001"

        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert "/jpm/v2/jobs" in call_args.args[1]
        payload = call_args.kwargs["json"]
        assert payload["customerId"] == 9001
        assert payload["technicianId"] == 42
        assert "2026-03-15" in payload["scheduledDate"]

    async def test_create_booking_minimal_fields(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"id": 7002})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="9001",
                appointment_date=date(2026, 3, 15),
            )

        assert result["success"] is True
        payload = mock_client.request.call_args.kwargs["json"]
        assert "technicianId" not in payload

    async def test_create_booking_error(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        mock_client = _build_mock_client(
            request_side_effect=httpx.ConnectError("connection refused"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="9001",
                appointment_date=date(2026, 3, 15),
            )

        assert result["success"] is False
        assert result["job_id"] is None

    # -- get_availability ------------------------------------------------

    async def test_get_availability_success(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        slots = [
            {"date": "2026-03-15", "start": "09:00", "end": "11:00"},
            {"date": "2026-03-15", "start": "13:00", "end": "15:00"},
        ]
        api_response = _make_mock_response({"data": slots})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 15), date(2026, 3, 16))

        assert len(result) == 2
        call_args = mock_client.request.call_args
        assert call_args.args[0] == "GET"
        assert "/dispatch/v2/capacity" in call_args.args[1]

    async def test_get_availability_error_returns_empty(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        mock_client = _build_mock_client(request_side_effect=httpx.ConnectError("down"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 15), date(2026, 3, 16))

        assert result == []

    # -- get_technicians -------------------------------------------------

    async def test_get_technicians_success(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        techs = [
            {"id": 1, "name": "Mike Johnson", "active": True},
            {"id": 2, "name": "Sarah Lee", "active": False},
        ]
        api_response = _make_mock_response({"data": techs})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[0]["name"] == "Mike Johnson"
        assert result[0]["active"] is True
        assert result[1]["active"] is False

    async def test_get_technicians_error_returns_empty(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        mock_client = _build_mock_client(request_side_effect=Exception("network failure"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert result == []

    # -- auth headers ----------------------------------------------------

    async def test_request_sends_correct_headers(self):
        crm = self._make_crm()
        crm._token = "my_bearer_tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"id": 1})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await crm._request("GET", "/test")

        call_kwargs = mock_client.request.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == "Bearer my_bearer_tok"
        assert headers["ST-App-Key"] == "test_app_key"
        assert headers["Content-Type"] == "application/json"

    async def test_request_builds_correct_url(self):
        crm = self._make_crm()
        crm._token = "tok"
        crm._token_expires = time.time() + 600

        api_response = _make_mock_response({"ok": True})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await crm._request("GET", "/crm/v2/customers")

        call_args = mock_client.request.call_args
        url = call_args.args[1]
        assert url == "https://api.servicetitan.io/v2/tenant/12345/crm/v2/customers"


# ===================================================================
# Housecall Pro CRM
# ===================================================================

class TestHousecallProCRM:
    """Tests for HousecallProCRM (src/integrations/housecallpro.py)."""

    def _make_crm(self):
        from src.integrations.housecallpro import HousecallProCRM
        return HousecallProCRM(api_key="hcp_test_key_123")

    # -- __init__ --------------------------------------------------------

    def test_init_stores_api_key_and_builds_headers(self):
        crm = self._make_crm()
        assert crm.api_key == "hcp_test_key_123"
        assert crm._headers["Authorization"] == "Bearer hcp_test_key_123"
        assert crm._headers["Content-Type"] == "application/json"
        assert crm._headers["Accept"] == "application/json"

    # -- create_customer -------------------------------------------------

    async def test_create_customer_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "customer": {"id": "hcp_cust_001", "first_name": "John"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234", email="j@d.com")

        assert result["success"] is True
        assert result["customer_id"] == "hcp_cust_001"
        assert result["error"] is None

        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert call_args.args[1].endswith("/customers")
        payload = call_args.kwargs["json"]
        assert payload["customer"]["first_name"] == "John"
        assert payload["customer"]["mobile_number"] == "+15125551234"
        assert payload["customer"]["email"] == "j@d.com"

    async def test_create_customer_unwraps_nested_data(self):
        """Verifies that the response is unwrapped from customer envelope."""
        crm = self._make_crm()
        api_response = _make_mock_response({
            "customer": {"id": "hcp_cust_002"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("Jane", None, "+15125559999")

        assert result["customer_id"] == "hcp_cust_002"

    async def test_create_customer_with_address(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "customer": {"id": "hcp_cust_003"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer(
                "Bob", "Builder", "+15125550000", address="456 Oak Ln",
            )

        assert result["success"] is True
        payload = mock_client.request.call_args.kwargs["json"]
        assert payload["customer"]["address"]["street"] == "456 Oak Ln"

    async def test_create_customer_error(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock()),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234")

        assert result["success"] is False
        assert result["customer_id"] is None
        assert "401" in result["error"]

    # -- create_lead -----------------------------------------------------

    async def test_create_lead_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "estimate": {"id": "est_001"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead("hcp_cust_001", "leadlock", description="Needs AC fix")

        assert result["success"] is True
        assert result["lead_id"] == "est_001"
        call_args = mock_client.request.call_args
        assert "/estimates" in call_args.args[1]

    async def test_create_lead_error(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=httpx.ConnectError("timeout"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead("hcp_cust_001", "leadlock")

        assert result["success"] is False
        assert result["lead_id"] is None

    # -- create_booking --------------------------------------------------

    async def test_create_booking_success_with_times(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "job": {"id": "job_001"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="hcp_cust_001",
                appointment_date=date(2026, 3, 20),
                time_start=dt_time(10, 0),
                time_end=dt_time(12, 0),
                service_type="Plumbing Repair",
                tech_id="emp_42",
                notes="Leaky faucet",
            )

        assert result["success"] is True
        assert result["job_id"] == "job_001"

        payload = mock_client.request.call_args.kwargs["json"]
        job_payload = payload["job"]
        assert job_payload["customer_id"] == "hcp_cust_001"
        assert "2026-03-20T10:00:00" in job_payload["schedule"]["scheduled_start"]
        assert "2026-03-20T12:00:00" in job_payload["schedule"]["scheduled_end"]
        assert job_payload["assigned_employee_ids"] == ["emp_42"]
        assert job_payload["notes"] == "Leaky faucet"
        assert job_payload["description"] == "Plumbing Repair"

    async def test_create_booking_uses_default_times(self):
        """When time_start/time_end are None, defaults to 09:00-11:00."""
        crm = self._make_crm()
        api_response = _make_mock_response({"job": {"id": "job_002"}})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="hcp_cust_001",
                appointment_date=date(2026, 4, 1),
            )

        assert result["success"] is True
        payload = mock_client.request.call_args.kwargs["json"]
        schedule = payload["job"]["schedule"]
        assert "T09:00:00" in schedule["scheduled_start"]
        assert "T11:00:00" in schedule["scheduled_end"]

    async def test_create_booking_error(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="hcp_cust_001",
                appointment_date=date(2026, 3, 20),
            )

        assert result["success"] is False
        assert result["job_id"] is None

    # -- get_availability ------------------------------------------------

    async def test_get_availability_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "availability": [
                {"date": "2026-03-20", "start_time": "09:00", "end_time": "11:00", "employee_id": "emp_1"},
                {"date": "2026-03-20", "start_time": "13:00", "end_time": "15:00", "employee_id": "emp_2"},
            ]
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 20), date(2026, 3, 21))

        assert len(result) == 2
        assert result[0]["date"] == "2026-03-20"
        assert result[0]["start"] == "09:00"
        assert result[0]["tech_id"] == "emp_1"

    async def test_get_availability_error_returns_empty(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=Exception("network error"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 20), date(2026, 3, 21))

        assert result == []

    # -- get_technicians -------------------------------------------------

    async def test_get_technicians_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "employees": [
                {"id": "emp_1", "first_name": "Mike", "last_name": "Jones", "active": True},
                {"id": "emp_2", "first_name": "Sarah", "last_name": "Lee", "active": False},
            ]
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert len(result) == 2
        assert result[0]["id"] == "emp_1"
        assert result[0]["name"] == "Mike Jones"
        assert result[0]["active"] is True
        assert result[1]["active"] is False

    async def test_get_technicians_error_returns_empty(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=Exception("timeout"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert result == []


# ===================================================================
# Jobber CRM (GraphQL)
# ===================================================================

class TestJobberCRM:
    """Tests for JobberCRM (src/integrations/jobber.py)."""

    def _make_crm(self):
        from src.integrations.jobber import JobberCRM
        return JobberCRM(api_key="jobber_test_key")

    # -- __init__ --------------------------------------------------------

    def test_init_stores_credentials(self):
        crm = self._make_crm()
        assert crm.api_key == "jobber_test_key"
        assert crm._headers["Authorization"] == "Bearer jobber_test_key"

    # -- _graphql --------------------------------------------------------

    async def test_graphql_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {"clientCreate": {"client": {"id": "c1"}}}
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm._graphql("mutation { clientCreate { client { id } } }")

        assert result == {"clientCreate": {"client": {"id": "c1"}}}
        call_args = mock_client.post.call_args
        assert "api.getjobber.com/api/graphql" in call_args.args[0]
        payload = call_args.kwargs["json"]
        assert "query" in payload
        assert "variables" in payload

    async def test_graphql_errors_raise_value_error(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "errors": [{"message": "Field 'name' is required"}]
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="Jobber API error"):
                await crm._graphql("mutation { bad }")

    async def test_graphql_sends_correct_headers(self):
        crm = self._make_crm()
        api_response = _make_mock_response({"data": {}})
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await crm._graphql("query { users { nodes { id } } }")

        call_kwargs = mock_client.post.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["Authorization"] == "Bearer jobber_test_key"
        assert headers["Content-Type"] == "application/json"

    # -- create_customer -------------------------------------------------

    async def test_create_customer_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "clientCreate": {
                    "client": {"id": "jb_c_001", "firstName": "John", "lastName": "Doe"},
                    "userErrors": [],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234", email="j@d.com")

        assert result["success"] is True
        assert result["customer_id"] == "jb_c_001"
        assert result["error"] is None

    async def test_create_customer_user_errors(self):
        """Jobber returns userErrors inside the mutation response."""
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "clientCreate": {
                    "client": None,
                    "userErrors": [{"message": "Phone already exists", "path": ["phone"]}],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234")

        assert result["success"] is False
        assert result["customer_id"] is None
        assert "Phone already exists" in result["error"]

    async def test_create_customer_graphql_error(self):
        """Top-level GraphQL errors should be caught and returned as error."""
        crm = self._make_crm()
        api_response = _make_mock_response({
            "errors": [{"message": "Unauthorized"}]
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234")

        assert result["success"] is False
        assert "Unauthorized" in result["error"]

    async def test_create_customer_with_email(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "clientCreate": {
                    "client": {"id": "jb_c_002", "firstName": "Jane", "lastName": ""},
                    "userErrors": [],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("Jane", None, "+15125559999", email="jane@test.com")

        assert result["success"] is True
        # Verify email was included in variables
        call_kwargs = mock_client.post.call_args.kwargs
        variables = call_kwargs["json"]["variables"]
        assert "emails" in variables["input"]

    # -- create_lead -----------------------------------------------------

    async def test_create_lead_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "requestCreate": {
                    "request": {"id": "req_001", "title": "AC Repair"},
                    "userErrors": [],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead(
                "jb_c_001", "leadlock", service_type="AC Repair", description="Unit not cooling",
            )

        assert result["success"] is True
        assert result["lead_id"] == "req_001"

    async def test_create_lead_user_errors(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "requestCreate": {
                    "request": None,
                    "userErrors": [{"message": "Client not found"}],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead("bad_id", "leadlock")

        assert result["success"] is False
        assert "Client not found" in result["error"]

    # -- create_booking --------------------------------------------------

    async def test_create_booking_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "jobCreate": {
                    "job": {"id": "job_jb_001", "title": "HVAC Service"},
                    "userErrors": [],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="jb_c_001",
                appointment_date=date(2026, 3, 20),
                time_start=dt_time(14, 0),
                time_end=dt_time(16, 0),
                service_type="HVAC Service",
                tech_id="tech_1",
                notes="Annual maintenance",
            )

        assert result["success"] is True
        assert result["job_id"] == "job_jb_001"

        # Verify UTC ISO8601 format
        variables = mock_client.post.call_args.kwargs["json"]["variables"]
        job_input = variables["input"]
        assert "2026-03-20T14:00:00+00:00" in job_input["startAt"]
        assert "2026-03-20T16:00:00+00:00" in job_input["endAt"]
        assert job_input["assignedUserIds"] == ["tech_1"]

    async def test_create_booking_default_times(self):
        """Without explicit times, defaults to 09:00-11:00 UTC."""
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "jobCreate": {
                    "job": {"id": "job_jb_002", "title": "Service Call"},
                    "userErrors": [],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="jb_c_001",
                appointment_date=date(2026, 4, 1),
            )

        assert result["success"] is True
        variables = mock_client.post.call_args.kwargs["json"]["variables"]
        assert "09:00:00" in variables["input"]["startAt"]
        assert "11:00:00" in variables["input"]["endAt"]

    async def test_create_booking_user_errors(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "jobCreate": {
                    "job": None,
                    "userErrors": [{"message": "Schedule conflict"}],
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="jb_c_001",
                appointment_date=date(2026, 3, 20),
            )

        assert result["success"] is False
        assert "Schedule conflict" in result["error"]

    async def test_create_booking_exception(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            post_side_effect=httpx.ConnectError("connection refused"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="jb_c_001",
                appointment_date=date(2026, 3, 20),
            )

        assert result["success"] is False
        assert result["job_id"] is None

    # -- get_availability ------------------------------------------------

    async def test_get_availability_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "calendarEvents": {
                    "nodes": [
                        {
                            "id": "evt_1",
                            "startAt": "2026-03-20T09:00:00Z",
                            "endAt": "2026-03-20T11:00:00Z",
                            "assignedUsers": [{"id": "u1"}],
                        },
                    ]
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 20), date(2026, 3, 21))

        assert len(result) == 1
        assert result[0]["date"] == "2026-03-20"
        assert result[0]["start"] == "09:00"
        assert result[0]["end"] == "11:00"
        assert result[0]["tech_id"] == "u1"

    async def test_get_availability_no_assigned_users(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "calendarEvents": {
                    "nodes": [
                        {
                            "id": "evt_2",
                            "startAt": "2026-03-20T09:00:00Z",
                            "endAt": "2026-03-20T11:00:00Z",
                            "assignedUsers": [],
                        },
                    ]
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 20), date(2026, 3, 21))

        assert result[0]["tech_id"] is None

    async def test_get_availability_error_returns_empty(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            post_side_effect=Exception("network failure"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 20), date(2026, 3, 21))

        assert result == []

    # -- get_technicians -------------------------------------------------

    async def test_get_technicians_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "data": {
                "users": {
                    "nodes": [
                        {"id": "u1", "name": {"full": "Mike Johnson"}, "role": "TECH", "isActive": True},
                        {"id": "u2", "name": {"full": "Sarah Lee"}, "role": "ADMIN", "isActive": False},
                    ]
                }
            }
        })
        mock_client = _build_mock_client(post_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert len(result) == 2
        assert result[0]["id"] == "u1"
        assert result[0]["name"] == "Mike Johnson"
        assert result[0]["active"] is True
        assert result[1]["active"] is False

    async def test_get_technicians_error_returns_empty(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            post_side_effect=Exception("timeout"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert result == []


# ===================================================================
# GoHighLevel CRM
# ===================================================================

class TestGoHighLevelCRM:
    """Tests for GoHighLevelCRM (src/integrations/gohighlevel.py)."""

    def _make_crm(self):
        from src.integrations.gohighlevel import GoHighLevelCRM
        return GoHighLevelCRM(api_key="ghl_test_key", location_id="loc_abc")

    # -- __init__ --------------------------------------------------------

    def test_init_stores_credentials_and_version_header(self):
        crm = self._make_crm()
        assert crm.api_key == "ghl_test_key"
        assert crm.location_id == "loc_abc"
        assert crm._headers["Authorization"] == "Bearer ghl_test_key"
        assert crm._headers["Version"] == "2021-07-28"
        assert crm._headers["Content-Type"] == "application/json"

    # -- create_customer -------------------------------------------------

    async def test_create_customer_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "contact": {"id": "ghl_c_001", "firstName": "John"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer(
                "John", "Doe", "+15125551234", email="j@d.com", address="789 Pine St",
            )

        assert result["success"] is True
        assert result["customer_id"] == "ghl_c_001"
        assert result["error"] is None

        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert "/contacts/" in call_args.args[1]
        payload = call_args.kwargs["json"]
        assert payload["firstName"] == "John"
        assert payload["locationId"] == "loc_abc"
        assert payload["email"] == "j@d.com"
        assert payload["address1"] == "789 Pine St"

    async def test_create_customer_includes_location_id(self):
        crm = self._make_crm()
        api_response = _make_mock_response({"contact": {"id": "ghl_c_002"}})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await crm.create_customer("Jane", None, "+15125559999")

        payload = mock_client.request.call_args.kwargs["json"]
        assert payload["locationId"] == "loc_abc"

    async def test_create_customer_error(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock()),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_customer("John", "Doe", "+15125551234")

        assert result["success"] is False
        assert result["customer_id"] is None

    # -- create_lead -----------------------------------------------------

    async def test_create_lead_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "opportunity": {"id": "opp_001"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead(
                "ghl_c_001", "leadlock", service_type="Roof Repair",
            )

        assert result["success"] is True
        assert result["lead_id"] == "opp_001"

        payload = mock_client.request.call_args.kwargs["json"]
        assert payload["contactId"] == "ghl_c_001"
        assert payload["locationId"] == "loc_abc"
        assert payload["source"] == "leadlock"
        assert payload["status"] == "open"

    async def test_create_lead_error(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=Exception("server error"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_lead("ghl_c_001", "leadlock")

        assert result["success"] is False
        assert result["lead_id"] is None

    # -- create_booking --------------------------------------------------

    async def test_create_booking_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "event": {"id": "evt_ghl_001"}
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="ghl_c_001",
                appointment_date=date(2026, 3, 25),
                time_start=dt_time(10, 30),
                time_end=dt_time(12, 30),
                service_type="Solar Panel Install",
                tech_id="cal_tech_1",
                notes="Roof must be clear",
            )

        assert result["success"] is True
        assert result["job_id"] == "evt_ghl_001"

        call_args = mock_client.request.call_args
        assert call_args.args[0] == "POST"
        assert "/calendars/events/appointments" in call_args.args[1]
        payload = call_args.kwargs["json"]
        assert payload["contactId"] == "ghl_c_001"
        assert payload["locationId"] == "loc_abc"
        assert payload["calendarId"] == "cal_tech_1"
        assert "2026-03-25" in payload["startTime"]
        assert "10:30:00" in payload["startTime"]

    async def test_create_booking_default_times(self):
        """Without explicit times, defaults to 09:00-11:00 UTC."""
        crm = self._make_crm()
        api_response = _make_mock_response({"event": {"id": "evt_ghl_002"}})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="ghl_c_001",
                appointment_date=date(2026, 4, 1),
            )

        assert result["success"] is True
        payload = mock_client.request.call_args.kwargs["json"]
        assert "09:00:00" in payload["startTime"]
        assert "11:00:00" in payload["endTime"]

    async def test_create_booking_no_calendar_id_without_tech(self):
        """When tech_id is None, calendarId should NOT be in payload."""
        crm = self._make_crm()
        api_response = _make_mock_response({"event": {"id": "evt_ghl_003"}})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await crm.create_booking(
                customer_id="ghl_c_001",
                appointment_date=date(2026, 4, 1),
            )

        payload = mock_client.request.call_args.kwargs["json"]
        assert "calendarId" not in payload

    async def test_create_booking_error(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=httpx.ConnectError("refused"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.create_booking(
                customer_id="ghl_c_001",
                appointment_date=date(2026, 3, 25),
            )

        assert result["success"] is False
        assert result["job_id"] is None

    # -- get_availability ------------------------------------------------

    async def test_get_availability_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "slots": [
                {"startTime": "2026-03-25T09:00:00Z", "endTime": "2026-03-25T11:00:00Z", "calendarId": "cal_1"},
            ]
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 25), date(2026, 3, 26))

        assert len(result) == 1
        assert result[0]["date"] == "2026-03-25"
        assert result[0]["start"] == "09:00"
        assert result[0]["end"] == "11:00"
        assert result[0]["tech_id"] == "cal_1"

        # Verify correct endpoint: /calendars/{location_id}/free-slots
        call_args = mock_client.request.call_args
        assert call_args.args[0] == "GET"
        assert "/calendars/loc_abc/free-slots" in call_args.args[1]

    async def test_get_availability_error_returns_empty(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=Exception("network failure"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_availability(date(2026, 3, 25), date(2026, 3, 26))

        assert result == []

    # -- get_technicians -------------------------------------------------

    async def test_get_technicians_success(self):
        crm = self._make_crm()
        api_response = _make_mock_response({
            "users": [
                {"id": "u_1", "firstName": "Mike", "lastName": "Johnson", "roles": ["tech"]},
                {"id": "u_2", "firstName": "Sarah", "lastName": "Lee", "roles": ["admin", "tech"]},
            ]
        })
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert len(result) == 2
        assert result[0]["id"] == "u_1"
        assert result[0]["name"] == "Mike Johnson"
        assert result[0]["specialty"] == ["tech"]
        assert result[0]["active"] is True

        # Verify locationId was sent as query param
        call_kwargs = mock_client.request.call_args.kwargs
        assert call_kwargs["params"]["locationId"] == "loc_abc"

    async def test_get_technicians_error_returns_empty(self):
        crm = self._make_crm()
        mock_client = _build_mock_client(
            request_side_effect=Exception("timeout"),
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await crm.get_technicians()

        assert result == []

    # -- version header --------------------------------------------------

    async def test_request_sends_version_header(self):
        crm = self._make_crm()
        api_response = _make_mock_response({"ok": True})
        mock_client = _build_mock_client(request_response=api_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await crm._request("GET", "/test")

        headers = mock_client.request.call_args.kwargs["headers"]
        assert headers["Version"] == "2021-07-28"


# ===================================================================
# Google Sheets CRM (Fallback)
# ===================================================================

class TestGoogleSheetsCRM:
    """Tests for GoogleSheetsCRM (src/integrations/google_sheets.py)."""

    def _make_crm(self):
        from src.integrations.google_sheets import GoogleSheetsCRM
        return GoogleSheetsCRM(spreadsheet_id="sheet_abc_123")

    # -- __init__ --------------------------------------------------------

    def test_init_stores_spreadsheet_id(self):
        crm = self._make_crm()
        assert crm.spreadsheet_id == "sheet_abc_123"
        assert crm.credentials_json is None

    def test_init_with_credentials(self):
        from src.integrations.google_sheets import GoogleSheetsCRM
        crm = GoogleSheetsCRM(
            spreadsheet_id="sheet_xyz",
            credentials_json='{"type": "service_account"}',
        )
        assert crm.credentials_json == '{"type": "service_account"}'

    # -- create_customer -------------------------------------------------

    async def test_create_customer_returns_phone_as_id(self):
        crm = self._make_crm()
        result = await crm.create_customer("John", "Doe", "+15125551234", email="j@d.com")

        assert result["success"] is True
        assert result["customer_id"] == "+15125551234"
        assert result["error"] is None

    async def test_create_customer_without_optional_fields(self):
        crm = self._make_crm()
        result = await crm.create_customer("Jane", None, "+15125559999")

        assert result["success"] is True
        assert result["customer_id"] == "+15125559999"

    # -- create_lead -----------------------------------------------------

    async def test_create_lead_success(self):
        crm = self._make_crm()
        result = await crm.create_lead("+15125551234", "leadlock", service_type="AC Repair")

        assert result["success"] is True
        assert result["lead_id"] == "+15125551234"
        assert result["error"] is None

    # -- create_booking --------------------------------------------------

    async def test_create_booking_success(self):
        crm = self._make_crm()
        result = await crm.create_booking(
            customer_id="+15125551234",
            appointment_date=date(2026, 3, 20),
            time_start=dt_time(9, 0),
            time_end=dt_time(11, 0),
            service_type="HVAC Repair",
            tech_id="mike",
            notes="Customer reports no cool air",
        )

        assert result["success"] is True
        assert result["job_id"] == "sheet_+15125551234"
        assert result["error"] is None

    async def test_create_booking_minimal(self):
        crm = self._make_crm()
        result = await crm.create_booking(
            customer_id="+15125559999",
            appointment_date=date(2026, 4, 1),
        )

        assert result["success"] is True
        assert "sheet_" in result["job_id"]

    # -- get_availability (unsupported) ----------------------------------

    async def test_get_availability_returns_empty_list(self):
        crm = self._make_crm()
        result = await crm.get_availability(date(2026, 3, 20), date(2026, 3, 21))
        assert result == []

    # -- get_technicians (unsupported) -----------------------------------

    async def test_get_technicians_returns_empty_list(self):
        crm = self._make_crm()
        result = await crm.get_technicians()
        assert result == []

    # -- _append_row -----------------------------------------------------

    async def test_append_row_returns_true(self):
        crm = self._make_crm()
        result = await crm._append_row("Customers", ["2026-01-01", "John", "Doe", "+1512555"])
        assert result is True

    async def test_append_row_logs_sheet_info(self):
        """Verify that _append_row logs the spreadsheet and sheet name."""
        crm = self._make_crm()
        with patch("src.integrations.google_sheets.logger") as mock_logger:
            await crm._append_row("Bookings", ["data"])
            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args.args[0]
            assert "Google Sheets append" in log_msg


# ===================================================================
# Cross-CRM: Abstract interface compliance
# ===================================================================

class TestCRMBaseCompliance:
    """Verify all CRM classes properly implement the CRMBase interface."""

    def test_servicetitan_is_subclass(self):
        from src.integrations.servicetitan import ServiceTitanCRM
        from src.integrations.crm_base import CRMBase
        assert issubclass(ServiceTitanCRM, CRMBase)

    def test_housecallpro_is_subclass(self):
        from src.integrations.housecallpro import HousecallProCRM
        from src.integrations.crm_base import CRMBase
        assert issubclass(HousecallProCRM, CRMBase)

    def test_jobber_is_subclass(self):
        from src.integrations.jobber import JobberCRM
        from src.integrations.crm_base import CRMBase
        assert issubclass(JobberCRM, CRMBase)

    def test_gohighlevel_is_subclass(self):
        from src.integrations.gohighlevel import GoHighLevelCRM
        from src.integrations.crm_base import CRMBase
        assert issubclass(GoHighLevelCRM, CRMBase)

    def test_google_sheets_is_subclass(self):
        from src.integrations.google_sheets import GoogleSheetsCRM
        from src.integrations.crm_base import CRMBase
        assert issubclass(GoogleSheetsCRM, CRMBase)

    @pytest.mark.parametrize("crm_module,crm_class", [
        ("src.integrations.servicetitan", "ServiceTitanCRM"),
        ("src.integrations.housecallpro", "HousecallProCRM"),
        ("src.integrations.jobber", "JobberCRM"),
        ("src.integrations.gohighlevel", "GoHighLevelCRM"),
        ("src.integrations.google_sheets", "GoogleSheetsCRM"),
    ])
    def test_crm_has_all_required_methods(self, crm_module, crm_class):
        import importlib
        module = importlib.import_module(crm_module)
        cls = getattr(module, crm_class)
        required_methods = [
            "create_customer",
            "create_lead",
            "create_booking",
            "get_availability",
            "get_technicians",
        ]
        for method_name in required_methods:
            assert hasattr(cls, method_name), f"{crm_class} missing {method_name}"
            assert callable(getattr(cls, method_name)), f"{crm_class}.{method_name} is not callable"
