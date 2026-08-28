#!/usr/bin/env python3
"""Normalize an AACR invocation into the Wave A detector schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-json", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--text-artifact", required=True, type=Path)
    parser.add_argument("--html-dir", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument("--command-status", required=True, type=int)
    parser.add_argument("--base", required=True)
    parser.add_argument("--tip", required=True)
    return parser.parse_args()


def find_finding_list(value: Any) -> list[Any] | None:
    if not isinstance(value, dict):
        return None
    for key in ("errors", "issues", "findings"):
        candidate = value.get(key)
        if isinstance(candidate, list):
            return candidate
    # Current AACR range JSON wraps its error list as
    # {"findings": {"errors": [...]}}.  Recurse through that wrapper instead
    # of falling back to a log-only count and losing the finding evidence.
    for key in ("analysis", "result", "results", "data", "output", "findings"):
        candidate = find_finding_list(value.get(key))
        if candidate is not None:
            return candidate
    return None


def normalize_failure(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        normalized = {}
        for key in ("title", "message", "description", "file", "path", "line", "severity"):
            if key in item:
                normalized[key] = item[key]
        current_schema = {
            "error_message": "message",
            "file_name": "file",
            "line_number": "line",
            "priority": "severity",
            "confidence_score": "confidence",
            "suggested_fix": "suggested_fix",
        }
        for source, destination in current_schema.items():
            if source in item:
                normalized[destination] = item[source]
        return normalized or {"raw": item}
    return {"message": str(item)}


def main() -> int:
    args = parse_args()
    log_text = ""
    raw: Any = None
    raw_error: str | None = None
    try:
        log_text = args.log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raw_error = f"cannot read AACR log: {exc}"

    if args.raw_json.is_file():
        try:
            raw = json.loads(args.raw_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raw_error = f"cannot parse AACR JSON: {exc}"

    findings = find_finding_list(raw)
    count: int | None = len(findings) if findings is not None else None
    if count is None:
        matches = re.findall(r"\b(\d+)\s+issues?\s+found\b", log_text, flags=re.IGNORECASE)
        if matches:
            count = int(matches[-1])
            findings = []

    run_url_match = re.search(r'https://aacr\.aws\.arm\.com/run/[A-Za-z0-9-]+', log_text)
    run_url = run_url_match.group(0) if run_url_match else None

    if args.command_status != 0:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "AACR_EXECUTION_FAILED"
    elif count is None:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "AACR_RESULT_UNREADABLE"
    elif count > 0:
        execution_status = "COMPLETE"
        detection_status = "DETECTED"
        classification = "FINDINGS_REPORTED"
    else:
        execution_status = "COMPLETE"
        detection_status = "NOT_DETECTED"
        classification = "NO_FINDINGS"

    normalized_findings = [normalize_failure(item) for item in (findings or [])]
    result = {
        "schema_version": 1,
        "wave": "A",
        "branch": "aacr",
        "candidate_sha": args.tip,
        "base_sha": args.base,
        "tip_sha": args.tip,
        "range": f"{args.base}..{args.tip}",
        "command": f"aacr-cli --target-sha {args.base}..{args.tip} --deep-analysis-codex --no-caching",
        "command_status": args.command_status,
        "execution_status": execution_status,
        "detection_status": detection_status,
        "classification": classification,
        "failure_count": count,
        "failures": normalized_findings,
        "run_url": run_url,
        "artifacts": {
            "log": str(args.log),
            "raw_json": str(args.raw_json),
            "text": str(args.text_artifact),
            "html_dir": str(args.html_dir),
        },
        "parse_error": raw_error,
    }
    lines = [
        "AACR RANGE SUMMARY",
        f"Range: {args.base}..{args.tip}",
        f"Execution status: {execution_status}",
        f"Detection status: {detection_status}",
        f"Classification: {classification}",
        f"Findings: {count if count is not None else 'unknown'}",
        f"Command status: {args.command_status}",
        f"Run URL: {run_url or 'not reported'}",
        f"Log: {args.log}",
    ]
    if raw_error:
        lines.append(f"Parse note: {raw_error}")

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
