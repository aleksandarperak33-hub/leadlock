"""
Tests for shared email constants — validates single source of truth.
"""
from src.utils.email_constants import GENERIC_EMAIL_PREFIXES


class TestGenericEmailPrefixes:
    """Validate the shared GENERIC_EMAIL_PREFIXES constant."""

    def test_is_frozenset(self):
        assert isinstance(GENERIC_EMAIL_PREFIXES, frozenset)

    def test_all_lowercase(self):
        for prefix in GENERIC_EMAIL_PREFIXES:
            assert prefix == prefix.lower(), f"Prefix '{prefix}' is not lowercase"

    def test_contains_critical_bounce_prefixes(self):
        """These 8 prefixes had 40-60% bounce rates on SMB domains."""
        critical = {"contact", "hello", "service", "support", "office", "team", "admin", "help"}
        missing = critical - GENERIC_EMAIL_PREFIXES
        assert not missing, f"Missing critical prefixes: {missing}"

    def test_contains_info_prefix(self):
        assert "info" in GENERIC_EMAIL_PREFIXES

    def test_contains_noreply_prefixes(self):
        assert "noreply" in GENERIC_EMAIL_PREFIXES
        assert "no-reply" in GENERIC_EMAIL_PREFIXES

    def test_contains_infrastructure_prefixes(self):
        infra = {"webmaster", "hostmaster", "postmaster", "abuse"}
        missing = infra - GENERIC_EMAIL_PREFIXES
        assert not missing, f"Missing infrastructure prefixes: {missing}"

    def test_contains_finance_prefixes(self):
        finance = {"accounts", "accounting", "billing"}
        missing = finance - GENERIC_EMAIL_PREFIXES
        assert not missing, f"Missing finance prefixes: {missing}"

    def test_does_not_contain_personal_names(self):
        """Personal-sounding names should NOT be in the generic list."""
        personal = {"john", "jane", "mike", "alek", "owner"}
        overlap = personal & GENERIC_EMAIL_PREFIXES
        assert not overlap, f"Personal names in generic list: {overlap}"

    def test_contains_compound_prefixes(self):
        """Compound prefixes (no separator) should be in the list."""
        compound = {"customerservice", "customercare", "contactus", "frontdesk", "helpdesk"}
        missing = compound - GENERIC_EMAIL_PREFIXES
        assert not missing, f"Missing compound prefixes: {missing}"

    def test_contains_operations_prefixes(self):
        operations = {"dispatch", "operations", "estimating", "estimates", "scheduling"}
        missing = operations - GENERIC_EMAIL_PREFIXES
        assert not missing, f"Missing operations prefixes: {missing}"

    def test_minimum_size(self):
        """Should contain at least 40 prefixes (expanded list)."""
        assert len(GENERIC_EMAIL_PREFIXES) >= 40
