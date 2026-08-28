#!/usr/bin/env python3
"""Normalize retained Arm Lint report XML for the Wave A RHEL8 detector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any


INFRA_RE = re.compile(
    r"licen[cs]e.*(?:denied|failed|unavailable)|out of memory|no space left|"
    r"connection (?:closed|timed out|refused)|could not resolve hostname|"
    r"command not found|setup failed|collection failed",
    re.IGNORECASE,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver-log", required=True, type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-pattern", required=True)
    parser.add_argument("--runner-status", required=True, type=int)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    return parser.parse_args()


def discover_artifact_dir(driver_text: str) -> Path | None:
    matches = re.findall(r"^LOCAL_ARTIFACT_DIR=(.+)$", driver_text, re.MULTILINE)
    if not matches or matches[-1] in {"NOT_CREATED", "UNKNOWN"}:
        return None
    return Path(matches[-1])


def value(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return (child.text or "").strip() if child is not None else ""


def integer(element: ET.Element, names: tuple[str, ...]) -> int:
    for name in names:
        text = value(element, name)
        if text:
            return int(text)
    return 0


def parse_report(path: Path) -> tuple[list[dict[str, str]], dict[str, int]]:
    root = ET.parse(path).getroot()
    if root.tag != "report":
        raise ValueError(f"unexpected XML root {root.tag!r}")
    findings: list[dict[str, str]] = []
    summary = {"remaining": 0, "waived": 0, "total": 0}
    summary_seen = False
    for table in root.findall(".//Table"):
        table_name = value(table, "Table-name")
        items = table.findall("Table-item") or [table]
        if table_name.endswith("All-Domains"):
            for item in items:
                remaining = integer(item, ("Checks-Count", "Errors"))
                if item.find("Checks-Count") is None:
                    remaining += integer(item, ("Warnings",))
                    remaining += integer(item, ("Info",))
                waived = integer(item, ("Waived",))
                total = integer(item, ("Number-of-Messages",)) or remaining + waived
                summary["remaining"] += remaining
                summary["waived"] += waived
                summary["total"] += total
                summary_seen = True
        for item in items:
            if item.find("Tag") is None or item.find("Message") is None:
                continue
            findings.append(
                {
                    "category": table_name,
                    "severity": value(item, "Severity"),
                    "rule": value(item, "Tag"),
                    "message": value(item, "Message"),
                    "source_location": value(item, "Source-Location"),
                    "instance_module": value(item, "Instance-Module"),
                }
            )
    if not summary_seen:
        summary["remaining"] = len(findings)
        summary["total"] = len(findings)
    return findings, summary


def first_existing(paths: list[Path]) -> Path | None:
    return next((path for path in paths if path.is_file()), None)


def main() -> int:
    args = arguments()
    driver_text = (
        args.driver_log.read_text(encoding="utf-8", errors="replace")
        if args.driver_log.is_file()
        else ""
    )
    artifact_dir = args.artifact_dir or discover_artifact_dir(driver_text)
    report_xml = first_existing(
        [
            artifact_dir / "reports/arm_lint_db/eda/report.xml",
            artifact_dir / "report.xml",
            artifact_dir / "superlint.xml",
        ]
        if artifact_dir
        else []
    )
    waiver_xml = first_existing(
        [artifact_dir / "reports/arm_lint_db/eda/report.waiver.xml"]
        if artifact_dir
        else []
    )
    eda_log = (
        artifact_dir / "reports/arm_lint_db/flow/eda.log"
        if artifact_dir
        else Path("missing-eda.log")
    )
    evidence_text = driver_text
    if eda_log.is_file():
        evidence_text += "\n" + eda_log.read_text(encoding="utf-8", errors="replace")
    infra = INFRA_RE.search(evidence_text)

    findings: list[dict[str, str]] = []
    counts: dict[str, int] = {"remaining": 0, "waived": 0, "total": 0}
    report_error: str | None = None
    if report_xml:
        try:
            findings, counts = parse_report(report_xml)
        except (ET.ParseError, OSError, ValueError) as exc:
            report_error = str(exc)
    else:
        report_error = "expected Arm Lint report.xml is missing"

    expected = re.compile(args.expected_pattern)
    attributed = [
        finding
        for finding in findings
        if expected.search(json.dumps(finding, sort_keys=True))
    ]
    report_complete = report_xml is not None and report_error is None
    attributable = bool(attributed)
    execution_complete = report_complete and args.runner_status == 0 and not infra

    if attributable and execution_complete:
        execution_status = "COMPLETE"
        detection_status = "DETECTED"
        classification = "VALIDATION_DETECTED"
    elif attributable:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "DETECTED"
        classification = "LINT_DETECTED_WITH_INFRA_LIMIT"
    elif execution_complete and counts["remaining"] > 0:
        execution_status = "COMPLETE"
        detection_status = "UNKNOWN"
        classification = "UNATTRIBUTED_LINT_FAILURE"
    elif execution_complete and counts["remaining"] == 0:
        execution_status = "COMPLETE"
        detection_status = "NOT_DETECTED"
        classification = "LINT_CLEAN"
    else:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "LINT_EXECUTION_INCOMPLETE"

    result: dict[str, Any] = {
        "schema_version": 1,
        "wave": "A",
        "branch": "rhel8_lint",
        "candidate_sha": args.candidate,
        "command": "dcs_superlint superlint_8x/configuration_top.yaml",
        "runner_status": args.runner_status,
        "execution_status": execution_status,
        "detection_status": detection_status,
        "classification": classification,
        "expected_pattern_regex": args.expected_pattern,
        "attributable_detection": attributable,
        "failure_count": counts["remaining"],
        "violations": counts,
        "failures": attributed,
        "all_unwaived_findings": findings,
        "report_complete": report_complete,
        "report_error": report_error,
        "infrastructure_signature": infra.group(0) if infra else None,
        "artifacts": {
            "driver_log": str(args.driver_log),
            "artifact_dir": str(artifact_dir) if artifact_dir else None,
            "report_xml": str(report_xml) if report_xml else None,
            "waiver_xml": str(waiver_xml) if waiver_xml else None,
            "eda_log": str(eda_log),
        },
    }
    lines = [
        "RHEL8 WAVE A LINT SUMMARY",
        f"Candidate: {args.candidate}",
        f"Execution status: {execution_status}",
        f"Detection status: {detection_status}",
        f"Classification: {classification}",
        f"Attributable detection: {str(attributable).lower()}",
        f"Unwaived findings: {counts['remaining']}",
        f"Report complete: {str(report_complete).lower()}",
        f"Report XML: {report_xml or 'missing'}",
    ]
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
