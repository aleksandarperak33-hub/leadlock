"""
Emergency detection tests — every keyword must be tested.
Missing an emergency can put lives at risk.
"""
import pytest
from src.utils.emergency import detect_emergency


class TestCriticalEmergencies:
    """Test critical severity keywords — immediate danger to life."""

    def test_gas_leak(self):
        result = detect_emergency("I think we have a gas leak in the basement")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"
        assert result["emergency_type"] == "gas_or_co"

    def test_gas_smell(self):
        result = detect_emergency("We smell gas in the kitchen")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_carbon_monoxide(self):
        result = detect_emergency("Our carbon monoxide detector is going off")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"
        assert result["emergency_type"] == "gas_or_co"

    def test_co_detector(self):
        result = detect_emergency("The co detector is beeping")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_fire(self):
        result = detect_emergency("There's a fire in the electrical panel")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"
        assert result["emergency_type"] == "fire_electrical"

    def test_electrical_fire(self):
        result = detect_emergency("We have an electrical fire")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_sparking(self):
        result = detect_emergency("The outlet is sparking")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_smoke(self):
        result = detect_emergency("There's smoke coming from the furnace")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_exposed_wires(self):
        result = detect_emergency("There are exposed wires in the wall")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_electrical_shock(self):
        result = detect_emergency("Someone got an electrical shock from the panel")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_sewage(self):
        result = detect_emergency("We have sewage coming up through the floor")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_sewer_backup(self):
        result = detect_emergency("The sewer backup is flooding the basement")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"


class TestUrgentEmergencies:
    """Test urgent severity keywords — significant but not immediately life-threatening."""

    def test_no_heat(self):
        result = detect_emergency("We have no heat and it's freezing")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"
        assert result["emergency_type"] == "no_heat"

    def test_no_ac(self):
        result = detect_emergency("Our AC stopped working, no ac at all")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"
        assert result["emergency_type"] == "no_cooling"

    def test_no_hot_water(self):
        result = detect_emergency("We have no hot water")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"
        assert result["emergency_type"] == "water_heater"

    def test_water_heater_leaking(self):
        result = detect_emergency("The water heater leaking all over the garage")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"

    def test_flooding(self):
        result = detect_emergency("Our basement is flooding")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"
        assert result["emergency_type"] == "flooding"

    def test_burst_pipe(self):
        result = detect_emergency("We have a burst pipe in the bathroom")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"

    def test_broken_pipe(self):
        result = detect_emergency("There's a broken pipe spraying water")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"

    def test_frozen_pipes(self):
        result = detect_emergency("Our pipes are frozen")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"
        assert result["emergency_type"] == "frozen_pipes"

    def test_heat_not_working(self):
        result = detect_emergency("The heat not working in our house")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"

    def test_furnace_not_working(self):
        result = detect_emergency("Our furnace not working")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"

    def test_ac_not_working(self):
        result = detect_emergency("The ac not working since yesterday")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"


class TestCustomKeywords:
    def test_custom_keyword_detected(self):
        result = detect_emergency(
            "The roof is leaking badly",
            custom_keywords=["roof is leaking"],
        )
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"  # Custom keywords are critical

    def test_custom_keyword_takes_priority(self):
        """Custom keywords should be checked before defaults."""
        result = detect_emergency(
            "special situation",
            custom_keywords=["special situation"],
        )
        assert result["is_emergency"] is True


class TestNonEmergencies:
    """Normal requests must NOT be flagged as emergencies."""

    def test_routine_repair(self):
        result = detect_emergency("I need my AC serviced for the summer")
        assert result["is_emergency"] is False

    def test_maintenance_request(self):
        result = detect_emergency("Can you come do annual maintenance?")
        assert result["is_emergency"] is False

    def test_quote_request(self):
        result = detect_emergency("How much does a new furnace cost?")
        assert result["is_emergency"] is False

    def test_scheduling_request(self):
        result = detect_emergency("Can you come out next Tuesday?")
        assert result["is_emergency"] is False

    def test_empty_message(self):
        result = detect_emergency("")
        assert result["is_emergency"] is False

    def test_none_message(self):
        result = detect_emergency(None)
        assert result["is_emergency"] is False

    def test_general_complaint(self):
        result = detect_emergency("My AC isn't cooling as well as it used to")
        assert result["is_emergency"] is False
