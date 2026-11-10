# Lens library

Pick the lenses that fit the target. Each lens has a finding-ID prefix and a brief to
paste into the reviewer's prompt (adapt the brief with specifics from the target and
codebase - name the actual modules, APIs and flows).

## Always include

### RT - Red team (assumptions and failure modes)
Find what is wrong or missing. Challenge every assumption stated as fact. Walk the
main flows end to end and at each step ask: what if this is slow, fails, returns
nothing, returns too much, is retried, runs twice concurrently, or the user changes
their mind? Look for partial-success states, race conditions, missing rollback, and
simpler alternatives that meet the same goal with less risk.

### REQ - Requirements and product gaps
Hunt for places where the target is silent, vague or contradictory about behavior the
business must decide: what users see and hear, edge-case policies, scope boundaries,
priorities, who is allowed to do what, what happens out of hours, data retention.
Most findings from this lens should be `product-question` type, with options and a
recommendation. Also flag requirements the target claims to meet but does not.

## Include when the target lives in a codebase

### FIT - Codebase fit
List every reference the target makes to existing code (files, modules, functions,
tables, config, env vars, queues, tests) and check each one exists and behaves as
described (`path:line`). Find existing code the target should reuse but ignores.
Check conventions: layout, naming, error handling, config/secrets loading, test style.
Find callers that a change to shared code would break.

## Include when the signal is present

### EXT - External systems (any third-party API, SDK, CRM, payment, telephony, cloud service)
Check every assumption about the external system against its official documentation,
fetched now (cite URLs): endpoints, fields, auth, regions, rate limits, pagination,
webhooks vs polling, idempotency, error codes, sandbox availability, quirks in the
docs' fine print. Count calls per user action and compare with limits.

### ARCH - Architecture and extensibility (new modules, integrations, "we will add more X later")
Find the boundary between core and the specific implementation. Pressure-test it
against 2-3 plausible future variants that differ in meaningful ways and say exactly
what would change. Flag provider details leaking into core, prompts, schemas or public
interfaces. Equally flag over-engineering: abstractions built for imaginary needs.
Recommend the smallest boundary that survives the second implementation.

### SEC - Security and privacy (personal, health, financial data; auth; multi-tenant; LLM tools)
Trace every piece of sensitive data: source, destination, storage, retention, who can
see it, whether it reaches logs, traces, analytics, transcripts or LLM prompts.
Check credential storage and least privilege, tenant isolation, identity verification
before disclosure or changes, prompt injection against tool-calling agents (checks
must be in code, not in the prompt). Raise regulatory concerns as product questions;
do not give legal conclusions.

### DATA - Data model and migrations (schema changes, backfills, sync between systems)
Check migrations are backward compatible and reversible, backfills are safe at real
data volume, IDs and sources of truth are clear, sync handles conflicts, deletes and
drift, and caches have an invalidation story.

### PERF - Latency, scale and cost (real-time flows, voice/chat agents, high volume, paid APIs)
Set or find a latency budget per user-visible step and add up sequential calls
against it. Check concurrency limits, fan-out, timeouts, back-pressure, and the cost
per operation at expected volume.

### OPS - Operability (anything going to production)
Rollout plan (flags, gradual, per-tenant), rollback, observability (logs, metrics,
alerts that a human will act on), runbooks, failure isolation (one tenant or provider
failing must not take down others), configuration and onboarding effort per customer.

### UX - User-facing experience (UI, conversational or voice flows, notifications)
Walk through what the user actually sees or hears in each path, including errors and
waits. Check wording, confirmations, recovery paths, accessibility, and handoff to a
human. Behavior choices are product questions.

### TEST - Testing strategy (when the target proposes or changes behavior)
Can each requirement and failure path be tested? Are external systems faked at the
right seam? Are there contract tests for third-party APIs? What will CI actually run?

### SIMPLE - Simplicity advocate (large or ambitious targets)
Propose the simplest design that meets the same stated requirements. Then list every
element of the target that the simple version does not need, and ask whether each
earns its cost. Findings are `simplification` type.

## Panel size
- quick: RT, REQ, plus the single most relevant other lens (3 total).
- standard: RT, REQ, FIT (if code exists), plus the 2-3 most relevant (5-6 total).
- deep: standard plus any other lens with a clear signal (up to 8).
Never pad the panel with lenses that have no signal in the target.
