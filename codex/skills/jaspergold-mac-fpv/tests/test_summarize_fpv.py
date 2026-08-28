#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_fpv.py"
WRAPPER = Path(__file__).resolve().parents[1] / "assets" / "save_up_to_five_cex.tcl"
RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "run_fpv.sh"


def proof_report(cex=0, proven=1, unresolved=0):
    return {
        "fpv": {
            "summary": {
                "asserts": {
                    "total": cex + proven + unresolved,
                    "cex": cex,
                    "ar_cex": 0,
                    "proven": proven,
                    "undetermined": unresolved,
                    "error": 0,
                }
            }
        }
    }


class SummarizeFpvTests(unittest.TestCase):
    def run_summary(self, log, status, report=None, final=False, vcd=False, expected="legal_hdr_return_addr"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "run"
            run_dir.mkdir()
            report_path = run_dir / "proof_report.json"
            if report is not None:
                report_path.write_text(json.dumps(report), encoding="utf-8")
            if final:
                (run_dir / "tex_flt_results.rpt").write_text("final\n", encoding="utf-8")
            if vcd:
                (run_dir / "cex.vcd").write_text("$date\n", encoding="utf-8")
            log_path = root / "ftrun.log"
            log_path.write_text(log, encoding="utf-8")
            output = root / "summary.json"
            completed = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--proof-report", str(report_path),
                    "--run-dir", str(run_dir),
                    "--log", str(log_path),
                    "--json-output", str(output),
                    "--text-output", str(root / "summary.txt"),
                    "--ftrun-status", str(status),
                    "--candidate", "d" * 40,
                    "--expected-property", expected,
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            return completed, json.loads(output.read_text(encoding="utf-8"))

    def test_complete_attributed_cex(self):
        log = 'INFO (IPF055): A counterexample (cex) with 3 cycles was found for the property "top.legal_hdr_return_addr"\n'
        completed, result = self.run_summary(log, 0, proof_report(cex=1), final=True, vcd=True)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertEqual(result["classification"], "VALIDATION_DETECTED")

    def test_cex_survives_later_oom_as_infra_limited_detection(self):
        log = (
            'INFO (IPF055): A counterexample (cex) with 3 cycles was found for the property "top.legal_hdr_return_addr"\n'
            'INFO (IPL017): The host machine is running out of memory.\n'
            'broken_piped\nWarning: Tool finished with exit code: 1 (UNKNOWN_ERROR)\n'
        )
        _, result = self.run_summary(log, 1, proof_report(cex=0, proven=0, unresolved=3))
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertEqual(result["execution_status"], "INFRASTRUCTURE_ERROR")
        self.assertEqual(result["classification"], "VALIDATION_DETECTED_WITH_INFRA_LIMIT")
        self.assertFalse(result["final_artifacts_complete"])

    def test_clean_bounded_run_is_not_detection(self):
        _, result = self.run_summary("normal completion\n", 0, proof_report(unresolved=2), final=True)
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "NOT_DETECTED")

    def test_unattributed_cex_does_not_satisfy_detector(self):
        log = 'INFO (IPF055): A counterexample (cex) with 4 cycles was found for the property "top.other"\n'
        _, result = self.run_summary(log, 0, proof_report(cex=1), final=True, vcd=True)
        self.assertEqual(result["detection_status"], "UNKNOWN")
        self.assertEqual(result["classification"], "UNATTRIBUTED_CEX")

    def test_stop_after_five_is_explicit_gap(self):
        _, result = self.run_summary("normal completion\n", 0, proof_report(), final=True)
        self.assertEqual(result["saved_cex_limit"], 5)
        self.assertFalse(result["stop_after_cex_implemented"])

    def test_standard_hook_runs_before_campaign_bounds(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertLess(
            wrapper.index("::WAVE_A_FPV::base_pre_configure", wrapper.index("proc ::fts::hook::pre_configure")),
            wrapper.index("::fts::cfg_set {tool_config jg run_limit}"),
        )
        self.assertNotIn("::fts::cfg_set {runtime failure_limit}", wrapper)

    def test_runner_requires_candidate_bound_serialized_preflight(self):
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("manifest_value SERIALIZED_BARRIER", runner)
        self.assertIn("manifest_value CANDIDATE_SHA", runner)
        self.assertIn("manifest_value COMMAND", runner)


if __name__ == "__main__":
    unittest.main()
