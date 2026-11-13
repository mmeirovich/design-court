"""End-to-end test of run.py -> score.py -> report.py using the stub CLI (no API calls).

    python3 -m unittest discover -s bench/tests
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BENCH))
from common import extract_json_obj, parse_cli_json  # noqa: E402

FAKE = str(Path(__file__).resolve().parent / "fake_claude.py")


def sh(*args, env=None):
    e = dict(os.environ, BENCH_CLAUDE_BIN=FAKE)
    e.update(env or {})
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=e)


class UnitTests(unittest.TestCase):
    def test_extract_json_skips_unrelated_objects(self):
        text = 'noise {"a": 1} more {"defects": [], "x": {"y": 2}} tail'
        self.assertEqual(extract_json_obj(text, "defects"), {"defects": [], "x": {"y": 2}})
        self.assertIsNone(extract_json_obj("no json here {", "defects"))

    def test_parse_cli_json_accepts_dict_and_event_list(self):
        self.assertEqual(parse_cli_json('{"result": "x"}'), {"result": "x"})
        self.assertEqual(parse_cli_json('[{"type":"system"},{"type":"result","result":"y"}]')["result"], "y")
        self.assertIsNone(parse_cli_json("not json"))


class PipelineTest(unittest.TestCase):
    def test_full_pipeline(self):
        with tempfile.TemporaryDirectory() as out:
            r = sh(BENCH / "run.py", "--bypass-permissions", "--reps", "6", "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertEqual(r.stdout.count(" ok=True"), 24, r.stdout)

            # resuming must not redo finished runs
            r2 = sh(BENCH / "run.py", "--bypass-permissions", "--reps", "6", "--out", out)
            self.assertEqual(r2.stdout.count("skip "), 24)

            r = sh(BENCH / "score.py", "--run-dir", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("scored 24, unparseable 0", r.stdout)

            r = sh(BENCH / "report.py", "--run-dir", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            rep = r.stdout
            for arm in ("A_superpowers", "B_baseline", "C_dc_full", "D_dc_nodebate"):
                self.assertIn("| %s | 6 |" % arm, rep)
            # weighted recall = detected weight / 15 (blocker 3, major 2, minor 1)
            row = {l.split("|")[1].strip(): l for l in rep.splitlines() if l.startswith("| ") and "_" in l.split("|")[1]}
            self.assertIn("67% +- 0%", row["C_dc_full"])    # D1-D5 = 10/15
            self.assertIn("53% +- 0%", row["B_baseline"])   # D1-D4 = 8/15
            self.assertIn("47% +- 0%", row["D_dc_nodebate"])  # D1-D3 = 7/15
            self.assertIn("33% +- 0%", row["A_superpowers"])  # D1-D2 = 5/15
            self.assertIn("C_dc_full vs B_baseline: weighted recall +13.3 pts", rep)
            self.assertIn("cost ratio 2.5x", rep)
            self.assertIn("C_dc_full is better", rep)
            self.assertNotIn("## Problems", rep)

    def test_failed_runs_are_reported_not_hidden(self):
        with tempfile.TemporaryDirectory() as out:
            r = sh(BENCH / "run.py", "--bypass-permissions", "--reps", "1", "--arms", "C_dc_full", "--out", out,
                   env={"BENCH_CLAUDE_BIN": "/nonexistent/claude"})
            self.assertEqual(r.returncode, 0)
            self.assertIn("ok=False", r.stdout)
            sh(BENCH / "score.py", "--run-dir", out)
            rep = sh(BENCH / "report.py", "--run-dir", out).stdout
            self.assertIn("## Problems", rep)
            self.assertIn("run failed", rep)

    def test_plugin_arm_that_never_ran_the_plugin_is_invalid(self):
        with tempfile.TemporaryDirectory() as out:
            r = sh(BENCH / "run.py", "--bypass-permissions", "--reps", "1", "--arms", "C_dc_full,B_baseline",
                   "--out", out, env={"FAKE_NO_SUBAGENTS": "1"})
            self.assertIn("C_dc_full/rep1 ok=False", r.stdout)   # require_subagents arm is rejected
            self.assertIn("B_baseline/rep1 ok=True", r.stdout)   # arm without the requirement is not
            sh(BENCH / "score.py", "--run-dir", out)
            rep = sh(BENCH / "report.py", "--run-dir", out).stdout
            self.assertIn("C_dc_full/rep1: run failed", rep)

    def test_relative_out_dir_gives_absolute_plugin_paths(self):
        # regression: a relative --out made --plugin-dir relative to the per-run workspace
        r = subprocess.run([sys.executable, str(BENCH / "run.py"), "--dry-run", "--reps", "1",
                            "--arms", "C_dc_full", "--out", "bench/results/_reltest"],
                           capture_output=True, text=True, cwd=str(BENCH.parent),
                           env=dict(os.environ, BENCH_CLAUDE_BIN=FAKE))
        self.assertIn("--plugin-dir %s" % (BENCH.parent / "bench/results/_reltest/plugins/dc-full").resolve(), r.stdout)

    def test_refuses_without_explicit_permission_choice(self):
        with tempfile.TemporaryDirectory() as out:
            env = {k: v for k, v in os.environ.items() if k != "BENCH_PERMISSION_MODE"}
            r = subprocess.run([sys.executable, str(BENCH / "run.py"), "--reps", "1", "--out", out],
                               capture_output=True, text=True, env=dict(env, BENCH_CLAUDE_BIN=FAKE))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("choose a permission mode", r.stderr)
            self.assertFalse(list(Path(out).glob("runs/*/*/*/result.json")))

    def test_dry_run_executes_nothing(self):
        with tempfile.TemporaryDirectory() as out:
            r = sh(BENCH / "run.py", "--dry-run", "--reps", "1", "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("DRY", r.stdout)
            self.assertFalse(list(Path(out).glob("runs/*/*/*/result.json")))


if __name__ == "__main__":
    unittest.main()
