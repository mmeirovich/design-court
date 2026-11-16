from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .invoices import Invoice, InvoiceLine, build_invoice
from .money import prorate_cents
from .payments import PaymentClient
from .periods import Period, days_remaining


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_cents: int
    interval: str  # "month" | "year"


PLANS = {
    "starter": Plan("starter", "Starter", 2_900, "month"),
    "team": Plan("team", "Team", 7_900, "month"),
    "business": Plan("business", "Business", 19_900, "month"),
    "starter_annual": Plan("starter_annual", "Starter (annual)", 29_000, "year"),
    "team_annual": Plan("team_annual", "Team (annual)", 79_000, "year"),
    "business_annual": Plan("business_annual", "Business (annual)", 199_000, "year"),
}

SEAT_PRICE_CENTS = 900  # per extra seat, per month


@dataclass
class Subscription:
    id: str
    customer_id: str
    region: str
    plan_id: str
    period: Period
    discount_bps: int = 0  # coupon, applied to every plan charge


def effective_price_cents(sub: Subscription, plan_id: str) -> int:
    """Price of `plan_id` for one full period after the subscription's discount."""
    price = PLANS[plan_id].price_cents
    return price - prorate_cents(price, sub.discount_bps, 10_000)


def add_seats(
    client: PaymentClient, sub: Subscription, seats: int, today: date, *, request_id: str
) -> Invoice:
    """Bill extra seats for the rest of the current period, immediately."""
    full = seats * SEAT_PRICE_CENTS
    full -= prorate_cents(full, sub.discount_bps, 10_000)
    amount = prorate_cents(full, days_remaining(sub.period, today), sub.period.days)
    invoice = build_invoice(sub.region, [InvoiceLine(f"{seats} extra seats (prorated)", amount)])
    client.charge(
        sub.customer_id,
        invoice.total_cents,
        idempotency_key=f"add-seats:{sub.id}:{request_id}",
    )
    return invoice
