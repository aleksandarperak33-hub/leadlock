"""
Deduplication tests.
"""
import pytest
from src.utils.dedup import make_dedup_key


class TestDedup:
    def test_same_input_same_key(self):
        """Same client + phone + source should produce same key."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client1", "+15125559876", "website")
        assert key1 == key2

    def test_different_phone_different_key(self):
        """Different phone numbers should produce different keys."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client1", "+15125551234", "website")
        assert key1 != key2

    def test_different_source_different_key(self):
        """Different sources should produce different keys."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client1", "+15125559876", "angi")
        assert key1 != key2

    def test_different_client_different_key(self):
        """Different clients should produce different keys."""
        key1 = make_dedup_key("client1", "+15125559876", "website")
        key2 = make_dedup_key("client2", "+15125559876", "website")
        assert key1 != key2

    def test_key_format(self):
        """Keys should have the correct prefix."""
        key = make_dedup_key("client1", "+15125559876", "website")
        assert key.startswith("leadlock:dedup:")
