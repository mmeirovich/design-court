const CATALOG_URL = process.env.CATALOG_URL!;

export interface CartLine {
  sku: string;
  qty: number;
}

/**
 * Price a cart for checkout. Unit prices come from the catalog API; the
 * returned totalCents is the amount the order service charges.
 */
export async function priceCart(lines: CartLine[], currency: string) {
  const priced = await Promise.all(
    lines.map(async (line) => {
      const res = await fetch(
        `${CATALOG_URL}/v1/products/${encodeURIComponent(line.sku)}?currency=${currency}`,
      );
      if (!res.ok) throw new Error(`catalog lookup failed for ${line.sku}: ${res.status}`);
      const product = await res.json();
      return { sku: line.sku, qty: line.qty, unitCents: product.price.amountCents as number };
    }),
  );
  const totalCents = priced.reduce((sum, l) => sum + l.unitCents * l.qty, 0);
  return { currency, lines: priced, totalCents };
}
