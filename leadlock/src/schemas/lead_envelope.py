"""
Normalized lead envelope — the universal input format for leads from ANY source.
Every webhook normalizes its payload into this format before processing.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LeadMetadata(BaseModel):
    """Source-specific metadata that travels with the lead."""
    source_lead_id: Optional[str] = None
    source_timestamp: Optional[datetime] = None
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    keyword: Optional[str] = None
    landing_page: Optional[str] = None
    referrer: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    form_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    raw_payload: Optional[dict] = None


class NormalizedLead(BaseModel):
    """Contact and service information extracted from the raw lead."""
    phone: str = Field(..., description="E.164 format phone number")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    state_code: Optional[str] = None
    service_type: Optional[str] = None
    problem_description: Optional[str] = None
    urgency: Optional[str] = None
    property_type: Optional[str] = None
    budget_range: Optional[str] = None


class LeadEnvelope(BaseModel):
    """
    The universal lead input format. Every webhook produces one of these.
    The conductor processes this to create a Lead record and kick off the pipeline.
    """
    source: str = Field(..., description="Lead source: google_lsa, angi, website, missed_call, text_in, facebook")
    client_id: str = Field(..., description="UUID of the client this lead belongs to")
    lead: NormalizedLead
    metadata: LeadMetadata = Field(default_factory=LeadMetadata)
    consent_type: str = Field(default="pec", description="pec or pewc")
    consent_method: str = Field(default="text_in", description="How consent was obtained")
    is_first_message: bool = Field(default=True, description="Is this a new lead or a reply?")
    inbound_message: Optional[str] = Field(default=None, description="The raw inbound message text (for SMS replies)")
