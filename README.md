# Design Court

Multi-agent adversarial design and review for Claude Code.

- `/design-court:review <target>`: a panel of independent reviewers critiques a design,
  spec, plan or code change. They then cross-examine and rebut each other's findings,
  a judge who took no part rules on the evidence, an editor applies the accepted fixes,
  and fresh reviewers verify. This repeats until no material issues remain.
- `/design-court:design <feature>`: 2-3 architects draft competing designs under different
  mandates, critique each other, and a judge picks the base and grafts in the best
  ideas. The result then goes through the full review loop.

You are asked only **product questions**: behavior, policy, scope and priorities.
Technical disagreements are settled by the judge from evidence. Add `unattended` and
you are asked nothing at all: each question gets the recommended option, and the
report lists it first as ASSUMED for you to confirm or overturn.

## Install

1. Put this folder somewhere permanent, e.g. `~/claude-plugins/design-court`.
2. In a terminal:
   ```
   claude plugin marketplace add ~/claude-plugins/design-court
   claude plugin install design-court@design-court
   ```
   Or, inside a Claude Code session in VS Code:
   `/plugin marketplace add ~/claude-plugins/design-court`, then
   `/plugin install design-court@design-court`.
3. Start a new session (or run `/reload-plugins`).

To share it with your team, push this folder to a (private) GitHub repo. Teammates
then run `claude plugin marketplace add <owner>/<repo>` and the same install command.

## Use

```
/design-court:review docs/designs/cliniko-integration.md
/design-court:review docs/designs/cliniko-integration.md quick
/design-court:review 142 review-only                  # PR #142, report only
/design-court:review my changes deep focus on concurrency
/design-court:review docs/designs/cliniko-integration.md unattended
/design-court:design Add Jane App integration alongside Cliniko. Requirements: docs/req/jane.md
```

Depth: `quick` (1 round, 3 reviewers, Sonnet, no debate), `standard` (default, up to
3 rounds), or `deep` (up to 4 rounds, larger panel).

## Running hands-off: permissions

Without help, Claude Code will stop to ask permission for the agents' file writes,
web lookups (official API docs) and git/test commands. Pick one:

- **Auto mode**, if your plan offers it (Shift+Tab to cycle modes): a classifier
  approves routine actions, so no prompts.
- **Accept edits mode** (Shift+Tab) plus allow rules in your project's
  `.claude/settings.json` for the rest. Adjust the test commands to your project:
  ```json
  {
    "permissions": {
      "allow": [
        "WebSearch",
        "WebFetch",
        "Bash(git diff *)",
        "Bash(git merge-base *)",
        "Bash(git ls-files *)",
        "Bash(git switch *)",
        "Bash(git status *)",
        "Bash(git fetch *)",
        "Bash(git rev-parse *)",
        "Bash(git worktree *)",
        "Bash(gh pr diff *)",
        "Bash(gh pr checkout *)",
        "Bash(npm test *)"
      ]
    }
  }
  ```
  `WebFetch` on its own allows fetching any site. To be stricter, list domains
  instead, e.g. `WebFetch(domain:docs.api.cliniko.com)`.

Everything Design Court writes is plain files in your repo, so you review the diff and
commit yourself. Design Court never commits or pushes.

## What you get

```
docs/designs/reviews/cliniko-integration/
  brief.md            what the panel was told, and why each lens was chosen
  decisions.md        every product answer (and ASSUMED default), plus technical calls
  state.md            run progress, so an interrupted run can pick up where it was
  round-1/
    1-<lens>.md       blind reviews, one per reviewer
    findings-anon.md  all findings, relabelled so reviewers can't tell whose is whose
    2-<lens>.md       each reviewer testing the others' findings
    3-<lens>.md       authors withdrawing, revising or defending
    4-ruling.md       the judge's verdict
    5-applied.md      what the editor changed
  round-2/ ...        verification round: fresh reviewers + a resolution check
  REPORT.md           final verdict, ASSUMED decisions, changes, open issues
```

`/design-court:design` also creates `docs/designs/<slug>/` with the brief, the competing
drafts and critiques, the judge's selection and the decisions log. Its review rounds
go to `docs/designs/reviews/<slug>/`, so a later `/design-court:review` of the same design
continues that history and doesn't re-ask anything.

## How it keeps the critique honest

- **Independence**: reviewers don't see each other's work until cross-examination,
  and the judge and editor never take part in the debate.
- **Evidence or it didn't happen**: every finding needs `path:line`, an official doc
  URL, or a checkable quote. The judge rules on evidence, not on votes.
- **Real debate**: findings are anonymized for cross-examination. Challenges need
  counter-evidence, and authors must withdraw, revise or defend with new evidence.
- **Fresh eyes each round**: verification rounds use new reviewers, a new judge and a
  resolution check on every earlier finding.
- **Lens library** (`skills/review/lenses.md`): red team, requirements and product
  gaps, codebase fit, external systems, architecture and extensibility, security and
  privacy, data, latency and cost, operability, UX, testing, and simplicity. The
  orchestrator picks lenses from signals in the target. Edit the file to add your own.

## Cost

A standard review launches roughly 15-30 agents on Opus and takes about 10-30
minutes. Use `quick` for routine documents. To run every agent on another model, set
`CLAUDE_CODE_SUBAGENT_MODEL`, or change `model:` in `agents/*.md`.

## Customize

- Add or change lenses: `plugins/design-court/skills/review/lenses.md`
- Change reviewer, judge, architect or editor behavior: `plugins/design-court/agents/*.md`
- Change the process (rounds, stop rules, workspace paths): the two `SKILL.md` files

After editing, run `/reload-plugins`. With a local marketplace, changes apply directly.
