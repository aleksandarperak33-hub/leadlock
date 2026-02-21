"""
Housecall Pro CRM integration - REST API v1.

Auth: Bearer token via API key.
Docs: https://docs.housecallpro.com
All calls have 10-second timeout per project standard.
"""
import logging
from datetime import date, time as dt_time
from typing import Optional

import httpx

from src.integrations.crm_base import CRMBase

logger = logging.getLogger(__name__)

BASE_URL = "https://api.housecallpro.com"
TIMEOUT = 10.0


class HousecallProCRM(CRMBase):
    """Housecall Pro API integration."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, json: Optional[dict] = None) -> dict:
        """Make an authenticated request to the Housecall Pro API."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(
                method,
                f"{BASE_URL}{path}",
                headers=self._headers,
                json=json,
            )
            response.raise_for_status()
            return response.json()

    async def create_customer(
        self,
        first_name: str,
        last_name: Optional[str],
        phone: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> dict:
        """Create a customer in Housecall Pro."""
        try:
            payload = {
                "first_name": first_name,
                "last_name": last_name or "",
                "mobile_number": phone,
            }
            if email:
                payload["email"] = email
            if address:
                payload["address"] = {"street": address}

            data = await self._request("POST", "/customers", json={"customer": payload})
            customer = data.get("customer", data)
            customer_id = customer.get("id")

            logger.info("HCP customer created: %s", customer_id)
            return {"customer_id": customer_id, "success": True, "error": None}
        except Exception as e:
            logger.error("HCP create_customer failed: %s", str(e))
            return {"customer_id": None, "success": False, "error": str(e)}

    async def create_lead(
        self,
        customer_id: str,
        source: str,
        service_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Create a lead/estimate in Housecall Pro."""
        try:
            payload = {
                "customer_id": customer_id,
                "lead_source": source,
            }
            if description:
                payload["notes"] = description

            data = await self._request("POST", "/estimates", json={"estimate": payload})
            estimate = data.get("estimate", data)
            return {"lead_id": estimate.get("id"), "success": True, "error": None}
        except Exception as e:
            logger.error("HCP create_lead failed: %s", str(e))
            return {"lead_id": None, "success": False, "error": str(e)}

    async def create_booking(
        self,
        customer_id: str,
        appointment_date: date,
        time_start: Optional[dt_time] = None,
        time_end: Optional[dt_time] = None,
        service_type: str = "",
        tech_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """Create a job in Housecall Pro."""
        try:
            payload = {
                "customer_id": customer_id,
                "schedule": {
                    "scheduled_start": f"{appointment_date.isoformat()}T{(time_start or dt_time(9, 0)).isoformat()}",
                    "scheduled_end": f"{appointment_date.isoformat()}T{(time_end or dt_time(11, 0)).isoformat()}",
                },
            }
            if tech_id:
                payload["assigned_employee_ids"] = [tech_id]
            if notes:
                payload["notes"] = notes
            if service_type:
                payload["description"] = service_type

            data = await self._request("POST", "/jobs", json={"job": payload})
            job = data.get("job", data)
            return {"job_id": job.get("id"), "success": True, "error": None}
        except Exception as e:
            logger.error("HCP create_booking failed: %s", str(e))
            return {"job_id": None, "success": False, "error": str(e)}

    async def get_availability(
        self,
        start_date: date,
        end_date: date,
        tech_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get available time slots from Housecall Pro schedule."""
        try:
            params = f"?start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
            data = await self._request("GET", f"/schedule/availability{params}")
            slots = data.get("availability", [])
            return [
                {
                    "date": slot.get("date"),
                    "start": slot.get("start_time"),
                    "end": slot.get("end_time"),
                    "tech_id": slot.get("employee_id"),
                }
                for slot in slots
            ]
        except Exception as e:
            logger.warning("HCP get_availability failed: %s", str(e))
            return []

    async def get_technicians(self) -> list[dict]:
        """Get list of employees/technicians from Housecall Pro."""
        try:
            data = await self._request("GET", "/employees")
            employees = data.get("employees", [])
            return [
                {
                    "id": emp.get("id"),
                    "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}".strip(),
                    "specialty": [],
                    "active": emp.get("active", True),
                }
                for emp in employees
            ]
        except Exception as e:
            logger.warning("HCP get_technicians failed: %s", str(e))
            return []
