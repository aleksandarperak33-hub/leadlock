"""
Tests for src/api/integrations.py - CRM integration endpoints (test, connect, status).
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from src.api.integrations import (
    test_integration as _test_integration_endpoint,
    connect_integration,
    integration_status,
    _get_crm_instance,
    SUPPORTED_CRMS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(**overrides):
    """Build a mock Client object for integration tests."""
    defaults = {
        "id": uuid.uuid4(),
        "business_name": "HVAC Pro",
        "tier": "pro",
        "crm_type": None,
        "crm_api_key_encrypted": None,
        "crm_tenant_id": None,
    }
    defaults.update(overrides)
    client = MagicMock()
    for k, v in defaults.items():
        setattr(client, k, v)
    return client


def _make_mock_request(json_data=None):
    """Build a mock Request object."""
    mock_request = AsyncMock()
    if json_data is not None:
        mock_request.json = AsyncMock(return_value=json_data)
    else:
        mock_request.json = AsyncMock(side_effect=Exception("Invalid JSON"))
    return mock_request


# ---------------------------------------------------------------------------
# _get_crm_instance (factory)
# ---------------------------------------------------------------------------


class TestGetCrmInstance:
    def test_housecallpro(self):
        """housecallpro type returns HousecallProCRM instance."""
        with patch("src.integrations.housecallpro.HousecallProCRM") as mock_cls:
            result = _get_crm_instance("housecallpro", "api_key_123")
            mock_cls.assert_called_once_with(api_key="api_key_123")
            assert result is not None

    def test_jobber(self):
        """jobber type returns JobberCRM instance."""
        with patch("src.integrations.jobber.JobberCRM") as mock_cls:
            result = _get_crm_instance("jobber", "api_key_456")
            mock_cls.assert_called_once_with(api_key="api_key_456")
            assert result is not None

    def test_gohighlevel(self):
        """gohighlevel type returns GoHighLevelCRM instance with location_id."""
        with patch("src.integrations.gohighlevel.GoHighLevelCRM") as mock_cls:
            result = _get_crm_instance("gohighlevel", "api_key_789", "location_abc")
            mock_cls.assert_called_once_with(api_key="api_key_789", location_id="location_abc")
            assert result is not None

    def test_unsupported_crm_returns_none(self):
        """Unsupported CRM type returns None."""
        result = _get_crm_instance("salesforce", "key123")
        assert result is None

    def test_servicetitan_returns_none(self):
        """ServiceTitan is in SUPPORTED_CRMS but not in factory (API-key based)."""
        result = _get_crm_instance("servicetitan", "key123")
        assert result is None


# ---------------------------------------------------------------------------
# POST /api/v1/integrations/test
# ---------------------------------------------------------------------------


class TestTestIntegration:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        """Invalid JSON body returns 400."""
        request = _make_mock_request()  # json() raises
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "Invalid JSON" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unsupported_crm_type_returns_400(self):
        """Unsupported CRM type returns 400 with valid options."""
        request = _make_mock_request(json_data={"crm_type": "salesforce", "api_key": "key"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "Unsupported CRM" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_google_sheets_always_returns_connected(self):
        """Google Sheets doesn't need an API key, always returns connected."""
        request = _make_mock_request(json_data={"crm_type": "google_sheets"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        result = await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert result["connected"] is True
        assert "always available" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_400(self):
        """Non-Google-Sheets CRM without API key returns 400."""
        request = _make_mock_request(json_data={"crm_type": "jobber", "api_key": ""})
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "API key is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_crm_factory_returns_none_for_unsupported_testing(self):
        """CRM type in SUPPORTED_CRMS but not in factory returns 400."""
        request = _make_mock_request(
            json_data={"crm_type": "servicetitan", "api_key": "key123"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400
        assert "not supported for testing" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_successful_connection(self):
        """Successful CRM connection returns technician count."""
        request = _make_mock_request(
            json_data={"crm_type": "housecallpro", "api_key": "valid_key"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        mock_crm = AsyncMock()
        mock_crm.get_technicians = AsyncMock(return_value=[
            {"id": "1", "name": "Mike"},
            {"id": "2", "name": "Sarah"},
        ])

        with patch("src.api.integrations._get_crm_instance", return_value=mock_crm):
            result = await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert result["connected"] is True
        assert result["technicians_found"] == 2
        assert "housecallpro" in result["message"]

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """CRM connection failure returns connected=False with error message."""
        request = _make_mock_request(
            json_data={"crm_type": "jobber", "api_key": "bad_key"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        mock_crm = AsyncMock()
        mock_crm.get_technicians = AsyncMock(
            side_effect=Exception("401 Unauthorized")
        )

        with patch("src.api.integrations._get_crm_instance", return_value=mock_crm):
            result = await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert result["connected"] is False
        assert "401 Unauthorized" in result["message"]
        assert result["technicians_found"] == 0

    @pytest.mark.asyncio
    async def test_crm_type_normalized_to_lowercase(self):
        """CRM type is normalized to lowercase and stripped."""
        request = _make_mock_request(
            json_data={"crm_type": " HouseCallPro ", "api_key": "key"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        mock_crm = AsyncMock()
        mock_crm.get_technicians = AsyncMock(return_value=[])

        with patch("src.api.integrations._get_crm_instance", return_value=mock_crm):
            result = await _test_integration_endpoint(request=request, db=mock_db, client=mock_client)

        assert result["connected"] is True


# ---------------------------------------------------------------------------
# POST /api/v1/integrations/connect
# ---------------------------------------------------------------------------


class TestConnectIntegration:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        """Invalid JSON body returns 400."""
        request = _make_mock_request()
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await connect_integration(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unsupported_crm_type_returns_400(self):
        """Unsupported CRM type returns 400."""
        request = _make_mock_request(json_data={"crm_type": "salesforce"})
        mock_db = AsyncMock()
        mock_client = _make_mock_client()

        with pytest.raises(HTTPException) as exc_info:
            await connect_integration(request=request, db=mock_db, client=mock_client)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_successful_connect(self):
        """Successful CRM connection sets client properties."""
        request = _make_mock_request(
            json_data={"crm_type": "jobber", "api_key": "new_key_123", "tenant_id": "t_1"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(tier="pro", crm_type=None)

        with patch("src.api.integrations.get_crm_integration_limit", return_value=None):
            result = await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert result["status"] == "connected"
        assert result["crm_type"] == "jobber"
        assert mock_client.crm_type == "jobber"
        assert mock_client.crm_api_key_encrypted == "new_key_123"
        assert mock_client.crm_tenant_id == "t_1"
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_starter_tier_allows_first_crm(self):
        """Starter tier can connect its first CRM (limit=1)."""
        request = _make_mock_request(
            json_data={"crm_type": "housecallpro", "api_key": "key1"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(tier="starter", crm_type=None)

        with patch("src.api.integrations.get_crm_integration_limit", return_value=1):
            result = await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert result["status"] == "connected"

    @pytest.mark.asyncio
    async def test_starter_tier_blocks_second_crm(self):
        """Starter tier blocks connecting a different CRM when one exists."""
        request = _make_mock_request(
            json_data={"crm_type": "jobber", "api_key": "key2"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            tier="starter",
            crm_type="housecallpro",
        )

        with (
            patch("src.api.integrations.get_crm_integration_limit", return_value=1),
            pytest.raises(HTTPException) as exc_info,
        ):
            await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert exc_info.value.status_code == 403
        assert "Starter plan allows 1 CRM" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_starter_tier_allows_same_crm_reconnect(self):
        """Starter tier can reconnect to the same CRM type."""
        request = _make_mock_request(
            json_data={"crm_type": "housecallpro", "api_key": "new_key"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            tier="starter",
            crm_type="housecallpro",
        )

        with patch("src.api.integrations.get_crm_integration_limit", return_value=1):
            result = await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert result["status"] == "connected"

    @pytest.mark.asyncio
    async def test_starter_tier_allows_google_sheets_plus_crm(self):
        """Starter tier with google_sheets can still connect a real CRM."""
        request = _make_mock_request(
            json_data={"crm_type": "jobber", "api_key": "key1"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            tier="starter",
            crm_type="google_sheets",
        )

        with patch("src.api.integrations.get_crm_integration_limit", return_value=1):
            result = await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert result["status"] == "connected"

    @pytest.mark.asyncio
    async def test_pro_tier_allows_multiple_crms(self):
        """Pro tier with unlimited CRMs can always connect."""
        request = _make_mock_request(
            json_data={"crm_type": "jobber", "api_key": "key3"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            tier="pro",
            crm_type="housecallpro",
        )

        with patch("src.api.integrations.get_crm_integration_limit", return_value=None):
            result = await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert result["status"] == "connected"

    @pytest.mark.asyncio
    async def test_connect_without_api_key_keeps_existing(self):
        """Connecting without API key doesn't overwrite existing encrypted key."""
        request = _make_mock_request(
            json_data={"crm_type": "google_sheets"}
        )
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            crm_api_key_encrypted="old_key_encrypted",
        )

        with patch("src.api.integrations.get_crm_integration_limit", return_value=None):
            result = await connect_integration(
                request=request, db=mock_db, client=mock_client
            )

        assert result["status"] == "connected"
        # crm_api_key_encrypted should not have been overwritten
        assert mock_client.crm_api_key_encrypted == "old_key_encrypted"


# ---------------------------------------------------------------------------
# GET /api/v1/integrations/status
# ---------------------------------------------------------------------------


class TestIntegrationStatus:
    @pytest.mark.asyncio
    async def test_no_crm_configured(self):
        """Client with no CRM returns not connected."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            crm_type=None,
            crm_api_key_encrypted=None,
            crm_tenant_id=None,
        )

        result = await integration_status(db=mock_db, client=mock_client)

        assert result["crm_type"] is None
        assert result["connected"] is False
        assert result["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_google_sheets_always_connected(self):
        """Google Sheets is always connected even without API key."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            crm_type="google_sheets",
            crm_api_key_encrypted=None,
            crm_tenant_id=None,
        )

        result = await integration_status(db=mock_db, client=mock_client)

        assert result["crm_type"] == "google_sheets"
        assert result["connected"] is True
        assert result["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_crm_with_api_key_connected(self):
        """CRM with API key is marked as connected."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            crm_type="housecallpro",
            crm_api_key_encrypted="encrypted_key_here",
            crm_tenant_id="tenant_123",
        )

        result = await integration_status(db=mock_db, client=mock_client)

        assert result["crm_type"] == "housecallpro"
        assert result["connected"] is True
        assert result["has_api_key"] is True
        assert result["tenant_id"] == "tenant_123"

    @pytest.mark.asyncio
    async def test_crm_without_api_key_not_connected(self):
        """CRM type set but no API key means not connected (unless google_sheets)."""
        mock_db = AsyncMock()
        mock_client = _make_mock_client(
            crm_type="jobber",
            crm_api_key_encrypted=None,
            crm_tenant_id=None,
        )

        result = await integration_status(db=mock_db, client=mock_client)

        assert result["crm_type"] == "jobber"
        assert result["connected"] is False
        assert result["has_api_key"] is False


# ---------------------------------------------------------------------------
# SUPPORTED_CRMS constant
# ---------------------------------------------------------------------------


class TestSupportedCrms:
    def test_expected_crms_included(self):
        """All expected CRM types are in SUPPORTED_CRMS."""
        expected = {"housecallpro", "jobber", "gohighlevel", "servicetitan", "google_sheets"}
        assert SUPPORTED_CRMS == expected

    def test_crms_are_lowercase(self):
        """All CRM identifiers are lowercase."""
        for crm in SUPPORTED_CRMS:
            assert crm == crm.lower()
