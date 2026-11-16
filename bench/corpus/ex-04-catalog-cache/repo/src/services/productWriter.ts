import { db } from "../db";
import { events } from "../lib/events";

export interface ProductPatch {
  names?: Record<string, string>;
  descriptions?: Record<string, string>;
  basePriceCents?: number;
  status?: "draft" | "active" | "retired";
}

/** Apply an edit to a product, recording price history and an audit entry. */
export async function updateProduct(sku: string, patch: ProductPatch, actor: string) {
  await db.transaction(async (tx) => {
    const current = await tx.products.lockForUpdate(sku);
    await tx.products.update(sku, patch);
    if (patch.basePriceCents !== undefined && patch.basePriceCents !== current.basePriceCents) {
      await tx.priceHistory.insert({
        sku,
        oldCents: current.basePriceCents,
        newCents: patch.basePriceCents,
        actor,
      });
    }
    await tx.audit.insert({ sku, actor, patch });
  });
  await events.publish("product.updated", { sku });
}
