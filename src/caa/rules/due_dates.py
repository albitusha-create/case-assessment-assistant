"""Assessment due date calculation. Calendar or business days, holidays skipped."""

from collections.abc import Iterable
from datetime import date, timedelta

from pydantic import BaseModel

from caa.rules.criteria import DueRule


class DueDateResult(BaseModel):
    due_date: date
    days_remaining: int  # calendar days from `today`; negative when overdue
    is_overdue: bool


def _add_business_days(start: date, days: int, holidays: set[date]) -> date:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:  # Mon=0 .. Fri=4
            added += 1
    return current


def calculate_due_date(
    start: date,
    rule: DueRule,
    today: date,
    holidays: Iterable[date] = (),
) -> DueDateResult:
    """Due date from a start date and rule. `today` is passed in so tests are stable."""
    if rule.day_type == "calendar":
        due = start + timedelta(days=rule.days)
    else:
        due = _add_business_days(start, rule.days, set(holidays))
    remaining = (due - today).days
    return DueDateResult(due_date=due, days_remaining=remaining, is_overdue=remaining < 0)
