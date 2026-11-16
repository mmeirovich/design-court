"""Money helpers for the billing package.

All amounts in billing are integer cents. Do not introduce float or Decimal values.
"""
from __future__ import annotations


def prorate_cents(amount_cents: int, numerator: int, denominator: int) -> int:
    """Return amount_cents * numerator / denominator as whole cents.

    Rounds half to even, using integer arithmetic only.
    """
    if denominator <= 0 or numerator < 0:
        raise ValueError("denominator must be positive and numerator non-negative")
    q, r = divmod(amount_cents * numerator, denominator)
    twice = 2 * r
    if twice > denominator or (twice == denominator and q % 2 == 1):
        q += 1
    return q


def format_cents(cents: int, currency: str = "USD") -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d} {currency}"
