"""
GoHighLevel CRM integration — REST API v2.

Auth: Bearer token via API key.
Docs: https://highlevel.stoplight.io/docs/integrations
All calls have 10-second timeout per project standard.
"""
import logging
from datetime import date, time as dt_time, datetime, timezone
from typing import Optional

import httpx

from src.integrations.crm_base import CRMBase

logger = logging.getLogger(__name__)

BASE_URL = "https://services.leadconnectorhq.com"
TIMEOUT = 10.0


class GoHighLevelCRM(CRMBase):
    """GoHighLevel API v2 integration."""

    def __init__(self, api_key: str, location_id: str):
        self.api_key = api_key
        self.location_id = location_id
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Version": "2021-07-28",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Make an authenticated request to the GoHighLevel API."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.request(
                method,
                f"{BASE_URL}{path}",
                headers=self._headers,
                json=json,
                params=params,
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
        """Create a contact in GoHighLevel."""
        try:
            payload = {
                "firstName": first_name,
                "lastName": last_name or "",
                "phone": phone,
                "locationId": self.location_id,
            }
            if email:
                payload["email"] = email
            if address:
                payload["address1"] = address

            data = await self._request("POST", "/contacts/", json=payload)
            contact = data.get("contact", data)
            contact_id = contact.get("id")

            logger.info("GHL contact created: %s", contact_id)
            return {"customer_id": contact_id, "success": True, "error": None}
        except Exception as e:
            logger.error("GHL create_customer failed: %s", str(e))
            return {"customer_id": None, "success": False, "error": str(e)}

    async def create_lead(
        self,
        customer_id: str,
        source: str,
        service_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Create an opportunity (lead) in GoHighLevel."""
        try:
            payload = {
                "contactId": customer_id,
                "locationId": self.location_id,
                "name": service_type or f"Lead from {source}",
                "source": source,
                "status": "open",
            }

            data = await self._request("POST", "/opportunities/", json=payload)
            opportunity = data.get("opportunity", data)
            return {"lead_id": opportunity.get("id"), "success": True, "error": None}
        except Exception as e:
            logger.error("GHL create_lead failed: %s", str(e))
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
        """Create a calendar event/appointment in GoHighLevel."""
        try:
            start_dt = datetime.combine(
                appointment_date,
                time_start or dt_time(9, 0),
                tzinfo=timezone.utc,
            )
            end_dt = datetime.combine(
                appointment_date,
                time_end or dt_time(11, 0),
                tzinfo=timezone.utc,
            )

            payload = {
                "contactId": customer_id,
                "locationId": self.location_id,
                "title": service_type or "Service Appointment",
                "startTime": start_dt.isoformat(),
                "endTime": end_dt.isoformat(),
            }
            if tech_id:
                payload["calendarId"] = tech_id
            if notes:
                payload["notes"] = notes

            data = await self._request("POST", "/calendars/events/appointments", json=payload)
            event = data.get("event", data)
            return {"job_id": event.get("id"), "success": True, "error": None}
        except Exception as e:
            logger.error("GHL create_booking failed: %s", str(e))
            return {"job_id": None, "success": False, "error": str(e)}

    async def get_availability(
        self,
        start_date: date,
        end_date: date,
        tech_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get available appointment slots from GoHighLevel calendars."""
        try:
            params = {
                "locationId": self.location_id,
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
            }
            data = await self._request("GET", "/calendars/events", params=params)
            events = data.get("events", [])
            return [
                {
                    "date": event.get("startTime", "")[:10],
                    "start": event.get("startTime", "")[11:16],
                    "end": event.get("endTime", "")[11:16],
                    "tech_id": event.get("calendarId"),
                }
                for event in events
            ]
        except Exception as e:
            logger.warning("GHL get_availability failed: %s", str(e))
            return []

    async def get_technicians(self) -> list[dict]:
        """Get list of users from GoHighLevel location."""
        try:
            params = {"locationId": self.location_id}
            data = await self._request("GET", "/users/", params=params)
            users = data.get("users", [])
            return [
                {
                    "id": user.get("id"),
                    "name": f"{user.get('firstName', '')} {user.get('lastName', '')}".strip(),
                    "specialty": user.get("roles", []),
                    "active": True,
                }
                for user in users
            ]
        except Exception as e:
            logger.warning("GHL get_technicians failed: %s", str(e))
            return []
