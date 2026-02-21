"""
Abstract CRM interface - all CRM integrations implement this.
CRITICAL: CRM operations NEVER go in the SMS response path.
They happen asynchronously via the crm_sync worker.
"""
from abc import ABC, abstractmethod
from typing import Optional
from datetime import date, time


class CRMBase(ABC):
    """Abstract base class for CRM integrations."""

    @abstractmethod
    async def create_customer(
        self,
        first_name: str,
        last_name: Optional[str],
        phone: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> dict:
        """
        Create a customer record in the CRM.
        Returns: {"customer_id": str, "success": bool, "error": str|None}
        """
        ...

    @abstractmethod
    async def create_lead(
        self,
        customer_id: str,
        source: str,
        service_type: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """
        Create a lead/opportunity in the CRM.
        Returns: {"lead_id": str, "success": bool, "error": str|None}
        """
        ...

    @abstractmethod
    async def create_booking(
        self,
        customer_id: str,
        appointment_date: date,
        time_start: Optional[time] = None,
        time_end: Optional[time] = None,
        service_type: str = "",
        tech_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Create a booking/job in the CRM.
        Returns: {"job_id": str, "success": bool, "error": str|None}
        """
        ...

    @abstractmethod
    async def get_availability(
        self,
        start_date: date,
        end_date: date,
        tech_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Get available appointment slots from the CRM.
        Returns: [{"date": str, "start": str, "end": str, "tech_id": str}]
        """
        ...

    @abstractmethod
    async def get_technicians(self) -> list[dict]:
        """
        Get list of technicians/team members.
        Returns: [{"id": str, "name": str, "specialty": list, "active": bool}]
        """
        ...
