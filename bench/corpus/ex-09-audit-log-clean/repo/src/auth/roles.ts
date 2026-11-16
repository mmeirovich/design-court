export type Role = 'support' | 'admin' | 'security_auditor';

export class ForbiddenError extends Error {}

/** Throws ForbiddenError unless the caller's single role is one of `allowed`. */
export function requireRole(ctx: { role: Role }, ...allowed: Role[]): void {
  if (!allowed.includes(ctx.role)) {
    throw new ForbiddenError(`role ${ctx.role} may not perform this action`);
  }
}
