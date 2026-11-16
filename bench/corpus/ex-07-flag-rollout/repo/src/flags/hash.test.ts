import { describe, expect, it } from 'vitest';
import { fnv1a } from './hash';

const N = 1_000_000;

function slots(key: string): number[] {
  const counts = new Array(100).fill(0);
  for (let id = 1; id <= N; id++) {
    counts[Math.floor((fnv1a(`${key}:${id}`) % 10_000) / 100)]++;
  }
  return counts;
}

describe('fnv1a bucketing', () => {
  it('spreads sequential ids evenly', () => {
    for (const c of slots('pricing-page-layout')) {
      expect(Math.abs(c - N / 100) / (N / 100)).toBeLessThan(0.03);
    }
  });

  it('is independent between keys', () => {
    let a = 0;
    let b = 0;
    let both = 0;
    for (let id = 1; id <= N; id++) {
      const x = fnv1a(`pricing-page-layout:${id}`) % 10_000 < 1_000;
      const y = fnv1a(`checkout-copy:${id}`) % 10_000 < 1_000;
      if (x) a++;
      if (y) b++;
      if (x && y) both++;
    }
    expect(Math.abs(both - (a * b) / N) / ((a * b) / N)).toBeLessThan(0.05);
  });
});
