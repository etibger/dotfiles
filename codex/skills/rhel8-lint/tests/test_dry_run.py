#!/usr/bin/env python3

from pathlib import Path
import subprocess
import unittest


SKILL = Path(__file__).resolve().parents[1]
RUNNER = SKILL / "scripts" / "run_remote_lint.sh"
REMOTE_RUNNER = SKILL / "scripts" / "run_lint.sh"
REPO = Path("/Users/tibger01/Projects/Fornjot/a_gpu")


class Rhel8LintDryRunTests(unittest.TestCase):
    @classmethod
    def head(cls) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(REPO),
                "rev-parse",
                "HEAD^{commit}",
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def test_explicit_attempt_token_selects_unique_retained_worktree(self):
        head = self.head()
        completed = subprocess.run(
            [
                str(RUNNER),
                "--commit",
                head,
                "--repo",
                str(REPO),
                "--attempt-token",
                "wave_a_fixture_1",
                "--dry-run",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ATTEMPT_TOKEN=wave_a_fixture_1", completed.stdout)
        self.assertIn(f"LOCAL_REPO={REPO}", completed.stdout)
        self.assertIn(
            f"REMOTE_WORKTREE=/home/tibger01/projects/fornjot/"
            f"tmp_gpu_lint_run_{head[:12]}_wave_a_fixture_1",
            completed.stdout,
        )
        self.assertIn("REMOTE_WORKTREE_RETAINED=1", completed.stdout)
        self.assertIn(
            "LINT_COMMAND=dcs_superlint superlint_8x/configuration_top.yaml",
            completed.stdout,
        )

    def test_unsafe_attempt_token_is_rejected_before_network_access(self):
        completed = subprocess.run(
            [
                str(RUNNER),
                "--commit",
                self.head(),
                "--attempt-token",
                "../escape",
                "--dry-run",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Rejected attempt token", completed.stderr)
        self.assertNotIn("Checking the fixed RHEL8", completed.stdout)

    def test_remote_executor_requires_same_attempt_token_guard(self):
        text = REMOTE_RUNNER.read_text(encoding="utf-8")
        self.assertIn("--attempt-token", text)
        self.assertIn('tmp_gpu_lint_run_${short_sha}_$attempt_token', text)
        self.assertIn("refusing to clean or reuse", text.lower())


if __name__ == "__main__":
    unittest.main()
