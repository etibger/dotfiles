#!/usr/bin/env python3
"""Combine four Wave A branches into an evidence-bound negative-test gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
from typing import Any


BRANCHES = ("aacr", "simulation", "fpv", "rhel8_lint")
EXPECTED_BRANCH_LIST = ",".join(BRANCHES)
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
ATTEMPT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}")
ENV_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")
SIMULATION_COMMAND = (
    "blk_val --build-clean --storage-services elk=n --set-lsf-mem-limit 12000 "
    "--no-bsub --no-bsub-build --dfs batch --bo 8x_mtcs --seed 1 "
    "--plusarg '+tex_trace_shim +tex_checkers_enable=all' "
    "test_mix_all_tiny__sanity"
)
FPV_SUMMARY_COMMAND = "ftrun tex_flt -local -batch -auto_run -slots 4 -save on_failure"
LINT_COMMAND = "dcs_superlint superlint_8x/configuration_top.yaml"
COMMAND_RELS = {
    "aacr": "aacr/command.txt",
    "simulation": "simulation/command.txt",
    "fpv": "fpv/command.txt",
    "rhel8_lint": "logs/rhel8-lint.driver.log",
}
LEGACY_LINT_COMMAND_REL = "rhel8-lint/lint.log"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-preflight", required=True, type=Path)
    parser.add_argument("--orchestration", required=True, type=Path)
    for branch in BRANCHES:
        parser.add_argument(f"--{branch.replace('_', '-')}", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--tip", required=True)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    parser.add_argument(
        "--allow-legacy-command-evidence",
        action="store_true",
        help=(
            "Permit an explicitly selected historical schema-v2 run whose exact raw "
            "commands predate collection-bound command SHA-256 fields"
        ),
    )
    return parser.parse_args()


def parse_env(path: Path, label: str) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    if not path.is_file():
        return values, [f"{label}: manifest is missing ({path})"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return values, [f"{label}: cannot read manifest ({exc})"]
    for line_number, line in enumerate(lines, start=1):
        if not line:
            continue
        if "=" not in line:
            errors.append(f"{label}: malformed line {line_number}")
            continue
        key, value = line.split("=", 1)
        if not ENV_KEY_RE.fullmatch(key):
            errors.append(f"{label}: invalid key on line {line_number}")
            continue
        if key in values:
            errors.append(f"{label}: duplicate key {key}")
            continue
        values[key] = value
    return values, errors


def sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def read_text(path: Path, label: str, reasons: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        reasons.append(f"{label}: cannot read command evidence ({exc})")
        return ""


def resolve_recorded_path(value: str, artifact: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (artifact.parent / path).resolve()


def validate_aacr_command(
    text: str, artifact: Path, base: str, tip: str, reasons: list[str]
) -> None:
    label = "aacr command evidence"
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        reasons.append(f"{label}: command is not shell-parseable ({exc})")
        return
    expected_fixed = [
        "aacr-cli",
        "--target-sha",
        f"{base}..{tip}",
        "--deep-analysis-codex",
        "--no-caching",
        "--json-output",
    ]
    if len(tokens) != 11 or tokens[:6] != expected_fixed:
        reasons.append(f"{label}: command is not the exact uncached base..tip review")
        return
    if tokens[7] != "--output-file" or tokens[9] != "--html-report":
        reasons.append(f"{label}: output option set/order is not exact")
        return
    expected_outputs = (
        (tokens[6], artifact.parent / "aacr.raw.json", "raw JSON"),
        (tokens[8], artifact.parent / "aacr.txt", "text report"),
        (tokens[10], artifact.parent / "html", "HTML report"),
    )
    for recorded, expected, description in expected_outputs:
        if resolve_recorded_path(recorded, artifact) != expected.resolve():
            reasons.append(f"{label}: {description} path is not bound to the selected run")


def validate_simulation_command(
    text: str, payload: dict[str, Any], reasons: list[str]
) -> None:
    label = "simulation command evidence"
    if text.strip() != SIMULATION_COMMAND:
        reasons.append(f"{label}: command is not the fixed seed-1 no-wave sanity test")
    expected = {
        "command": SIMULATION_COMMAND,
        "test": "test_mix_all_tiny__sanity",
        "seed": 1,
        "build_option": "8x_mtcs",
        "dfs": "batch",
        "waves": False,
        "uvm_high": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            reasons.append(f"simulation: {key} does not match the fixed executor contract")


def validate_fpv_command(
    text: str,
    artifact: Path,
    run_root: Path,
    payload: dict[str, Any],
    reasons: list[str],
) -> None:
    label = "fpv command evidence"
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        reasons.append(f"{label}: command is not shell-parseable ({exc})")
        tokens = []
    if (
        len(tokens) != 14
        or tokens[:4] != ["FTRUN_RUN_LIMIT=10m", "ftrun", "tex_flt", "-tcl"]
        or tokens[5] != "-build_dir"
        or tokens[7:] != ["-local", "-batch", "-auto_run", "-slots", "4", "-save", "on_failure"]
    ):
        reasons.append(f"{label}: target, proof limit, slot count, or option set is not exact")
    else:
        wrapper = tokens[4]
        installed_wrapper = "/codex-wave-a/jaspergold-mac-fpv/assets/save_up_to_five_cex.tcl"
        legacy_wrapper_suffix = "/jaspergold-mac-fpv/assets/save_up_to_five_cex.tcl"
        if wrapper != installed_wrapper and not (
            wrapper.startswith("/gpu/") and wrapper.endswith(legacy_wrapper_suffix)
        ):
            reasons.append(f"{label}: Tcl wrapper identity is not save_up_to_five_cex.tcl")
        build_dir = Path(tokens[6])
        expected_build = (run_root / "fpv/fts_run_tex_flt").resolve()
        if str(build_dir).startswith("/gpu/"):
            gpu_relative = str(build_dir).removeprefix("/gpu/")
            # A retained replay can contain a nested Git worktree. Accept the
            # /gpu mapping only when one actual repository ancestor maps the
            # recorded path to this selected run's FPV directory.
            mapped_candidates = [
                (candidate / gpu_relative).resolve()
                for candidate in (run_root, *run_root.parents)
                if (candidate / ".git").exists()
            ]
            resolved_build = expected_build if expected_build in mapped_candidates else None
        else:
            resolved_build = build_dir.resolve() if build_dir.is_absolute() else None
        if resolved_build != expected_build:
            reasons.append(f"{label}: build directory is not bound to the selected run")
    expected = {
        "command": FPV_SUMMARY_COMMAND,
        "target": "tex_flt",
        "proof_limit": "10m",
        "slots": 4,
        "saved_cex_limit": 5,
        "stop_after_cex_implemented": False,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            reasons.append(f"fpv: {key} does not match the fixed executor contract")


def validate_lint_command(
    text: str,
    artifact: Path,
    run_root: Path,
    run_id: str | None,
    tip: str,
    payload: dict[str, Any],
    reasons: list[str],
) -> None:
    label = "rhel8_lint command evidence"
    commands = re.findall(r"^LINT_COMMAND=(.+)$", text, re.MULTILINE)
    if not commands or any(command != LINT_COMMAND for command in commands):
        reasons.append(f"{label}: command is not the exact 8x Superlint invocation")
    lint_summary_expected = {
        "command": LINT_COMMAND,
        "runner_status": 0,
        "report_complete": True,
    }
    for key, value in lint_summary_expected.items():
        if payload.get(key) != value:
            reasons.append(f"rhel8_lint: {key} does not match the fixed executor contract")

    if artifact.relative_to(run_root).as_posix() == LEGACY_LINT_COMMAND_REL:
        status_path = run_root / "rhel8-lint/status.env"
        status, errors = parse_env(status_path, "rhel8_lint legacy status")
        reasons.extend(errors)
        expected = {
            "RUN_ID": run_id,
            "CANDIDATE_SHA": tip,
            "EXIT_STATUS": "0",
        }
        for key, value in expected.items():
            if status.get(key) != value:
                reasons.append(f"rhel8_lint legacy status: {key} does not match selected run")
        expected_worktree = f"/home/tibger01/projects/fornjot/tmp_gpu_lint_run_{tip[:12]}"
        if status.get("WORKTREE") != expected_worktree:
            reasons.append("rhel8_lint legacy status: WORKTREE does not match candidate")
        return

    expected_ref = f"refs/codex/validation-campaign/rhel8-lint/{tip}"
    expected_worktree = (
        f"/home/tibger01/projects/fornjot/tmp_gpu_lint_run_{tip[:12]}_{run_id}"
    )
    required_lines = (
        f"Transferring exact candidate {tip} to custom ref {expected_ref}.",
        f"ATTEMPT_TOKEN={run_id}",
        f"REMOTE_WORKTREE={expected_worktree}",
        "RHEL8_LINT_DRIVER_STATUS=COMPLETE",
    )
    lines = set(text.splitlines())
    for line in required_lines:
        if line not in lines:
            reasons.append(f"{label}: selected run identity is missing {line.split('=', 1)[0]!r}")


def parse_timestamp(
    value: str | None, label: str, reasons: list[str]
) -> datetime | None:
    if not value:
        reasons.append(f"{label}: timestamp is missing")
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value):
        reasons.append(f"{label}: timestamp is not RFC3339 UTC")
        return None
    try:
        timestamp_body = value[:-1]
        if "." in timestamp_body:
            whole_seconds, fraction = timestamp_body.rsplit(".", 1)
            timestamp_body = f"{whole_seconds}.{fraction.ljust(6, '0')}"
        parsed = datetime.fromisoformat(timestamp_body + "+00:00")
    except ValueError:
        reasons.append(f"{label}: timestamp is invalid")
        return None
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        reasons.append(f"{label}: timestamp is not UTC")
        return None
    return parsed


def resolve_run_relative(
    run_root: Path,
    value: str | None,
    label: str,
    reasons: list[str],
    *,
    marker: bool = False,
) -> Path | None:
    if not value:
        reasons.append(f"{label}: relative path is missing")
        return None
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        reasons.append(f"{label}: path must be a normalized run-relative path")
        return None
    resolved = (run_root / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(run_root)
    except ValueError:
        reasons.append(f"{label}: path escapes the retained run root")
        return None
    if marker and resolved.parent != (run_root / "orchestration").resolve():
        reasons.append(f"{label}: marker is outside the run orchestration directory")
        return None
    return resolved


def load_result(
    path: Path, branch: str
) -> tuple[dict[str, Any], str | None, str | None]:
    if not path.is_file():
        return {}, f"{branch}: summary is missing ({path})", None
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{branch}: summary is invalid ({exc})", None
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(payload, dict):
        return {}, f"{branch}: summary root is not an object", digest
    if payload.get("branch") != branch:
        return payload, f"{branch}: summary identifies branch={payload.get('branch')!r}", digest
    return payload, None, digest


def validate_marker_identity(
    values: dict[str, str],
    *,
    label: str,
    run_id: str | None,
    attempt_id: str | None,
    branch: str,
    base: str,
    tip: str,
    reasons: list[str],
) -> None:
    expected = {
        "SCHEMA_VERSION": "1",
        "PROVENANCE_MODE": "LIVE_COORDINATOR",
        "RUN_ID": run_id,
        "ATTEMPT_ID": attempt_id,
        "BRANCH": branch,
        "BASE_SHA": base,
        "TIP_SHA": tip,
        "RANGE": f"{base}..{tip}",
    }
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            reasons.append(f"{label}: {key} does not match the selected live attempt")


def main() -> int:
    args = arguments()
    reasons: list[str] = []
    run_root = args.orchestration.resolve().parent
    expected_range = f"{args.base}..{args.tip}"

    if not SHA_RE.fullmatch(args.base):
        reasons.append("range: base is not a full lowercase SHA")
    if not SHA_RE.fullmatch(args.tip):
        reasons.append("range: tip is not a full lowercase SHA")

    preflight, preflight_errors = parse_env(args.source_preflight, "source_preflight")
    orchestration_manifest, orchestration_errors = parse_env(
        args.orchestration, "orchestration"
    )
    reasons.extend(preflight_errors)
    reasons.extend(orchestration_errors)

    run_id = orchestration_manifest.get("RUN_ID")
    if not run_id or not RUN_ID_RE.fullmatch(run_id):
        reasons.append("orchestration: RUN_ID is missing or invalid")
    elif run_root.name != run_id:
        reasons.append("orchestration: RUN_ID does not match retained run directory")
    if orchestration_manifest.get("SCHEMA_VERSION") != "2":
        reasons.append("orchestration: schema version is not 2")
    if orchestration_manifest.get("PROVENANCE_MODE") != "LIVE_COORDINATOR":
        reasons.append("orchestration: live coordinator provenance is missing")
    if orchestration_manifest.get("BASE_SHA") != args.base:
        reasons.append("orchestration: base does not equal the selected range")
    if orchestration_manifest.get("TIP_SHA") != args.tip:
        reasons.append("orchestration: tip does not equal the selected range")
    if orchestration_manifest.get("RANGE") != expected_range:
        reasons.append("orchestration: range does not equal base..tip")
    if orchestration_manifest.get("BRANCH_LAUNCH_MODE") != "parallel":
        reasons.append("orchestration: branch launch mode is not parallel")
    if orchestration_manifest.get("START_ALL_BEFORE_WAIT") != "1":
        reasons.append("orchestration: branches were not all started before waiting")
    if orchestration_manifest.get("COLLECT_ALL_BRANCHES") != "1":
        reasons.append("orchestration: collect-all policy was not attested")
    if orchestration_manifest.get("STARTED_BRANCHES") != EXPECTED_BRANCH_LIST:
        reasons.append("orchestration: started branch set/order is incomplete")
    if orchestration_manifest.get("COLLECTED_BRANCHES") != EXPECTED_BRANCH_LIST:
        reasons.append("orchestration: collected branch set/order is incomplete")

    command_binding_keys = [
        f"{branch.upper()}_{suffix}"
        for branch in BRANCHES
        for suffix in ("COMMAND_REL", "COMMAND_SHA256")
    ]
    present_command_binding_keys = [
        key for key in command_binding_keys if key in orchestration_manifest
    ]
    command_digests_bound = len(present_command_binding_keys) == len(
        command_binding_keys
    )
    if present_command_binding_keys and not command_digests_bound:
        reasons.append(
            "orchestration: raw command digest binding is partial; all four branches are required"
        )
    if not present_command_binding_keys and not args.allow_legacy_command_evidence:
        reasons.append(
            "orchestration: collection-bound raw command SHA-256 fields are absent; "
            "historical replay requires explicit legacy authorization"
        )
    command_binding_mode = (
        "collection_sha256"
        if command_digests_bound
        else "explicit_legacy_raw_validation"
    )

    coordinator_started = parse_timestamp(
        orchestration_manifest.get("COORDINATOR_STARTED_UTC"),
        "orchestration COORDINATOR_STARTED_UTC",
        reasons,
    )
    all_started = parse_timestamp(
        orchestration_manifest.get("ALL_BRANCHES_STARTED_UTC"),
        "orchestration ALL_BRANCHES_STARTED_UTC",
        reasons,
    )
    first_wait = parse_timestamp(
        orchestration_manifest.get("FIRST_COMPLETION_WAIT_UTC"),
        "orchestration FIRST_COMPLETION_WAIT_UTC",
        reasons,
    )
    all_collected = parse_timestamp(
        orchestration_manifest.get("ALL_BRANCHES_COLLECTED_UTC"),
        "orchestration ALL_BRANCHES_COLLECTED_UTC",
        reasons,
    )
    if coordinator_started and all_started and coordinator_started > all_started:
        reasons.append("orchestration: all-started timestamp precedes coordinator start")
    if all_started and first_wait and all_started > first_wait:
        reasons.append("orchestration: first completion wait began before all branches started")
    if first_wait and all_collected and first_wait > all_collected:
        reasons.append("orchestration: all-collected timestamp precedes first completion wait")

    if preflight.get("SCHEMA_VERSION") != "1":
        reasons.append("source_preflight: schema version is not 1")
    if preflight.get("STATUS") != "PASS":
        reasons.append("source_preflight: serialized make-sources barrier did not pass")
    if preflight.get("SERIALIZED_BARRIER") != "1":
        reasons.append("source_preflight: serialization marker is absent")
    if preflight.get("CANDIDATE_SHA") != args.tip:
        reasons.append("source_preflight: candidate does not equal tip")
    if preflight.get("COMMAND") != "design/logical/make_sources":
        reasons.append("source_preflight: command identity is not design/logical/make_sources")
    preflight_completed = parse_timestamp(
        preflight.get("COMPLETED_UTC"), "source_preflight COMPLETED_UTC", reasons
    )
    if coordinator_started and preflight_completed and preflight_completed < coordinator_started:
        reasons.append("source_preflight: completion timestamp precedes coordinator start")

    preflight_path = resolve_run_relative(
        run_root,
        orchestration_manifest.get("SOURCE_PREFLIGHT_REL"),
        "orchestration SOURCE_PREFLIGHT_REL",
        reasons,
    )
    if preflight_path and preflight_path != args.source_preflight.resolve():
        reasons.append("source_preflight: selected path does not match orchestration evidence")
    expected_preflight_digest = orchestration_manifest.get("SOURCE_PREFLIGHT_SHA256")
    if not expected_preflight_digest or not DIGEST_RE.fullmatch(expected_preflight_digest):
        reasons.append("source_preflight: SHA-256 digest is missing or malformed")
    actual_preflight_digest = sha256(args.source_preflight)
    if (
        actual_preflight_digest
        and expected_preflight_digest
        and actual_preflight_digest != expected_preflight_digest
    ):
        reasons.append("source_preflight: SHA-256 digest does not match selected manifest")

    paths = {
        "aacr": args.aacr,
        "simulation": args.simulation,
        "fpv": args.fpv,
        "rhel8_lint": args.rhel8_lint,
    }
    results: dict[str, dict[str, Any]] = {}
    branch_evidence: dict[str, dict[str, Any]] = {}
    used_attempt_ids: set[str] = set()
    used_marker_paths: set[Path] = set()
    used_summary_paths: set[Path] = set()
    used_command_paths: set[Path] = set()
    used_pids: set[str] = set()

    for branch, path in paths.items():
        payload, error, actual_digest = load_result(path, branch)
        results[branch] = payload
        if error:
            reasons.append(error)
        else:
            if payload.get("schema_version") != 1:
                reasons.append(f"{branch}: summary schema version is not 1")
            if payload.get("wave") != "A":
                reasons.append(f"{branch}: summary wave is not A")
            if payload.get("candidate_sha") != args.tip:
                reasons.append(f"{branch}: candidate does not equal tip")
            if branch == "aacr":
                if payload.get("base_sha") != args.base:
                    reasons.append("aacr: base does not equal selected base")
                if payload.get("tip_sha") != args.tip:
                    reasons.append("aacr: tip does not equal selected tip")
                if payload.get("range") != expected_range:
                    reasons.append("aacr: reviewed range does not equal selected base..tip")
                if payload.get("command_status") != 0:
                    reasons.append("aacr: command status is not a completed review")

        prefix = branch.upper()
        attempt_id = orchestration_manifest.get(f"{prefix}_ATTEMPT_ID")
        if not attempt_id or not ATTEMPT_ID_RE.fullmatch(attempt_id):
            reasons.append(f"{branch}: selected ATTEMPT_ID is missing or invalid")
        elif attempt_id in used_attempt_ids:
            reasons.append(f"{branch}: selected ATTEMPT_ID is not unique")
        else:
            used_attempt_ids.add(attempt_id)
            if run_id and not attempt_id.startswith(f"{run_id}.{branch}."):
                reasons.append(f"{branch}: selected ATTEMPT_ID is not bound to run and branch")

        summary_rel = orchestration_manifest.get(f"{prefix}_SUMMARY_REL")
        selected_summary = resolve_run_relative(
            run_root, summary_rel, f"{branch} summary", reasons
        )
        if selected_summary:
            if selected_summary in used_summary_paths:
                reasons.append(f"{branch}: selected summary path is not unique")
            used_summary_paths.add(selected_summary)
            if selected_summary != path.resolve():
                reasons.append(f"{branch}: CLI summary path is not the selected live summary")

        expected_digest = orchestration_manifest.get(f"{prefix}_SUMMARY_SHA256")
        if not expected_digest or not DIGEST_RE.fullmatch(expected_digest):
            reasons.append(f"{branch}: summary SHA-256 is missing or malformed")
        if actual_digest and expected_digest and actual_digest != expected_digest:
            reasons.append(f"{branch}: summary SHA-256 does not match selected evidence")

        marker_values: dict[str, dict[str, str]] = {}
        marker_paths: dict[str, Path | None] = {}
        for phase in ("START", "FINISH", "COLLECTION"):
            marker_label = f"{branch} {phase.lower()} marker"
            marker_path = resolve_run_relative(
                run_root,
                orchestration_manifest.get(f"{prefix}_{phase}_MARKER_REL"),
                marker_label,
                reasons,
                marker=True,
            )
            marker_paths[phase] = marker_path
            if marker_path:
                if marker_path in used_marker_paths:
                    reasons.append(f"{marker_label}: marker path is not unique")
                used_marker_paths.add(marker_path)
                values, errors = parse_env(marker_path, marker_label)
                marker_values[phase] = values
                reasons.extend(errors)
                validate_marker_identity(
                    values,
                    label=marker_label,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    branch=branch,
                    base=args.base,
                    tip=args.tip,
                    reasons=reasons,
                )
            else:
                marker_values[phase] = {}

        start_values = marker_values["START"]
        finish_values = marker_values["FINISH"]
        collection_values = marker_values["COLLECTION"]
        started = parse_timestamp(
            start_values.get("STARTED_UTC"), f"{branch} start marker", reasons
        )
        finished = parse_timestamp(
            finish_values.get("FINISHED_UTC"), f"{branch} finish marker", reasons
        )
        collected = parse_timestamp(
            collection_values.get("COLLECTED_UTC"),
            f"{branch} collection marker",
            reasons,
        )

        start_pid = start_values.get("PID")
        finish_pid = finish_values.get("PID")
        if not start_pid or not start_pid.isdigit() or int(start_pid) <= 0:
            reasons.append(f"{branch}: start marker PID is missing or invalid")
        elif start_pid in used_pids:
            reasons.append(f"{branch}: start marker PID is not unique")
        else:
            used_pids.add(start_pid)
        if finish_pid != start_pid:
            reasons.append(f"{branch}: finish marker PID does not match start marker")
        exit_status = finish_values.get("EXIT_STATUS")
        if not exit_status or not exit_status.isdigit() or not 0 <= int(exit_status) <= 255:
            reasons.append(f"{branch}: finish marker exit status is missing or invalid")
        elif int(exit_status) != 0:
            reasons.append(f"{branch}: selected branch executor exited nonzero")

        if collection_values.get("SUMMARY_REL") != summary_rel:
            reasons.append(f"{branch}: collection marker summary path does not match selection")
        if collection_values.get("SUMMARY_SHA256") != expected_digest:
            reasons.append(f"{branch}: collection marker digest does not match selection")

        command_rel: str | None
        command_artifact: Path | None
        expected_command_digest: str | None = None
        if command_digests_bound:
            command_rel = orchestration_manifest.get(f"{prefix}_COMMAND_REL")
            command_artifact = resolve_run_relative(
                run_root,
                command_rel,
                f"{branch} command evidence",
                reasons,
            )
            if command_rel != COMMAND_RELS[branch]:
                reasons.append(
                    f"{branch}: raw command path does not match the fixed executor contract"
                )
            expected_command_digest = orchestration_manifest.get(
                f"{prefix}_COMMAND_SHA256"
            )
            if not expected_command_digest or not DIGEST_RE.fullmatch(
                expected_command_digest
            ):
                reasons.append(f"{branch}: command SHA-256 is missing or malformed")
            if collection_values.get("COMMAND_REL") != command_rel:
                reasons.append(
                    f"{branch}: collection marker command path does not match selection"
                )
            if collection_values.get("COMMAND_SHA256") != expected_command_digest:
                reasons.append(
                    f"{branch}: collection marker command digest does not match selection"
                )
        else:
            command_rel = COMMAND_RELS[branch]
            command_artifact = resolve_run_relative(
                run_root,
                command_rel,
                f"{branch} command evidence",
                reasons,
            )
            if branch == "rhel8_lint" and (
                command_artifact is None or not command_artifact.is_file()
            ):
                command_rel = LEGACY_LINT_COMMAND_REL
                command_artifact = resolve_run_relative(
                    run_root,
                    command_rel,
                    f"{branch} legacy command evidence",
                    reasons,
                )
            if "COMMAND_REL" in collection_values or "COMMAND_SHA256" in collection_values:
                reasons.append(
                    f"{branch}: collection has command binding absent from orchestration"
                )

        actual_command_digest = sha256(command_artifact) if command_artifact else None
        if command_artifact:
            if command_artifact in used_command_paths:
                reasons.append(f"{branch}: raw command path is not unique")
            used_command_paths.add(command_artifact)
            if not command_artifact.is_file():
                reasons.append(
                    f"{branch}: raw command evidence is missing ({command_artifact})"
                )
            if (
                expected_command_digest
                and actual_command_digest
                and expected_command_digest != actual_command_digest
            ):
                reasons.append(f"{branch}: command SHA-256 does not match selected evidence")
            command_text = read_text(
                command_artifact, f"{branch} command evidence", reasons
            )
            if branch == "aacr":
                validate_aacr_command(command_text, command_artifact, args.base, args.tip, reasons)
            elif branch == "simulation":
                validate_simulation_command(command_text, payload, reasons)
            elif branch == "fpv":
                validate_fpv_command(
                    command_text, command_artifact, run_root, payload, reasons
                )
            else:
                validate_lint_command(
                    command_text,
                    command_artifact,
                    run_root,
                    run_id,
                    args.tip,
                    payload,
                    reasons,
                )

        if coordinator_started and started and started < coordinator_started:
            reasons.append(f"{branch}: start timestamp precedes coordinator start")
        if preflight_completed and started and started < preflight_completed:
            reasons.append(f"{branch}: start timestamp precedes source-preflight completion")
        if started and all_started and started > all_started:
            reasons.append(f"{branch}: selected attempt started after all-started barrier")
        if started and first_wait and started > first_wait:
            reasons.append(f"{branch}: selected attempt started after first completion wait")
        if finished and all_started and finished < all_started:
            reasons.append(f"{branch}: selected attempt finished before all branches started")
        if started and finished and started > finished:
            reasons.append(f"{branch}: finish timestamp precedes start")
        if finished and collected and finished > collected:
            reasons.append(f"{branch}: collection timestamp precedes finish")
        if first_wait and collected and collected < first_wait:
            reasons.append(f"{branch}: collection timestamp precedes first completion wait")
        if collected and all_collected and collected > all_collected:
            reasons.append(f"{branch}: collection timestamp follows all-collected barrier")

        branch_evidence[branch] = {
            "attempt_id": attempt_id,
            "summary_rel": summary_rel,
            "expected_summary_sha256": expected_digest,
            "actual_summary_sha256": actual_digest,
            "command_rel": command_rel,
            "expected_command_sha256": expected_command_digest,
            "actual_command_sha256": actual_command_digest,
            "command_digest_bound_at_collection": command_digests_bound,
            "start_marker": str(marker_paths["START"]) if marker_paths["START"] else None,
            "finish_marker": str(marker_paths["FINISH"]) if marker_paths["FINISH"] else None,
            "collection_marker": (
                str(marker_paths["COLLECTION"]) if marker_paths["COLLECTION"] else None
            ),
            "started_utc": start_values.get("STARTED_UTC"),
            "finished_utc": finish_values.get("FINISHED_UTC"),
            "collected_utc": collection_values.get("COLLECTED_UTC"),
            "exit_status": finish_values.get("EXIT_STATUS"),
        }

    aacr = results.get("aacr", {})
    if aacr and aacr.get("execution_status") != "COMPLETE":
        reasons.append("aacr: review did not complete")

    for branch in ("simulation", "fpv", "rhel8_lint"):
        payload = results.get(branch, {})
        if not payload:
            continue
        if payload.get("detection_status") != "DETECTED":
            reasons.append(f"{branch}: intentional bug was not detected")
        if payload.get("attributable_detection") is not True:
            reasons.append(f"{branch}: detection is not attributable to the intentional bug")

    fpv = results.get("fpv", {})
    fpv_infra_limited_detection = bool(
        fpv.get("classification") == "VALIDATION_DETECTED_WITH_INFRA_LIMIT"
        and fpv.get("detection_status") == "DETECTED"
        and fpv.get("attributable_detection") is True
    )
    if fpv and fpv.get("execution_status") != "COMPLETE" and not fpv_infra_limited_detection:
        reasons.append("fpv: execution was incomplete without conclusive attributable CEX evidence")
    for branch in ("simulation", "rhel8_lint"):
        payload = results.get(branch, {})
        if payload and payload.get("execution_status") != "COMPLETE":
            reasons.append(f"{branch}: execution did not complete")

    reasons = list(dict.fromkeys(reasons))
    gate_status = "PASS" if not reasons else "BLOCKED"
    orchestration = {
        "schema_version": orchestration_manifest.get("SCHEMA_VERSION"),
        "provenance_mode": orchestration_manifest.get("PROVENANCE_MODE"),
        "run_id": run_id,
        "base_sha": orchestration_manifest.get("BASE_SHA"),
        "tip_sha": orchestration_manifest.get("TIP_SHA"),
        "range": orchestration_manifest.get("RANGE"),
        "branch_launch_mode": orchestration_manifest.get("BRANCH_LAUNCH_MODE"),
        "start_all_before_wait": orchestration_manifest.get("START_ALL_BEFORE_WAIT") == "1",
        "collect_all_branches": orchestration_manifest.get("COLLECT_ALL_BRANCHES") == "1",
        "started_branches": [
            item
            for item in orchestration_manifest.get("STARTED_BRANCHES", "").split(",")
            if item
        ],
        "collected_branches": [
            item
            for item in orchestration_manifest.get("COLLECTED_BRANCHES", "").split(",")
            if item
        ],
        "coordinator_started_utc": orchestration_manifest.get("COORDINATOR_STARTED_UTC"),
        "all_branches_started_utc": orchestration_manifest.get("ALL_BRANCHES_STARTED_UTC"),
        "first_completion_wait_utc": orchestration_manifest.get("FIRST_COMPLETION_WAIT_UTC"),
        "all_branches_collected_utc": orchestration_manifest.get("ALL_BRANCHES_COLLECTED_UTC"),
        "command_binding_mode": command_binding_mode,
        "manifest": str(args.orchestration),
        "branches": branch_evidence,
    }
    state = {
        "schema_version": 2,
        "campaign_kind": "validation",
        "wave": "A",
        "base_sha": args.base,
        "tip_sha": args.tip,
        "range": expected_range,
        "gate": {
            "name": "negative_test_independent_detection",
            "status": gate_status,
            "next_wave_allowed": gate_status == "PASS",
            "requirements": {
                "source_preflight": "candidate-bound serialized make sources with matching SHA-256",
                "orchestration": "schema-v2 live provenance with start/finish/collection chronology",
                "summaries": "selected run-relative paths and matching SHA-256 for all four branches",
                "commands": "raw exact executor contracts; collection-bound SHA-256 for new runs",
                "aacr": "exact base..tip review completes; findings are not required",
                "simulation": "complete attributable intentional-bug detection",
                "fpv": "attributable CEX; post-CEX infrastructure limit remains visible but does not block",
                "rhel8_lint": "complete attributable intentional-bug detection",
            },
            "blocking_reasons": reasons,
        },
        "source_preflight": {
            "manifest": str(args.source_preflight),
            "values": preflight,
            "expected_sha256": expected_preflight_digest,
            "actual_sha256": actual_preflight_digest,
        },
        "orchestration": orchestration,
        "branches": results,
        "artifacts": {branch: str(path) for branch, path in paths.items()},
    }
    lines = [
        "GPU VALIDATION CAMPAIGN — WAVE A",
        f"Range: {expected_range}",
        f"Gate A: {gate_status}",
        f"Next wave allowed: {str(gate_status == 'PASS').lower()}",
        f"Provenance: {orchestration_manifest.get('PROVENANCE_MODE', 'MISSING')}",
        f"Run ID: {run_id or 'MISSING'}",
    ]
    for branch in BRANCHES:
        payload = results.get(branch, {})
        lines.append(
            f"{branch}: execution={payload.get('execution_status', 'MISSING')} "
            f"detection={payload.get('detection_status', 'MISSING')} "
            f"classification={payload.get('classification', 'MISSING')}"
        )
    if reasons:
        lines.append("Blocking reasons:")
        lines.extend(f"- {reason}" for reason in reasons)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"WAVE_A_SUMMARY_JSON={args.json_output}")
    print(f"WAVE_A_GATE_STATUS={gate_status}")
    return 0 if gate_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
