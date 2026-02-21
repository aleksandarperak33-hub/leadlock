"""
Client configuration schema - the full business configuration stored as JSONB.
"""
from typing import Optional
from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    lat: float
    lng: float


class ServiceArea(BaseModel):
    center: GeoPoint
    radius_miles: int = 35
    valid_zips: list[str] = Field(default_factory=list)


class BusinessHours(BaseModel):
    start: str = "07:00"
    end: str = "18:00"
    days: list[str] = Field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri"])


class Hours(BaseModel):
    business: BusinessHours = Field(default_factory=BusinessHours)
    saturday: Optional[BusinessHours] = None
    sunday: Optional[BusinessHours] = None
    after_hours_handling: str = "ai_responds_books_next_available"
    emergency_handling: str = "ai_responds_plus_owner_alert"


class TeamMember(BaseModel):
    name: str
    specialty: list[str] = Field(default_factory=list)
    calendar_id: Optional[str] = None
    crm_tech_id: Optional[str] = None
    languages: list[str] = Field(default_factory=lambda: ["en"])
    active: bool = True


class Persona(BaseModel):
    rep_name: str = "Sarah"
    tone: str = "friendly_professional"  # friendly_professional, casual, formal
    languages: list[str] = Field(default_factory=lambda: ["en"])
    emergency_contact_phone: Optional[str] = None


class Services(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    do_not_quote: list[str] = Field(default_factory=list)


class LeadSourceConfig(BaseModel):
    enabled: bool = True
    webhook_url: Optional[str] = None
    api_key: Optional[str] = None


class LeadSources(BaseModel):
    google_lsa: Optional[LeadSourceConfig] = None
    angi: Optional[LeadSourceConfig] = None
    facebook: Optional[LeadSourceConfig] = None
    website: Optional[LeadSourceConfig] = None
    missed_call: Optional[LeadSourceConfig] = None
    text_in: Optional[LeadSourceConfig] = None
    thumbtack: Optional[LeadSourceConfig] = None


class SchedulingConfig(BaseModel):
    slot_duration_minutes: int = 120
    buffer_minutes: int = 30
    max_daily_bookings: int = 8
    advance_booking_days: int = 14


class ClientConfig(BaseModel):
    """Complete client configuration - stored as JSONB on the Client model."""
    service_area: ServiceArea = Field(default_factory=ServiceArea)
    hours: Hours = Field(default_factory=Hours)
    team: list[TeamMember] = Field(default_factory=list)
    persona: Persona = Field(default_factory=Persona)
    services: Services = Field(default_factory=Services)
    emergency_keywords: list[str] = Field(default_factory=list)
    lead_sources: dict = Field(default_factory=dict)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
