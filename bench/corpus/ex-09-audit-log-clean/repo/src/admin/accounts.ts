import type { Pool } from 'pg';
import { emitEvent, withTransaction } from '../db/tx';
import { requireRole, type Role } from '../auth/roles';

export interface AdminContext {
  adminId: string;   // admin_users.id
  role: Role;
  ip: string;        // client address resolved by the request middleware
  requestId: string; // UUID assigned by the request middleware
}

export type SuspendReason = 'fraud' | 'nonpayment' | 'abuse' | 'customer_request';

/** Returns false when the account was already suspended and nothing changed. */
export async function suspendAccount(
  pool: Pool,
  ctx: AdminContext,
  accountId: string,
  reason: SuspendReason,
): Promise<boolean> {
  requireRole(ctx, 'admin');
  return withTransaction(pool, async (tx) => {
    const res = await tx.query(
      `UPDATE accounts SET status = 'suspended', suspended_at = now(), updated_at = now()
        WHERE id = $1 AND status = 'active'`,
      [accountId],
    );
    if (res.rowCount === 0) return false;
    await emitEvent(tx, 'account.suspended', { accountId, reason });
    return true;
  });
}

/** Returns false when the account was not suspended and nothing changed. */
export async function reinstateAccount(
  pool: Pool,
  ctx: AdminContext,
  accountId: string,
): Promise<boolean> {
  requireRole(ctx, 'admin');
  return withTransaction(pool, async (tx) => {
    const res = await tx.query(
      `UPDATE accounts SET status = 'active', suspended_at = NULL, updated_at = now()
        WHERE id = $1 AND status = 'suspended'`,
      [accountId],
    );
    if (res.rowCount === 0) return false;
    await emitEvent(tx, 'account.reinstated', { accountId });
    return true;
  });
}
