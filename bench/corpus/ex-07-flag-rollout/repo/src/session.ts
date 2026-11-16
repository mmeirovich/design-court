export type Session = {
  userId: number | null;
  orgId: number | null;
  plan: string;
};

const VISITOR: Session = { userId: null, orgId: null, plan: 'visitor' };

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function decodeClaims(token: string): { uid: number; oid: number; plan: string } {
  const payload = token.split('.')[1];
  return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
}

export function currentSession(): Session {
  const token = readCookie('pn_session');
  if (!token) return VISITOR;
  try {
    const claims = decodeClaims(token);
    return { userId: claims.uid, orgId: claims.oid, plan: claims.plan };
  } catch {
    return VISITOR;
  }
}
