#!/usr/bin/env python3

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "normalize_rhel8_lint.py"


def repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("cannot locate repository root")


TEST_TEMP_ROOT = repository_root() / "private/tmp/to_clean/validate-gpu-wave-a-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def report_xml(findings):
    root = ET.Element("report")
    summary = ET.SubElement(root, "Table")
    ET.SubElement(summary, "Table-name").text = "Domain:-All-Domains"
    item = ET.SubElement(summary, "Table-item")
    ET.SubElement(item, "Category").text = "all"
    ET.SubElement(item, "Errors").text = str(len(findings))
    ET.SubElement(item, "Warnings").text = "0"
    ET.SubElement(item, "Info").text = "0"
    ET.SubElement(item, "Waived").text = "0"
    ET.SubElement(item, "Number-of-Messages").text = str(len(findings))
    table = ET.SubElement(root, "Table")
    ET.SubElement(table, "Table-name").text = "ERROR-DOMAIN"
    for finding in findings:
        message = ET.SubElement(table, "Table-item")
        ET.SubElement(message, "Severity").text = "Error"
        ET.SubElement(message, "Tag").text = finding["rule"]
        ET.SubElement(message, "Message").text = finding["message"]
        ET.SubElement(message, "Source-Location").text = finding["source"]
        ET.SubElement(message, "Instance-Module").text = "vithar_tex_flt_msgout"
    return ET.tostring(root, encoding="unicode")


class NormalizeRhel8LintTests(unittest.TestCase):
    def run_summary(self, findings=None, status=0, pattern="legal_hdr_return_addr", include_report=True):
        findings = findings or []
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            report = artifacts / "reports/arm_lint_db/eda/report.xml"
            report.parent.mkdir(parents=True)
            if include_report:
                report.write_text(report_xml(findings), encoding="utf-8")
            driver = root / "driver.log"
            driver.write_text(f"LOCAL_ARTIFACT_DIR={artifacts}\n", encoding="utf-8")
            output = root / "summary.json"
            completed = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--driver-log", str(driver),
                    "--candidate", "e" * 40,
                    "--expected-pattern", pattern,
                    "--runner-status", str(status),
                    "--json-output", str(output),
                    "--text-output", str(root / "summary.txt"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            return completed, json.loads(output.read_text(encoding="utf-8"))

    def test_attributed_unwaived_report_finding_is_detection(self):
        completed, result = self.run_summary(
            [{"rule": "TEX_RETURN", "message": "legal_hdr_return_addr violated", "source": "vithar_tex_flt_msgout.sv:19"}]
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertTrue(result["attributable_detection"])
        self.assertTrue(result["report_complete"])

    def test_nonzero_runner_preserves_detection_but_is_incomplete(self):
        _, result = self.run_summary(
            [{"rule": "TEX_RETURN", "message": "legal_hdr_return_addr violated", "source": "file.sv:1"}],
            status=1,
        )
        self.assertEqual(result["execution_status"], "INFRASTRUCTURE_ERROR")
        self.assertEqual(result["detection_status"], "DETECTED")
        self.assertEqual(result["classification"], "LINT_DETECTED_WITH_INFRA_LIMIT")

    def test_clean_report_is_not_detection(self):
        _, result = self.run_summary([])
        self.assertEqual(result["execution_status"], "COMPLETE")
        self.assertEqual(result["detection_status"], "NOT_DETECTED")

    def test_unattributed_violation_is_ambiguous(self):
        _, result = self.run_summary(
            [{"rule": "OTHER", "message": "different finding", "source": "other.sv:7"}]
        )
        self.assertEqual(result["detection_status"], "UNKNOWN")
        self.assertEqual(result["classification"], "UNATTRIBUTED_LINT_FAILURE")

    def test_missing_expected_report_is_infrastructure_error(self):
        _, result = self.run_summary(include_report=False)
        self.assertEqual(result["execution_status"], "INFRASTRUCTURE_ERROR")
        self.assertEqual(result["detection_status"], "UNKNOWN")
        self.assertIn("report.xml is missing", result["report_error"])


if __name__ == "__main__":
    unittest.main()
