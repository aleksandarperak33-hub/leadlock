"""
Webhook payload schemas - raw input from each lead source.
Each webhook normalizes its payload into a LeadEnvelope before processing.
"""
from typing import Optional
from pydantic import BaseModel, Field


class TwilioSmsPayload(BaseModel):
    """Twilio inbound SMS webhook payload."""
    MessageSid: str
    AccountSid: str
    From: str  # E.164 phone number
    To: str
    Body: str
    NumMedia: str = "0"
    FromCity: Optional[str] = None
    FromState: Optional[str] = None
    FromZip: Optional[str] = None
    FromCountry: Optional[str] = None


class TwilioStatusPayload(BaseModel):
    """Twilio delivery status callback."""
    MessageSid: str
    MessageStatus: str  # queued, sent, delivered, undelivered, failed
    ErrorCode: Optional[str] = None
    ErrorMessage: Optional[str] = None
    To: Optional[str] = None
    From: Optional[str] = None


class WebFormPayload(BaseModel):
    """Website contact form submission."""
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    service: Optional[str] = None
    message: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    urgency: Optional[str] = None
    property_type: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class GoogleLsaPayload(BaseModel):
    """Google Local Services Ads lead payload."""
    lead_id: str
    customer_name: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    job_type: Optional[str] = None
    postal_code: Optional[str] = None
    lead_type: str = "message"  # message, phone_call
    create_time: Optional[str] = None
    geo_location: Optional[dict] = None


class AngiPayload(BaseModel):
    """Angi/HomeAdvisor lead payload."""
    leadId: str
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phone: str
    email: Optional[str] = None
    serviceDescription: Optional[str] = None
    zipCode: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    urgency: Optional[str] = None
    propertyType: Optional[str] = None


class FacebookLeadPayload(BaseModel):
    """Facebook Lead Ads payload (simplified)."""
    entry: list[dict] = Field(default_factory=list)


class MissedCallPayload(BaseModel):
    """Missed call notification - typically from the phone system."""
    caller_phone: str
    called_phone: str
    call_duration: int = 0
    timestamp: Optional[str] = None
    caller_name: Optional[str] = None
    caller_city: Optional[str] = None
    caller_state: Optional[str] = None
    caller_zip: Optional[str] = None
    voicemail_url: Optional[str] = None


# --- Thumbtack ---

class ThumbLocationPayload(BaseModel):
    """Location from Thumbtack lead."""
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None


class ThumbDetailPayload(BaseModel):
    """Question/answer detail from Thumbtack lead."""
    question: Optional[str] = None
    answer: Optional[str] = None


class ThumbRequestPayload(BaseModel):
    """Service request details from Thumbtack."""
    requestID: Optional[str] = None
    category: Optional[str] = None
    categoryID: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    schedule: Optional[str] = None
    location: Optional[ThumbLocationPayload] = None
    travelPreferences: Optional[str] = None
    details: list[ThumbDetailPayload] = Field(default_factory=list)


class ThumbCustomerPayload(BaseModel):
    """Customer info from Thumbtack."""
    customerID: Optional[str] = None
    name: Optional[str] = None


class ThumbBusinessPayload(BaseModel):
    """Business info from Thumbtack."""
    businessID: Optional[str] = None
    name: Optional[str] = None


class ThumbtackLeadPayload(BaseModel):
    """Thumbtack NegotiationCreatedV4 webhook payload.

    Note: Thumbtack does not include customer phone/email in the webhook.
    Communication happens through their Messages API. When a phone number
    is provided separately (via custom integration), use 'customer_phone'.
    """
    leadID: str
    createTimestamp: Optional[str] = None
    price: Optional[str] = None
    request: Optional[ThumbRequestPayload] = None
    customer: Optional[ThumbCustomerPayload] = None
    business: Optional[ThumbBusinessPayload] = None
    # Extended fields (some custom integrations include these)
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
