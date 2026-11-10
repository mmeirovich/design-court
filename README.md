# Design Court

Multi-agent adversarial design and review for Claude Code.

> **Status: experimental.** Design Court works and has been checked for consistency,
> but it has not yet been benchmarked against simpler review setups. See
> [docs/research](docs/research/existing-tools-and-evidence.md) for what the evidence
> says about multi-agent review, and feedback via issues is welcome.

Design Court has two commands:

- **`/design-court:review <target>`** hardens a design, spec, plan or code change.
  Independent reviewers critique it without seeing each other's work. They then
  cross-examine and rebut each other's findings. A judge who took no part rules on the
  evidence, an editor applies the accepted fixes, and fresh reviewers check the result.
  This repeats until no serious issues remain (at most 3 rounds by default).
- **`/design-court:design <feature>`** creates a design. Two or three architects draft
  competing designs, critique each other's, and a judge picks the best base and grafts
  in the best ideas from the others. The result then goes through the review loop.

**You are asked only product questions**: behavior, policy, scope and priorities.
Technical disagreements are settled by the judge from evidence. If you'd rather not be
asked anything, add `unattended`: each question gets the recommended answer, and the
final report lists those answers first so you can confirm or overturn them.

## Before you start

You need:

- **Claude Code** (CLI, VS Code extension, or desktop), recent enough to support plugins.
- **Access to Opus.** All agents use Opus by default. See [Cost](#cost) to change that.
- **The GitHub CLI (`gh`)**, logged in, only if you want to review pull requests.
- **A git repository** for the project you want reviewed. Design Court writes its
  reports into it.

## Step 1: Install

In a terminal:

```
claude plugin marketplace add mmeirovich/design-court
claude plugin install design-court@design-court
```

Or, inside a Claude Code session (including the VS Code panel):

```
/plugin marketplace add mmeirovich/design-court
/plugin install design-court@design-court
```

Then start a new Claude Code session. Type `/design-court` and you should see
`/design-court:review` and `/design-court:design` in the suggestions.

## Step 2: Let it run without stopping (once per project)

A review runs many agents that write report files, look up official documentation on
the web, and run git commands. By default Claude Code asks permission for each of
these, so a run keeps stopping. Choose one of these:

- **Option A: auto mode**, if your plan has it. Press Shift+Tab until the mode
  indicator shows auto. Routine actions are then approved without asking.
- **Option B: accept-edits mode plus allow rules.** Create or edit
  `.claude/settings.json` in your project. If it already has a `permissions.allow`
  list, add these lines to it:
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
  Replace `npm test *` with your project's test command. `WebFetch` alone allows
  any website; to be stricter, list domains instead, such as
  `WebFetch(domain:docs.stripe.com)`. Then, before each run, press Shift+Tab until
  the mode shows accept edits.

If you skip this step, Design Court still works. You'll just need to approve each
action as it comes up.

## Step 3: Run your first review

Start small: a quick review of a design doc you already have.

```
/design-court:review docs/designs/my-feature.md quick
```

What happens:

1. It reads the doc, maps the code it touches, and picks a panel of reviewers.
   You'll see a task list next to the conversation showing each step.
2. The reviewers work in parallel. Expect a quick review to take several minutes and
   a standard one 10-30 minutes.
3. If the reviewers raise questions only you can answer, such as how a feature
   should behave, you'll see them as multiple-choice questions with a recommended
   option. Nothing technical is asked.
4. It applies the accepted fixes to your doc and ends with a short verdict: ready,
   ready with caveats, or not ready.

## Step 4: Read the results and commit

1. Open `REPORT.md` in the review folder. For `docs/designs/my-feature.md` that's
   `docs/designs/reviews/my-feature/REPORT.md`. It has the verdict, any answers marked
   ASSUMED, what changed, and anything still open.
2. Look at the changes to your doc with `git diff`. Every change traces back to a
   finding in the round files if you want to know why.
3. Commit the doc and the reviews folder together. Design Court never commits or
   pushes for you.

When the quick review looks useful, run a standard one (just leave out `quick`).

## Other ways to use it

```
/design-court:review docs/designs/my-feature.md            # standard: up to 3 rounds
/design-court:review docs/designs/my-feature.md deep       # up to 4 rounds, bigger panel
/design-court:review docs/designs/my-feature.md unattended # never asks you anything
/design-court:review docs/designs/my-feature.md review-only  # report only, no edits
/design-court:review 142                                    # pull request #142
/design-court:review my changes focus on concurrency        # your uncommitted changes
/design-court:design Add rate limiting to the public API. Requirements: docs/req/rate-limits.md
```

Anything after the target and options is passed to the agents as extra instructions.

| Depth | Rounds | Reviewers | Debate | Model |
|---|---|---|---|---|
| `quick` | 1 | 3 | No | Sonnet |
| `standard` (default) | up to 3 | 5-6 | Yes | Opus |
| `deep` | up to 4 | up to 8 | Yes | Opus |

Running the same review again later continues where the last one stopped, and never
re-asks a question you already answered.

## What it writes

```
docs/designs/reviews/my-feature/
  REPORT.md           start here: verdict, ASSUMED answers, changes, open issues
  decisions.md        every product answer and technical decision, with reasons
  brief.md            what the panel was told, and why each reviewer was chosen
  state.md            progress, so an interrupted run can pick up where it was
  round-1/
    1-<lens>.md       each reviewer's independent review
    findings-anon.md  all findings, relabelled so reviewers can't tell whose is whose
    2-<lens>.md       each reviewer testing the others' findings
    3-<lens>.md       authors withdrawing, revising or defending their findings
    4-ruling.md       the judge's verdict
    5-applied.md      what the editor changed
  round-2/ ...        a check round with fresh reviewers
```

Reviews of code changes go to `docs/reviews/<branch or pr-N>/` instead.
`/design-court:design` writes the new design to `docs/designs/<slug>.md`, its drafts
and decisions to `docs/designs/<slug>/`, and its review to
`docs/designs/reviews/<slug>/`. If your repo already keeps designs in another folder,
it uses that.

## How it keeps the critique honest

- **Independence**: reviewers don't see each other's work until cross-examination,
  and the judge and editor take no part in the debate.
- **Evidence or it doesn't count**: every finding needs a file and line, an official
  documentation link, or a checkable quote. The judge rules on evidence, not votes.
- **Real debate**: findings are anonymized for cross-examination. A challenge needs
  counter-evidence, and authors must withdraw, revise or defend with new evidence.
- **Fresh eyes each round**: check rounds use new reviewers, a new judge, and a
  resolution check on every earlier finding.
- **Reviewer types** are picked from signals in the target: red team, product gaps,
  codebase fit, external systems, architecture, security and privacy, data, latency
  and cost, operability, user experience, testing, and simplicity.

## Cost

A standard review launches roughly 15-30 Opus agents and takes 10-30 minutes; on
API pricing that can be several dollars or more per run. Use `quick` for routine
documents. To run every agent on another model, set the `CLAUDE_CODE_SUBAGENT_MODEL`
environment variable, or change `model:` in the agent files.

## Update or remove

```
claude plugin marketplace update design-court       # fetch the latest from GitHub
claude plugin update design-court@design-court      # install it
claude plugin uninstall design-court                # remove the plugin
claude plugin marketplace remove design-court       # remove the marketplace too
```

## Customize

Fork this repo, edit, then install from your fork (`claude plugin marketplace add
<you>/design-court`).

- Reviewer types: `plugins/design-court/skills/review/lenses.md`
- Reviewer, judge, architect and editor behavior: `plugins/design-court/agents/*.md`
- The process (rounds, stop rules, folders): `plugins/design-court/skills/*/SKILL.md`

To test edits without publishing, add your local clone instead:
`claude plugin marketplace add ./design-court`, then run `/reload-plugins` after
each change.

## License

MIT
