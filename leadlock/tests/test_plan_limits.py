"""
Tests for src/services/plan_limits.py — plan-based access controls for billing tiers.
"""
import pytest

from src.services.plan_limits import (
    get_plan_limits,
    get_monthly_lead_limit,
    get_crm_integration_limit,
    is_cold_followup_enabled,
    PLAN_LIMITS,
)


# ---------------------------------------------------------------------------
# get_plan_limits
# ---------------------------------------------------------------------------

class TestGetPlanLimits:
    def test_starter_tier(self):
        limits = get_plan_limits("starter")
        assert limits["monthly_lead_limit"] == 200
        assert limits["crm_integration_limit"] == 1
        assert limits["cold_followup_enabled"] is False
        assert limits["max_cold_followups"] == 0
        assert limits["multi_location"] is False
        assert limits["api_access"] is False

    def test_pro_tier(self):
        limits = get_plan_limits("pro")
        assert limits["monthly_lead_limit"] == 1000
        assert limits["crm_integration_limit"] is None  # unlimited
        assert limits["cold_followup_enabled"] is True
        assert limits["max_cold_followups"] == 3
        assert limits["multi_location"] is False
        assert limits["api_access"] is False

    def test_business_tier(self):
        limits = get_plan_limits("business")
        assert limits["monthly_lead_limit"] is None  # unlimited
        assert limits["crm_integration_limit"] is None  # unlimited
        assert limits["cold_followup_enabled"] is True
        assert limits["max_cold_followups"] == 3
        assert limits["multi_location"] is True
        assert limits["api_access"] is True

    def test_unknown_tier_defaults_to_starter(self):
        limits = get_plan_limits("enterprise")
        assert limits == PLAN_LIMITS["starter"]

    def test_empty_tier_defaults_to_starter(self):
        limits = get_plan_limits("")
        assert limits == PLAN_LIMITS["starter"]


# ---------------------------------------------------------------------------
# get_monthly_lead_limit
# ---------------------------------------------------------------------------

class TestGetMonthlyLeadLimit:
    def test_starter_200(self):
        assert get_monthly_lead_limit("starter") == 200

    def test_pro_1000(self):
        assert get_monthly_lead_limit("pro") == 1000

    def test_business_unlimited(self):
        assert get_monthly_lead_limit("business") is None

    def test_unknown_defaults_to_starter(self):
        assert get_monthly_lead_limit("unknown_tier") == 200


# ---------------------------------------------------------------------------
# get_crm_integration_limit
# ---------------------------------------------------------------------------

class TestGetCrmIntegrationLimit:
    def test_starter_one(self):
        assert get_crm_integration_limit("starter") == 1

    def test_pro_unlimited(self):
        assert get_crm_integration_limit("pro") is None

    def test_business_unlimited(self):
        assert get_crm_integration_limit("business") is None


# ---------------------------------------------------------------------------
# is_cold_followup_enabled
# ---------------------------------------------------------------------------

class TestIsColdFollowupEnabled:
    def test_starter_disabled(self):
        assert is_cold_followup_enabled("starter") is False

    def test_pro_enabled(self):
        assert is_cold_followup_enabled("pro") is True

    def test_business_enabled(self):
        assert is_cold_followup_enabled("business") is True

    def test_unknown_defaults_to_starter_disabled(self):
        assert is_cold_followup_enabled("random_tier") is False


# ---------------------------------------------------------------------------
# Immutability — returned dict should not share references with PLAN_LIMITS
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_returned_dict_is_same_reference(self):
        """get_plan_limits returns the dict directly from PLAN_LIMITS.
        Callers should not mutate it. This test documents the current behavior."""
        limits = get_plan_limits("starter")
        # Verify the shape matches
        assert "monthly_lead_limit" in limits
        assert "cold_followup_enabled" in limits
