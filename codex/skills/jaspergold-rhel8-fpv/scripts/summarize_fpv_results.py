#!/usr/bin/env python3
"""Create stable aggregate assertion and cover totals from an FTS FPV report."""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Optional, Tuple


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
CONCURRENCY_MARKER_RE = re.compile(
    r"LOCAL_FPV_CONCURRENCY:\s+max_local_jobs=(\d+)\s+"
    r"per_engine_max_local_jobs=(\d+)"
)
PROOF_THREAD_RE = re.compile(r"Settings used for proof thread\s+([^:]+):")
PROOF_SETTING_RE = re.compile(
    r"^\s*(?:jg:\s*)?"
    r"(proofgrid_mode|proofgrid_max_jobs|proofgrid_per_engine_max_jobs|"
    r"max engine jobs)\s*=\s*(.*?)\s*$"
)
MAX_ENGINE_CAP_RE = re.compile(r"\(max\s+(\d+)\)")
PROOFGRID_USABLE_LEVEL_RE = re.compile(r"ProofGrid usable level:\s+(\d+)")
PROCESS_DETAILS_HEADER = (
    "epoch\tpid\tppid\tstate\tpcpu\tetimes\tcomm\trole\targs"
)
WORKTREE_ROOT = "/home/tibger01/projects/fornjot"
ATTEMPT_TOKEN_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--ftrun-status", required=True, type=int)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--jobs", required=True, type=int)
    parser.add_argument("--proof-limit", required=True)
    parser.add_argument("--cex-save-limit", required=True, type=int)
    parser.add_argument("--run-log", required=True, type=Path)
    parser.add_argument("--process-samples", required=True, type=Path)
    parser.add_argument("--process-details", type=Path)
    return parser.parse_args()


def validate_worktree_identity(
    worktree: str,
    candidate_sha: str,
) -> tuple[Dict[str, Any], list[str]]:
    """Describe and validate an isolated candidate-specific FPV worktree."""

    candidate_sha12 = candidate_sha[:12].lower()
    expected_prefix = f"{WORKTREE_ROOT}/tmp_gpu_fpv_run_{candidate_sha12}"
    match = re.fullmatch(
        rf"{re.escape(expected_prefix)}(?:_(?P<attempt>{ATTEMPT_TOKEN_PATTERN}))?",
        worktree,
    )
    errors: list[str] = []
    attempt_token: Optional[str] = None
    if match is None:
        errors.append(
            "worktree is not the isolated exact-candidate FPV path "
            f"{expected_prefix}[_ATTEMPT_TOKEN]: {worktree}"
        )
    else:
        attempt_token = match.group("attempt")
    identity = {
        "schema_version": 1,
        "validated": not errors,
        "path": worktree,
        "workflow": "fpv",
        "candidate_sha": candidate_sha,
        "candidate_sha12": candidate_sha12,
        "attempt_token": attempt_token,
    }
    return identity, errors


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
    categorized_total = sum(value for key, value in counts.items() if key != "total")
    if categorized_total != counts["total"]:
        raise ValueError(
            f"{label} status counts do not add up: "
            f"categorized={categorized_total} total={counts['total']}"
        )
    return counts


def total(counts: Dict[str, int], keys: Tuple[str, ...]) -> int:
    return sum(counts.get(key, 0) for key in keys)


def failing_properties(tasks: Any) -> list[Dict[str, Any]]:
    failures = []  # type: list[Dict[str, Any]]
    if not isinstance(tasks, dict):
        return failures
    for task_name, task in tasks.items():
        if not isinstance(task, dict) or not isinstance(task.get("results"), list):
            continue
        for prop in task["results"]:
            if not isinstance(prop, dict):
                continue
            if prop.get("type") != "assert" or prop.get("status") not in ASSERT_FAIL_KEYS:
                continue
            failures.append(
                {
                    "task": task_name,
                    "name": prop.get("name"),
                    "status": prop.get("status"),
                    "location": prop.get("location"),
                    "bound": prop.get("bound"),
                    "engine": prop.get("engine"),
                }
            )
    return failures


def _integer_setting(value: Any) -> Optional[int]:
    if not isinstance(value, str) or not value.isdigit():
        return None
    return int(value)


def _max_engine_cap(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    match = MAX_ENGINE_CAP_RE.search(value)
    if match:
        return int(match.group(1))
    return int(value) if value.isdigit() else None


def _turnover_correlated(run_log: str, epoch: int, requested_jobs: int) -> bool:
    """Recognize a one-second retiring/replacement engine overlap."""

    sample_time = datetime.fromtimestamp(epoch)
    stamps = {
        (sample_time + timedelta(seconds=offset)).strftime("%d/%m %H:%M:%S")
        for offset in (-1, 0, 1)
    }
    nearby = [line for line in run_log.splitlines() if any(stamp in line for stamp in stamps)]
    shutdown_seen = any(
        marker in line
        for line in nearby
        for marker in (
            "Requesting engine job to terminate",
            "Stopped processing property",
            "Exited with Success",
        )
    )
    replacement_seen = any("Proofgrid shell started" in line for line in nearby)
    bounded_level_seen = any(
        f"ProofGrid usable level: {requested_jobs}" in line for line in nearby
    )
    return shutdown_seen and replacement_seen and bounded_level_seen


def _isolated_overage(records: list[Dict[str, int]], index: int, requested_jobs: int) -> bool:
    previous_ok = index == 0 or records[index - 1]["count"] <= requested_jobs
    next_ok = index == len(records) - 1 or records[index + 1]["count"] <= requested_jobs
    return previous_ok and next_ok


def _parse_process_details(
    content: str,
    errors: list[str],
) -> Dict[int, Dict[str, int]]:
    """Return canonical per-epoch JG worker counts.

    Older samplers labeled every .proofgrid_*.bs argv as `proofgrid_engine`.
    ProofMaster cache workers use that argv shape too, so Linux `comm` is the
    authoritative discriminator for jg_engineCache.  Accept the old recorded
    role for those rows so retained evidence can be normalized correctly.
    """

    lines = content.splitlines()
    if not lines or lines[0] != PROCESS_DETAILS_HEADER:
        errors.append("invalid or missing proof-process detail header")
        return {}
    per_epoch = {}  # type: Dict[int, Dict[str, int]]
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        fields = line.split("\t", 8)
        if len(fields) != 9:
            errors.append(f"invalid proof-process detail at line {line_number}")
            continue
        epoch, pid, ppid, _state, _pcpu, etimes, comm, role, args = fields
        if (
            not epoch.isdigit()
            or not pid.isdigit()
            or not ppid.isdigit()
            or not etimes.isdigit()
            or role
            not in (
                "ordinary_proof_engine",
                "proofgrid_engine",
                "proof_cache_worker",
                "controller_or_other",
            )
        ):
            errors.append(f"invalid proof-process detail at line {line_number}")
            continue

        if comm == "jg_engineCache":
            if role not in ("proof_cache_worker", "proofgrid_engine"):
                errors.append(
                    "jg_engineCache row has an incompatible recorded role at line "
                    f"{line_number}: {role}"
                )
            canonical_role = "proof_cache_worker"
        elif re.search(r"\.proofgrid_[^ ]*\.bs(?:\s|$)", args):
            if role not in ("ordinary_proof_engine", "proofgrid_engine"):
                errors.append(
                    "ProofGrid argv row has an incompatible recorded role at line "
                    f"{line_number}: {role}"
                )
            canonical_role = "ordinary_proof_engine"
        else:
            if role != "controller_or_other":
                errors.append(
                    "non-ProofGrid helper row has an incompatible recorded role at line "
                    f"{line_number}: {role}"
                )
            canonical_role = "controller_or_other"

        counts = per_epoch.setdefault(
            int(epoch),
            {
                "ordinary_proof_engine": 0,
                "proof_cache_worker": 0,
                "controller_or_other": 0,
            },
        )
        counts[canonical_role] += 1
    return per_epoch


def verify_concurrency(
    run_log: str,
    process_samples: str,
    process_details: Optional[str],
    requested_jobs: int,
    run_log_source: Path,
    process_samples_source: Path,
    process_details_source: Optional[Path],
) -> Dict[str, Any]:
    """Verify proof-job slots; retain raw OS process counts as diagnostics."""

    errors = []  # type: list[str]
    marker_matches = list(CONCURRENCY_MARKER_RE.finditer(run_log))
    marker = marker_matches[-1] if marker_matches else None
    configured_jobs = int(marker.group(1)) if marker else None
    configured_per_engine = int(marker.group(2)) if marker else None
    marker_offset = marker.start() if marker else -1

    if marker is None:
        errors.append("missing LOCAL_FPV_CONCURRENCY marker")
    else:
        if configured_jobs != requested_jobs:
            errors.append(
                "local-cap marker does not match requested jobs "
                f"(requested={requested_jobs} marker={configured_jobs})"
            )
        if not configured_per_engine or configured_per_engine > requested_jobs:
            errors.append(
                "invalid per-engine local cap in marker "
                f"(requested={requested_jobs} marker={configured_per_engine})"
            )

    blocks = []  # type: list[Dict[str, Any]]
    current = None  # type: Optional[Dict[str, Any]]
    line_offset = 0
    for line in run_log.splitlines(keepends=True):
        current_offset = line_offset
        line_offset += len(line)
        header = PROOF_THREAD_RE.search(line)
        if header:
            if current is not None:
                blocks.append(current)
            current = {
                "thread": header.group(1).strip(),
                "offset": current_offset,
                "settings": {},
            }
            continue
        if current is None:
            continue
        setting = PROOF_SETTING_RE.match(line)
        if setting:
            current["settings"][setting.group(1)] = setting.group(2)
    if current is not None:
        blocks.append(current)

    post_marker_blocks = [block for block in blocks if block["offset"] > marker_offset]
    observed = []  # type: list[Dict[str, Any]]
    exact_cap_seen = False
    for block in post_marker_blocks:
        settings = block["settings"]
        mode = settings.get("proofgrid_mode")
        max_jobs = _integer_setting(settings.get("proofgrid_max_jobs"))
        per_engine = _integer_setting(settings.get("proofgrid_per_engine_max_jobs"))
        engine_cap = _max_engine_cap(settings.get("max engine jobs"))
        observed.append(
            {
                "thread": block["thread"],
                "proofgrid_mode": mode,
                "proofgrid_max_jobs": max_jobs,
                "proofgrid_per_engine_max_jobs": per_engine,
                "max_engine_jobs_cap": engine_cap,
            }
        )

        label = f"proof thread {block['thread']}"
        if mode != "local":
            errors.append(f"{label} is not local (mode={mode or 'MISSING'})")
        if max_jobs is None or max_jobs < 1 or max_jobs > requested_jobs:
            errors.append(
                f"{label} lacks a bounded proofgrid_max_jobs <= {requested_jobs} "
                f"(effective={max_jobs if max_jobs is not None else 'MISSING'})"
            )
        if per_engine is None or per_engine < 1 or per_engine > requested_jobs:
            errors.append(
                f"{label} lacks a bounded per-engine cap <= {requested_jobs} "
                f"(effective={per_engine if per_engine is not None else 'MISSING'})"
            )
        if engine_cap is None or engine_cap < 1 or engine_cap > requested_jobs:
            errors.append(
                f"{label} has no effective max-engine ceiling <= {requested_jobs} "
                f"(effective={engine_cap if engine_cap is not None else 'MISSING'})"
            )
        if (
            mode == "local"
            and max_jobs == requested_jobs
            and engine_cap == requested_jobs
        ):
            exact_cap_seen = True

    if not post_marker_blocks:
        errors.append("no post-marker IPF031 proof-thread settings found")
    elif not exact_cap_seen:
        errors.append(
            f"no IPF031 proof thread confirms the requested local cap of {requested_jobs}"
        )

    usable_levels = [
        int(value)
        for value in PROOFGRID_USABLE_LEVEL_RE.findall(run_log[marker_offset + 1 :])
    ]
    positive_usable_levels = [value for value in usable_levels if value > 0]
    usable_level_peak = max(positive_usable_levels, default=None)
    if not positive_usable_levels:
        errors.append("no positive post-marker ProofGrid usable level was observed")
    elif usable_level_peak is not None and usable_level_peak > requested_jobs:
        errors.append(
            "ProofGrid usable level exceeds requested proof-job slots "
            f"(requested={requested_jobs} peak={usable_level_peak})"
        )

    slot_errors = list(errors)
    process_records = []  # type: list[Dict[str, int]]
    for line_number, line in enumerate(process_samples.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if (
            len(fields) != 2
            or not fields[0].isdigit()
            or not fields[1].isdigit()
        ):
            errors.append(f"invalid proof-process sample at line {line_number}")
            continue
        process_records.append(
            {"epoch": int(fields[0]), "count": int(fields[1])}
        )
    process_counts = [record["count"] for record in process_records]
    positive_process_samples = sum(count > 0 for count in process_counts)
    peak_processes = max(process_counts, default=0)
    if not positive_process_samples:
        errors.append("no run-scoped jg_proof process was observed")

    detail_counts = None  # type: Optional[Dict[int, Dict[str, int]]]
    peak_ordinary_engines = None  # type: Optional[int]
    peak_cache_workers = None  # type: Optional[int]
    peak_controller_or_other = None  # type: Optional[int]
    ordinary_engine_peak_within_limit = None  # type: Optional[bool]
    if process_details is not None:
        detail_counts = _parse_process_details(process_details, errors)
        sample_epochs = {record["epoch"] for record in process_records}
        for epoch in detail_counts:
            if epoch not in sample_epochs:
                errors.append(f"proof-process detail epoch {epoch} has no count sample")
        for record in process_records:
            counts = detail_counts.get(
                record["epoch"],
                {
                    "ordinary_proof_engine": 0,
                    "proof_cache_worker": 0,
                    "controller_or_other": 0,
                },
            )
            detailed_total = sum(counts.values())
            if detailed_total != record["count"]:
                errors.append(
                    "proof-process count/detail mismatch at epoch "
                    f"{record['epoch']} (count={record['count']} detail={detailed_total})"
                )
        peak_ordinary_engines = max(
            (counts["ordinary_proof_engine"] for counts in detail_counts.values()),
            default=0,
        )
        peak_cache_workers = max(
            (counts["proof_cache_worker"] for counts in detail_counts.values()),
            default=0,
        )
        peak_controller_or_other = max(
            (counts["controller_or_other"] for counts in detail_counts.values()),
            default=0,
        )
        ordinary_engine_peak_within_limit = peak_ordinary_engines <= requested_jobs
        if not ordinary_engine_peak_within_limit:
            ordinary_peak_error = (
                "ordinary proof-engine process peak exceeds requested proof-job "
                f"slots (requested={requested_jobs} peak={peak_ordinary_engines})"
            )
            errors.append(ordinary_peak_error)
            slot_errors.append(ordinary_peak_error)

    overage_indexes = [
        index
        for index, record in enumerate(process_records)
        if record["count"] > requested_jobs
    ]
    turnover_correlated = False
    raw_peak_classification = "NOT_OBSERVED"
    if positive_process_samples:
        raw_peak_classification = "WITHIN_PROOF_JOB_CAP"
    if detail_counts is not None:
        # Detailed `comm` evidence makes the raw total diagnostic rather than
        # a proof-slot limit.  Cache and controller helpers may increase that
        # total; only ordinary proof engines are constrained by --jobs.
        if ordinary_engine_peak_within_limit is False:
            raw_peak_classification = "ORDINARY_PROOF_ENGINE_EXCESS"
        elif overage_indexes:
            overage_counts = [
                detail_counts.get(
                    process_records[index]["epoch"],
                    {
                        "ordinary_proof_engine": 0,
                        "proof_cache_worker": 0,
                        "controller_or_other": 0,
                    },
                )
                for index in overage_indexes
            ]
            if any(counts["proof_cache_worker"] for counts in overage_counts):
                raw_peak_classification = "PROOF_CACHE_WORKER_OVERHEAD"
            elif any(counts["controller_or_other"] for counts in overage_counts):
                raw_peak_classification = "CONTROLLER_OR_OTHER_OVERHEAD"
            else:
                raw_peak_classification = "UNCLASSIFIED_RAW_OVERHEAD"
    elif peak_processes > requested_jobs + 1:
        raw_peak_classification = "ANOMALOUS_EXCESS"
        errors.append(
            "raw run-scoped jg_proof peak exceeds conservative job-plus-one envelope "
            f"(requested={requested_jobs} peak={peak_processes})"
        )
    elif overage_indexes:
        index = overage_indexes[0]
        record = process_records[index]
        turnover_correlated = (
            len(overage_indexes) == 1
            and record["count"] == requested_jobs + 1
            and _isolated_overage(process_records, index, requested_jobs)
            and _turnover_correlated(run_log, record["epoch"], requested_jobs)
        )
        if turnover_correlated:
            raw_peak_classification = "TRANSIENT_TURNOVER_OVERLAP_LEGACY"
        else:
            raw_peak_classification = "ANOMALOUS_EXCESS"
            errors.append(
                "legacy raw jg_proof overage is not a single isolated, "
                "log-correlated engine turnover"
            )

    # Keep ordering stable while removing duplicate diagnostics from repeated
    # uncapped proof threads.
    errors = list(dict.fromkeys(errors))
    effective_jobs = max(
        (
            item["proofgrid_max_jobs"]
            for item in observed
            if isinstance(item["proofgrid_max_jobs"], int)
        ),
        default=None,
    )
    effective_per_engine = max(
        (
            item["proofgrid_per_engine_max_jobs"]
            for item in observed
            if isinstance(item["proofgrid_per_engine_max_jobs"], int)
        ),
        default=None,
    )
    return {
        "verified": not errors,
        "status": "VERIFIED" if not errors else "UNVERIFIED",
        "requested_jobs": requested_jobs,
        "requested_proof_job_slots": requested_jobs,
        "configured_max_local_jobs": configured_jobs,
        "configured_per_engine_max_local_jobs": configured_per_engine,
        "effective_max_jobs": effective_jobs,
        "effective_proof_job_slots": effective_jobs,
        "effective_per_engine_max_jobs": effective_per_engine,
        "proofgrid_mode": "local" if exact_cap_seen else None,
        "proof_threads_observed": len(post_marker_blocks),
        "proof_job_slot_cap_verified": not slot_errors,
        "verification_basis": (
            "WRAPPER_MARKER_IPF031_PROOFGRID_USABLE_LEVEL_AND_"
            "ORDINARY_PROOF_ENGINE_PEAK"
        ),
        "proofgrid_usable_levels": usable_levels,
        "proofgrid_usable_level_peak": usable_level_peak,
        "generic_auto_reset_seen": bool(
            re.search(r"set_proofgrid_max_jobs\s+0(?:\s|$)", run_log[marker_offset + 1 :])
        ),
        "process_sample_count": len(process_counts),
        "positive_process_samples": positive_process_samples,
        "peak_local_jg_proof_processes": (
            peak_processes if positive_process_samples else None
        ),
        "peak_run_scoped_jg_proof_processes": (
            peak_processes if positive_process_samples else None
        ),
        "process_peak_within_limit": (
            peak_processes <= requested_jobs if positive_process_samples else None
        ),
        "peak_raw_total_cpu_worker_processes": (
            peak_processes if positive_process_samples else None
        ),
        "raw_total_cpu_worker_peak_within_limit": (
            peak_processes <= requested_jobs if positive_process_samples else None
        ),
        "raw_total_cpu_worker_count_authoritative": False,
        "raw_process_count_authoritative": False,
        "raw_process_conservative_envelope": requested_jobs + 1,
        "raw_process_conservative_envelope_applies": process_details is None,
        "raw_process_samples_above_job_cap": len(overage_indexes),
        "raw_process_peak_classification": raw_peak_classification,
        "raw_process_turnover_correlated": turnover_correlated,
        "process_details_available": process_details is not None,
        "process_detail_role_schema_version": (
            2 if process_details is not None else None
        ),
        "peak_ordinary_proof_engine_processes": peak_ordinary_engines,
        "ordinary_proof_engine_peak_within_limit": (
            ordinary_engine_peak_within_limit
        ),
        "peak_proof_cache_worker_processes": peak_cache_workers,
        "proof_cache_workers_count_toward_proof_job_slots": False,
        # Compatibility alias: schema-v2 excludes comm=jg_engineCache from
        # this formerly argv-only ProofGrid-engine peak.
        "peak_signature_proofgrid_engine_processes": peak_ordinary_engines,
        "peak_controller_or_other_jg_proof_processes": peak_controller_or_other,
        "evidence_errors": errors,
        "source": str(run_log_source),
        "process_samples_source": str(process_samples_source),
        "process_details_source": (
            str(process_details_source) if process_details_source is not None else None
        ),
        "ipf031": observed,
    }


def main() -> int:
    args = parse_args()
    worktree_identity, worktree_errors = validate_worktree_identity(
        args.worktree, args.candidate_sha
    )
    try:
        report = json.loads(args.input.read_text(encoding="utf-8"))
        run_log = args.run_log.read_text(encoding="utf-8", errors="replace")
        process_samples = args.process_samples.read_text(
            encoding="utf-8", errors="replace"
        )
        process_details = (
            args.process_details.read_text(encoding="utf-8", errors="replace")
            if args.process_details is not None
            else None
        )
        summary = report["fpv"]["summary"]
        asserts = require_counts(summary.get("asserts"), "asserts")
        covers = require_counts(summary.get("covers"), "covers")
        assumes = require_counts(summary.get("assumes"), "assumes")
        failures = failing_properties(report["fpv"].get("task"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"FPV property summary failed: {exc}", file=sys.stderr)
        return 1

    assert_passed = total(asserts, ASSERT_PASS_KEYS)
    assert_failed = total(asserts, ASSERT_FAIL_KEYS)
    assert_unresolved = total(asserts, ASSERT_UNRESOLVED_KEYS)
    assert_unclassified = asserts["total"] - (
        assert_passed + assert_failed + assert_unresolved
    )
    cover_hit = total(covers, COVER_HIT_KEYS)
    cover_unreachable = total(covers, COVER_UNREACHABLE_KEYS)
    cover_unresolved = total(covers, COVER_UNRESOLVED_KEYS)

    cex_count = total(asserts, ("cex", "ar_cex"))
    concurrency = verify_concurrency(
        run_log,
        process_samples,
        process_details,
        args.jobs,
        args.run_log,
        args.process_samples,
        args.process_details,
    )
    no_property_processed = (
        asserts["total"] > 0 and asserts.get("unprocessed", 0) == asserts["total"]
    )
    if worktree_errors:
        classification = "ERROR"
    elif assert_failed:
        classification = "FAIL"
    elif args.ftrun_status:
        classification = "ERROR"
    elif not concurrency["verified"]:
        classification = "ERROR"
    elif no_property_processed or assert_unclassified:
        classification = "ERROR"
    else:
        classification = "PASS"
    proof_completeness = "INCOMPLETE" if assert_unresolved else "COMPLETE"

    result = {
        "schema_version": 1,
        "wave": "B",
        "branch": "fpv",
        "classification": classification,
        "candidate_sha": args.candidate_sha,
        "host": args.host,
        "worktree": args.worktree,
        "worktree_identity": worktree_identity,
        "command": f"ftrun tex_flt -local -batch -auto_run -slots {args.jobs}",
        "command_status": args.ftrun_status,
        "ftrun_status": args.ftrun_status,
        "proof_limit": args.proof_limit,
        "jobs": args.jobs,
        "concurrency_verified": concurrency["verified"],
        "concurrency": concurrency,
        "cex_save_limit": args.cex_save_limit,
        "individual_cex_stop": "UNVERIFIED_GAP",
        "failure_count": assert_failed,
        "cex_count": cex_count,
        "proof_completeness": proof_completeness,
        "execution_evidence": (
            "NO_PROPERTIES_PROCESSED"
            if no_property_processed
            else (
                "UNCLASSIFIED_ASSERTION_STATUS"
                if assert_unclassified
                else "PROPERTIES_PROCESSED"
            )
        ),
        "eap_triage_urls": [],
        "failures": failures,
        "source": str(args.input),
        "assertions": {
            "total": asserts["total"],
            "passed": assert_passed,
            "failed": assert_failed,
            "unresolved": assert_unresolved,
            "unclassified": assert_unclassified,
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
        f"Candidate: {args.candidate_sha}",
        f"Host: {args.host}",
        f"Worktree retained: {args.worktree}",
        "Worktree attempt token: "
        f"{worktree_identity['attempt_token'] or 'NONE'}",
        f"Proof limit: {args.proof_limit}",
        f"Requested proof-job slots: {args.jobs}",
        f"Concurrency verification: {concurrency['status']}",
        "Effective local proof-job-slot cap: "
        f"{concurrency['effective_max_jobs'] if concurrency['effective_max_jobs'] is not None else 'MISSING'}",
        "Concurrency effective per-engine cap: "
        f"{concurrency['effective_per_engine_max_jobs'] if concurrency['effective_per_engine_max_jobs'] is not None else 'MISSING'}",
        "ProofGrid usable-level peak: "
        f"{concurrency['proofgrid_usable_level_peak'] if concurrency['proofgrid_usable_level_peak'] is not None else 'MISSING'}",
        "Ordinary proof-engine process peak: "
        f"{concurrency['peak_ordinary_proof_engine_processes'] if concurrency['peak_ordinary_proof_engine_processes'] is not None else 'LEGACY_UNCLASSIFIED'}",
        "Proof-cache worker process peak: "
        f"{concurrency['peak_proof_cache_worker_processes'] if concurrency['peak_proof_cache_worker_processes'] is not None else 'LEGACY_UNCLASSIFIED'}",
        "Raw total run-scoped CPU-worker peak (diagnostic): "
        f"{concurrency['peak_raw_total_cpu_worker_processes'] if concurrency['peak_raw_total_cpu_worker_processes'] is not None else 'NOT_OBSERVED'}",
        f"Raw process classification: {concurrency['raw_process_peak_classification']}",
        f"CEX save cap: {args.cex_save_limit}",
        "Individual-property CEX stop: UNVERIFIED_GAP",
        f"Proof completeness: {proof_completeness}",
        "Execution evidence: "
        + (
            "NO_PROPERTIES_PROCESSED"
            if no_property_processed
            else (
                "UNCLASSIFIED_ASSERTION_STATUS"
                if assert_unclassified
                else "PROPERTIES_PROCESSED"
            )
        ),
        f"FTRun status: {args.ftrun_status}",
        f"Assertions: total={asserts['total']} passed={assert_passed} "
        f"failed={assert_failed} unresolved={assert_unresolved} "
        f"unclassified={assert_unclassified}",
        "  " + " ".join(f"{key}={asserts[key]}" for key in sorted(asserts)),
        f"Covers: total={covers['total']} covered={cover_hit} "
        f"unreachable={cover_unreachable} unresolved={cover_unresolved}",
        "  " + " ".join(f"{key}={covers[key]}" for key in sorted(covers)),
        f"Assumptions: total={assumes['total']}",
        "  " + " ".join(f"{key}={assumes[key]}" for key in sorted(assumes)),
        f"Source: {args.input}",
        f"Concurrency source: {args.run_log}",
        f"Concurrency process samples: {args.process_samples}",
        "Concurrency process details: "
        f"{args.process_details if args.process_details is not None else 'LEGACY_COUNT_ONLY'}",
    ]
    for error in concurrency["evidence_errors"]:
        lines.append(f"  CONCURRENCY ERROR: {error}")
    for error in worktree_errors:
        lines.append(f"  WORKTREE ERROR: {error}")
    for failure in failures:
        lines.append(
            "  FAILURE: status={status} property={name} location={location}".format(
                status=failure.get("status") or "UNKNOWN",
                name=failure.get("name") or "UNKNOWN",
                location=failure.get("location") or "UNKNOWN",
            )
        )

    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"FPV_REPORT_TEXT={args.text_output}")
    print(f"FPV_REPORT_JSON={args.json_output}")
    return 0 if concurrency["verified"] and not worktree_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
