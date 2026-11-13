#!/usr/bin/env python3
"""Stub of `claude -p --output-format json` for testing the harness without API calls.

Behaves differently per arm (recognised from the prompt) so the report has something to
rank: C finds D1-D5, D finds D1-D3, B finds D1-D4, A finds D1-D2. It also asserts that
plugin variants were built correctly. As the judge it marks a defect detected when the
text PLANTED:<id> appears in the tool output, and fixed when FIXED:<id> does.
"""
import json
import os
import re
import sys
from pathlib import Path

argv = sys.argv[1:]
stdin = sys.stdin.read()


def emit(result, cost, spawned=4):
    spawned = 0 if os.environ.get("FAKE_NO_SUBAGENTS") else spawned
    print(json.dumps({"subagent_stats": {"spawned": spawned}, "type": "result", "subtype": "success", "is_error": False, "result": result,
                      "total_cost_usd": cost, "num_turns": 3, "duration_ms": 1000, "session_id": "fake",
                      "usage": {"input_tokens": 10, "output_tokens": 5}}))


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


if stdin.startswith("You are scoring"):
    key = json.loads(stdin.split("=== ANSWER KEY ===")[1].split("=== DESIGN DOCUMENT")[0])
    out = stdin.split("=== TOOL OUTPUT ===")[1]
    defects = [{"id": d["id"], "detected": "PLANTED:%s" % d["id"] in out,
                "fixed": ("FIXED:%s" % d["id"] in out) or False, "evidence": "stub"} for d in key["defects"]]
    findings = [{"summary": "found %s" % d["id"], "class": "defect:%s" % d["id"]} for d in defects if d["detected"]]
    findings.append({"summary": "style nit", "class": "invalid"})
    emit("Here is my verdict:\n" + json.dumps({"defects": defects, "findings": findings}) + "\nDone.", 0.01)
    sys.exit(0)

plugin_dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--plugin-dir"]
for pd in plugin_dirs:
    skill = Path(pd, "skills", "review", "SKILL.md")
    if not skill.exists():
        fail("plugin dir missing review skill: %s" % pd)
    text = skill.read_text()
    if "design-court" in text or "design-court" in Path(pd, ".claude-plugin", "plugin.json").read_text():
        fail("plugin was not renamed: %s" % pd)
    if Path(pd).name == "dc-nodebate" and "BENCHMARK VARIANT" not in text:
        fail("no_debate patch missing")
    if Path(pd).name == "dc-full" and "BENCHMARK VARIANT" in text:
        fail("full variant must not be patched")

ws = Path.cwd()
target = next(Path("docs/designs").glob("*.md"))
if "/dc-full:" in stdin:
    ids, cost, where = ["D1", "D2", "D3", "D4", "D5"], 5.0, Path("docs/designs/reviews/x/REPORT.md")
elif "/dc-nodebate:" in stdin:
    ids, cost, where = ["D1", "D2", "D3"], 3.0, Path("docs/designs/reviews/x/REPORT.md")
elif "5 independent" in stdin:
    ids, cost, where = ["D1", "D2", "D3", "D4"], 2.0, Path("FINDINGS.md")
else:
    ids, cost, where = ["D1", "D2"], 1.0, Path("FINDINGS.md")
where.parent.mkdir(parents=True, exist_ok=True)
where.write_text("\n".join("- PLANTED:%s identified" % i for i in ids) + "\n")
target.write_text(target.read_text() + "\n" + "\n".join("FIXED:%s" % i for i in ids[:1]) + "\n")
emit("Review complete. " + " ".join("PLANTED:%s" % i for i in ids[:1]), cost)
