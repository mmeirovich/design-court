#!/usr/bin/env python3
"""Score each run's bundle.md against the corpus answer key with an LLM judge.

  python3 bench/score.py --run-dir bench/results/main
  BENCH_JUDGE_CMD='gemini -p' python3 bench/score.py --run-dir ...   # cross-family judge

The judge sees the answer key, the target and the arm's output (file names that would
reveal the arm are stripped, but the content may still give it away). It decides, per
planted defect, whether it was detected and whether the target diff fixes it, and
classifies every problem the arm asserted. A custom judge command (BENCH_JUDGE_CMD) gets
the prompt on stdin and must print the JSON object on stdout. Scoring is resumable.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, extract_json_obj, load_json, run_claude, write_json  # noqa: E402
import os  # noqa: E402

PROMPT = """You are scoring an automated design-review tool. You get (1) the ANSWER KEY of defects that were deliberately planted in a design document, (2) the design document, and (3) everything the tool produced. Be strict and literal.

For each planted defect decide:
- "detected": true only if the tool's output explicitly identifies this problem with a diagnosis that matches the defect (different wording is fine; a vague or adjacent remark is not). Ignore findings the tool itself withdrew or rejected.
- "fixed": true if the TARGET DOCUMENT CHANGES (diff) correct the defect, false if it is not corrected, null if there is no diff at all.

Then list every DISTINCT problem the tool asserts in its final output (ignore process chatter and withdrawn findings) and classify each:
- "defect:<id>" if it matches a planted defect;
- "valid_extra" if it is a real, checkable problem in the document that is not in the key (it must be demonstrable from the document text; if you are not sure, use "unverifiable");
- "invalid" if it is wrong, contradicted by the document, or only a style preference;
- "unverifiable" if you cannot tell.

Reply with ONLY one JSON object, no prose, in this shape:
{"defects":[{"id":"D1","detected":true,"fixed":false,"evidence":"<short quote or reason>"}],
 "findings":[{"summary":"<one line>","class":"defect:D1"}]}
Include every defect id from the key exactly once.

=== ANSWER KEY ===
%(key)s

=== DESIGN DOCUMENT (original) ===
%(target)s

=== TOOL OUTPUT ===
%(bundle)s
"""


def judge(prompt: str, model, timeout: int) -> str:
    cmd = os.environ.get("BENCH_JUDGE_CMD")
    if cmd:
        r = subprocess.run(shlex.split(cmd), input=prompt, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    with tempfile.TemporaryDirectory(prefix="bench-judge-") as d:
        args = ["--model", model] if model else []
        res = run_claude(prompt, Path(d), args, timeout)
    j = res["json"] or {}
    return j.get("result") if isinstance(j.get("result"), str) else res["stdout"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--corpus", default=str(ROOT / "corpus"))
    ap.add_argument("--judge-model", default=os.environ.get("BENCH_JUDGE_MODEL"))
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--force", action="store_true", help="re-score runs that already have score.json")
    a = ap.parse_args()

    runs = sorted(Path(a.run_dir, "runs").glob("*/*/rep*"))
    done = bad = 0
    for rd in runs:
        if not (rd / "result.json").exists() or not (rd / "bundle.md").exists():
            continue
        sj = rd / "score.json"
        if sj.exists() and not a.force and load_json(sj).get("parsed"):
            continue
        tid = rd.parents[1].name
        tdir = Path(a.corpus) / tid
        key = (tdir / "answer-key.json").read_text(encoding="utf-8")
        prompt = PROMPT % {"key": key, "target": (tdir / "target.md").read_text(encoding="utf-8"),
                           "bundle": (rd / "bundle.md").read_text(encoding="utf-8")}
        raw = judge(prompt, a.judge_model, a.timeout)
        obj = extract_json_obj(raw, "defects")
        write_json(rd / "score.json", {"parsed": obj is not None, "score": obj, "raw": None if obj else raw[:4000]})
        if obj is None:
            bad += 1
            print("UNPARSEABLE judge output: %s" % rd)
        else:
            done += 1
            print("scored %s" % rd.relative_to(Path(a.run_dir) / "runs"))
    print("\nscored %d, unparseable %d (re-run to retry the unparseable ones)" % (done, bad))


if __name__ == "__main__":
    main()
