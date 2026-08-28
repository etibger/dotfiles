#!/usr/bin/env python3
"""Normalize one tb_tex fixed-seed sanity result for the Wave A gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


INFRA_PATTERNS = re.compile(
    r"licen[cs]e.*(denied|failed|unavailable)|no space left|out of memory|"
    r"killed by signal|sigkill|command not found|failed to (compile|elaborate)",
    flags=re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-log", required=True, type=Path)
    parser.add_argument("--error-json", required=True, type=Path)
    parser.add_argument("--driver-log", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument("--command-status", required=True, type=int)
    parser.add_argument("--blk-status", required=True, type=int)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-pattern", default="")
    return parser.parse_args()


def load_error(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.is_file():
        return [], None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], str(exc)
    error_log = payload.get("error_log", {}) if isinstance(payload, dict) else {}
    failures: list[dict[str, Any]] = []
    if isinstance(error_log, dict):
        primary = error_log.get("primary_error")
        if isinstance(primary, dict):
            failures.append(primary)
        messages = error_log.get("msg")
        if isinstance(messages, list):
            for item in messages:
                if isinstance(item, dict) and item not in failures:
                    failures.append(item)
    return failures, None


def main() -> int:
    args = parse_args()
    test_log = args.test_log.read_text(encoding="utf-8", errors="replace") if args.test_log.is_file() else ""
    driver_log = args.driver_log.read_text(encoding="utf-8", errors="replace") if args.driver_log.is_file() else ""
    combined = test_log + "\n" + driver_log
    failures, error_parse_error = load_error(args.error_json)
    failure_text = json.dumps(failures, sort_keys=True)
    evidence_text = combined + "\n" + failure_text
    expected_re = re.compile(args.expected_pattern) if args.expected_pattern else None

    has_pass = "** BLK TEST PASS" in test_log
    has_fail = bool(re.search(r"\*\* BLK TEST (?:FAIL|FATAL)\b", test_log))
    has_skip = "** BLK TEST SKIP" in test_log
    infra_signature = INFRA_PATTERNS.search(combined)
    attributable = bool(
        has_fail
        and not infra_signature
        and (expected_re is None or expected_re.search(evidence_text))
    )

    if attributable:
        execution_status = "COMPLETE"
        detection_status = "DETECTED"
        classification = "VALIDATION_DETECTED"
    elif has_fail and not infra_signature:
        execution_status = "COMPLETE"
        detection_status = "UNKNOWN"
        classification = "UNATTRIBUTED_TEST_FAILURE"
    elif has_pass and args.command_status == 0 and args.blk_status == 0:
        execution_status = "COMPLETE"
        detection_status = "NOT_DETECTED"
        classification = "TEST_PASS"
    elif has_skip:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "TEST_SKIPPED"
    elif infra_signature:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "SIMULATION_INFRASTRUCTURE_FAILURE"
    else:
        execution_status = "INFRASTRUCTURE_ERROR"
        detection_status = "UNKNOWN"
        classification = "RESULT_MISSING_OR_INCONSISTENT"

    result = {
        "schema_version": 1,
        "wave": "A",
        "branch": "simulation",
        "candidate_sha": args.candidate,
        "test": "test_mix_all_tiny__sanity",
        "seed": 1,
        "build_option": "8x_mtcs",
        "dfs": "batch",
        "waves": False,
        "uvm_high": False,
        "command": "blk_val --build-clean --storage-services elk=n --set-lsf-mem-limit 12000 --no-bsub --no-bsub-build --dfs batch --bo 8x_mtcs --seed 1 --plusarg '+tex_trace_shim +tex_checkers_enable=all' test_mix_all_tiny__sanity",
        "command_status": args.command_status,
        "blk_status": args.blk_status,
        "execution_status": execution_status,
        "detection_status": detection_status,
        "classification": classification,
        "expected_pattern_regex": args.expected_pattern or None,
        "attributable_detection": attributable,
        "failure_count": len(failures) if failures else (1 if has_fail else 0),
        "failures": failures,
        "artifacts": {
            "test_log": str(args.test_log),
            "error_json": str(args.error_json),
            "driver_log": str(args.driver_log),
        },
        "error_json_parse_error": error_parse_error,
        "infrastructure_signature": infra_signature.group(0) if infra_signature else None,
    }
    lines = [
        "TB_TEX WAVE A SANITY SUMMARY",
        f"Candidate: {args.candidate}",
        "Test: test_mix_all_tiny__sanity seed=1 bo=8x_mtcs dfs=batch waves=off",
        f"Execution status: {execution_status}",
        f"Detection status: {detection_status}",
        f"Classification: {classification}",
        f"Attributable detection: {str(attributable).lower()}",
        f"Command status: {args.command_status}",
        f"blk_status: {args.blk_status}",
        f"Primary log: {args.test_log}",
    ]
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
