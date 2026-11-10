# Benchmark harness

Compares Design Court against Superpowers and against simpler setups on the same
design documents, with known planted defects as ground truth. It answers one question:
**does the debate layer earn its cost?**

Python 3.8+, standard library only. It drives the `claude` CLI in headless mode.

## What it compares

| Arm | What it is |
|---|---|
| `A_superpowers` | Superpowers' spec/plan review practice (uses your installed Superpowers plugin) |
| `B_baseline` | 5 blind reviewers, merge, one verifier, edit. No debate. The Bugbot / Code Review pattern |
| `C_dc_full` | Design Court `review` from this repo's working tree (not the installed copy) |
| `D_dc_nodebate` | Same, with cross-examination and rebuttal (steps 4b, 4c) switched off |

Plugins under test are copied from the repo and renamed (`dc-full`, `dc-nodebate`) so
they never clash with the installed `design-court`. Edit `arms.json` to change prompts or
add arms. Keep prompts equivalent in spirit: wording is a bias source.

## Quick start

```
python3 -m unittest discover -s bench/tests        # harness self-test, no API calls
python3 bench/run.py --dry-run                      # show what would run
python3 bench/run.py --smoke --bypass-permissions    # real but cheap: 1 target, 1 rep, quick reviews
python3 bench/run.py --reps 3 --bypass-permissions --out bench/results/main
python3 bench/score.py  --run-dir bench/results/main
python3 bench/report.py --run-dir bench/results/main   # also writes report.md
```

`run.py` and `score.py` are resumable: re-run the same command and finished work is skipped.
Useful flags: `--arms A,B`, `--targets id1,id2`, `--model <m>` (same model for every arm),
`--budget <usd>` per run, `--jobs N` (parallel; mind rate limits), `--timeout <s>`.

## Building the corpus (the hard part)

One folder per target under `corpus/`:

```
corpus/<id>/
  target.md          the design doc / plan to review (copied to docs/designs/<id>.md)
  answer-key.json    the defects (see corpus/_TEMPLATE/answer-key.json)
  repo/              optional: code and docs the target refers to (copied to the workspace root)
```

`ex-01-webhook` is a small synthetic example so the harness can be demonstrated; do not
draw conclusions from it alone. For a trustworthy result you want 10-20 targets:

- **Past designs whose real problems surfaced later** in implementation or production
  (best ground truth; cite the PR or incident in the key's `note`).
- **Planted defects** in real docs: wrong API limits, missing failure paths, internal
  contradictions, references to code that does not exist, undecided product behavior.
- Mix severities (`blocker`, `major`, `minor`). Weighted recall uses 3 / 2 / 1.
- Write `detect_if` and `fixed_if` precisely. The judge is literal.
- Keep a few targets with **no** defects, or defects only in code, to expose false positives.

## How scoring works

Each run is saved as `results/<name>/runs/<target>/<arm>/rep<N>/`:
`result.json` (cost, time, tokens), `raw.json`, `stderr.txt`, `bundle.md` (everything the
arm produced), `workspace/` (the full working copy, for inspection), and after scoring
`score.json`.

`score.py` gives a judge model the answer key, the original doc and `bundle.md`. It returns,
per defect, `detected` and `fixed` (does the diff of the target correct it), and classifies
every problem the arm asserted as a planted defect, `valid_extra`, `invalid` or
`unverifiable`. `report.py` turns that into per-arm tables, a defect-by-arm detection
matrix, and paired comparisons with a standard-error check (it refuses to call a winner
below 6 pairs).

Use a **different model family as judge** if you can, since same-family judges favor
their own style:

```
BENCH_JUDGE_CMD='your-cli --flags' python3 bench/score.py --run-dir ...   # prompt on stdin, JSON on stdout
```

Do a blind human spot-check of a few `bundle.md` files against their `score.json`.

## Decision rule

Keep cross-examination and rebuttal only if `C_dc_full` clearly beats **both** `B_baseline`
and `D_dc_nodebate` at comparable cost. If B is about as good as C, simplify Design Court.
Treat gaps under ~10-15 points as noise unless n is large.

## Known limits (read before trusting numbers)

- **Not verified against a live CLI.** The harness was tested end to end only against a
  stub (`tests/fake_claude.py`). Run `--smoke` first and read `raw.json` and `stderr.txt`.
  Assumed, and worth confirming on your CLI version: `claude -p` reads the prompt from
  stdin; `--output-format json` returns `result`, `total_cost_usd`, `usage`;
  `--plugin-dir`, `--permission-mode`, `--model`, `--max-budget-usd` exist; a
  `/plugin:skill` prompt invokes the skill in headless mode; and `total_cost_usd`
  includes subagent spend. If cost reads `-`, the report's cost columns are not
  comparable; wall time is measured independently.
- **Profile isolation is partial.** Variants are renamed so they cannot clash, but your
  installed plugins (Superpowers, Design Court 1.0.x, others) still load in every arm. Arms
  name their skills explicitly to limit cross-triggering. For a cleaner run, restrict
  settings, e.g. `BENCH_CLAUDE_ARGS='--setting-sources project'` (check this flag on your
  version, and note Superpowers must stay enabled for arm A).
- **Permissions are opt-in.** `run.py` refuses to start until you choose: pass
  `--bypass-permissions` (agents may run any tool, including shell and network, with your
  credentials, inside throwaway workspaces that are not otherwise sandboxed) or set
  `--permission-mode` / `BENCH_PERMISSION_MODE`. Headless runs cannot prompt, so a mode that
  asks will deny tools and skew the comparison. Use a container or a disposable machine if
  you want real isolation; the environment is not scrubbed because the CLI needs your auth.
- **Scoring is not fully blind.** File names are neutralised, but a Design Court
  transcript reads like one. Spot-check by hand.
- **Arm A is a prompt, not a feature.** Superpowers has no design-review loop, so arm A
  asks Claude to use its spec/plan review practice. Its result depends on that wording.
- **Debate-off (arm D) is a prompt patch** on the review skill, not a separate
  implementation. It is applied by `build_plugin` in `run.py`; if the skill's step
  headings change, the build fails loudly rather than silently benchmarking the wrong thing.
- **Cost matching is post hoc.** Check the `$ / run` column. If B is far cheaper than C,
  raise B's panel size in `arms.json` and rerun before concluding anything.
- **Variance is real.** Run at least 3 reps and 10+ targets before believing a gap.
