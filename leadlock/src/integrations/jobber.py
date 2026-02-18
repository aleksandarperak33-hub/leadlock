"""
Jobber CRM integration — GraphQL API.

Auth: Bearer token via API key.
Docs: https://developer.getjobber.com/docs
All calls have 10-second timeout per project standard.
"""
import logging
from datetime import date, time as dt_time
from typing import Optional

import httpx

from src.integrations.crm_base import CRMBase

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.getjobber.com/api/graphql"
TIMEOUT = 10.0


class JobberCRM(CRMBase):
    """Jobber GraphQL API integration."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query against the Jobber API."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                GRAPHQL_URL,
                headers=self._headers,
                json={"query": query, "variables": variables or {}},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errors"):
                error_msg = data["errors"][0].get("message", "GraphQL error")
                raise ValueError(f"Jobber API error: {error_msg}")
            return data.get("data", {})

    async def create_customer(
        self,
        first_name: str,
        last_name: Optional[str],
        phone: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> dict:
        """Create a client in Jobber."""
        try:
            mutation = """
            mutation CreateClient($input: ClientCreateInput!) {
                clientCreate(input: $input) {
                    client { id firstName lastName }
                    userErrors { message path }
                }
            }
            """
            variables = {
                "input": {
                    "firstName": first_name,
                    "lastName": last_name or "",
                    "phones": [{"number": phone, "primary": True}],
                }
            }
            if email:
                variables["input"]["emails"] = [{"address": email, "primary": True}]

            data = await self._graphql(mutation, variables)
            result = data.get("clientCreate", {})
            errors = result.get("userErrors", [])
            if errors:
                error_msg = errors[0].get("message", "Unknown error")
                return {"customer_id": None, "success": False, "error": error_msg}

            client = result.get("client", {})
            customer_id = client.get("id")
            logger.info("Jobber client created: %s", customer_id)
            return {"customer_id": customer_id, "success": True, "error": None}
        except Exception as e:
            logger.error("Jobber create_customer failed: %s", str(e))
            return {"customer_id": None, "success": False, "error": str(e)}

    async def create_lead(
        self,
        customer_id: str,
        source: str,
        service_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Create a request (lead) in Jobber."""
        try:
            mutation = """
            mutation CreateRequest($input: RequestCreateInput!) {
                requestCreate(input: $input) {
                    request { id title }
                    userErrors { message path }
                }
            }
            """
            variables = {
                "input": {
                    "clientId": customer_id,
                    "title": service_type or f"Lead from {source}",
                    "details": description or "",
                }
            }

            data = await self._graphql(mutation, variables)
            result = data.get("requestCreate", {})
            errors = result.get("userErrors", [])
            if errors:
                return {"lead_id": None, "success": False, "error": errors[0].get("message")}

            request_obj = result.get("request", {})
            return {"lead_id": request_obj.get("id"), "success": True, "error": None}
        except Exception as e:
            logger.error("Jobber create_lead failed: %s", str(e))
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
        """Create a job in Jobber."""
        try:
            # Include timezone offset to avoid server-side timezone ambiguity
            from datetime import datetime as dt_cls, timezone as tz
            start_dt = dt_cls.combine(appointment_date, time_start or dt_time(9, 0), tzinfo=tz.utc)
            end_dt = dt_cls.combine(appointment_date, time_end or dt_time(11, 0), tzinfo=tz.utc)
            start_at = start_dt.isoformat()
            end_at = end_dt.isoformat()

            mutation = """
            mutation CreateJob($input: JobCreateInput!) {
                jobCreate(input: $input) {
                    job { id title }
                    userErrors { message path }
                }
            }
            """
            variables = {
                "input": {
                    "clientId": customer_id,
                    "title": service_type or "Service Call",
                    "startAt": start_at,
                    "endAt": end_at,
                    "instructions": notes or "",
                }
            }
            if tech_id:
                variables["input"]["assignedUserIds"] = [tech_id]

            data = await self._graphql(mutation, variables)
            result = data.get("jobCreate", {})
            errors = result.get("userErrors", [])
            if errors:
                return {"job_id": None, "success": False, "error": errors[0].get("message")}

            job = result.get("job", {})
            return {"job_id": job.get("id"), "success": True, "error": None}
        except Exception as e:
            logger.error("Jobber create_booking failed: %s", str(e))
            return {"job_id": None, "success": False, "error": str(e)}

    async def get_availability(
        self,
        start_date: date,
        end_date: date,
        tech_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get available schedule slots from Jobber."""
        try:
            query = """
            query GetSchedule($startDate: ISO8601Date!, $endDate: ISO8601Date!) {
                calendarEvents(startDate: $startDate, endDate: $endDate) {
                    nodes {
                        id
                        startAt
                        endAt
                        assignedUsers { id }
                    }
                }
            }
            """
            variables = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
            }
            data = await self._graphql(query, variables)
            events = data.get("calendarEvents", {}).get("nodes", [])
            return [
                {
                    "date": event.get("startAt", "")[:10],
                    "start": event.get("startAt", "")[11:16],
                    "end": event.get("endAt", "")[11:16],
                    "tech_id": event.get("assignedUsers", [{}])[0].get("id") if event.get("assignedUsers") else None,
                }
                for event in events
            ]
        except Exception as e:
            logger.warning("Jobber get_availability failed: %s", str(e))
            return []

    async def get_technicians(self) -> list[dict]:
        """Get list of users/team members from Jobber."""
        try:
            query = """
            query GetUsers {
                users {
                    nodes {
                        id
                        name { full }
                        role
                        isActive
                    }
                }
            }
            """
            data = await self._graphql(query)
            users = data.get("users", {}).get("nodes", [])
            return [
                {
                    "id": user.get("id"),
                    "name": user.get("name", {}).get("full", ""),
                    "specialty": [],
                    "active": user.get("isActive", True),
                }
                for user in users
            ]
        except Exception as e:
            logger.warning("Jobber get_technicians failed: %s", str(e))
            return []
