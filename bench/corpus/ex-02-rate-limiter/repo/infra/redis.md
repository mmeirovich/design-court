# Shared Redis cluster (production)

Owner: SRE. Consumers: sessions, public API cache, job locks.

## Topology

- Redis 7.2 in **cluster mode**: 3 primaries and 3 replicas (one replica per primary), one
  per availability zone. 16384 hash slots, split evenly across the primaries.
- `maxmemory` 4 GB per primary, `maxmemory-policy volatile-lru`. Current usage is about
  1.4 GB per primary, almost all of it session data.
- Clients must be cluster-aware (`redis.cluster.RedisCluster`); see `src/redis_client.py`.
  The sessions service builds its multi-key operations around `sess:{<user_id>}` keys.

## Latency and failover

- Same-AZ round trip: p50 0.3 ms, p99 0.8 ms. Cross-AZ: p99 about 2 ms.
- `cluster-node-timeout` is 15000 ms. When a primary fails, writes to its slots return errors
  until a replica is promoted, typically 15 to 25 seconds after the failure.

## Sizing figures

Measured on staging with `MEMORY USAGE`:

| Shape | Bytes |
|---|---|
| Hash with two short fields, key about 20 characters, with TTL | 168 |
| String counter, key about 30 characters, with TTL | 96 |
| Session hash (typical) | 1,900 |

## Conventions

- Prefix keys with the owning service (`sess:`, `cache:`, `lock:`, `rl:`).
- Every key must have a TTL.
