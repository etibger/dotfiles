#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_aacr.py"


class SummarizeAacrTests(unittest.TestCase):
    def run_summary(self, raw, log, status=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_path = root / "raw.json"
            if raw is not None:
                raw_path.write_text(json.dumps(raw), encoding="utf-8")
            log_path = root / "run.log"
            log_path.write_text(log, encoding="utf-8")
            output = root / "summary.json"
            command = [
                sys.executable,
                str(SCRIPT),
                "--raw-json", str(raw_path),
                "--log", str(log_path),
                "--text-artifact", str(root / "report.txt"),
                "--html-dir", str(root / "html"),
                "--json-output", str(output),
                "--text-output", str(root / "summary.txt"),
                "--command-status", str(status),
                "--base", "a" * 40,
                "--tip", "b" * 40,
            ]
            completed = subprocess.run(command, check=False, text=True, capture_output=True)
            return completed, json.loads(output.read_text(encoding="utf-8"))

    def test_finding_is_independent_detection(self):
        completed, result = self.run_summary(
            {"errors": [{"message": "bad return address", "file": "tex.sv", "line": 10}]},
            "1 issue found\n",
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertEqual(result["failure_count"], 1)
        self.assertIn("--no-caching", result["command"])

    def test_current_aacr_findings_wrapper_preserves_error(self):
        completed, result = self.run_summary(
            {
                "findings": {
                    "errors": [
                        {
                            "file_name": "design/tex.sv",
                            "line_number": [480],
                            "error_message": "bad response return address",
                            "priority": "HIGH",
                        }
                    ]
                }
            },
            "1 issue found\n",
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(result["failures"][0]["file"], "design/tex.sv")
        self.assertEqual(result["failures"][0]["line"], [480])
        self.assertEqual(result["failures"][0]["severity"], "HIGH")

    def test_zero_findings_is_complete_but_not_detected(self):
        _, result = self.run_summary({"errors": []}, "0 issues found\n")
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "NOT_DETECTED")

    def test_log_count_is_fallback(self):
        _, result = self.run_summary(None, "Selected 1 files\n2 issues found\n")
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertEqual(result["failure_count"], 2)

    def test_nonzero_command_is_infrastructure_error(self):
        _, result = self.run_summary({"errors": [{"message": "partial"}]}, "", status=7)
        self.assertEqual(result["execution_status"], "INFRASTRUCTURE_ERROR")
        self.assertEqual(result["detection_status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
