#!/usr/bin/env python3
"""Create stable aggregate assertion and cover totals from an FTS FPV report."""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, Tuple


ASSERT_PASS_KEYS = (
    "proven",
    "bounded_proven_auto",
    "bounded_proven_user",
    "marked_proven",
)
ASSERT_FAIL_KEYS = ("cex", "ar_cex", "error")
ASSERT_UNRESOLVED_KEYS = ("undetermined", "unprocessed", "processing")
COVER_HIT_KEYS = ("covered", "ar_covered")
COVER_UNREACHABLE_KEYS = ("unreachable", "bounded_unreachable_user")
COVER_UNRESOLVED_KEYS = ("undetermined", "unprocessed", "processing", "error")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--ftrun-status", required=True, type=int)
    return parser.parse_args()


def require_counts(group: Any, label: str) -> Dict[str, int]:
    if not isinstance(group, dict):
        raise ValueError(f"missing {label} summary")
    counts = {}  # type: Dict[str, int]
    for key, value in group.items():
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"invalid {label}.{key} count: {value!r}")
        counts[key] = value
    if "total" not in counts:
        raise ValueError(f"missing {label}.total")
    return counts


def total(counts: Dict[str, int], keys: Tuple[str, ...]) -> int:
    return sum(counts.get(key, 0) for key in keys)


def main() -> int:
    args = parse_args()
    try:
        report = json.loads(args.input.read_text(encoding="utf-8"))
        summary = report["fpv"]["summary"]
        asserts = require_counts(summary.get("asserts"), "asserts")
        covers = require_counts(summary.get("covers"), "covers")
        assumes = require_counts(summary.get("assumes"), "assumes")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"FPV property summary failed: {exc}", file=sys.stderr)
        return 1

    assert_passed = total(asserts, ASSERT_PASS_KEYS)
    assert_failed = total(asserts, ASSERT_FAIL_KEYS)
    assert_unresolved = total(asserts, ASSERT_UNRESOLVED_KEYS)
    cover_hit = total(covers, COVER_HIT_KEYS)
    cover_unreachable = total(covers, COVER_UNREACHABLE_KEYS)
    cover_unresolved = total(covers, COVER_UNRESOLVED_KEYS)

    if assert_failed:
        classification = "ASSERTION_FAILURE"
    elif assert_unresolved:
        classification = "INCOMPLETE"
    else:
        classification = "ASSERTIONS_PASS"

    result = {
        "classification": classification,
        "ftrun_status": args.ftrun_status,
        "source": str(args.input),
        "assertions": {
            "total": asserts["total"],
            "passed": assert_passed,
            "failed": assert_failed,
            "unresolved": assert_unresolved,
            "status_counts": asserts,
        },
        "covers": {
            "total": covers["total"],
            "covered": cover_hit,
            "unreachable": cover_unreachable,
            "unresolved": cover_unresolved,
            "status_counts": covers,
        },
        "assumptions": assumes,
    }

    lines = [
        "FPV PROPERTY SUMMARY",
        f"Classification: {classification}",
        f"FTRun status: {args.ftrun_status}",
        f"Assertions: total={asserts['total']} passed={assert_passed} "
        f"failed={assert_failed} unresolved={assert_unresolved}",
        "  " + " ".join(f"{key}={asserts[key]}" for key in sorted(asserts)),
        f"Covers: total={covers['total']} covered={cover_hit} "
        f"unreachable={cover_unreachable} unresolved={cover_unresolved}",
        "  " + " ".join(f"{key}={covers[key]}" for key in sorted(covers)),
        f"Assumptions: total={assumes['total']}",
        "  " + " ".join(f"{key}={assumes[key]}" for key in sorted(assumes)),
        f"Source: {args.input}",
    ]

    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"FPV_REPORT_TEXT={args.text_output}")
    print(f"FPV_REPORT_JSON={args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
