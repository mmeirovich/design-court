import type { Pool } from 'pg';
import { withTransaction } from '../db/tx';

type Publish = (topic: string, payload: unknown) => Promise<void>;

/**
 * Publishes up to `batch` outbox rows, then deletes them, in one transaction. Several relays
 * can run at once (rows locked by another relay are skipped). If the process dies after
 * publishing but before the commit, the rows are published again on the next run.
 */
export async function relayOnce(pool: Pool, publish: Publish, batch = 100): Promise<number> {
  return withTransaction(pool, async (tx) => {
    const { rows } = await tx.query(
      'SELECT id, topic, payload FROM outbox ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED',
      [batch],
    );
    for (const row of rows) {
      await publish(row.topic, row.payload);
    }
    if (rows.length > 0) {
      await tx.query('DELETE FROM outbox WHERE id = ANY($1::bigint[])', [
        rows.map((r) => r.id),
      ]);
    }
    return rows.length;
  });
}
