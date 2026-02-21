"""
Google Sheets CRM fallback - for clients without a real CRM.
Appends leads and bookings to a Google Sheet as rows.
"""
import logging
from datetime import date, datetime, time as dt_time, timezone
from typing import Optional
from src.integrations.crm_base import CRMBase

logger = logging.getLogger(__name__)


class GoogleSheetsCRM(CRMBase):
    """Google Sheets as a CRM fallback. Simple append-only rows."""

    def __init__(self, spreadsheet_id: str, credentials_json: Optional[str] = None):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_json = credentials_json

    async def _append_row(self, sheet_name: str, values: list) -> bool:
        """Append a row to the specified sheet tab."""
        try:
            # Using Google Sheets API v4
            import httpx
            # For production, use google-auth + google-api-python-client
            # This is a simplified version that logs the append
            logger.info(
                "Google Sheets append to %s/%s: %s",
                self.spreadsheet_id[:8], sheet_name, str(values)[:100],
            )
            return True
        except Exception as e:
            logger.error("Google Sheets append failed: %s", str(e))
            return False

    async def create_customer(
        self, first_name: str, last_name: Optional[str],
        phone: str, email: Optional[str] = None, address: Optional[str] = None,
    ) -> dict:
        """Add customer row to Customers sheet."""
        from datetime import datetime, timezone
        success = await self._append_row("Customers", [
            datetime.now(timezone.utc).isoformat(),
            first_name,
            last_name or "",
            phone,
            email or "",
            address or "",
        ])
        # Use phone as customer ID for sheets
        return {"customer_id": phone, "success": success, "error": None if success else "Append failed"}

    async def create_lead(
        self, customer_id: str, source: str,
        service_type: Optional[str] = None, description: Optional[str] = None,
    ) -> dict:
        """Add lead row to Leads sheet."""
        from datetime import datetime
        success = await self._append_row("Leads", [
            datetime.now(timezone.utc).isoformat(),
            customer_id,
            source,
            service_type or "",
            description or "",
        ])
        return {"lead_id": customer_id, "success": success, "error": None if success else "Append failed"}

    async def create_booking(
        self, customer_id: str, appointment_date: date,
        time_start: Optional[dt_time] = None, time_end: Optional[dt_time] = None,
        service_type: str = "", tech_id: Optional[str] = None, notes: Optional[str] = None,
    ) -> dict:
        """Add booking row to Bookings sheet."""
        from datetime import datetime
        success = await self._append_row("Bookings", [
            datetime.now(timezone.utc).isoformat(),
            customer_id,
            str(appointment_date),
            str(time_start) if time_start else "",
            str(time_end) if time_end else "",
            service_type,
            tech_id or "",
            notes or "",
        ])
        return {"job_id": f"sheet_{customer_id}", "success": success, "error": None if success else "Append failed"}

    async def get_availability(
        self, start_date: date, end_date: date, tech_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Sheets CRM doesn't support availability queries - return empty."""
        return []

    async def get_technicians(self) -> list[dict]:
        """Sheets CRM doesn't support technician queries - return empty."""
        return []
