# Design: AcmePay webhook ingestion

Status: draft for review. Owner: payments team.

## 1. Goal
Keep our `payments` table in sync with AcmePay by receiving its webhooks, instead of the
nightly reconciliation job. Events in scope: `payment.succeeded`, `payment.refunded`,
`payment.disputed` (see `docs/acmepay-api.md`).

## 2. Receiving events
`POST /webhooks/acmepay` parses the JSON body, then verifies the `X-Acme-Signature` header
by computing HMAC-SHA256 over the re-serialised JSON (`json.dumps(body, sort_keys=True)`)
using the endpoint secret. Requests that fail verification get a 401.

The webhook secret is stored in `config/settings.yaml` next to the other integration
settings so that operations can rotate it without a deploy.

## 3. Processing
The handler does all the work inside the request, in this order: update the `payments` row,
send the customer a confirmation email, and post an entry to the ledger service. It then
returns 200. The ledger call is typically 2-4 seconds under load.

AcmePay delivers each event exactly once, so no de-duplication is needed. If a step fails
we return 500 and rely on AcmePay to retry.

Follow-up work (analytics export) is handed to the existing queue with
`queue.enqueue_job("analytics", payload)`.

## 4. Data model
Add the event id to `payments` so we can trace each row back to the event that last changed it:

```sql
ALTER TABLE payments ADD COLUMN acme_event_id TEXT NOT NULL;
```

Raw webhook payloads are kept for 30 days for support investigations.

## 5. Refunds
`payment.refunded` events set the payment status to `refunded` and notify the customer.

## 6. Rollout
Deploy behind the `acmepay_webhooks` flag, enable for 10% of merchants, then all. The
nightly reconciliation job stays until we have a week of clean data.

## 7. Privacy
Webhook payloads contain customer identifiers. Payloads are stored encrypted, and deleted
after 90 days to match our data retention policy.
