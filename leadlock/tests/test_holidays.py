"""
Holiday computation tests.
Florida FTSA restricts messaging on state holidays - $500-$1,500/violation.
"""
from datetime import date

from src.utils.holidays import (
    get_federal_holidays,
    get_florida_holidays,
    is_florida_holiday,
    is_federal_holiday,
    _nth_weekday,
    _observed_date,
)


class TestNthWeekday:
    def test_first_monday_january_2026(self):
        # Jan 1, 2026 is Thursday. First Monday is Jan 5.
        assert _nth_weekday(2026, 1, 0, 1) == date(2026, 1, 5)

    def test_third_monday_january_2026(self):
        # MLK Day 2026: 3rd Monday in January = Jan 19
        assert _nth_weekday(2026, 1, 0, 3) == date(2026, 1, 19)

    def test_fourth_thursday_november_2026(self):
        # Thanksgiving 2026: 4th Thursday in November = Nov 26
        assert _nth_weekday(2026, 11, 3, 4) == date(2026, 11, 26)


class TestObservedDate:
    def test_saturday_observed_friday(self):
        # July 4, 2026 is Saturday - observed on Friday July 3
        assert _observed_date(date(2026, 7, 4)) == date(2026, 7, 3)

    def test_sunday_observed_monday(self):
        # Jan 1, 2023 is Sunday - observed Monday Jan 2
        assert _observed_date(date(2023, 1, 1)) == date(2023, 1, 2)

    def test_weekday_unchanged(self):
        # Jan 1, 2026 is Thursday - no adjustment
        assert _observed_date(date(2026, 1, 1)) == date(2026, 1, 1)


class TestFederalHolidays:
    def test_returns_11_holidays(self):
        holidays = get_federal_holidays(2026)
        assert len(holidays) == 11

    def test_new_years_day(self):
        holidays = get_federal_holidays(2026)
        assert date(2026, 1, 1) in holidays

    def test_christmas(self):
        holidays = get_federal_holidays(2026)
        assert date(2026, 12, 25) in holidays

    def test_independence_day_2026_observed(self):
        # July 4, 2026 is Saturday - observed Friday July 3
        holidays = get_federal_holidays(2026)
        assert date(2026, 7, 3) in holidays

    def test_thanksgiving_2026(self):
        holidays = get_federal_holidays(2026)
        assert date(2026, 11, 26) in holidays

    def test_memorial_day_2026(self):
        # Last Monday in May 2026 = May 25
        holidays = get_federal_holidays(2026)
        assert date(2026, 5, 25) in holidays

    def test_labor_day_2026(self):
        # 1st Monday in September 2026 = Sep 7
        holidays = get_federal_holidays(2026)
        assert date(2026, 9, 7) in holidays


class TestFloridaHolidays:
    def test_includes_all_federal_holidays(self):
        federal = get_federal_holidays(2026)
        florida = get_florida_holidays(2026)
        assert federal.issubset(florida)

    def test_includes_good_friday_2026(self):
        # Easter 2026 is April 5, Good Friday is April 3
        florida = get_florida_holidays(2026)
        assert date(2026, 4, 3) in florida

    def test_includes_day_after_thanksgiving_2026(self):
        # Thanksgiving 2026 is Nov 26, day after = Nov 27
        florida = get_florida_holidays(2026)
        assert date(2026, 11, 27) in florida

    def test_more_holidays_than_federal(self):
        federal = get_federal_holidays(2026)
        florida = get_florida_holidays(2026)
        assert len(florida) > len(federal)


class TestIsFloridaHoliday:
    def test_good_friday_is_holiday(self):
        assert is_florida_holiday(date(2026, 4, 3)) is True

    def test_random_weekday_not_holiday(self):
        assert is_florida_holiday(date(2026, 3, 10)) is False

    def test_christmas_is_holiday(self):
        assert is_florida_holiday(date(2026, 12, 25)) is True


class TestIsFederalHoliday:
    def test_new_years_is_holiday(self):
        assert is_federal_holiday(date(2026, 1, 1)) is True

    def test_random_date_not_holiday(self):
        assert is_federal_holiday(date(2026, 6, 15)) is False
