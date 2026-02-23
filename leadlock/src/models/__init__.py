"""
Database models - import all models here so Alembic can discover them.
"""
from src.models.client import Client
from src.models.lead import Lead
from src.models.consent import ConsentRecord
from src.models.conversation import Conversation
from src.models.booking import Booking
from src.models.followup import FollowupTask
from src.models.event_log import EventLog
from src.models.agency_partner import AgencyPartner
from src.models.outreach import Outreach
from src.models.scrape_job import ScrapeJob
from src.models.outreach_email import OutreachEmail
from src.models.sales_config import SalesEngineConfig
from src.models.email_blacklist import EmailBlacklist
from src.models.webhook_event import WebhookEvent
from src.models.failed_lead import FailedLead
from src.models.ab_test import ABTestExperiment, ABTestVariant

__all__ = [
    "Client",
    "Lead",
    "ConsentRecord",
    "Conversation",
    "Booking",
    "FollowupTask",
    "EventLog",
    "AgencyPartner",
    "Outreach",
    "ScrapeJob",
    "OutreachEmail",
    "SalesEngineConfig",
    "EmailBlacklist",
    "WebhookEvent",
    "FailedLead",
    "ABTestExperiment",
    "ABTestVariant",
]
