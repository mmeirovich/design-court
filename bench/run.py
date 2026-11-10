#!/usr/bin/env python3
"""Run every (target, arm, repetition) in a fresh workspace and collect what each arm produced.

  python3 bench/run.py --smoke                      # cheap wiring check, one target, one rep
  python3 bench/run.py --reps 3 --out bench/results/main
  python3 bench/run.py --out bench/results/main     # re-run the same command to resume

Each run gets its own git-initialised copy of the target (plus its `repo/` files), runs
`claude -p` headless in it, and saves: result.json (cost, time, tokens), raw.json,
stderr.txt, and bundle.md (everything the arm produced, with arm-identifying file names
stripped, for blind scoring).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (REPO, ROOT, discover_targets, env_args, load_json,  # noqa: E402
                    run_claude, summarize_cli_json, write_json)

NO_DEBATE_NOTE = (
    "\n> **BENCHMARK VARIANT - debate disabled.** Steps 4b (cross-examination) and 4c "
    "(rebuttal) are disabled in this variant: do not run them, do not write "
    "`findings-anon.md` or `mapping.md`, and in step 4d give the judge only the "
    "independent reports (the judge verifies every finding itself). Everything else is "
    "unchanged.\n"
)
MAX_FILE = 60_000
MAX_BUNDLE = 400_000


def build_plugin(spec: dict, dest_root: Path) -> Path:
    """Copy a plugin from the repo under a new name so it cannot clash with the installed copy."""
    dst = dest_root / spec["rename"]
    if dst.exists():
        return dst
    shutil.copytree(str(REPO / spec["path"]), str(dst), ignore=shutil.ignore_patterns(".git"))
    for p in dst.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".json"):
            p.write_text(p.read_text(encoding="utf-8").replace("design-court", spec["rename"]),
                         encoding="utf-8")
    if spec.get("patch") == "no_debate":
        skill = dst / "skills" / "review" / "SKILL.md"
        marker = "## 4. Run a round"
        text = skill.read_text(encoding="utf-8")
        if marker not in text:
            sys.exit("cannot build no_debate variant: %r not found in review/SKILL.md "
                     "(the skill changed; update NO_DEBATE_NOTE placement in run.py)" % marker)
        skill.write_text(text.replace(marker, marker + "\n" + NO_DEBATE_NOTE, 1), encoding="utf-8")
    return dst


def git(ws: Path, *a: str) -> str:
    r = subprocess.run(["git", "-c", "user.email=bench@local", "-c", "user.name=bench", *a],
                       cwd=str(ws), capture_output=True, text=True)
    return r.stdout


def make_workspace(tdir: Path, ws: Path) -> str:
    ws.mkdir(parents=True, exist_ok=True)
    if (tdir / "repo").exists():
        shutil.copytree(str(tdir / "repo"), str(ws), dirs_exist_ok=True)
    rel = "docs/designs/%s.md" % tdir.name
    (ws / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(tdir / "target.md"), str(ws / rel))
    git(ws, "init", "-q")
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "init")
    return rel


def collect_bundle(ws: Path, rel_target: str, reply: str) -> str:
    """Everything the arm produced, labelled neutrally so the scorer is (mostly) blind."""
    git(ws, "add", "-A")
    parts = ["# FINAL REPLY\n\n%s\n" % (reply or "(empty)")]
    n, total = 0, len(parts[0])
    for line in git(ws, "diff", "--cached", "--name-status").splitlines():
        status, _, path = line.partition("\t")
        if status.startswith("A"):
            content = (ws / path).read_text(encoding="utf-8", errors="replace")
            n += 1
            label = "OTHER OUTPUT FILE %d" % n
        elif path == rel_target:
            content = git(ws, "diff", "--cached", "--", path)
            label = "TARGET DOCUMENT CHANGES (diff)"
        elif status.startswith("M"):
            content = git(ws, "diff", "--cached", "--", path)
            n += 1
            label = "OTHER CHANGED FILE %d (diff)" % n
        else:
            continue
        if len(content) > MAX_FILE:
            content = content[:MAX_FILE] + "\n[truncated]"
        if total + len(content) > MAX_BUNDLE:
            parts.append("\n# [bundle size cap reached; remaining files omitted]\n")
            break
        total += len(content)
        parts.append("\n# %s\n\n%s\n" % (label, content))
    if not any(p.startswith("\n# TARGET DOCUMENT") for p in parts):
        parts.append("\n# TARGET DOCUMENT CHANGES (diff)\n\n(none)\n")
    return "".join(parts)


def run_one(job: dict) -> str:
    rd: Path = job["dir"]
    if (rd / "result.json").exists():
        return "skip %s" % rd.name
    ws = rd / "workspace"
    if ws.exists():
        shutil.rmtree(str(ws))
    rel = make_workspace(job["tdir"], ws)
    arm = job["arm"]
    prompt = (arm.get("smoke_prompt") if job["smoke"] and arm.get("smoke_prompt")
              else arm["prompt"]).replace("{target}", rel)
    args = ["--permission-mode", job["permission_mode"]] if job["permission_mode"] else []
    for p in job["plugin_dirs"]:
        args += ["--plugin-dir", str(p)]
    if job["model"]:
        args += ["--model", job["model"]]
    if job["budget"]:
        args += ["--max-budget-usd", str(job["budget"])]
    args += env_args() + arm.get("claude_args", [])
    if job["dry_run"]:
        return "DRY %s\n  cwd=%s\n  stdin=%s\n  args=%s" % (rd.name, ws, prompt[:100], " ".join(args))
    res = run_claude(prompt, ws, args, job["timeout"])
    j = res["json"] or {}
    reply = j.get("result") if isinstance(j.get("result"), str) else res["stdout"]
    bundle = collect_bundle(ws, rel, reply)
    (rd / "bundle.md").write_text(bundle, encoding="utf-8")
    (rd / "raw.json").write_text(res["stdout"], encoding="utf-8")
    (rd / "stderr.txt").write_text(res["stderr"], encoding="utf-8")
    meta = summarize_cli_json(res["json"])
    meta.update({
        "target": job["tdir"].name, "arm": job["arm_name"], "rep": job["rep"],
        "returncode": res["returncode"], "wall_s": res["wall_s"],
        "ok": res["returncode"] == 0 and not meta["is_error"] and res["json"] is not None,
        "bundle_bytes": len(bundle), "smoke": job["smoke"],
    })
    write_json(rd / "result.json", meta)
    return "%s ok=%s cost=%s wall=%ss" % (rd.relative_to(rd.parents[2]), meta["ok"],
                                          meta["cost_usd"], meta["wall_s"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--corpus", default=str(ROOT / "corpus"))
    ap.add_argument("--arms-file", default=str(ROOT / "arms.json"))
    ap.add_argument("--arms", help="comma-separated arm names (default: all)")
    ap.add_argument("--targets", help="comma-separated corpus ids (default: all)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", help="results dir (reuse a dir to resume)")
    ap.add_argument("--jobs", type=int, default=1, help="parallel runs (mind rate limits)")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds per run")
    ap.add_argument("--model", default=os.environ.get("BENCH_MODEL"), help="same model for all arms")
    ap.add_argument("--budget", type=float, help="--max-budget-usd cap per run")
    ap.add_argument("--permission-mode", default=os.environ.get("BENCH_PERMISSION_MODE"),
                    help="claude permission mode for every run (headless runs cannot prompt, so\n"
                         "modes that ask will simply deny tools and skew the comparison)")
    ap.add_argument("--bypass-permissions", action="store_true",
                    help="opt in to --permission-mode bypassPermissions. Agents then run any tool,\n"
                         "including shell and network, with your credentials. Only use on a machine\n"
                         "or container you are happy to let them act on.")
    ap.add_argument("--smoke", action="store_true", help="1 target, 1 rep, cheap prompts")
    ap.add_argument("--dry-run", action="store_true", help="print what would run, run nothing")
    a = ap.parse_args()

    if a.bypass_permissions and not a.permission_mode:
        a.permission_mode = "bypassPermissions"
    if not a.permission_mode and not a.dry_run:
        sys.exit("refusing to start: choose a permission mode. Pass --bypass-permissions (agents may "
                 "run any tool, with your credentials; see --help) or --permission-mode <mode> / "
                 "BENCH_PERMISSION_MODE.")
    cfg = load_json(Path(a.arms_file))["arms"]
    names = a.arms.split(",") if a.arms else list(cfg)
    unknown = [n for n in names if n not in cfg]
    if unknown:
        sys.exit("unknown arms: %s (have: %s)" % (unknown, list(cfg)))
    targets = discover_targets(Path(a.corpus), a.targets.split(",") if a.targets else None)
    if not targets:
        sys.exit("no corpus targets found in %s" % a.corpus)
    if a.smoke:
        targets, a.reps = targets[:1], 1
    out = Path(a.out) if a.out else ROOT / "results" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "config.json", {"arms": names, "targets": [t.name for t in targets],
                                     "reps": a.reps, "model": a.model, "smoke": a.smoke})

    plugin_dirs = {}
    for n in names:
        plugin_dirs[n] = [build_plugin(s, out / "plugins") for s in cfg[n].get("plugins", [])]

    jobs = []
    for rep in range(1, a.reps + 1):
        for t in targets:
            for n in names:
                jobs.append({"dir": out / "runs" / t.name / n / ("rep%d" % rep), "tdir": t,
                             "arm": cfg[n], "arm_name": n, "rep": rep, "plugin_dirs": plugin_dirs[n],
                             "model": a.model, "budget": a.budget, "timeout": a.timeout,
                             "permission_mode": a.permission_mode, "smoke": a.smoke,
                             "dry_run": a.dry_run})
    print("%d runs -> %s" % (len(jobs), out))
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        for line in ex.map(run_one, jobs):
            print(line, flush=True)
    if not a.dry_run:
        print("\nnext: python3 bench/score.py --run-dir %s && python3 bench/report.py --run-dir %s" % (out, out))


if __name__ == "__main__":
    main()
