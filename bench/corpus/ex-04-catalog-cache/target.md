# RFC-0412: Read-through Redis cache for the product detail endpoint

Author: Dana Okafor (catalog platform). Reviewers: storefront, cart, SRE. Status: ready for review.

## 1. Summary

Put a Redis read-through cache in front of `GET /v1/products/:sku` and invalidate it from the
write path. Targets: at least 95% of detail reads served from Redis, and an end to the load
shedding we see during campaigns. Out of scope: list and search endpoints, stock levels
(`/v1/stock/:sku` is a separate endpoint and its data is not part of the detail payload),
and CDN changes.

## 2. Background

- Peak traffic on the detail endpoint is about 2,400 rps (last campaign). A normal weekday
  peak is about 600 rps.
- The service runs as 6 pods (`infra/catalog-service.yaml`) reading from the read-replica
  pool. During campaigns we return 503 for roughly 6% of detail requests.
- Campaign SKUs have several hundred variants each. The detail query for those is about 300 ms,
  against roughly 15 ms for a typical product. The top campaign SKU takes about 15% of all
  detail reads (about 360 rps at peak).
- Consumers of the endpoint: web storefront, mobile apps, and the cart service
  (`src/services/cart.ts`, which prices carts from it).
- The active catalog is about 900k products. A serialised detail response averages 2.8 KB
  (sampled from production last month).
- Writes go through `updateProduct` in `src/services/productWriter.ts`. Merchandising edits
  and the ERP price sync both use it; combined volume is a few writes per second.

## 3. Design

### 3.1 Read path

The handler in `src/handlers/product.ts` is wrapped with the existing `cache.getOrLoad`
helper (`src/lib/cache.ts`): on a hit we return the stored response body, on a miss we run the
current handler logic once, store the result, and return it. The cached value is the final
serialised response, so a hit skips the query and the formatting.

```ts
const PRODUCT_TTL = 21_600; // seconds (6 h)
const body = await cache.getOrLoad(productKey(sku), PRODUCT_TTL, loadResponse);
```

### 3.2 Keys and values

Key format: `catalog:v1:product:{sku}`. The value is the JSON response body. The `v1` segment is
bumped whenever the response shape changes, so pods running different builds during a rolling
deploy never read each other's incompatible payloads: the new build simply starts with a cold
namespace and the old one ages out under LRU.

Stock is not part of this payload, so inventory changes do not need to invalidate anything.

### 3.3 TTL

| Entry | TTL | Why |
|---|---|---|
| Product found | 6 h | Safety net behind write invalidation; also bounds how long an orphaned key can live |
| Product not found | 30 s | See 3.4 |

Freshness is driven by invalidation (3.5), not by expiry. The 6 h value was picked as the
longest period we are comfortable with if an invalidation is ever missed. Expiry is jittered
by +/-10% so that the keys populated right after a deploy or a Redis restart do not all expire
in the same second.

### 3.4 Negative entries

Unknown and inactive SKUs are cached as a not-found marker for 30 seconds (this is built into
`getOrLoad`). This protects the database from SKU-enumeration scans, which today produce a
steady stream of misses on the primary key index. New SKUs are created inactive by the importer
and activated by a scheduled job at least 15 minutes before launch, so a 30 s negative entry
cannot delay a launch.

### 3.5 Write path

`updateProduct` already does all of its work in one database transaction (row lock, update,
price history, audit entry). We add one statement to that transaction, the last before it
returns:

```ts
await cache.del(productKey(sku));
```

Doing this inside the transaction ties invalidation to the write: if the transaction fails we
never evict, and if `cache.del` throws, the transaction rolls back and the caller sees the
error. The existing `product.updated` event (published after the transaction) is unchanged and
is not used for invalidation.

### 3.6 Failure handling

Redis errors and the 100 ms command timeout in `cache.ts` are treated as misses: the request is
served from the database and `catalog_cache_errors_total` is incremented. A hit ratio below 80%
for 10 minutes pages the on-call.

## 4. Capacity

### 4.1 Memory

Because the TTL is long, residency is effectively "everything read in the last six hours". The
sitemap job and search-engine crawlers touch most of the active catalog every day, so we size for
the whole catalog: 900k products at about 2.8 KB each. That fits comfortably on the 4 GB
cache node (`infra/redis.yaml`), so no per-key size cap or admission policy is needed. Eviction
policy stays `allkeys-lru` as a backstop.

### 4.2 Database load

With a hit ratio of 95% or better, the 2,400 rps peak turns into roughly 120 rps of misses.
That is well inside what the 6 pods can serve, so the 503s during campaigns should go away.
We considered adding request coalescing (single-flight) in the helper and decided against it for
v1: at this miss rate it is extra machinery with its own failure modes (lock leaks, waiter
timeouts). We will revisit it if the miss dashboards show pressure.

### 4.3 Latency

Redis p99 in the same availability zone is about 2 ms. A hit should bring the endpoint p95 from
about 90 ms (typical products) to under 15 ms including serialisation.

## 5. Rollout

1. Merge behind the `catalog_cache_pct` flag at 0%. Deploy to all pods.
2. Raise to 5%, then 25%, then 100% over two weeks, holding at each step for at least two
   business days. Gate each step on 5xx rate, p95 latency, and hit ratio.
3. After one week at 100%, remove the flag and keep the helper.

Rollback is setting the flag to 0%; Redis can be flushed afterwards if needed.

## 6. Observability

- `catalog_cache_hits_total`, `catalog_cache_misses_total`, `catalog_cache_errors_total`,
  per outcome (found / not found).
- Redis `used_memory`, `evicted_keys`, `keyspace_hits`.
- A panel for the top 20 SKUs by request rate, so we can see skew during campaigns.

## 7. Alternatives considered

- **CDN caching of the detail endpoint.** Purge propagation takes one to two minutes and purges
  are per URL, which makes write-time invalidation slow and expensive for products with many
  URLs. Rejected for now; may be added in front of the cache later.
- **In-process LRU in each pod.** Cheapest option, but with 6 pods an invalidation would have to
  be broadcast, and each pod would warm separately after a deploy. Rejected.
- **Write-through (store the new value on write).** Requires the writer to build the response
  body, which duplicates handler logic. Delete-on-write is simpler and the next read repopulates.
- **Shorter TTL (60 s) with no invalidation.** Simple, but it means every price change is up to
  a minute late and the miss rate at peak would be many times the 120 rps estimated above.

## 8. Open questions

- Should the sitemap job pre-warm the cache after a Redis failover, or is the load from a cold
  start acceptable? Needs a load test.
- Do we want a `Cache-Status` response header for debugging, or keep that behind an internal
  header only?
