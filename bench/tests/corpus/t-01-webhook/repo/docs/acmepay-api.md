# AcmePay webhooks (vendor documentation, excerpt)

- Events are delivered **at least once**. The same event may arrive more than once, and
  events may arrive **out of order**. Every event has a unique `id` (`evt_...`).
- Your endpoint must return a 2xx status **within 5 seconds**. Slower or non-2xx responses
  count as failed deliveries and are retried with exponential backoff for up to 24 hours.
- Each request carries `X-Acme-Signature`: HMAC-SHA256 of the **raw request body** using your
  endpoint secret, hex encoded. Compute it over the bytes exactly as received.
- Maximum payload size: 256 KB.
- Event types: `payment.succeeded`, `payment.refunded` (full or partial), `payment.disputed`.
