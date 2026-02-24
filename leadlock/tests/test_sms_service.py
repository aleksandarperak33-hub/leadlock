"""
SMS service tests - error classification, encoding, message length enforcement.
"""
import pytest
from src.services.sms import (
    classify_error,
    is_gsm7,
    count_segments,
    enforce_message_length,
    mask_phone,
    MAX_SEGMENTS,
)


class TestClassifyError:
    """Every carrier error code should be classified correctly."""

    def test_opt_out_21610(self):
        assert classify_error("21610") == "opt_out"

    def test_landline_30006(self):
        assert classify_error("30006") == "landline"

    def test_invalid_number_21211(self):
        assert classify_error("21211") == "invalid"

    def test_invalid_number_21612(self):
        assert classify_error("21612") == "invalid"

    def test_permanent_error_covers_all_invalid(self):
        # Both 21211 and 21612 are in PERMANENT_ERRORS but classified more specifically
        assert classify_error("21211") == "invalid"

    def test_transient_30007(self):
        assert classify_error("30007") == "transient"

    def test_transient_30008(self):
        assert classify_error("30008") == "transient"

    def test_transient_30009(self):
        assert classify_error("30009") == "transient"

    def test_transient_30010(self):
        assert classify_error("30010") == "transient"

    def test_tollfree_rejection_30489(self):
        """Toll-free A2P registration rejected (website not established) is permanent."""
        assert classify_error("30489") == "permanent"

    def test_tollfree_rejection_30475(self):
        """Toll-free A2P registration rejected (consent bundled) is permanent."""
        assert classify_error("30475") == "permanent"

    def test_unknown_code(self):
        assert classify_error("99999") == "unknown"

    def test_none_code(self):
        assert classify_error(None) == "unknown"

    def test_empty_string(self):
        assert classify_error("") == "unknown"


class TestIsGsm7:
    def test_ascii_text(self):
        assert is_gsm7("Hello World!") is True

    def test_with_em_dash(self):
        assert is_gsm7("Hello \u2014 World") is False

    def test_with_smart_quotes(self):
        assert is_gsm7("It\u2019s a test") is False

    def test_empty_string(self):
        assert is_gsm7("") is True

    def test_gsm_extended_chars(self):
        assert is_gsm7("Price: 50\u20ac") is True  # Euro sign is GSM extended


class TestCountSegments:
    def test_short_gsm_one_segment(self):
        assert count_segments("Hello") == 1

    def test_exactly_160_gsm_one_segment(self):
        assert count_segments("x" * 160) == 1

    def test_161_gsm_two_segments(self):
        assert count_segments("x" * 161) == 2

    def test_long_gsm_three_segments(self):
        assert count_segments("x" * 400) == 3

    def test_ucs2_short_one_segment(self):
        # UCS-2 message under 70 chars
        assert count_segments("\u2014" * 50) == 1

    def test_ucs2_long_multiple_segments(self):
        # 150 UCS-2 chars = ceil(150/67) = 3 segments
        assert count_segments("\u2014" * 150) == 3


class TestEnforceMessageLength:
    def test_short_message_unchanged(self):
        msg, segments, encoding = enforce_message_length("Hello!")
        assert msg == "Hello!"
        assert segments == 1
        assert encoding == "gsm7"

    def test_max_segments_respected(self):
        long_msg = "x" * 1000  # Way over 3 segments
        msg, segments, encoding = enforce_message_length(long_msg)
        assert segments <= MAX_SEGMENTS

    def test_truncation_adds_ellipsis(self):
        long_msg = "x" * 1000
        msg, _, _ = enforce_message_length(long_msg)
        assert msg.endswith("...")

    def test_ucs2_truncation(self):
        long_msg = "\u2014" * 500  # Way over UCS-2 3-segment limit
        msg, segments, encoding = enforce_message_length(long_msg)
        assert segments <= MAX_SEGMENTS
        assert encoding == "ucs2"


class TestMaskPhone:
    def test_masks_phone(self):
        assert mask_phone("+15125559876") == "+15125***"

    def test_short_phone_unchanged(self):
        assert mask_phone("+1512") == "+1512"
