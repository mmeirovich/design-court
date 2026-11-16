"""Client for the PayRail payments API (see docs/payments-api.md)."""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 10


class ChargeTimeout(Exception):
    """The request to PayRail did not complete within the client timeout."""


class ChargeDeclined(Exception):
    """PayRail answered and declined the charge."""


@dataclass(frozen=True)
class Charge:
    id: str
    amount_cents: int
    currency: str
    status: str  # "succeeded" | "pending"


class PaymentClient:
    def __init__(self, api_key: str, timeout_s: int = DEFAULT_TIMEOUT_S):
        self._api_key = api_key
        self._timeout_s = timeout_s

    def charge(
        self,
        customer_id: str,
        amount_cents: int,
        currency: str = "USD",
        *,
        idempotency_key: str | None = None,
    ) -> Charge:
        """Create a charge on the customer's default card.

        `idempotency_key` is sent as the Idempotency-Key header.
        Raises ChargeTimeout or ChargeDeclined.
        """
        ...

    def refund(
        self,
        charge_id: str,
        amount_cents: int,
        *,
        idempotency_key: str | None = None,
    ) -> str:
        """Refund part or all of a captured charge to its original card. Returns the refund id."""
        ...
