"""Invoice construction. Prices are tax-exclusive; tax is added per invoice."""
from __future__ import annotations

from dataclasses import dataclass

from .money import prorate_cents

# Tax rate in basis points, keyed by the customer's billing region.
TAX_RATE_BPS = {
    "US-NY": 800,
    "US-OR": 0,
    "DE": 1900,
    "GB": 2000,
}


@dataclass(frozen=True)
class InvoiceLine:
    description: str
    amount_cents: int


@dataclass(frozen=True)
class Invoice:
    lines: list[InvoiceLine]
    subtotal_cents: int
    tax_cents: int
    total_cents: int


def build_invoice(region: str, lines: list[InvoiceLine]) -> Invoice:
    """Sum the lines and add tax for `region`. Callers charge `total_cents`."""
    subtotal = sum(line.amount_cents for line in lines)
    tax = prorate_cents(subtotal, TAX_RATE_BPS[region], 10_000)
    return Invoice(lines, subtotal, tax, subtotal + tax)
