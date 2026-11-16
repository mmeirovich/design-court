import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL!, {
  commandTimeout: 100,
  maxRetriesPerRequest: 1,
});

const NOT_FOUND_MARKER = "__not_found__";
const NEGATIVE_TTL_MS = 30_000;

/** Fetch a JSON value. Returns null on a miss or if Redis is unavailable. */
export async function get<T>(key: string): Promise<T | null> {
  try {
    const raw = await redis.get(key);
    return raw === null ? null : (JSON.parse(raw) as T);
  } catch {
    return null;
  }
}

/**
 * Store a JSON value.
 * @param ttlMs time to live in milliseconds
 */
export async function set(key: string, value: unknown, ttlMs: number): Promise<void> {
  try {
    await redis.set(key, JSON.stringify(value), "PX", ttlMs);
  } catch {
    // a cache write failure must never fail the request
  }
}

/** Delete a key. Errors propagate so callers can decide whether to retry. */
export async function del(...keys: string[]): Promise<void> {
  await redis.del(...keys);
}

/**
 * Read-through helper.
 *
 * @param ttlMs  time to live of a loaded value, in milliseconds
 * @param loader produces the value on a miss; return null for "does not exist".
 *               A null result is remembered for 30 seconds so repeated lookups
 *               of unknown keys do not reach the database.
 */
export async function getOrLoad<T>(
  key: string,
  ttlMs: number,
  loader: () => Promise<T | null>,
): Promise<T | null> {
  let raw: string | null = null;
  try {
    raw = await redis.get(key);
  } catch {
    raw = null;
  }
  if (raw === NOT_FOUND_MARKER) return null;
  if (raw !== null) return JSON.parse(raw) as T;

  const value = await loader();
  try {
    if (value === null) {
      await redis.set(key, NOT_FOUND_MARKER, "PX", NEGATIVE_TTL_MS);
    } else {
      await redis.set(key, JSON.stringify(value), "PX", ttlMs);
    }
  } catch {
    // ignore: the caller still gets the loaded value
  }
  return value;
}
