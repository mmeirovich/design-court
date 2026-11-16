# RFC: Percentage rollouts evaluated in the browser

Author: Dana K. (web platform). Reviewers: web platform, security, growth. Status: request for comments.

## TL;DR

We replace build-time environment flags with one JSON ruleset that every browser downloads and
evaluates locally. Product can ramp a feature from 0 to 100% by publishing a new ruleset, with
no deploy. Evaluating a flag costs a function call and no network. A kill list in the same file
turns a feature off for everyone within a minute.

## Background

Flags today are `FLAG_*` environment variables baked into the web bundle at build time.
Changing a percentage means a rebuild and a deploy, about 25 minutes end to end. Last quarter
we ramped four features this way and every ramp took three deploys. Growth also wants to run
layout tests on the logged-out pricing page, which the current setup cannot do at all.

A prototype lives in `src/flags/`. This RFC describes what we ship around it, and the
prototype's behaviour is the starting point rather than a rewrite.

## Requirements

- **R1.** Change a percentage without a deploy.
- **R2.** Evaluate synchronously during render. A page checks 30-40 flags, so a network call
  per flag is out of the question.
- **R3.** A kill switch that takes effect within a minute.
- **R4.** Ramps are monotonic: moving a flag from 10% to 25% only adds users, it never swaps
  them.
- **R5.** Early access for named customer organisations (design partners) regardless of the
  percentage.
- **R6.** Exposure events, so analytics can attribute a metric to a flag.
- **R7.** Works in the signed-in app and on the logged-out marketing site.

## Design

### The ruleset

`config/flags/rules.json` is the source of truth. The admin tool validates it (percentages
between 0 and 100, weights summing to 10,000, known flag keys) and publishes it to
`https://app.pixelnest.example/flags/rules.json`. The file has a `version`, a `killed` list
and a map of flags. A flag is either a `rollout` (a percentage) or an `experiment` (named
variants with weights in basis points). Both may carry `allowOrgs` for R5, which targets
customers by organisation id. It is rules only, with no per-user data, and with the ~60 flags
we expect it is about 9 KB gzipped.

### Rollouts

`enabled(key)` computes `bucket = userId % 100` and returns `bucket < percent`. User ids are
sequential integers, so `% 100` spreads users evenly over the 100 buckets without a hash, and
because the bucket is a pure function of the id, raising the percentage only ever adds users
(R4). Users whose organisation is in `allowOrgs` get the flag regardless of their bucket.

The user's id comes from the session cookie, which is all the client needs to compute a
bucket.

### Experiments

`variant(key)` uses 32-bit FNV-1a over `<key>:<userId>`, modulo 10,000, and maps the result
onto the variant weights. We use FNV-1a rather than a cryptographic hash because all it has to
do is spread ids evenly and independently per experiment key. It is a few lines, has no
dependency and runs in about a microsecond. Two experiments therefore split users
independently of each other, which is what growth needs when more than one test runs at once.

### Delivery and the kill switch

`start()` fetches the ruleset before the first render, then refreshes it every 60 seconds
(`REFRESH_MS`). The file is served through the CDN like our other static JSON. Killing a
feature is a one-line publish that adds its key to `killed`; clients pick it up on their next
poll, so it is in effect within a minute (R3).

If a refresh fails, the client keeps the last good ruleset. If the very first fetch fails,
every flag evaluates to off and every experiment to `control`. A ruleset with a lower
`version` than the one in memory is ignored.

Polling load at peak is 24,000 open tabs, each polling once a minute: 400 requests per second,
about 3.6 MB/s at 9 KB each. That is trivial for the CDN.

### Exposure logging

Each evaluation emits a `flag_exposed` event with the flag key, the value and the ruleset
version. The event is emitted once per flag per page load, which keeps volume proportional to
the number of flags on the page rather than the number of renders. Analytics joins on the user
id to attribute conversion to a flag.

## Ramp plan

| Flag | What it is | Stages |
|---|---|---|
| `checkout-v3` | rebuilt payment step | 0.1%, 1%, 5%, 25%, 100%, 24 h at each |
| `shared-boards-v2` | real-time boards that teammates edit together | 10%, 25%, 50%, 100%, a week each |
| `new-onboarding-checklist` | first-run checklist | 25%, then 100% |
| `pricing-page-layout` | logged-out pricing page, 3 layouts | experiment, 50/25/25 |
| `usage-based-pricing-2027` | new billing model | design partners only (`allowOrgs`) |

`checkout-v3` starts at 0.1% so a payment-step regression is visible in the error rate while it
touches about 2,400 of our 2.4M registered accounts. Up to six flags are in flight at the same
time during the first quarter, so growth will read several of these ramps against the same
baseline metrics.

## Alternatives considered

- **Server-side evaluation behind a flag service.** The server would evaluate and ship the
  result per request. It needs either a call per flag or server-rendered pages, and it breaks
  R2 for the client-rendered app.
- **A hosted flag product.** The quote was $2,400/month at 310k weekly actives against near
  zero for this design. We can revisit it if the rules grow past what a JSON file can express.
- **Evaluate at the edge.** Possible, and it would keep the ruleset private, but the edge
  runtime cannot read the session cookie's claims today and the work is larger than the rest of
  this RFC. Deferred.

## FAQ

**Does a signed-in user see the same thing on every device?** Yes. The bucket and the
experiment hash both come from the user id, so a phone and a laptop agree.

**What happens when a visitor signs in?** From then on they are evaluated with their user id,
like everyone else.

**What stops someone editing the ruleset by hand?** Only the admin tool can publish, and it
runs the validation above. Browsers cannot change the file for anyone else.

**Can a flag depend on another flag?** Not in this version.

## Open questions

- Who can edit the ruleset? Proposal: any member of `product-eng`, with the change log kept
  by the admin tool.
- Should staging and production share one ruleset with an `env` field, or have two files?
- Do we want a per-flag description field for the admin UI?
