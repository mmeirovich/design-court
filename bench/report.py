#!/usr/bin/env python3
"""Aggregate scored runs into a per-arm table and paired arm comparisons.

  python3 bench/report.py --run-dir bench/results/main

Writes <run-dir>/report.md and prints it. Failed or unscored runs are listed, never
silently counted as zero or dropped.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, SEVERITY_WEIGHT, load_json  # noqa: E402


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def sd(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def fmt(x, nd=2, pct=False, prefix=""):
    if x is None:
        return "-"
    return "%s%.0f%%" % (prefix, x * 100) if pct else "%s%.*f" % (prefix, nd, x)


def metrics(res: dict, score: dict, key: dict) -> dict:
    defects = {d["id"]: d for d in key["defects"]}
    judged = {d.get("id"): d for d in (score.get("defects") or [])}
    tot = sum(SEVERITY_WEIGHT.get(d.get("severity"), 1) for d in defects.values())
    det = fix = wdet = 0
    detected = {}
    for did, d in defects.items():
        j = judged.get(did, {})
        hit = j.get("detected") is True
        detected[did] = hit
        det += hit
        wdet += hit * SEVERITY_WEIGHT.get(d.get("severity"), 1)
        fix += j.get("fixed") is True
    cls = [(f.get("class") or "").lower() for f in (score.get("findings") or [])]
    n = len(cls)
    return {
        "recall": det / len(defects), "wrecall": wdet / tot, "fixed": fix / len(defects),
        "n_findings": n, "extras": sum(c == "valid_extra" for c in cls),
        "invalid": sum(c == "invalid" for c in cls), "unverifiable": sum(c == "unverifiable" for c in cls),
        "fp_rate": (sum(c == "invalid" for c in cls) / n) if n else 0.0,
        "cost": res.get("cost_usd"), "wall": res.get("wall_s"), "detected": detected,
    }


def paired(rows, a, b):
    """Paired difference in weighted recall (a - b) over (target, rep) pairs both arms completed."""
    ra = {(r["target"], r["rep"]): r for r in rows if r["arm"] == a}
    rb = {(r["target"], r["rep"]): r for r in rows if r["arm"] == b}
    keys = sorted(set(ra) & set(rb))
    diffs = [ra[k]["m"]["wrecall"] - rb[k]["m"]["wrecall"] for k in keys]
    ca, cb = mean([ra[k]["m"]["cost"] for k in keys]), mean([rb[k]["m"]["cost"] for k in keys])
    n = len(diffs)
    if n == 0:
        return "%s vs %s: no overlapping scored runs" % (a, b)
    d = sum(diffs) / n
    s = sd(diffs)
    se = s / math.sqrt(n) if s is not None else None
    if n < 6 or se is None:
        verdict = "too few pairs (%d) to call; need >= 6" % n
    elif abs(d) > 2 * se:
        verdict = "%s is %s (diff %.1f%% > 2 SE)" % (a, "better" if d > 0 else "worse", abs(d) * 100)
    else:
        verdict = "no clear difference (within noise)"
    cost = "cost ratio %.1fx" % (ca / cb) if ca and cb else "cost n/a"
    return "%s vs %s: weighted recall %+.1f pts (SE %s, n=%d), %s -> %s" % (
        a, b, d * 100, "%.1f" % (se * 100) if se is not None else "-", n, cost, verdict)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--corpus", default=str(ROOT / "corpus"))
    ap.add_argument("--arms-file", default=str(ROOT / "arms.json"))
    a = ap.parse_args()
    run_dir = Path(a.run_dir)

    rows, problems, keys = [], [], {}
    for rd in sorted(run_dir.glob("runs/*/*/rep*")):
        tid, arm, rep = rd.parents[1].name, rd.parent.name, int(rd.name[3:])
        rj, sj = rd / "result.json", rd / "score.json"
        if not rj.exists():
            problems.append("%s/%s/%s: no result (run did not finish)" % (tid, arm, rd.name))
            continue
        res = load_json(rj)
        if not res.get("ok"):
            problems.append("%s/%s/%s: run failed (rc=%s, see stderr.txt)" % (tid, arm, rd.name, res.get("returncode")))
            continue
        if not sj.exists() or not load_json(sj).get("parsed"):
            problems.append("%s/%s/%s: not scored" % (tid, arm, rd.name))
            continue
        if tid not in keys:
            keys[tid] = load_json(Path(a.corpus) / tid / "answer-key.json")
        rows.append({"target": tid, "arm": arm, "rep": rep, "m": metrics(res, load_json(sj)["score"], keys[tid])})

    arms = sorted({r["arm"] for r in rows})
    out = ["# Benchmark report", "", "Run dir: `%s`. Scored runs: %d. Problems: %d." % (run_dir, len(rows), len(problems)), ""]
    out += ["## Per arm (mean over scored runs; +- is the sample SD)", "",
            "| Arm | n | Recall | Weighted recall | Fixed | Findings | Valid extras | Invalid rate | $ / run | Wall min | Wtd recall per $ |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        ms = [r["m"] for r in rows if r["arm"] == arm]
        wr, cost = mean([m["wrecall"] for m in ms]), mean([m["cost"] for m in ms])
        out.append("| %s | %d | %s | %s +- %s | %s | %s | %s | %s | %s | %s | %s |" % (
            arm, len(ms), fmt(mean([m["recall"] for m in ms]), pct=True), fmt(wr, pct=True),
            fmt(sd([m["wrecall"] for m in ms]), pct=True), fmt(mean([m["fixed"] for m in ms]), pct=True),
            fmt(mean([m["n_findings"] for m in ms]), 1), fmt(mean([m["extras"] for m in ms]), 1),
            fmt(mean([m["fp_rate"] for m in ms]), pct=True), fmt(cost, 2, prefix="$"),
            fmt((mean([m["wall"] for m in ms]) or 0) / 60 or None, 1),
            fmt(wr / cost if wr is not None and cost else None, 2)))
    out += ["", "## Which planted defects each arm finds (detection rate)", ""]
    if arms:
        out += ["| Target / defect | severity | " + " | ".join(arms) + " |", "|---|---|" + "---|" * len(arms)]
        for tid in sorted(keys):
            for d in keys[tid]["defects"]:
                cells = []
                for arm in arms:
                    hits = [r["m"]["detected"].get(d["id"]) for r in rows if r["arm"] == arm and r["target"] == tid]
                    cells.append(fmt(sum(hits) / len(hits), pct=True) if hits else "-")
                out.append("| %s / %s %s | %s | %s |" % (tid, d["id"], d.get("title", "")[:50], d.get("severity", ""), " | ".join(cells)))
    out += ["", "## Paired comparisons (same target and repetition)", ""]
    for x, y in load_json(Path(a.arms_file)).get("compare", []):
        if x in arms and y in arms:
            out.append("- " + paired(rows, x, y))
    out += ["", "Decision rule: keep cross-examination and rebuttal only if C_dc_full clearly beats both "
            "B_baseline and D_dc_nodebate at comparable cost. Treat gaps under ~10-15 points as noise "
            "unless n is large.", ""]
    if problems:
        out += ["## Problems (excluded from the numbers above)", ""] + ["- " + p for p in problems] + [""]
    text = "\n".join(out)
    (run_dir / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
