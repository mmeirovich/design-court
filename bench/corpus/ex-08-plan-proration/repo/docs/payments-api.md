# PayRail payments API (internal summary)

Base URL `https://api.payrail.example/v2`. Amounts are integers in the currency's minor unit.

## Create a charge
`POST /charges` with `customer`, `amount`, `currency`. Charges the customer's default card
and returns `{id, status}` where status is `succeeded` or `pending` (3-D Secure or bank
review). Declines return HTTP 402.

## Idempotency
Send an `Idempotency-Key` header (up to 255 characters) on any `POST`. PayRail stores the
first response for a key for 24 hours; a repeated request with the same key returns that
stored response and does not create a second charge. A request without the header is never
de-duplicated: every call creates a new charge.

## Timeouts
Typical latency is under 2 seconds, but PayRail can take up to 30 seconds to answer when a
card network is slow. A client that gives up waiting has no way to know the outcome from
the connection alone: the charge may still complete after the client has disconnected.

## Refunds
`POST /charges/{id}/refunds` with `amount`. Refunds go to the original card only, cannot
exceed the captured amount of that charge, and appear on the cardholder's statement after 5
to 10 business days. PayRail has no concept of account credit or balances.
