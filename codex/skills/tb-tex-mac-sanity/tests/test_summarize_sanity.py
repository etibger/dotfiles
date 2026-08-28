#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_sanity.py"
RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "run_sanity.sh"


class SummarizeSanityTests(unittest.TestCase):
    def run_summary(self, log, error=None, command_status=0, blk_status=0, expected="legal_hdr_return_addr"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test_log = root / "test.log"
            test_log.write_text(log, encoding="utf-8")
            error_json = root / "error.json"
            if error is not None:
                error_json.write_text(json.dumps(error), encoding="utf-8")
            driver = root / "driver.log"
            driver.write_text(log, encoding="utf-8")
            output = root / "summary.json"
            completed = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--test-log", str(test_log),
                    "--error-json", str(error_json),
                    "--driver-log", str(driver),
                    "--json-output", str(output),
                    "--text-output", str(root / "summary.txt"),
                    "--command-status", str(command_status),
                    "--blk-status", str(blk_status),
                    "--candidate", "c" * 40,
                    "--expected-pattern", expected,
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            return completed, json.loads(output.read_text(encoding="utf-8"))

    def test_assertion_failure_is_detected_even_with_nonzero_process(self):
        error = {"error_log": {"primary_error": {"error_cat_0": "Assertion Error", "log_msg": "legal_hdr_return_addr failed"}}}
        completed, result = self.run_summary("** BLK TEST FAIL, Assertion Error\n", error, 2, 1)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertTrue(result["attributable_detection"])
        self.assertEqual(result["failure_count"], 1)

    def test_unattributed_failure_does_not_satisfy_detector(self):
        error = {"error_log": {"primary_error": {"error_cat_0": "Assertion Error", "log_msg": "some_other_assertion failed"}}}
        _, result = self.run_summary("** BLK TEST FAIL, Assertion Error\n", error)
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "UNKNOWN")
        self.assertEqual(result["classification"], "UNATTRIBUTED_TEST_FAILURE")
        self.assertFalse(result["attributable_detection"])

    def test_pass_is_not_detection(self):
        _, result = self.run_summary("** BLK TEST PASS\n")
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "NOT_DETECTED")

    def test_missing_result_is_infrastructure_error(self):
        _, result = self.run_summary("compile stopped\n", command_status=3, blk_status=125)
        self.assertEqual(result["execution_status"], "INFRASTRUCTURE_ERROR")
        self.assertEqual(result["detection_status"], "UNKNOWN")

    def test_license_failure_is_not_bug_detection(self):
        _, result = self.run_summary("** BLK TEST FAIL\nlicense checkout failed\n", command_status=2, blk_status=1)
        self.assertEqual(result["execution_status"], "INFRASTRUCTURE_ERROR")
        self.assertEqual(result["detection_status"], "UNKNOWN")

    def test_runner_requires_candidate_bound_serialized_preflight(self):
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("manifest_value SERIALIZED_BARRIER", runner)
        self.assertIn("manifest_value CANDIDATE_SHA", runner)
        self.assertIn("manifest_value COMMAND", runner)


if __name__ == "__main__":
    unittest.main()
