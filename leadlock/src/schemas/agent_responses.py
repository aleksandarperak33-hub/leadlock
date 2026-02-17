"""
Agent response schemas — structured output from each AI agent.
"""
from typing import Optional
from pydantic import BaseModel, Field


class IntakeResponse(BaseModel):
    """Response from the intake agent — always template-based, never free-form AI."""
    message: str = Field(..., description="The SMS message to send")
    template_id: str = Field(..., description="Which template was used")
    is_emergency: bool = Field(default=False)
    emergency_type: Optional[str] = None
    internal_notes: str = Field(default="")


class QualificationData(BaseModel):
    """Structured qualification data extracted during the qualify conversation."""
    service_type: Optional[str] = None
    urgency: Optional[str] = None  # emergency, today, this_week, flexible, just_quote
    property_type: Optional[str] = None  # residential, commercial
    budget_range: Optional[str] = None
    problem_description: Optional[str] = None
    homeowner: Optional[bool] = None
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    additional_info: Optional[str] = None


class QualifyResponse(BaseModel):
    """Response from the qualify agent — conversational AI with structured output."""
    message: str = Field(..., description="The SMS message to send")
    qualification: QualificationData = Field(default_factory=QualificationData)
    internal_notes: str = Field(default="")
    next_action: str = Field(
        default="continue_qualifying",
        description="continue_qualifying, ready_to_book, mark_cold, escalate_emergency"
    )
    score_adjustment: int = Field(default=0, description="Points to add/subtract from lead score")
    is_qualified: bool = Field(default=False, description="True when all 4 fields collected")
    ai_cost_usd: float = Field(default=0.0, description="AI generation cost for this response")
    ai_latency_ms: Optional[int] = Field(default=None, description="AI generation latency")


class BookResponse(BaseModel):
    """Response from the book agent — appointment confirmation."""
    message: str = Field(..., description="The SMS message to send")
    appointment_date: Optional[str] = None
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    tech_name: Optional[str] = None
    booking_confirmed: bool = Field(default=False)
    needs_human_handoff: bool = Field(default=False)
    internal_notes: str = Field(default="")
    ai_cost_usd: float = Field(default=0.0, description="AI generation cost for this response")
    ai_latency_ms: Optional[int] = Field(default=None, description="AI generation latency")


class FollowupResponse(BaseModel):
    """Response from the follow-up agent."""
    message: str = Field(..., description="The SMS message to send")
    followup_type: str = Field(default="cold_nurture")  # cold_nurture, day_before_reminder, review_request
    sequence_number: int = Field(default=1)
    internal_notes: str = Field(default="")
    should_stop_sequence: bool = Field(default=False, description="True if we should stop following up")
