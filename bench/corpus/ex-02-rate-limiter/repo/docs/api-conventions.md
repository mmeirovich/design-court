# Public API conventions

## Request headers

- `Authorization: Bearer <api key>`; keys look like `pk_live_...` and map to one account.
- `X-Request-Timestamp`: Unix time in milliseconds. Sent by the official SDKs on every call
  and used in support tooling to line up client and server logs. Optional for callers
  using raw HTTP.
- `Idempotency-Key`: honoured on POST requests.

## Rate limit headers

Returned on every response once rate limiting is enabled for the caller:

| Header | Meaning |
|---|---|
| `X-RateLimit-Limit` | Requests per minute allowed for the caller's plan |
| `X-RateLimit-Remaining` | Whole requests left in the current allowance |
| `X-RateLimit-Reset` | Unix time in seconds (UTC) at which the allowance is fully restored |

Throttled requests get `429 Too Many Requests` with a `Retry-After` header (whole seconds)
and the standard error body:

```json
{"error": {"code": "rate_limited", "message": "Too many requests", "retry_after": 3}}
```

SDKs read `X-RateLimit-Reset` as an epoch timestamp and sleep until then when
`Remaining` is 0.

## Errors

All errors use the body shape `{"error": {"code": ..., "message": ...}}`. Codes are stable;
messages are not.
