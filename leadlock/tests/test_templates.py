"""
Template rendering tests.
"""
import pytest
from src.utils.templates import render_template


class TestTemplates:
    def test_standard_intake_renders(self):
        result = render_template(
            template_key="standard",
            category="intake",
            first_name="John",
            rep_name="Sarah",
            business_name="Austin HVAC",
            service_type="AC Repair",
        )
        assert "John" in result
        assert "Sarah" in result
        assert "Austin HVAC" in result
        assert "STOP" in result

    def test_emergency_intake_renders(self):
        result = render_template(
            template_key="emergency",
            category="intake",
            first_name="Bob",
            rep_name="Sarah",
            business_name="Austin HVAC",
            service_type="Heating",
        )
        assert "STOP" in result
        assert "Austin HVAC" in result

    def test_missing_variable_doesnt_crash(self):
        """Missing variables should show as {var_name} placeholders."""
        result = render_template(
            template_key="standard",
            category="intake",
            first_name="John",
            # Missing rep_name, business_name, service_type
        )
        assert "John" in result
        # Missing vars should show as {var_name} literals
        assert "{rep_name}" in result
        assert "{business_name}" in result

    def test_cold_nurture_renders(self):
        result = render_template(
            template_key="cold_nurture_1",
            category="followup",
            first_name="John",
            business_name="Austin HVAC",
            rep_name="Sarah",
            service_type="AC Repair",
        )
        assert "Austin HVAC" in result

    def test_booking_confirm_renders(self):
        result = render_template(
            template_key="confirm",
            category="booking",
            first_name="John",
            date="Monday, Feb 16",
            time_window="8:00 AM - 10:00 AM",
            service_type="AC Repair",
            tech_name="Mike",
        )
        assert "John" in result

    def test_variant_a_renders(self):
        result = render_template(
            template_key="standard",
            category="intake",
            variant="A",
            first_name="Test",
            rep_name="Sarah",
            business_name="ACME",
            service_type="Plumbing",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_variant_b_renders(self):
        result = render_template(
            template_key="standard",
            category="intake",
            variant="B",
            first_name="Test",
            rep_name="Sarah",
            business_name="ACME",
            service_type="Plumbing",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_template_returns_fallback(self):
        result = render_template(
            template_key="nonexistent",
            category="intake",
            fallback="Default fallback message",
        )
        assert result == "Default fallback message"
