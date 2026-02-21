"""
CRM integration tests.
"""
import pytest
from src.integrations.google_sheets import GoogleSheetsCRM


class TestGoogleSheetsCRM:
    @pytest.mark.asyncio
    async def test_create_customer(self):
        crm = GoogleSheetsCRM(spreadsheet_id="test_sheet_id")
        result = await crm.create_customer(
            first_name="John",
            last_name="Smith",
            phone="+15125559876",
            email="john@example.com",
        )
        assert result["success"] is True
        assert result["customer_id"] == "+15125559876"

    @pytest.mark.asyncio
    async def test_create_lead(self):
        crm = GoogleSheetsCRM(spreadsheet_id="test_sheet_id")
        result = await crm.create_lead(
            customer_id="+15125559876",
            source="website",
            service_type="AC Repair",
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_availability_returns_empty(self):
        """Sheets CRM doesn't support availability - should return empty."""
        from datetime import date
        crm = GoogleSheetsCRM(spreadsheet_id="test_sheet_id")
        result = await crm.get_availability(date(2026, 2, 16), date(2026, 2, 20))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_technicians_returns_empty(self):
        """Sheets CRM doesn't support technicians - should return empty."""
        crm = GoogleSheetsCRM(spreadsheet_id="test_sheet_id")
        result = await crm.get_technicians()
        assert result == []
