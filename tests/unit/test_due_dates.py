from datetime import date

from caa.rules import calculate_due_date
from caa.rules.criteria import DueRule

CALENDAR_30 = DueRule(days=30, day_type="calendar", starts_from="intake_date")
BUSINESS_10 = DueRule(days=10, day_type="business", starts_from="review_trigger_date")


def test_calendar_days() -> None:
    result = calculate_due_date(date(2026, 11, 2), CALENDAR_30, today=date(2026, 11, 22))
    assert result.due_date == date(2026, 12, 2)
    assert result.days_remaining == 10
    assert not result.is_overdue


def test_business_days_skip_weekends() -> None:
    # Fri Nov 6, 2026 + 10 business days = Fri Nov 20, 2026
    result = calculate_due_date(date(2026, 11, 6), BUSINESS_10, today=date(2026, 11, 6))
    assert result.due_date == date(2026, 11, 20)


def test_business_days_skip_holidays() -> None:
    # Mon Nov 16 + 10 business days, skipping Thu Nov 26, = Tue Dec 1
    result = calculate_due_date(
        date(2026, 11, 16), BUSINESS_10, today=date(2026, 11, 16), holidays=[date(2026, 11, 26)]
    )
    assert result.due_date == date(2026, 12, 1)


def test_overdue_has_negative_days_remaining() -> None:
    result = calculate_due_date(date(2026, 10, 1), CALENDAR_30, today=date(2026, 11, 5))
    assert result.is_overdue
    assert result.days_remaining == -5


def test_due_today_is_not_overdue() -> None:
    result = calculate_due_date(date(2026, 10, 1), CALENDAR_30, today=date(2026, 10, 31))
    assert result.days_remaining == 0
    assert not result.is_overdue
