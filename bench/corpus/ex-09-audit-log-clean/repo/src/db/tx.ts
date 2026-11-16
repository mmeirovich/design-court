import { randomUUID } from 'node:crypto';
import type { Pool, PoolClient } from 'pg';

/** Runs `fn` in one transaction (READ COMMITTED): commit if it resolves, roll back if it throws. */
export async function withTransaction<T>(
  pool: Pool,
  fn: (tx: PoolClient) => Promise<T>,
): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

/**
 * Writes an event to the outbox using the caller's transaction. The stored payload gets an
 * `event_id` (a fresh UUID) that consumers can use to recognise redeliveries.
 */
export async function emitEvent(
  tx: PoolClient,
  topic: string,
  payload: Record<string, unknown>,
): Promise<void> {
  const stored = { event_id: randomUUID(), ...payload };
  await tx.query('INSERT INTO outbox (topic, payload) VALUES ($1, $2)', [
    topic,
    JSON.stringify(stored),
  ]);
}
