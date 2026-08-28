#!/usr/bin/env python3
"""Normalize local Wave A FPV, preserving a CEX across later infra failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ASSERT_PASS_KEYS = ("proven", "bounded_proven_auto", "bounded_proven_user", "marked_proven")
ASSERT_FAIL_KEYS = ("cex", "ar_cex", "error")
ASSERT_UNRESOLVED_KEYS = ("undetermined", "unprocessed", "processing")
INFRA_RE = re.compile(
    r"broken_piped|out of memory|host machine is running out of memory|"
    r"UNKNOWN_ERROR|killed by signal|SIGKILL|exit code:\s*(?:1|137)",
    flags=re.IGNORECASE,
)
CEX_RE = re.compile(
    r'A counterexample \(cex\).*?property "([^"]+)"',
    flags=re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proof-report", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument("--ftrun-status", required=True, type=int)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-property", default="")
    return parser.parse_args()


def require_counts(group: Any) -> dict[str, int]:
    if not isinstance(group, dict) or not isinstance(group.get("total"), int):
        raise ValueError("missing assertion summary")
    counts: dict[str, int] = {}
    for key, value in group.items():
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"invalid assertion count {key}={value!r}")
        counts[key] = value
    return counts


def main() -> int:
    args = parse_args()
    log_text = args.log.read_text(encoding="utf-8", errors="replace") if args.log.is_file() else ""
    log_cex = sorted(set(CEX_RE.findall(log_text)))
    expected_re = re.compile(args.expected_property) if args.expected_property else None
    attributed_cex = [name for name in log_cex if expected_re is None or expected_re.search(name)]
    infra_match = INFRA_RE.search(log_text)

    report_valid = False
    report_error: str | None = None
    assert_counts: dict[str, int] = {}
    report_cex_count = 0
    if args.proof_report.is_file():
        try:
            report = json.loads(args.proof_report.read_text(encoding="utf-8"))
            assert_counts = require_counts(report["fpv"]["summary"]["asserts"])
            report_cex_count = sum(assert_counts.get(key, 0) for key in ("cex", "ar_cex"))
            report_valid = True
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            report_error = str(exc)
    else:
        report_error = "proof_report.json is missing"

    vcds = sorted(str(path) for path in args.run_dir.rglob("*.vcd")) if args.run_dir.is_dir() else []
    final_reports = []
    if args.run_dir.is_dir():
        for pattern in ("*_results.rpt", "verification_results.json"):
            final_reports.extend(str(path) for path in args.run_dir.rglob(pattern))
    final_reports = sorted(set(final_reports))

    any_cex = bool(log_cex or report_cex_count)
    attributable = bool(attributed_cex) if args.expected_property else any_cex
    final_artifacts_complete = report_valid and bool(final_reports) and (not any_cex or bool(vcds))

    if attributable and (args.ftrun_status != 0 or infra_match or not final_artifacts_complete):
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "DETECTED"
        classification = "VALIDATION_DETECTED_WITH_INFRA_LIMIT"
    elif attributable:
        execution_status = "COMPLETE"
        detection_status = "DETECTED"
        classification = "VALIDATION_DETECTED"
    elif any_cex:
        execution_status = "COMPLETE" if args.ftrun_status == 0 and final_artifacts_complete else "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "UNATTRIBUTED_CEX"
    elif args.ftrun_status == 0 and final_artifacts_complete:
        execution_status = "COMPLETE"
        detection_status = "NOT_DETECTED"
        classification = "NO_CEX_WITHIN_LIMIT"
    else:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "FPV_EXECUTION_INCOMPLETE"

    assert_passed = sum(assert_counts.get(key, 0) for key in ASSERT_PASS_KEYS)
    assert_failed = sum(assert_counts.get(key, 0) for key in ASSERT_FAIL_KEYS)
    assert_unresolved = sum(assert_counts.get(key, 0) for key in ASSERT_UNRESOLVED_KEYS)
    result = {
        "schema_version": 1,
        "wave": "A",
        "branch": "fpv",
        "candidate_sha": args.candidate,
        "target": "tex_flt",
        "proof_limit": "10m",
        "slots": 4,
        "saved_cex_limit": 5,
        "requested_stop_after_cex": 5,
        "stop_after_cex_implemented": False,
        "executor_gap": "No tested individual-property CEX monitor and cancellation mechanism is implemented.",
        "command": "ftrun tex_flt -local -batch -auto_run -slots 4 -save on_failure",
        "ftrun_status": args.ftrun_status,
        "execution_status": execution_status,
        "detection_status": detection_status,
        "classification": classification,
        "expected_property_regex": args.expected_property or None,
        "attributable_detection": attributable,
        "failure_count": len(attributed_cex) if attributed_cex else (report_cex_count if attributable else 0),
        "cex_count_from_report": report_cex_count,
        "cex_properties_from_log": log_cex,
        "attributed_cex_properties": attributed_cex,
        "failures": [{"property": name, "kind": "cex"} for name in attributed_cex],
        "assertions": {
            "total": assert_counts.get("total"),
            "passed": assert_passed,
            "failed": assert_failed,
            "unresolved": assert_unresolved,
            "status_counts": assert_counts,
        },
        "final_artifacts_complete": final_artifacts_complete,
        "infrastructure_signature": infra_match.group(0) if infra_match else None,
        "report_error": report_error,
        "artifacts": {
            "run_dir": str(args.run_dir),
            "log": str(args.log),
            "proof_report": str(args.proof_report),
            "final_reports": final_reports,
            "vcds": vcds,
        },
    }
    lines = [
        "MAC WAVE A FPV SUMMARY",
        f"Candidate: {args.candidate}",
        "Bounds: target=tex_flt proof_limit=10m slots=4 saved_cex_limit=5",
        "Stop-after-five-CEX implemented: no (executor gap)",
        f"Execution status: {execution_status}",
        f"Detection status: {detection_status}",
        f"Classification: {classification}",
        f"FTRun status: {args.ftrun_status}",
        f"Attributed CEX: {', '.join(attributed_cex) if attributed_cex else 'none'}",
        f"Final artifacts complete: {str(final_artifacts_complete).lower()}",
        f"Run directory: {args.run_dir}",
    ]
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
