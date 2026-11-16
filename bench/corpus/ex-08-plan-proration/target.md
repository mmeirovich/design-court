# Mid-cycle plan changes with proration

Status: ready for review. Author: billing squad. Reviewers: payments, support.

## 1. Summary
Today a customer can only move between Starter, Team and Business at renewal; anything else
goes through support, who edit the subscription by hand and raise a manual credit. This
design lets customers change plan from the settings page at any time. The price difference
is prorated over the days left in the current billing period.

## 2. Background
- Plans and prices live in `PLANS` in `src/billing/subscriptions.py`: Starter $29, Team $79
  and Business $199 per month, and annual variants at ten times the monthly price.
- A `Period` (`src/billing/periods.py`) has an inclusive `start` and an exclusive `end`.
  Monthly periods renew on the signup day of month, clamped to the last day of shorter
  months. `days_remaining(period, on)` returns whole days from `on` to `end`.
- `add_seats` already prorates extra seats for the rest of the period and bills the customer
  immediately. Plan changes follow the same shape.
- Card charges go through `PaymentClient` (`src/billing/payments.py`), a thin wrapper over
  the PayRail API (`docs/payments-api.md`).

## 3. Behaviour
1. **Scope.** A customer can move between plans of the same interval only: monthly to
   monthly, annual to annual. Switching between monthly and annual remains a renewal-time
   action and is out of scope.
2. **Upgrade.** A change to a plan with a higher price takes effect immediately. The
   customer pays the prorated difference now rather than on the next renewal invoice, as
   `add_seats` does.
3. **Downgrade.** A change to a plan with a lower price also takes effect immediately. The
   customer gets back the unused value of the old plan, less the cost of the new plan for
   the remaining days. That is the same net calculation as for an upgrade, and it comes out
   negative.
4. **Annual plans.** Annual plans follow the same rules over their 12-month period.
5. **Billing period.** The period does not move. The renewal date and the anchor day stay as
   they were, so the next renewal charges the full price of the new plan.
6. **Dates.** All day counts use UTC calendar dates.
7. **Limits.** At most one plan change can be pending per subscription (see section 6).

## 4. Calculation
For a change on date `on` in period `p` from plan `old` to plan `new`:

```python
def preview_change(sub, new_plan_id, on):
    frac = days_remaining(sub.period, on) / sub.period.days
    credit = round(PLANS[sub.plan_id].price_cents * frac)
    charge = round(PLANS[new_plan_id].price_cents * frac)
    return charge - credit          # cents; negative for a downgrade
```

- The credit is the unused part of the old plan; the charge is the new plan for the same
  remaining days.
- Each of the two amounts is rounded to the cent separately, half to even, and the net is
  their difference. The net is not rounded again.
- Because the unit is the day, the day of the change counts as a day on the new plan.

## 5. Worked example
Customer on Starter ($29.00) upgrades to Team ($79.00) on 21 Feb 2026. Their period runs
3 Feb 2026 to 3 Mar 2026, so 10 of the period's 30 days remain.

| Item | Calculation | Amount |
|---|---|---|
| Credit, Starter | 2900 x 10/30 = 966.67, rounded | $9.67 |
| Charge, Team | 7900 x 10/30 = 2633.33, rounded | $26.33 |
| Net | 26.33 - 9.67 | **$16.66** |

The settings page shows this net before the customer confirms. At the next renewal on
3 Mar the customer is billed the full $79.00.

## 6. Data model
```sql
CREATE TABLE plan_changes (
  id              uuid PRIMARY KEY,
  subscription_id uuid        NOT NULL REFERENCES subscriptions (id),
  from_plan       text        NOT NULL,
  to_plan         text        NOT NULL,
  effective_on    date        NOT NULL,
  net_cents       integer     NOT NULL,
  status          text        NOT NULL CHECK (status IN ('pending', 'applied', 'failed')),
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX plan_changes_one_pending
  ON plan_changes (subscription_id) WHERE status = 'pending';
```
The partial unique index enforces the one-pending-change limit even if two browser tabs
confirm at once; the loser gets a 409 and the UI reloads the preview.

## 7. Change flow
`POST /subscriptions/{id}/plan-change` with the target plan and the net amount the customer
was shown.

1. In one short transaction, lock the subscription row (`SELECT ... FOR UPDATE`) and
   recompute the preview on the server. If its net differs from the amount the client sent
   (for example because the UTC date rolled over while the page was open), return 409 with
   the new preview and stop.
2. In the same transaction insert a `plan_changes` row with status `pending`, then commit
   before talking to PayRail.
3. Settle the net:
   - net greater than zero: `PaymentClient.charge(customer_id, net, currency)`;
   - net less than zero: return the amount to the customer;
   - net zero: nothing to settle.
4. In one database transaction, set `subscriptions.plan_id` to the new plan, set the
   `plan_changes` row to `applied`, and add the change to the customer's invoice history
   with a line for the net amount.
5. Send the confirmation email through the existing notification queue.

## 8. Failure handling
- `ChargeDeclined`: set the row to `failed`, keep the old plan, and show the card error in
  the UI. Nothing is retried.
- `ChargeTimeout`: retry the charge up to 3 more times with backoff of 1, 2 and 4 seconds.
  If the last attempt also times out, set the row to `failed` and keep the old plan. The UI
  shows "we could not complete the change, please try again".
- Crash between step 3 and step 4: a `pending` row older than 10 minutes raises an alert
  to the billing on-call, who settle it by hand. Rows are never auto-completed.

## 9. Rollout
1. Ship the migration. The table is new and nothing reads it, so this is safe on its own.
2. Enable the `plan_changes` flag for staff workspaces for one week.
3. Enable for 5% of customers on monthly plans for one week, then 100% of monthly plans.
4. Enable for annual plans one week after step 3 completes, because the amounts are larger
   and an error costs more to unwind.

Exit criteria for each step: fewer than 2% of changes end `failed`, and no recorded case of
the charged net differing from the previewed net.

## 10. Alternatives considered
- **Changes only at renewal** (status quo, plus a "scheduled change" button). Simplest, but
  it does not remove the support load for customers who need Team features today.
- **Bill a daily rate and true up on the renewal invoice.** Avoids charging mid-period but
  makes the renewal invoice hard to explain and delays revenue on upgrades.
- **Move the renewal date to the change date.** Gives clean full-price charges but surprises
  customers with a new billing day and breaks annual reporting by cohort.

## 11. Open questions
- Should the confirmation email show the day-by-day working for the net amount? Support
  would like it; deferred to a follow-up.
- Do we need a per-subscription rate limit on plan changes beyond the single pending slot?
  We will watch the first two weeks of data and decide.
