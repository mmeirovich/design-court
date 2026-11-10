"""Shared helpers for the benchmark harness (stdlib only, Python 3.8+)."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SEVERITY_WEIGHT = {"blocker": 3, "major": 2, "minor": 1}


def claude_bin() -> str:
    """Path of the claude CLI. Override with BENCH_CLAUDE_BIN (the tests use a stub)."""
    return os.environ.get("BENCH_CLAUDE_BIN", "claude")


def env_args() -> list:
    """Extra CLI args applied to every run, e.g. BENCH_CLAUDE_ARGS='--setting-sources project'."""
    return shlex.split(os.environ.get("BENCH_CLAUDE_ARGS", ""))


def _text(x) -> str:
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else x


def run_claude(prompt: str, cwd: Path, args: list, timeout: int) -> dict:
    """Run `claude -p` headless with the prompt on stdin. Never raises."""
    cmd = [claude_bin(), "-p", "--output-format", "json"] + list(args)
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd), input=prompt, capture_output=True, text=True, timeout=timeout
        )
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = -9, _text(e.stdout), "TIMEOUT after %ss\n%s" % (timeout, _text(e.stderr))
    except OSError as e:
        rc, out, err = 127, "", "cannot run %s: %s" % (cmd[0], e)
    return {
        "cmd": cmd,
        "returncode": rc,
        "stdout": out,
        "stderr": err,
        "wall_s": round(time.time() - t0, 1),
        "json": parse_cli_json(out),
    }


def parse_cli_json(stdout: str):
    """The `--output-format json` payload: a dict, or a list of events whose last is the result."""
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if isinstance(data, list):
        results = [d for d in data if isinstance(d, dict) and d.get("type") == "result"]
        return results[-1] if results else None
    return data if isinstance(data, dict) else None


def summarize_cli_json(j) -> dict:
    """Pull cost / usage out of the CLI payload defensively (fields may be absent)."""
    j = j or {}
    usage = j.get("usage") or {}
    return {
        "is_error": bool(j.get("is_error", False)),
        "cost_usd": j.get("total_cost_usd", j.get("cost_usd")),
        "num_turns": j.get("num_turns"),
        "duration_ms": j.get("duration_ms"),
        "session_id": j.get("session_id"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
    }


def extract_json_obj(text: str, must_have: str):
    """First JSON object in `text` that contains the key `must_have`, else None."""
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict) and must_have in obj:
                return obj
        except ValueError:
            pass
        i = text.find("{", i + 1)
    return None


def load_json(path: Path):
    with open(str(path), encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def discover_targets(corpus: Path, wanted=None) -> list:
    """Corpus entries: directories holding target.md and answer-key.json (`_`-prefixed are skipped)."""
    out = []
    for d in sorted(corpus.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and (d / "target.md").exists():
            if (d / "answer-key.json").exists() and (not wanted or d.name in wanted):
                out.append(d)
    return out
