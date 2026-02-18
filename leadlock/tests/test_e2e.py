"""
End-to-end flow tests.
"""
import pytest
from src.services.phone_validation import normalize_phone, is_valid_us_phone
from src.utils.metrics import Timer, response_time_bucket
from src.services.sms import count_segments


class TestPhoneNormalization:
    def test_10_digit(self):
        assert normalize_phone("5125559876") == "+15125559876"

    def test_11_digit_with_1(self):
        assert normalize_phone("15125559876") == "+15125559876"

    def test_already_e164(self):
        assert normalize_phone("+15125559876") == "+15125559876"

    def test_with_formatting(self):
        assert normalize_phone("(512) 555-9876") == "+15125559876"

    def test_with_dashes(self):
        assert normalize_phone("512-555-9876") == "+15125559876"

    def test_invalid_short(self):
        assert normalize_phone("12345") is None

    def test_valid_us_phone(self):
        assert is_valid_us_phone("+15125559876") is True

    def test_invalid_us_phone(self):
        assert is_valid_us_phone("5125559876") is False

    def test_empty_string_returns_none(self):
        assert normalize_phone("") is None

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_toll_free_number(self):
        result = normalize_phone("1-800-555-0000")
        # Should either normalize to E.164 or return None
        assert result is None or result.startswith("+1")


class TestSmsSegments:
    def test_short_message_one_segment(self):
        assert count_segments("Hi there!") == 1

    def test_160_chars_one_segment(self):
        assert count_segments("a" * 160) == 1

    def test_161_chars_two_segments(self):
        assert count_segments("a" * 161) == 2

    def test_long_message_multiple_segments(self):
        msg = "a" * 500
        assert count_segments(msg) >= 3


class TestTimer:
    def test_timer_basic(self):
        timer = Timer().start()
        ms = timer.stop()
        assert isinstance(ms, (int, float))
        assert ms >= 0

    def test_elapsed_ms(self):
        timer = Timer().start()
        assert isinstance(timer.elapsed_ms, (int, float))
        assert timer.elapsed_ms >= 0

    def test_timer_measures_time(self):
        """Timer should actually measure elapsed time, not always return 0."""
        import time as time_mod
        timer = Timer().start()
        time_mod.sleep(0.01)  # 10ms
        ms = timer.stop()
        assert ms >= 5  # Allow margin but verify it's not 0


class TestResponseTimeBucket:
    def test_under_10s(self):
        assert response_time_bucket(5000) == "0-10s"

    def test_under_30s(self):
        assert response_time_bucket(15000) == "10-30s"

    def test_under_60s(self):
        assert response_time_bucket(45000) == "30-60s"

    def test_over_60s(self):
        assert response_time_bucket(90000) == "60s+"
