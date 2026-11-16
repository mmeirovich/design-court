import type { Request, Response } from "express";
import { products } from "../db/products";
import { convert, resolveCurrency } from "../lib/money";
import { pickLocale } from "../lib/i18n";

// GET /v1/products/:sku
export async function getProduct(req: Request, res: Response) {
  const sku = req.params.sku;
  const locale = pickLocale(req.headers["accept-language"]);
  const currency = resolveCurrency(req.query.currency as string | undefined, req.geo?.country);

  const row = await products.findDetail(sku);
  if (!row || row.status !== "active") {
    return res.status(404).json({ error: "not_found" });
  }

  res.set("Content-Language", locale);
  res.json({
    sku: row.sku,
    name: row.names[locale] ?? row.names["en"],
    description: row.descriptions[locale] ?? row.descriptions["en"],
    price: {
      amountCents: convert(row.basePriceCents, row.baseCurrency, currency),
      currency,
    },
    variants: row.variants.map((v) => ({
      sku: v.sku,
      label: v.labels[locale] ?? v.labels["en"],
      priceDeltaCents: convert(v.priceDeltaCents, row.baseCurrency, currency),
    })),
    images: row.images,
    updatedAt: row.updatedAt.toISOString(),
  });
}
