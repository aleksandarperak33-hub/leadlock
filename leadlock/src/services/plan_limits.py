"""
Plan-based access control limits.

Central source of truth for what each billing tier includes.
Used by conductor (lead limits), integrations (CRM limits),
follow-up scheduler (sequence gating), and billing API (plan info).
"""
from typing import Optional


PLAN_LIMITS: dict[str, dict] = {
    "starter": {
        "monthly_lead_limit": 200,
        "crm_integration_limit": 1,
        "cold_followup_enabled": False,
        "max_cold_followups": 0,
        "multi_location": False,
        "api_access": False,
    },
    "pro": {
        "monthly_lead_limit": 1000,
        "crm_integration_limit": None,  # unlimited
        "cold_followup_enabled": True,
        "max_cold_followups": 3,
        "multi_location": False,
        "api_access": False,
    },
    "business": {
        "monthly_lead_limit": None,  # unlimited
        "crm_integration_limit": None,  # unlimited
        "cold_followup_enabled": True,
        "max_cold_followups": 3,
        "multi_location": True,
        "api_access": True,
    },
}


def get_plan_limits(tier: str) -> dict:
    """Get limits for a given tier. Defaults to starter for unknown tiers."""
    return PLAN_LIMITS.get(tier, PLAN_LIMITS["starter"])


def get_monthly_lead_limit(tier: str) -> Optional[int]:
    """Get the monthly lead limit. None means unlimited."""
    return get_plan_limits(tier)["monthly_lead_limit"]


def get_crm_integration_limit(tier: str) -> Optional[int]:
    """Get the CRM integration limit. None means unlimited."""
    return get_plan_limits(tier)["crm_integration_limit"]


def is_cold_followup_enabled(tier: str) -> bool:
    """Check if cold follow-up sequences are enabled for this tier."""
    return get_plan_limits(tier)["cold_followup_enabled"]
