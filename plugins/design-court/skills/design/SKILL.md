---
name: design
description: Design a feature with competing independent architects who critique each other, a judge who picks and merges the best ideas, and then the full design-court adversarial review loop on the result. The human is asked only product questions.
when_to_use: When the user asks to design, plan or architect a new feature or integration and wants the strongest design, multiple perspectives, or a design that has been challenged before implementation.
argument-hint: <feature description | path to requirements> [quick|deep] [unattended] [extra instructions]
disable-model-invocation: true
---
# Design Court design

You orchestrate a design competition followed by an adversarial review. You do not
write the design or rule on it yourself: architects draft and critique, a judge
decides, the editor assembles, the review panel hardens it. You brief, route files,
keep the state file current, and ask the human only product questions.

Arguments: `$ARGUMENTS`

## 0. Parse the request
- **Feature**: a description in the arguments, or a path to a requirements doc/issue.
- **Depth**: `quick` (2 architects, Sonnet, then a quick review), `standard` (3
  architects, then a standard review), `deep` (3 architects, then a deep review).
- **unattended**: never call AskUserQuestion; adopt recommended options and mark them
  ASSUMED. Pass this on to the review stage.
- Pick a short kebab-case slug for the feature.
- **Design dir**: `docs/designs/`, unless the repo already keeps designs elsewhere
  (look for an existing designs/specs/adr/rfc folder); then use that.
- **Design path**: `<design dir>/<slug>.md`. **Workspace**: `<design dir>/<slug>/`.
  The decisions file is `<workspace>/decisions.md` (the review skill finds it there).
- Create a task list (TaskCreate) for the steps below and keep `<workspace>/state.md`
  current (step, agent IDs per architect, questions asked). If your context is ever
  compacted or you lose track, re-read `state.md` before continuing.

## 1. Understand the ground
- Read the requirements and anything they link to.
- Launch Explore agents (in parallel) to map the codebase areas the feature touches:
  entry points, similar features and integrations, config and secrets handling, data
  model, tests. Ask for paths and short summaries, not dumps.
- Write `<workspace>/brief.md` (under 80 lines): requirements as stated, the codebase
  map with paths, external systems involved (with official doc URLs if known),
  constraints, and an explicit list of what the requirements leave undecided.

## 2. Ask the foundational product questions (once, up front)
From the undecided list, keep only questions whose answer would change the
architecture. Typical examples: which user actions are in scope for v1, who the users
are, hard constraints on data location or compliance, expected scale, whether more
providers are definitely coming. Ask at most 4, in one AskUserQuestion call: each
question standalone in plain language, recommended option first with "(Recommended)".
Unattended or unavailable: adopt the recommended option, mark ASSUMED.
Record each in the decisions file:
`D-<n> | question | answer | answered/ASSUMED | - | date`.
Everything else goes to the architects as "open: list it, assume, and recommend".

## 3. Competing drafts (parallel, blind)
Choose mandates that differ in ways that matter for this feature. Defaults:
- **A - Simplest complete**: the smallest design that fully meets the requirements.
- **B - Robust**: optimise for failure handling, operational safety, data integrity.
- **C - Evolvable**: optimise for the changes the brief says are coming (more
  providers, channels, tenants), without speculative generality.
(quick: A and B only.) Tailor them if the brief points elsewhere (e.g. latency-first
for real-time flows).
Launch one `design-court:architect` per mandate in a single message: "Mode 1: DRAFT",
paths to the brief and decisions file, its mandate, the user's extra instructions,
the off-limits paths (the workspace and `<design dir>/reviews/`; it may open only the
exact files you hand it), and output path `<workspace>/drafts/<A|B|C>.md`. For quick pass `model: sonnet`.
Record agent IDs in `state.md`.

## 4. Cross-critique
Resume each architect with SendMessage: "Mode 2: CRITIQUE", the draft paths, which
letter is its own, and output path `<workspace>/drafts/critique-<letter>.md`. If one
cannot be resumed, launch a fresh architect with the same inputs and its letter.
Parallel.

## 5. Select
Launch a fresh `design-court:judge` with paths to brief.md, the decisions file, all drafts
and critiques, output path `<workspace>/selection.md`, and this ruling format instead
of its default:
"Choose the best base design and the specific ideas to graft from the others, based on
evidence and the requirements, not on which draft is longest. Write: (1) the base and
why, (2) the grafts, each with source and reason, (3) ideas deliberately rejected and
why, (4) a merged list of product questions from all drafts, each with options,
recommendation and what depends on it, excluding any answered in the decisions file,
(5) technical decisions you made to settle disagreements between drafts."

## 6. Ask the remaining product questions
Same rules as step 2: batch, at most 4 per call, standalone plain-language wording,
recommended first, ASSUMED when unattended, every answer logged. Log the judge's
technical decisions from section (5) as type `technical`. Ask nothing technical.

## 7. Assemble the design
Launch a `design-court:editor` with this task: create the design at the design path from
the chosen base draft, apply the grafts and technical decisions from `selection.md`
(its sections 1, 2 and 5 are the change list; there is no "Accepted" section), and
apply every product decision in the decisions file everywhere it affects the
design. Use the architect's section structure. Add a short "Decisions" section near
the top listing the D-n entries that shaped the design, ASSUMED ones marked. Keep
"Open product questions" only for questions still unanswered. Report path:
`<workspace>/assembly.md`.

## 8. Harden it with the review loop
Read `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` and follow it from step 1, with:
- target = the design path, same depth, `unattended` if this run is unattended;
- its default workspace (`<design dir>/reviews/<slug>/`), so later standalone reviews
  of this design find the history;
- the decisions file = `<workspace>/decisions.md` (read and append; do not create a
  second one), so nothing is asked twice;
- where it says `${CLAUDE_SKILL_DIR}`, use `${CLAUDE_PLUGIN_ROOT}/skills/review`;
  where it says `$ARGUMENTS`, use the depth and the user's extra instructions.
At its step 8, write REPORT.md but **do not send its final reply**; continue to step 9.

## 9. Report
Reply to the user with: where the design is, which draft won and what was grafted in
(2-4 lines), the review verdict, the ASSUMED decisions to confirm, and any open issues
or "applied, not verified" edits. Never commit; suggest reviewing and committing the
design together with its workspace and reviews folders.
