# Billing conventions

- **Money** is integer cents, with an ISO currency code alongside. No floats.
- **Rounding.** Every invoice line is rounded half to even on its own, using
  `money.prorate_cents`. Invoice totals are sums of rounded lines and are never re-rounded.
- **Periods.** `Period.end` is exclusive. Prorations use whole days from the change date to
  `Period.end` over the actual length of the period in days.
- **Tax.** Plan prices exclude tax. Tax is calculated per invoice from the customer's
  billing region by `invoices.build_invoice`. Whatever is charged to a card for a
  subscription is an invoice total, never a bare line amount.
- **Discounts.** A subscription's `discount_bps` applies to every plan charge. Use
  `effective_price_cents` rather than the plan's list price for anything that is billed,
  credited or refunded.
- **Credits.** A credit or refund for a period never exceeds what the customer paid for that
  period.
