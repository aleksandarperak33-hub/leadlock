"""
Database models — import all models here so Alembic can discover them.
"""
from src.models.client import Client
from src.models.lead import Lead
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.booking import Booking
from src.models.followup import FollowupTask
from src.models.event_log import EventLog
from src.models.agency_partner import AgencyPartner

__all__ = [
    "Client",
    "Lead",
    "ConsentRecord",
    "Conversation",
    "Booking",
    "FollowupTask",
    "EventLog",
    "AgencyPartner",
]
