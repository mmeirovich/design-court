"""Billing periods. A period runs from `start` (inclusive) to `end` (exclusive);
`end` is the next renewal date."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def days_remaining(period: Period, on: date) -> int:
    """Whole days from `on` to the end of the period, never negative."""
    return max((period.end - on).days, 0)


def add_months(d: date, months: int, anchor_day: int) -> date:
    """Move `d` forward by `months`, landing on `anchor_day` or the last day of a shorter month."""
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor_day, last))


def next_period(period: Period, interval: str, anchor_day: int) -> Period:
    months = 12 if interval == "year" else 1
    return Period(period.end, add_months(period.end, months, anchor_day))
