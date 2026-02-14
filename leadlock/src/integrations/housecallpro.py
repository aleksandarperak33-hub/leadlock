"""
Housecall Pro CRM integration — stub for future implementation.
"""
import logging
from datetime import date, time as dt_time
from typing import Optional
from src.integrations.crm_base import CRMBase

logger = logging.getLogger(__name__)


class HousecallProCRM(CRMBase):
    """Housecall Pro API integration (stub)."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def create_customer(self, first_name: str, last_name: Optional[str],
                              phone: str, email: Optional[str] = None,
                              address: Optional[str] = None) -> dict:
        logger.warning("Housecall Pro integration not yet implemented")
        return {"customer_id": None, "success": False, "error": "Not implemented"}

    async def create_lead(self, customer_id: str, source: str,
                          service_type: Optional[str] = None,
                          description: Optional[str] = None) -> dict:
        return {"lead_id": None, "success": False, "error": "Not implemented"}

    async def create_booking(self, customer_id: str, appointment_date: date,
                             time_start: Optional[dt_time] = None,
                             time_end: Optional[dt_time] = None,
                             service_type: str = "", tech_id: Optional[str] = None,
                             notes: Optional[str] = None) -> dict:
        return {"job_id": None, "success": False, "error": "Not implemented"}

    async def get_availability(self, start_date: date, end_date: date,
                               tech_ids: Optional[list[str]] = None) -> list[dict]:
        return []

    async def get_technicians(self) -> list[dict]:
        return []
