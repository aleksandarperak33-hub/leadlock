"""
ServiceTitan V2 CRM integration.
Uses OAuth 2.0 client credentials flow. Token expires every 15 minutes.
Requires ST-App-Key header for all requests.
"""
import logging
import time
from datetime import date, time as dt_time
from typing import Optional
import httpx
from src.integrations.crm_base import CRMBase

logger = logging.getLogger(__name__)

ST_AUTH_URL = "https://auth.servicetitan.io/connect/token"
ST_API_BASE = "https://api.servicetitan.io"


class ServiceTitanCRM(CRMBase):
    """ServiceTitan V2 API integration."""

    def __init__(self, client_id: str, client_secret: str, app_key: str, tenant_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.app_key = app_key
        self.tenant_id = tenant_id
        self._token: Optional[str] = None
        self._token_expires: float = 0

    async def _get_token(self) -> str:
        """Get or refresh OAuth token (15-min expiry)."""
        if self._token and time.time() < self._token_expires:
            return self._token

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                ST_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["access_token"]
            # Refresh 1 minute before expiry
            self._token_expires = time.time() + data.get("expires_in", 900) - 60
            return self._token

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make authenticated request to ServiceTitan API."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method,
                f"{ST_API_BASE}/v2/tenant/{self.tenant_id}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "ST-App-Key": self.app_key,
                    "Content-Type": "application/json",
                },
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    async def create_customer(
        self, first_name: str, last_name: Optional[str],
        phone: str, email: Optional[str] = None, address: Optional[str] = None,
    ) -> dict:
        """Create customer in ServiceTitan."""
        try:
            data = await self._request("POST", "/crm/v2/customers", json={
                "name": f"{first_name} {last_name or ''}".strip(),
                "type": "Residential",
                "contacts": [{"type": "Phone", "value": phone}],
            })
            return {"customer_id": str(data.get("id")), "success": True, "error": None}
        except Exception as e:
            logger.error("ServiceTitan create_customer failed: %s", str(e))
            return {"customer_id": None, "success": False, "error": str(e)}

    async def create_lead(
        self, customer_id: str, source: str,
        service_type: Optional[str] = None, description: Optional[str] = None,
    ) -> dict:
        """Create lead/opportunity in ServiceTitan."""
        try:
            data = await self._request("POST", "/crm/v2/booking-provider/bookings", json={
                "customerId": int(customer_id),
                "source": source,
                "summary": description or service_type or "New lead from LeadLock",
            })
            return {"lead_id": str(data.get("id")), "success": True, "error": None}
        except Exception as e:
            logger.error("ServiceTitan create_lead failed: %s", str(e))
            return {"lead_id": None, "success": False, "error": str(e)}

    async def create_booking(
        self, customer_id: str, appointment_date: date,
        time_start: Optional[dt_time] = None, time_end: Optional[dt_time] = None,
        service_type: str = "", tech_id: Optional[str] = None, notes: Optional[str] = None,
    ) -> dict:
        """Create job/booking in ServiceTitan."""
        try:
            data = await self._request("POST", "/jpm/v2/jobs", json={
                "customerId": int(customer_id),
                "typeId": 1,
                "summary": notes or f"LeadLock booking: {service_type}",
            })
            return {"job_id": str(data.get("id")), "success": True, "error": None}
        except Exception as e:
            logger.error("ServiceTitan create_booking failed: %s", str(e))
            return {"job_id": None, "success": False, "error": str(e)}

    async def get_availability(
        self, start_date: date, end_date: date, tech_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get available slots from ServiceTitan dispatch."""
        try:
            data = await self._request("GET", "/dispatch/v2/capacity", params={
                "startsOnOrAfter": start_date.isoformat(),
                "endsOnOrBefore": end_date.isoformat(),
            })
            return data.get("data", [])
        except Exception as e:
            logger.error("ServiceTitan get_availability failed: %s", str(e))
            return []

    async def get_technicians(self) -> list[dict]:
        """Get technicians from ServiceTitan."""
        try:
            data = await self._request("GET", "/settings/v2/technicians")
            return [
                {"id": str(t["id"]), "name": t.get("name", ""), "active": t.get("active", True)}
                for t in data.get("data", [])
            ]
        except Exception as e:
            logger.error("ServiceTitan get_technicians failed: %s", str(e))
            return []
