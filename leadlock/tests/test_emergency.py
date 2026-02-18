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


class TestFalsePositives:
    """Ambiguous keywords must NOT trigger on non-emergency contexts.

    These are regression tests for known false positives where common
    words like "fire", "smoke", and "flood" have non-emergency meanings.
    """

    # --- "fire" used as verb meaning "to dismiss" ---

    def test_fire_the_contractor(self):
        result = detect_emergency("We need to fire the old contractor")
        assert result["is_emergency"] is False

    def test_fire_our_plumber(self):
        result = detect_emergency("I want to fire our plumber")
        assert result["is_emergency"] is False

    def test_fire_him(self):
        result = detect_emergency("We should fire him and hire someone else")
        assert result["is_emergency"] is False

    def test_fire_them(self):
        result = detect_emergency("Can you fire them for me?")
        assert result["is_emergency"] is False

    def test_got_fired(self):
        result = detect_emergency("The last tech got fired")
        assert result["is_emergency"] is False

    def test_youre_fired(self):
        result = detect_emergency("You're fired, we're going with another company")
        assert result["is_emergency"] is False

    # --- "fire" as actual emergency still works ---

    def test_real_fire_standalone(self):
        result = detect_emergency("Fire!")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_real_fire_in_location(self):
        result = detect_emergency("There's a fire in the basement")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_real_on_fire(self):
        result = detect_emergency("The furnace is on fire")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    # --- "smoke" used for personal habit ---

    def test_smoke_outside(self):
        result = detect_emergency("I'll smoke outside while you work")
        assert result["is_emergency"] is False

    def test_smoke_cigarettes(self):
        result = detect_emergency("I smoke cigarettes on the patio")
        assert result["is_emergency"] is False

    def test_smoker(self):
        result = detect_emergency("The tech was a smoker which I didn't like")
        assert result["is_emergency"] is False

    def test_going_to_smoke(self):
        result = detect_emergency("I'm going outside to smoke")
        assert result["is_emergency"] is False

    # --- "smoke" as actual emergency still works ---

    def test_real_smoke_from_furnace(self):
        result = detect_emergency("There's smoke coming from the furnace")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_real_smell_smoke(self):
        result = detect_emergency("I smell smoke in the house")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    def test_real_smoke_standalone(self):
        result = detect_emergency("Smoke everywhere!")
        assert result["is_emergency"] is True
        assert result["severity"] == "critical"

    # --- "flood" used metaphorically ---

    def test_flooded_with_calls(self):
        result = detect_emergency("She is flooded with calls")
        assert result["is_emergency"] is False

    def test_flood_of_requests(self):
        result = detect_emergency("We got a flood of requests today")
        assert result["is_emergency"] is False

    # --- "flood" as actual emergency still works ---

    def test_real_flood_in_basement(self):
        result = detect_emergency("There's a flood in the basement")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"

    def test_real_flooding(self):
        result = detect_emergency("The basement is flooding")
        assert result["is_emergency"] is True
        assert result["severity"] == "urgent"
