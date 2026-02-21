"""
Dynamic holiday computation - replaces hardcoded holiday lists.
Computes federal and Florida state holidays for any year.

Uses dateutil for Easter-dependent holidays.
All computations are pure functions with no external dependencies beyond dateutil.
"""
from datetime import date, timedelta
from functools import lru_cache
from typing import Set

from dateutil.easter import easter


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """
    Find the nth occurrence of a weekday in a given month.
    weekday: 0=Monday, 6=Sunday
    n: 1-based (1st, 2nd, 3rd, etc.)
    """
    first_day = date(year, month, 1)
    # Days until the target weekday
    days_ahead = weekday - first_day.weekday()
    if days_ahead < 0:
        days_ahead += 7
    first_occurrence = first_day + timedelta(days=days_ahead)
    return first_occurrence + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Find the last occurrence of a weekday in a given month."""
    # Start from last day of month
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    days_back = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_back)


def _observed_date(holiday: date) -> date:
    """
    Federal holiday observed rule:
    - Saturday → observed Friday
    - Sunday → observed Monday
    """
    if holiday.weekday() == 5:  # Saturday
        return holiday - timedelta(days=1)
    elif holiday.weekday() == 6:  # Sunday
        return holiday + timedelta(days=1)
    return holiday


@lru_cache(maxsize=16)
def get_federal_holidays(year: int) -> Set[date]:
    """
    Compute all federal holidays for a given year.
    Returns observed dates (adjusted for weekends).
    """
    holidays = set()

    # Fixed-date holidays (observed if on weekend)
    holidays.add(_observed_date(date(year, 1, 1)))     # New Year's Day
    holidays.add(_observed_date(date(year, 7, 4)))     # Independence Day
    holidays.add(_observed_date(date(year, 11, 11)))   # Veterans Day
    holidays.add(_observed_date(date(year, 12, 25)))   # Christmas Day

    # Floating holidays (always on specific weekday - no observed adjustment needed)
    holidays.add(_nth_weekday(year, 1, 0, 3))    # MLK Day: 3rd Monday Jan
    holidays.add(_nth_weekday(year, 2, 0, 3))    # Presidents' Day: 3rd Monday Feb
    holidays.add(_last_weekday(year, 5, 0))       # Memorial Day: Last Monday May
    holidays.add(_observed_date(date(year, 6, 19)))  # Juneteenth: June 19
    holidays.add(_nth_weekday(year, 9, 0, 1))    # Labor Day: 1st Monday Sep
    holidays.add(_nth_weekday(year, 10, 0, 2))   # Columbus Day: 2nd Monday Oct
    holidays.add(_nth_weekday(year, 11, 3, 4))   # Thanksgiving: 4th Thursday Nov

    return holidays


@lru_cache(maxsize=16)
def get_florida_holidays(year: int) -> Set[date]:
    """
    Compute Florida state holidays for a given year.
    Florida FTSA restricts messaging on all federal holidays
    plus additional state-specific holidays.
    """
    holidays = get_federal_holidays(year).copy()

    # Florida-specific additions per Florida statute 110.117
    # Good Friday (Friday before Easter)
    easter_date = easter(year)
    holidays.add(easter_date - timedelta(days=2))  # Good Friday

    # Day after Thanksgiving
    thanksgiving = _nth_weekday(year, 11, 3, 4)
    holidays.add(thanksgiving + timedelta(days=1))

    return holidays


def is_florida_holiday(check_date: date) -> bool:
    """Check if a date is a Florida holiday."""
    return check_date in get_florida_holidays(check_date.year)


def is_federal_holiday(check_date: date) -> bool:
    """Check if a date is a federal holiday."""
    return check_date in get_federal_holidays(check_date.year)
