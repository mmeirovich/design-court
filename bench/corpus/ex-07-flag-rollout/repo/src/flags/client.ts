import { track } from '../analytics';
import { currentSession } from '../session';
import { fnv1a } from './hash';

const RULES_URL = '/flags/rules.json';
const REFRESH_MS = 60_000;

type Rule = {
  kind: 'rollout' | 'experiment';
  percent?: number;
  variants?: Record<string, number>; // weights in basis points, summing to 10000
  allowOrgs?: { id: number; name: string }[];
};

type RuleSet = {
  version: number;
  updatedAt: string;
  killed: string[];
  flags: Record<string, Rule>;
};

let rules: RuleSet | null = null;

async function refresh(): Promise<void> {
  try {
    const res = await fetch(RULES_URL, { cache: 'no-cache' });
    if (!res.ok) return;
    const next: RuleSet = await res.json();
    if (!rules || next.version >= rules.version) rules = next;
  } catch {
    // keep the last good ruleset
  }
}

export async function start(): Promise<void> {
  await refresh();
  setInterval(refresh, REFRESH_MS);
}

function expose(key: string, value: boolean | string): void {
  track('flag_exposed', { flag: key, value, version: rules?.version });
}

export function enabled(key: string): boolean {
  const rule = rules?.flags[key];
  if (!rules || !rule || rules.killed.includes(key)) return false;

  const session = currentSession();
  let on = rule.allowOrgs?.some((o) => o.id === session.orgId) ?? false;
  if (!on && rule.kind === 'rollout') {
    const bucket = Number(session.userId) % 100;
    on = bucket < (rule.percent ?? 0);
  }
  expose(key, on);
  return on;
}

export function variant(key: string): string {
  const rule = rules?.flags[key];
  if (!rules || !rule?.variants || rules.killed.includes(key)) return 'control';

  const session = currentSession();
  const stickyKey = `ff.sticky.${session.userId}.${key}`;
  const saved = localStorage.getItem(stickyKey);
  if (saved && saved in rule.variants) return saved;

  const slot = fnv1a(`${key}:${session.userId}`) % 10_000;
  let upper = 0;
  let chosen = 'control';
  for (const [name, weight] of Object.entries(rule.variants)) {
    upper += weight;
    if (slot < upper) {
      chosen = name;
      break;
    }
  }
  localStorage.setItem(stickyKey, chosen);
  expose(key, chosen);
  return chosen;
}
