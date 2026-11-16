import type { Pool } from 'pg';
import { withTransaction } from '../db/tx';

export interface SiemClient {
  send(event: Record<string, unknown>): Promise<void>;
}

/** Topics forwarded to the SIEM. */
export const SIEM_TOPICS = ['account.suspended', 'account.reinstated'];

/**
 * Forwards one event to the SIEM unless its `event_id` was already forwarded. The seen-row
 * insert and the send share a transaction: if send() throws, the seen-row rolls back and a
 * redelivery tries again. If send() succeeds but the commit then fails, the redelivery
 * forwards the event a second time.
 */
export async function handleSiemEvent(
  pool: Pool,
  siem: SiemClient,
  event: { event_id: string } & Record<string, unknown>,
): Promise<void> {
  await withTransaction(pool, async (tx) => {
    const res = await tx.query(
      'INSERT INTO siem_export_seen (event_id) VALUES ($1) ON CONFLICT (event_id) DO NOTHING',
      [event.event_id],
    );
    if (res.rowCount === 0) return;
    await siem.send(event);
  });
}
