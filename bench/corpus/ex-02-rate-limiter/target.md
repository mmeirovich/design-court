# RFC-017: Per-API-key rate limiting for the public API

| | |
|---|---|
| Status | In review |
| Owner | API platform |
| Reviewers | SRE, Billing, Developer Relations |
| Target | 2026.12 release train |

## 1. Summary

Today the public API is limited only by the edge proxy's per-IP rule (`limit_req`, 20 r/s).
That stops floods, but it cannot tell a paying customer's integration from a scraper behind
the same NAT, and it cannot express plans. This RFC adds a token-bucket limiter per API key
and per account, enforced in the API middleware. Plan values come from
`config/rate_limits.yaml`; state lives in the shared Redis cluster (`infra/redis.md`).

Non-goals: per-endpoint limits, cost-weighted requests, customer-facing usage dashboards. The
bucket script already takes a `cost` argument, so these can follow without a data change.

## 2. Requirements

| # | Requirement |
|---|---|
| R1 | A request is admitted only if both its key bucket and its account bucket have a token. |
| R2 | Added p99 latency on the request path stays under 1 ms. |
| R3 | 429 responses and `X-RateLimit-*` headers follow `docs/api-conventions.md`. |
| R4 | Plan values live in config, not code. |
| R5 | Rejections are observable per key (`ratelimit_rejected_total` and the abuse report). |

## 3. Design

### 3.1 Token bucket

Each bucket is a Redis hash with fields `tokens` and `ts` (milliseconds). Capacity is the
plan's `burst`; refill is continuous at the plan's `refill_per_sec`. On evaluation:

    tokens = min(burst, tokens + (now - ts) / 1000 * refill_per_sec)
    admit if tokens >= cost, then tokens -= cost; ts = now

A bucket that does not exist is treated as full. We prefer a bucket over fixed windows
because fixed windows admit up to twice the limit across a boundary, and over a sliding
window log because the log costs memory proportional to the limit (see section 8).

### 3.2 Evaluating key and account together

Both buckets are evaluated in one Lua script, `ratelimit/bucket.lua`, so a request is debited
from both or from neither (R1). Keys are `rl:key:<key_id>` and `rl:acct:<account_id>`:

```lua
-- KEYS[1] = rl:key:<key_id>      KEYS[2] = rl:acct:<account_id>
-- ARGV    = now_ms, cost, key_burst, key_refill, acct_burst, acct_refill, ttl_s
-- returns { allowed, key_tokens, acct_tokens, retry_after_ms }
```

The script is registered once at start-up with `load_script` and called through
`run_script` in `src/redis_client.py`. It does one round trip and no read-modify-write
happens outside it.

### 3.3 Local balance cache

Going to Redis on every request would put roughly 38k script calls per second on the
cluster at fleet peak and add about 0.8 ms p99 per request, which spends most of R2. Instead
each API process keeps a local copy of the buckets it has seen (balance and last-sync time)
and decides locally:

- On a request, admit if `synced_balance - spent_since_sync >= cost`, and add `cost` to
  `spent_since_sync`.
- Every 2 s a background task takes each bucket touched in the last interval and calls the
  script from 3.2 with `cost = spent_since_sync`, clamped at the available balance. The
  returned balances replace the local copy.
- A key the process has not seen is loaded with a synchronous script call (`cost = 0`).
  Local entries idle for 60 s are dropped.

Because every sync debits the authoritative bucket, the worst-case overshoot of a limit is
one sync interval of refill: 2 s at the plan's `refill_per_sec`, about 2 tokens on Free and 40
on Pro. We consider that acceptable for a limiter whose purpose is protecting capacity.

### 3.4 Time source

The script takes `now_ms` as an argument rather than calling `TIME`, so a script can be
replayed against fixtures and so that every replica agrees on the clock used for refill. `now_ms`
is read from the `X-Request-Timestamp` header when present (the SDKs set it on every call)
and falls back to the API process's wall clock otherwise. This also means a request that sat in
a client-side retry queue is charged at the time the client made it.

### 3.5 Bucket expiry

Bucket hashes are written with a 60 s TTL, refreshed on every write, so idle keys disappear
and Redis memory follows active keys rather than issued keys. The infra convention that
every key has a TTL (`infra/redis.md`) is met by this.

### 3.6 Redis errors

`src/redis_client.py` uses a 50 ms socket timeout. If the load in 3.3 times out or fails, the
middleware logs it, increments `ratelimit_redis_errors_total` and admits the request. Failed
background syncs are retried on the next 2 s tick and the local copy keeps being used in the
meantime. We page when the error rate stays above 1% for 5 minutes.

## 4. Plans

| Plan | Per-key limit | Per-key burst | Per-account limit | Per-account burst |
|---|---|---|---|---|
| Free | 100 req/min | 200 | 300 req/min | 600 |
| Pro | 1,200 req/min | 2,400 | 3,600 req/min | 7,200 |
| Enterprise | 6,000 req/min | 12,000 | 30,000 req/min | 60,000 |

Burst is two minutes of the sustained limit on every plan. Refill rates are set per plan in
`config/rate_limits.yaml` and loaded at start-up (R4); changing a plan needs a restart, which the
rolling deploy makes cheap.

## 5. Capacity

Redis memory, worst case where every issued key and account is active at once:

    (1.2M key buckets + 85k account buckets) x ~170 B = ~218 MB

The 170 B figure is the staging measurement for a two-field hash with a TTL
(`infra/redis.md`: 168 B). Spread over three primaries that is about 73 MB each, against
4 GB `maxmemory` and 1.4 GB already in use. We do not need to resize the cluster.

Script traffic after 3.3 scales with active keys, not requests: one call per active key per
2 s sync. The busiest hour in the last quarter had about 180k distinct active keys.

Rejection counters (R5) are `rl:rej:<key_id>:<yyyymmddhh>` strings maintained with
`incr_with_ttl(key, 7200)` from `src/redis_client.py`. They cost 96 B each and only exist for
keys that were actually throttled in the last two hours.

## 6. Response headers

Per R3 and `docs/api-conventions.md`:

- `X-RateLimit-Limit`: the plan's per-key limit per minute.
- `X-RateLimit-Remaining`: `floor(min(key_tokens, acct_tokens))`.
- `X-RateLimit-Reset`: seconds until the key bucket is full again.
- On 429, `Retry-After` is `ceil(retry_after_ms / 1000)` and the body is the standard
  `rate_limited` error.

## 7. Rollout

1. Ship with `ratelimit_mode=shadow`: evaluate and log the decision and the metrics, never reject.
2. After one week of shadow data, compare would-be rejections against the top 50 keys by
   volume with Developer Relations and warn any customer who would be throttled.
3. Enforce for Free (`ratelimit_mode=enforce_free`), then Pro, then Enterprise, a week apart.
4. Remove the flag after Enterprise has been enforced for two weeks without escalations.

Rollback at any stage is the flag; the buckets are inert when mode is `off`.

## 8. Alternatives considered

- **Edge-only limiting at the proxy.** Rejected: the API key is only known after
  authentication, and the proxy cannot see accounts.
- **Fixed-window counters with `incr_with_ttl`.** Simple and cheap, but a client can send two
  full windows back to back across a boundary. We still use `incr_with_ttl` for the
  rejection counters, where precision is not needed.
- **Sliding-window log in sorted sets.** Exact, but memory is proportional to the limit:
  6,000 entries per Enterprise key.
- **Per-process limits with no shared state.** Cheapest, but a customer's effective limit would
  depend on which replicas they happen to hit.

## 9. Open questions

- Should `/v1/export` get a stricter per-endpoint bucket? Deferred; the `cost` argument leaves
  room for it.
- Do Enterprise contracts need per-account overrides? If so we add an `overrides:` block to
  `config/rate_limits.yaml` keyed by account id; no schema change.
