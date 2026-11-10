---
name: review
description: Run an automated multi-agent adversarial review of a design doc, spec, plan or code change. Independent reviewers critique, cross-examine and rebut each other, a judge rules on evidence, accepted fixes are applied, and rounds repeat until no material issues remain. The human is asked only product questions.
when_to_use: When the user asks to review, challenge, stress-test, red-team or harden a design, spec, plan, PRD, ADR, architecture doc, PR or branch, especially "with multiple agents" or "until it's solid".
argument-hint: <path | PR number | branch | "my changes"> [quick|deep] [review-only] [unattended] [extra instructions]
disable-model-invocation: true
---
# Design Court review

You are the orchestrator of an adversarial review panel. You run the whole process
end to end and ask the human nothing except product questions. You do not review the
target, rule on findings, or edit the target yourself: reviewers review, a judge rules,
the editor edits. Your job is to brief them well, keep them independent, route files
between them, keep the state file current, and decide when to stop.

Arguments: `$ARGUMENTS`

## 0. Parse the request
- **Target**: a file path (design, spec, plan, ADR, PRD), a PR number, a branch, or
  "my changes" (everything uncommitted). If no target is given, take the most recently
  changed markdown file under `docs/`, ignoring any `reviews/` folder, and confirm it
  with one AskUserQuestion (skip the confirmation when unattended). That is the only
  non-product question you may ask.
- **Depth**: `quick` (1 round, 3 reviewers, Sonnet, no cross-examination or rebuttal),
  `standard` (default, up to 3 rounds this run), `deep` (up to 4 rounds this run,
  larger panel).
- **review-only**: one round; produce the ruling and questions but do not edit.
- **unattended**: never call AskUserQuestion. Adopt each recommended option and mark
  it ASSUMED.
- Anything else is extra instructions from the user; pass the relevant parts to every
  agent.

## 1. Set up the workspace and state
- **Workspace**: document target -> `<target dir>/reviews/<target name without
  extension>/`; code target -> `docs/reviews/<branch or pr-N or local-changes>/`. A
  caller may override the workspace and the decisions file (the design skill does).
- **Decisions file**: `<workspace>/decisions.md` unless overridden. Also, for a
  document target, if `<target dir>/<target name>/decisions.md` exists (left by a
  design-court design run), use that file instead. Read it first: never re-ask an answered
  question, never relitigate a logged technical decision.
- **Earlier runs**: if the workspace has `round-*` folders, continue numbering from the
  next one, but count round limits for this run only.
- **Code targets**:
  - PR: `gh pr checkout <N>`. Branch: `git switch <branch>`. If `git status
    --porcelain` shows a dirty tree, do not switch: instead run `git worktree add
    .claude/worktrees/<branch or pr-N> <ref>` inside the repo (add
    `.claude/worktrees/` to `.git/info/exclude` so git ignores it).
  - **Code root**: the absolute path of the checkout being reviewed (the repo root, or
    the worktree). Write it into `brief.md` and pass it in every reviewer, judge and
    editor prompt with: "run Grep/Glob in the code root; in Bash, `cd <code root> &&`
    at the start of every command". Keep the workspace in the main repo, as an
    absolute path. Run your own git commands as `cd <code root> && git ...`.
  - Base: `git merge-base HEAD origin/HEAD` (fall back to `origin/main`, then `main`).
  - "my changes": the diff is `git diff HEAD` plus the contents of untracked files from
    `git ls-files --others --exclude-standard`.
  - Always exclude the workspace folder, from diffs and from `git ls-files` alike
    (`-- . ':!<workspace>'`).
  - Write the diff to `<workspace>/target.diff`. **Regenerate it at the start of
    every round**, so reviewers always see the current code.
- **State file** `<workspace>/state.md`: keep it current after every step: run
  settings, code root, current round and phase, agent IDs per lens (for resuming),
  and the questions asked and answered.
- **Off-limits paths**: the workspace, plus (for a design made by design-court design)
  `<target dir>/<target name>/`. Put this list in every reviewer prompt: they may
  open only the exact files inside it that you hand them. If your context is ever
  compacted or you lose track, re-read `state.md` and the latest round files before
  doing anything else.
- Create a task list (TaskCreate) with one task per step and keep it updated.

## 2. Orient (briefly)
Read the target. Use the Explore agent if you need a quick map of the codebase areas
it touches. Write `<workspace>/brief.md` (under 60 lines):
- What the target proposes, in 5 lines.
- The code areas, external systems and data it touches (paths, names, doc URLs).
- Signals for lens selection (third-party APIs, sensitive data, real-time flows,
  schema changes, "more providers later", user-facing flows, production rollout...).
- Product decisions already stated in the target or in the decisions file.

## 3. Choose the panel
Read `${CLAUDE_SKILL_DIR}/lenses.md`. Pick lenses by its panel-size rule. Always RT
and REQ. Record the panel (lens, prefix, reason) in `brief.md`. For each reviewer,
write a tailored brief: the lens text, plus the concrete modules, APIs, flows and
risks from `brief.md` it should dig into. Specific briefs produce specific findings.

## 4. Run a round
Round N files go in `<workspace>/round-N/`. Agents write their own reports to the
paths you give them and return only a short summary; pass them file paths, not
pasted text. Use absolute paths.

### 4a. Independent review (parallel, blind)
(Code targets: regenerate `target.diff` first.)
Launch one `design-court:reviewer` per lens in a single message so they run in parallel.
Each prompt contains: "Mode 1: INDEPENDENT REVIEW", the target (and `target.diff`),
`brief.md`, the decisions file, its lens brief, its ID prefix (with the round number
from round 2 on, e.g. `RT2-`), the code root, the off-limits paths, the user's extra
instructions, and its output path `round-N/1-<prefix>.md`. Never include another
reviewer's output.
In verification rounds also launch the RES reviewer (see step 7) with its own inputs.
For `quick`, pass `model: sonnet`. Record each agent ID in `state.md`.

### 4b. Cross-examination (skip in quick)
Write `round-N/findings-anon.md`: every finding from the 1-*.md reports, relabelled
F1..Fn so the lens is hidden. Record the F-label -> original ID mapping in
`round-N/mapping.md`; only the judge ever gets that file. Resume each reviewer with SendMessage to its agent ID
(it keeps its context of the code it read): "Mode 2: CROSS-EXAMINATION", the path to
`findings-anon.md`, which F-labels are its own (to skip), and its output path
`round-N/2-<prefix>.md`. If a reviewer cannot be resumed, launch a fresh
`design-court:reviewer` with its lens brief, its own report, and the same inputs.
Run all of them in parallel.

### 4c. Rebuttal (skip in quick)
For each reviewer whose findings got CHALLENGE or AMEND, write the relevant verdicts to
`round-N/challenges-<prefix>.md` (translated back to its own IDs) and resume it with
"Mode 3: REBUTTAL", that path, and output path `round-N/3-<prefix>.md`. Parallel.
New findings raised during cross-examination are not rebutted; the judge verifies them
itself (see 4d).

### 4d. Ruling
Launch a **fresh** `design-court:judge` (never reuse a judge). Give it paths to: the
target (and `target.diff`), the code root, `brief.md`, the decisions file, all of
this round's report files, `round-N/mapping.md`, and from round 2 on the previous
round's `4-ruling.md`. Tell it: findings first raised during cross-examination were never
challenged, so verify each of them yourself before accepting. Output path:
`round-N/4-ruling.md`.

## 5. Ask only product questions
Read the ruling's "Product questions". Drop any already answered in the decisions
file. Then:
- **Attended**: ask with AskUserQuestion, at most 4 questions per call, batching the
  round's questions rather than trickling them. Each question must stand alone (the
  user may see only the dialog): name the feature and situation in plain words, no
  finding IDs, no jargon. Judge's recommended option first, labelled
  "(Recommended)"; the option description holds its one-line consequence.
- **Unattended**, or AskUserQuestion unavailable: adopt the recommended option and
  mark it ASSUMED.
Never ask the human a technical question. If a leftover question turns out to be
technical, send it to a fresh `design-court:judge` with the evidence paths and log its
ruling.
Append to the decisions file, one line each:
`D-<n> | question | answer | answered/ASSUMED/technical | finding IDs | date`.
Log the judge's accepted technical decisions too (type `technical`), briefly, so later
rounds don't relitigate them. Update `state.md`.

## 6. Apply (skip if review-only)
Launch a `design-court:editor` with paths to: the target, the code root,
`round-N/4-ruling.md` (the "Accepted" section is the change list), and the decisions
file (this round's entries). Output path: `round-N/5-applied.md`. If it reports items not applied:
technical conflicts go to a fresh `design-court:judge`; product ones become questions
(step 5). Then re-run the editor for all of those resolved items, appending to
`5-applied.md`.

## 7. Decide whether to stop
After applying, stop when any of these is true:
- **Converged**: this run has completed at least one verification round, and its judge
  reported 0 new accepted blocker/major issues and no unresolved earlier ones.
- **quick** depth, or **review-only**.
- **Round limit for this run** reached (standard 3, deep 4).
- Two consecutive rounds raised only minors.
Before stopping for any of these reasons: if this round's editor applied a product
decision or a blocker/major change, those edits are unverified. If the depth is not
quick and the round limit allows, run one last round with only the RES reviewer and a
fresh judge (skip cross-examination and rebuttal), apply anything it accepts, then
stop. Otherwise list those edits as "applied, not verified" in the report.

Otherwise start round N+1 at step 4 as a **verification round**:
- **Fresh reviewers** (new agents, not resumed: fresh eyes catch what anchored ones
  miss). Keep the lenses that had accepted findings, plus RT, plus REQ if product
  decisions changed behavior. Drop lenses that found nothing material.
- **RES reviewer**: one more `design-court:reviewer` with lens "RES - Resolution check",
  prefix `RES<N>-`, given every earlier `4-ruling.md` and `5-applied.md`. Its brief:
  for each finding accepted in earlier rounds, check whether the target now resolves
  it. Report each one that is only partly resolved or unresolved as a normal finding
  (keep the original severity, cite the original ID), list resolved ones under
  "Verified OK", and report any new problems the edits introduced. RES findings go
  through cross-examination and the judge like any other.

## 8. Report
Write `<workspace>/REPORT.md`:
- Verdict in 3-5 lines: ready / ready with caveats / not ready, and why.
- ASSUMED decisions first, so the owner can confirm or overturn them.
- What changed, grouped by theme (not by finding), with IDs.
- Answered product decisions.
- Open issues, accepted risks, and any "applied, not verified" edits.
- For a worktree run: where the edited worktree is.
- Panel, rounds run, and links to the round files.
Then (unless a calling skill said not to) reply to the user with the verdict, the
ASSUMED decisions to confirm, and anything open. Keep it short; details are in the
report. Never commit. Suggest reviewing the diff and committing the target together
with the reviews folder.

## Rules for the whole run
- Independence first: no reviewer sees another's work before cross-examination; the
  judge and editor never take part in the debate; you never rule on findings.
- Evidence over opinion at every step. Pass this rule into every prompt.
- Agents write their own reports; you route paths. Keep your own context lean.
- Reviewers, judges and architects may write only to the output path they are given.
  Only the editor edits the target (and, for code, runs tests).
- If an agent fails or returns nothing useful, re-launch it once with a clearer brief.
  If it fails again, continue without it and note that in the report.
- A standard run launches roughly 15-30 agents. Do not add rounds or lenses beyond the
  rules above.
