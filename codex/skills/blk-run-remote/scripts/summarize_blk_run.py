#!/usr/bin/env python3
"""Create a stable Wave B simulation result from blk_run artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Optional


URL_RE = re.compile(r"https?://[^\s<>\"']+")
SIMU_RES_RE = re.compile(
    r"\*\*\*\s+SIMU-RES\s*:\s*"
    r"(?P<pass>\d+)\s+PASS\s+"
    r"(?P<fail>\d+)\s+FAIL\s+"
    r"(?P<abort>\d+)\s+ABORT\s+"
    r"(?P<skip>\d+)\s+SKIP",
    re.IGNORECASE,
)
FAILURE_FILE_RE = re.compile(
    r"^.+?__(?P<test>.+?)__(?P<regression>sanity|smoke|nightly)__"
    r"s(?P<seed>\d+)__.+_error\.json$"
)
TEST_RESULT_STATUSES = ("PASS", "FAIL", "ABORT", "SKIP")
REQUIRED_CACHE_COLUMNS = {
    "test_id",
    "tests_str",
    "seed",
    "status",
    "substatus",
    "base_file",
    "cmd_line_orig",
}
WORKTREE_ROOT = "/home/tibger01/projects/fornjot"
ATTEMPT_TOKEN_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Collected run root containing sim2/regression.json and sim2/logs_tests.",
    )
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument("--status", required=True, type=int)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--regression", required=True, choices=("sanity", "smoke", "nightly"))
    return parser.parse_args()


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def validate_worktree_identity(
    worktree: str,
    candidate_sha: str,
    regression: str,
) -> tuple[dict[str, Any], list[str]]:
    """Describe and validate an isolated candidate-specific simulation worktree."""

    candidate_sha12 = candidate_sha[:12].lower()
    expected_prefix = (
        f"{WORKTREE_ROOT}/tmp_gpu_blk_run_{candidate_sha12}_{regression}"
    )
    match = re.fullmatch(
        rf"{re.escape(expected_prefix)}(?:_(?P<attempt>{ATTEMPT_TOKEN_PATTERN}))?",
        worktree,
    )
    errors: list[str] = []
    attempt_token: Optional[str] = None
    if match is None:
        errors.append(
            "worktree is not the isolated exact-candidate blk_run path "
            f"{expected_prefix}[_ATTEMPT_TOKEN]: {worktree}"
        )
    else:
        attempt_token = match.group("attempt")
    identity = {
        "schema_version": 1,
        "validated": not errors,
        "path": worktree,
        "workflow": "blk-run",
        "regression": regression,
        "candidate_sha": candidate_sha,
        "candidate_sha12": candidate_sha12,
        "attempt_token": attempt_token,
    }
    return identity, errors


def useful_eap_urls(text: str) -> list[str]:
    """Return human-facing EAP triage/result links, not upload API endpoints."""
    urls: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.lower()
        if not (
            "eap triage link" in line
            or "triage result can be viewed in eap" in line
            or "eapv2 ui result" in line
        ):
            continue
        for url in URL_RE.findall(raw_line):
            url = url.rstrip(".,;:)]}")
            lower_url = url.lower()
            if "eap" not in lower_url:
                continue
            # Session records are implementation detail. Regression and dynamic
            # test records are the useful campaign/triage entry points.
            if "ce_session_schema" in lower_url:
                continue
            urls.append(url)
    return unique(urls)


def terminal_counts(text: str) -> Optional[dict[str, int]]:
    matches = list(SIMU_RES_RE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    return {name: int(match.group(name)) for name in ("pass", "fail", "abort", "skip")}


def require_nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def read_regression_result(
    path: Path, expected_candidate: str
) -> tuple[dict[str, int], str, Optional[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("regression.json is not an object")
    raw_counts = data.get("test_count")
    if not isinstance(raw_counts, dict):
        raise ValueError("regression.json has no test_count object")
    counts = {
        name.lower(): require_nonnegative_int(raw_counts.get(name), f"test_count.{name}")
        for name in ("PASS", "FAIL", "ABORT", "SKIP", "TOTAL")
    }
    categorized_total = sum(counts[name] for name in ("pass", "fail", "abort", "skip"))
    if categorized_total != counts["total"]:
        raise ValueError(
            "regression.json test counts do not add up: "
            f"categorized={categorized_total} total={counts['total']}"
        )
    global_data = data.get("global")
    if not isinstance(global_data, dict) or not isinstance(global_data.get("overall_status"), str):
        raise ValueError("regression.json has no global.overall_status")
    overall_status = global_data["overall_status"].upper()

    recorded_candidate: Optional[str] = None
    configuration = data.get("configuration")
    if isinstance(configuration, dict):
        revision = configuration.get("revision")
        if isinstance(revision, dict) and isinstance(revision.get("revision"), str):
            recorded_candidate = revision["revision"]
            if recorded_candidate != expected_candidate:
                raise ValueError(
                    "regression.json candidate mismatch: "
                    f"expected={expected_candidate} actual={recorded_candidate}"
                )
    return counts, overall_status, recorded_candidate


def result_url_for_test_log(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for url in useful_eap_urls(text):
        if "ce_dynamic_test_schema" in url.lower() and "/result/" in url.lower():
            return url
    return None


def read_failures(logs_dir: Path, regression: str) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[dict[str, Any]] = []
    errors: list[str] = []
    if not logs_dir.is_dir():
        return failures, errors
    for path in sorted(logs_dir.glob("*_error.json")):
        match = FAILURE_FILE_RE.match(path.name)
        if match is None or match.group("regression") != regression:
            errors.append(f"unrecognized failure artifact name: {path.name}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            primary = data["error_log"]["primary_error"]
            if not isinstance(primary, dict):
                raise TypeError("primary_error is not an object")
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            errors.append(f"unreadable failure artifact {path.name}: {exc}")
            continue
        signature = primary.get("log_msg")
        if not isinstance(signature, str) or not signature.strip():
            signature = primary.get("id")
        if not isinstance(signature, str) or not signature.strip():
            signature = "Failure artifact has no primary signature"
        test_log = path.with_name(path.name.removesuffix("_error.json") + ".log")
        failure: dict[str, Any] = {
            # The regression suffix is part of the executable blk_val test
            # identity and must be retained for an exact local replay.
            "test": f"{match.group('test')}__{match.group('regression')}",
            "seed": match.group("seed"),
            "signature": " ".join(signature.split())[:500],
            "severity": primary.get("severity"),
            "category": primary.get("error_cat_0"),
            "source": str(path),
            "eap_url": result_url_for_test_log(test_log),
        }
        failures.append(failure)
    return failures, errors


def read_test_records(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int], list[str], Optional[str]]:
    """Read blk_run's per-test cache through a strictly read-only connection."""
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    schema_version: Optional[str] = None
    observed_statuses: Counter[str] = Counter()

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
        timeout=1.0,
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'simulation_logs'"
        ).fetchone()
        if table is None:
            raise ValueError("cache.sqlite has no simulation_logs table")
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(simulation_logs)")
        }
        missing_columns = sorted(REQUIRED_CACHE_COLUMNS - columns)
        if missing_columns:
            raise ValueError(
                "cache.sqlite simulation_logs is missing columns: "
                + ", ".join(missing_columns)
            )

        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone():
            version_row = connection.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if version_row is not None and isinstance(version_row[0], str):
                schema_version = version_row[0]

        rows = connection.execute(
            """
            SELECT test_id, tests_str, seed, status, substatus, base_file, cmd_line_orig
              FROM simulation_logs
             ORDER BY tests_str COLLATE BINARY, seed, test_id
            """
        )
        for row in rows:
            row_id = row["test_id"]
            name = row["tests_str"]
            seed = row["seed"]
            raw_status = row["status"]
            substatus = row["substatus"]
            remote_base_file = row["base_file"]
            replay_command = row["cmd_line_orig"]

            if not isinstance(name, str) or not name.strip():
                errors.append(f"cache.sqlite test_id={row_id} has no test name")
                name = None
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                errors.append(f"cache.sqlite test_id={row_id} has invalid seed: {seed!r}")
                seed = None
            if not isinstance(raw_status, str) or not raw_status.strip():
                errors.append(f"cache.sqlite test_id={row_id} has no status")
                status = None
            else:
                status = raw_status.upper()
                observed_statuses[status] += 1
                if status not in TEST_RESULT_STATUSES:
                    errors.append(
                        f"cache.sqlite test_id={row_id} has unsupported status: {status}"
                    )
            if substatus is not None and not isinstance(substatus, str):
                errors.append(
                    f"cache.sqlite test_id={row_id} has invalid substatus: {substatus!r}"
                )
                substatus = None
            if (
                not isinstance(remote_base_file, str)
                or not remote_base_file.strip()
                or not remote_base_file.startswith("/")
            ):
                errors.append(
                    f"cache.sqlite test_id={row_id} has no absolute remote base_file"
                )
                remote_base_file = None
            if not isinstance(replay_command, str) or not replay_command.strip():
                errors.append(f"cache.sqlite test_id={row_id} has no replay command")
                replay_command = None

            records.append(
                {
                    "name": name,
                    "seed": seed,
                    "status": status,
                    "substatus": substatus,
                    "remote_base_file": remote_base_file,
                    # Keep blk_run's original command byte-for-byte. It is
                    # evidence and a replay starting point, not a command the
                    # normalizer silently rewrites into a debug recipe.
                    "replay_command": replay_command,
                }
            )
    finally:
        connection.close()

    status_counts = {
        status: observed_statuses.get(status, 0) for status in TEST_RESULT_STATUSES
    }
    return records, status_counts, errors, schema_version


def compare_test_evidence(
    record_count: int,
    status_counts: dict[str, int],
    expected: dict[str, int],
    label: str,
) -> list[str]:
    errors: list[str] = []
    expected_total = expected.get("total")
    if expected_total is None:
        expected_total = sum(expected[name] for name in ("pass", "fail", "abort", "skip"))
    if record_count != expected_total:
        errors.append(
            f"cache.sqlite/{label} record count mismatch: "
            f"cache={record_count} {label}={expected_total}"
        )
    for name in ("pass", "fail", "abort", "skip"):
        observed = status_counts[name.upper()]
        if observed != expected[name]:
            errors.append(
                f"cache.sqlite/{label} {name} mismatch: "
                f"cache={observed} {label}={expected[name]}"
            )
    return errors


def main() -> int:
    args = parse_args()
    try:
        text = args.log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"blk_run summary failed: {exc}", file=sys.stderr)
        return 1

    worktree_identity, worktree_errors = validate_worktree_identity(
        args.worktree, args.candidate_sha, args.regression
    )
    evidence_errors: list[str] = list(worktree_errors)
    terminal = terminal_counts(text)
    canonical: Optional[dict[str, int]] = None
    overall_status: Optional[str] = None
    recorded_candidate: Optional[str] = None
    failures: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    test_status_counts = {status: 0 for status in TEST_RESULT_STATUSES}
    test_evidence_errors: list[str] = []
    cache_loaded = False
    cache_schema_version: Optional[str] = None
    cache_path: Optional[Path] = None
    artifact_texts = [text]

    if args.artifacts_dir is not None:
        regression_path = args.artifacts_dir / "sim2" / "regression.json"
        if regression_path.is_file():
            try:
                canonical, overall_status, recorded_candidate = read_regression_result(
                    regression_path, args.candidate_sha
                )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                evidence_errors.append(f"invalid regression.json: {exc}")
        else:
            evidence_errors.append(f"missing canonical regression result: {regression_path}")

        if terminal is None:
            evidence_errors.append("missing terminal SIMU-RES result in run log")
        if canonical is not None and recorded_candidate is None:
            evidence_errors.append("regression.json does not record the candidate revision")

        logs_dir = args.artifacts_dir / "sim2" / "logs_tests"
        failures, failure_errors = read_failures(logs_dir, args.regression)
        evidence_errors.extend(failure_errors)
        cache_path = logs_dir / "cache.sqlite"
        if cache_path.is_file():
            try:
                (
                    tests,
                    test_status_counts,
                    test_evidence_errors,
                    cache_schema_version,
                ) = read_test_records(cache_path)
                cache_loaded = True
            except (OSError, sqlite3.Error, ValueError) as exc:
                test_evidence_errors.append(f"invalid cache.sqlite: {exc}")
        else:
            test_evidence_errors.append(f"missing per-test result cache: {cache_path}")
        if logs_dir.is_dir():
            for test_log in sorted(logs_dir.glob("*.log")):
                try:
                    artifact_texts.append(test_log.read_text(encoding="utf-8", errors="replace"))
                except OSError as exc:
                    evidence_errors.append(f"unreadable test log {test_log.name}: {exc}")
    else:
        test_evidence_errors.append(
            "artifacts directory is required for per-test cache.sqlite evidence"
        )

    if canonical is not None and terminal is not None:
        for name in ("pass", "fail", "abort", "skip"):
            if canonical[name] != terminal[name]:
                evidence_errors.append(
                    f"terminal/canonical {name} mismatch: "
                    f"terminal={terminal[name]} canonical={canonical[name]}"
                )

    if cache_loaded:
        if canonical is not None:
            test_evidence_errors.extend(
                compare_test_evidence(
                    len(tests), test_status_counts, canonical, "regression.json"
                )
            )
        else:
            test_evidence_errors.append(
                "cache.sqlite cannot be verified without valid regression.json counts"
            )
        if terminal is not None:
            test_evidence_errors.extend(
                compare_test_evidence(len(tests), test_status_counts, terminal, "run log")
            )
        else:
            test_evidence_errors.append(
                "cache.sqlite cannot be verified without terminal run-log counts"
            )
    evidence_errors.extend(test_evidence_errors)

    test_by_identity = {
        (record["name"], str(record["seed"])): record
        for record in tests
        if record["name"] is not None and record["seed"] is not None
    }
    for failure in failures:
        test_record = test_by_identity.get((failure.get("test"), str(failure.get("seed"))))
        if test_record is not None:
            failure.update(
                {
                    "status": test_record["status"],
                    "substatus": test_record["substatus"],
                    "remote_base_file": test_record["remote_base_file"],
                    "replay_command": test_record["replay_command"],
                }
            )

    verdict = canonical or terminal
    verdict_failures = 0 if verdict is None else verdict["fail"] + verdict["abort"]
    failure_count = max(verdict_failures, len(failures))
    failure_details_complete = verdict_failures == len(failures)
    if args.artifacts_dir is not None and canonical is not None and not failure_details_complete:
        evidence_errors.append(
            "canonical/terminal failure count does not match detailed artifacts: "
            f"verdict={verdict_failures} detailed={len(failures)}"
        )
    if args.status != 0 and failure_count == 0:
        failure_count = 1
        failures.append(
            {
                "test": None,
                "seed": None,
                "signature": "blk_run exited nonzero without a captured test failure",
                "severity": None,
                "category": "Orchestration",
                "source": str(args.log),
                "eap_url": None,
            }
        )

    if canonical is not None and overall_status == "PASS" and verdict_failures != 0:
        evidence_errors.append("regression overall_status PASS conflicts with nonzero FAIL/ABORT counts")
    if canonical is not None and overall_status != "PASS" and verdict_failures == 0:
        evidence_errors.append(
            f"regression overall_status {overall_status} conflicts with zero FAIL/ABORT counts"
        )

    if evidence_errors:
        classification = "ERROR"
    elif args.status != 0 or failure_count != 0 or (overall_status not in (None, "PASS")):
        classification = "FAIL"
    else:
        classification = "PASS"

    urls = unique(url for contents in artifact_texts for url in useful_eap_urls(contents))
    for failure in failures:
        eap_url = failure.get("eap_url")
        if isinstance(eap_url, str):
            urls = unique([*urls, eap_url])

    command = (
        f"blk_run --build-clean --{args.regression} --set-lsf-mem-limit 12000 "
        "--no-bsub --no-bsub-build --worker=local --max-jobs 2"
    )
    result = {
        "schema_version": 1,
        "wave": "B",
        "branch": "simulation",
        "classification": classification,
        "candidate_sha": args.candidate_sha,
        "recorded_candidate_sha": recorded_candidate,
        "host": args.host,
        "worktree": args.worktree,
        "worktree_identity": worktree_identity,
        "regression": args.regression,
        "command": command,
        "command_status": args.status,
        "failure_count": failure_count,
        "detailed_failure_count": len(failures),
        "failure_details_complete": failure_details_complete,
        "cex_count": 0,
        "terminal_counts": terminal,
        "regression_counts": canonical,
        "regression_overall_status": overall_status,
        "evidence_errors": evidence_errors,
        "test_records_verified": cache_loaded and not test_evidence_errors,
        "test_evidence": {
            "source": str(cache_path) if cache_path is not None else None,
            "schema_version": cache_schema_version,
            "record_count": len(tests),
            "status_counts": test_status_counts,
            "verified": cache_loaded and not test_evidence_errors,
            "evidence_errors": test_evidence_errors,
        },
        "eap_triage_urls": urls,
        "tests": tests,
        "failures": failures,
        "source_log": str(args.log),
        "artifacts_dir": str(args.artifacts_dir) if args.artifacts_dir is not None else None,
    }

    lines = [
        "WAVE B SIMULATION SUMMARY",
        f"Classification: {classification}",
        f"Candidate: {args.candidate_sha}",
        f"Host: {args.host}",
        f"Regression: {args.regression}",
        f"Command status: {args.status}",
        f"Failures: {failure_count} (detailed records: {len(failures)})",
        f"Failure details complete: {failure_details_complete}",
        f"Terminal counts: {terminal or 'UNAVAILABLE'}",
        f"Canonical counts: {canonical or 'UNAVAILABLE'}",
        f"Canonical status: {overall_status or 'UNAVAILABLE'}",
        f"Per-test cache records: {len(tests)}",
        f"Per-test cache status counts: {test_status_counts}",
        f"Per-test cache verified: {cache_loaded and not test_evidence_errors}",
        f"EAP triage/result URLs: {len(urls)}",
        f"Worktree retained: {args.worktree}",
        "Worktree attempt token: "
        f"{worktree_identity['attempt_token'] or 'NONE'}",
    ]
    for error in evidence_errors:
        lines.append(f"  EVIDENCE_ERROR: {error}")
    for url in urls:
        lines.append(f"  EAP: {url}")
    for test in tests:
        lines.append(
            "  TEST: name={name} seed={seed} status={status} substatus={substatus} "
            "remote_base_file={base_file} replay={replay}".format(
                name=test.get("name") or "UNKNOWN",
                seed=test.get("seed") if test.get("seed") is not None else "UNKNOWN",
                status=test.get("status") or "UNKNOWN",
                substatus=test.get("substatus") or "UNAVAILABLE",
                base_file=test.get("remote_base_file") or "UNAVAILABLE",
                replay=test.get("replay_command") or "UNAVAILABLE",
            )
        )
    for failure in failures:
        lines.append(
            "  FAILURE: test={test} seed={seed} signature={signature} eap={eap}".format(
                test=failure.get("test") or "UNKNOWN",
                seed=failure.get("seed") or "UNKNOWN",
                signature=failure.get("signature") or "UNKNOWN",
                eap=failure.get("eap_url") or "UNAVAILABLE",
            )
        )

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"SIMULATION_SUMMARY_JSON={args.json_output}")
    print(f"SIMULATION_SUMMARY_REPORT={args.text_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
