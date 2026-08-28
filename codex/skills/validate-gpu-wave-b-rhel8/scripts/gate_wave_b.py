#!/usr/bin/env python3
"""Combine two normalized branch results into the Wave B gate."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
from typing import Any, Optional


WORKTREE_ROOT = "/home/tibger01/projects/fornjot"
HANDOFF_ROOT = f"{WORKTREE_ROOT}/push_gpu"
REMOTE_EVIDENCE_ROOT = (
    f"{HANDOFF_ROOT}/private/tmp/to_persist/validation-campaign/wave-b"
)
ATTEMPT_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RUN_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SHA256_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")
SIMULATION_COMMAND = (
    "blk_run --build-clean --sanity --set-lsf-mem-limit 12000 "
    "--no-bsub --no-bsub-build --worker=local --max-jobs 2"
)
FPV_SUMMARY_COMMAND = "ftrun tex_flt -local -batch -auto_run -slots 6"
FPV_CONFIG_INCLUDE = "validation_campaign_disable_prove_cache"
FPV_CONFIG_ASSET = "disable_campaign_prove_cache.yaml"
TRUSTED_FINAL_DRIVER_SHA256 = {
    "run_wave_b_remote.sh": (
        "96dc935912ec90aa5f06398cb3c8fc43c624e67863f33e9fc668ce11034d1515"
    ),
    "run_branch_remote.sh": (
        "844e4f04705ac58fc38c3b5ddf105d0c01c872cd2b8f297b9cf10f5e7685373c"
    ),
}


def fpv_execution_command(fpv_task_dir: str) -> str:
    return (
        f"ftrun tex_flt -include {FPV_CONFIG_INCLUDE} -tcl "
        f"{fpv_task_dir}/capture_up_to_five_cex_vcd.tcl "
        "-local -batch -auto_run -slots 6 -save on_failure"
    )
ORCHESTRATION_KEYS = {
    "SCHEMA_VERSION",
    "WAVE",
    "HOST",
    "CANDIDATE_SHA",
    "CANDIDATE_SHA12",
    "ATTEMPT_TOKEN",
    "WORKTREE_ROOT",
    "RUN_TOKEN",
    "RESULT_ROOT",
    "SIMULATION_WORKTREE",
    "FPV_WORKTREE",
    "SIMULATION_RUN_ID",
    "FPV_RUN_ID",
    "PREPARATION_MODE",
    "BRANCH_LAUNCH_MODE",
    "START_ALL_BEFORE_WAIT",
    "COLLECT_ALL_BRANCHES",
    "SIMULATION_COMMAND",
    "FPV_COMMAND",
    "TASK_DIRS_CREATED_AFTER_PREPARATION",
    "SIMULATION_TASK_DIR",
    "FPV_TASK_DIR",
    "SERIAL_PREPARATION_VERIFIED",
    "BOTH_PREPARATIONS_COMPLETE_EPOCH_NS",
    "SIMULATION_LAUNCH_EPOCH_NS",
    "FPV_LAUNCH_EPOCH_NS",
    "WAIT_BEGAN_EPOCH_NS",
    "SIMULATION_COORDINATOR_PID",
    "FPV_COORDINATOR_PID",
    "STARTED_BRANCHES",
    "ALL_BRANCHES_LAUNCHED_BEFORE_FIRST_WAIT",
    "SIMULATION_BRANCH_STATUS",
    "FPV_BRANCH_STATUS",
    "COLLECTED_BRANCHES",
    "ALL_BRANCHES_COLLECTED",
    "COORDINATOR_FINISHED_UTC",
    "COORDINATOR_FINISHED_EPOCH_NS",
    "WAVE_B_DRIVER_STATUS",
}
PREPARATION_KEYS = {
    "LABEL",
    "WORKTREE",
    "CANDIDATE_SHA",
    "PREPARATION_STARTED_EPOCH_NS",
    "PREPARATION_STARTED_UTC",
    "PREPARATION_FINISHED_EPOCH_NS",
    "PREPARATION_FINISHED_UTC",
    "PREPARATION_STATUS",
}
BRANCH_KEYS = {
    "SCHEMA_VERSION",
    "WAVE",
    "WORKFLOW",
    "CANDIDATE_SHA",
    "ATTEMPT_TOKEN",
    "RUN_TOKEN",
    "WORKTREE",
    "RUN_ID",
    "TASK_DIR",
    "VALIDATION_COMMAND",
    "BRANCH_STARTED_EPOCH_NS",
    "BRANCH_STARTED_UTC",
    "VALIDATION_FINISHED_EPOCH_NS",
    "VALIDATION_FINISHED_UTC",
    "RUNNER_STATUS",
    "ARTIFACT_ARCHIVE",
    "ARTIFACT_FILE_COUNT",
    "ARTIFACT_ARCHIVE_STATUS",
    "BRANCH_FINISHED_EPOCH_NS",
    "BRANCH_FINISHED_UTC",
}
SIMULATION_TEST_STATUSES = ("PASS", "FAIL", "ABORT", "SKIP")
SIMULATION_TEST_RECORD_KEYS = {
    "name",
    "seed",
    "status",
    "substatus",
    "remote_base_file",
    "replay_command",
}
SIMULATION_TEST_EVIDENCE_KEYS = {
    "source",
    "schema_version",
    "record_count",
    "status_counts",
    "verified",
    "evidence_errors",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--simulation-status", required=True, type=int)
    parser.add_argument("--fpv-status", required=True, type=int)
    parser.add_argument("--simulation-summary", type=Path)
    parser.add_argument("--fpv-summary", type=Path)
    parser.add_argument(
        "--attempt-token",
        required=True,
        help="Exact token appended to both retained candidate worktrees.",
    )
    parser.add_argument(
        "--run-token",
        required=True,
        help="Exact final-driver run token recorded by the remote coordinator.",
    )
    parser.add_argument(
        "--evidence-root",
        required=True,
        type=Path,
        help=(
            "Collected final-result directory containing orchestration.env, "
            "preparation/*.env, and results/*/branch.env."
        ),
    )
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--text-output", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_regular_file_within(path: Path, root: Path) -> bool:
    try:
        resolved_path = path.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
    except OSError:
        return False
    return (
        path.is_file()
        and not path.is_symlink()
        and resolved_path.is_relative_to(resolved_root)
    )


def load_env_evidence(
    path: Path, label: str, expected_keys: set[str], evidence_root: Path
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    values: dict[str, str] = {}
    try:
        if not is_regular_file_within(path, evidence_root):
            raise OSError("not a regular file contained by the evidence root")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return values, [f"{label} is unreadable: {exc}"]
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line or "=" not in line:
            errors.append(f"{label} line {line_number} is not KEY=VALUE evidence")
            continue
        key, value = line.split("=", 1)
        if not ENV_KEY_RE.fullmatch(key):
            errors.append(f"{label} line {line_number} has invalid key {key!r}")
            continue
        if key in values:
            errors.append(f"{label} repeats key {key}")
            continue
        values[key] = value
    missing = sorted(expected_keys - set(values))
    unexpected = sorted(set(values) - expected_keys)
    if missing:
        errors.append(f"{label} missing keys: {','.join(missing)}")
    if unexpected:
        errors.append(f"{label} unexpected keys: {','.join(unexpected)}")
    return values, errors


def require_env_values(
    values: dict[str, str],
    expected: dict[str, str],
    label: str,
) -> list[str]:
    errors: list[str] = []
    for key, expected_value in expected.items():
        actual = values.get(key)
        if actual != expected_value:
            errors.append(
                f"{label} {key}={actual!r}; expected {expected_value!r}"
            )
    return errors


def parse_positive_decimal(
    values: dict[str, str], key: str, label: str, errors: list[str]
) -> Optional[int]:
    raw = values.get(key)
    if raw is None or not re.fullmatch(r"[1-9][0-9]*", raw):
        errors.append(f"{label} {key}={raw!r}; expected a positive decimal integer")
        return None
    return int(raw)


def validate_epoch_utc_pair(
    values: dict[str, str],
    epoch_key: str,
    utc_key: str,
    label: str,
    errors: list[str],
) -> Optional[int]:
    epoch_ns = parse_positive_decimal(values, epoch_key, label, errors)
    raw_utc = values.get(utc_key)
    try:
        parsed = datetime.strptime(raw_utc or "", "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        errors.append(
            f"{label} {utc_key}={raw_utc!r}; expected canonical UTC timestamp"
        )
        return epoch_ns
    if epoch_ns is not None:
        epoch_second = epoch_ns // 1_000_000_000
        utc_second = int(parsed.timestamp())
        # The driver calls date separately for the nanoseconds and text values;
        # a legitimate second-boundary rollover may differ by one second.
        if abs(epoch_second - utc_second) > 1:
            errors.append(
                f"{label} {epoch_key}/{utc_key} disagree by more than one second"
            )
    return epoch_ns


def safe_relative_archive_entry(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_archive_evidence(
    evidence_root: Path,
    workflow: str,
    branch: dict[str, str],
    expected_remote_archive: str,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    branch_root = evidence_root / "results" / workflow
    archive = branch_root / "small-artifacts.tar"
    checksum = branch_root / "small-artifacts.tar.sha256"
    file_list = branch_root / "files.list"
    command_file = branch_root / "command.txt"
    for label, path in (
        ("artifact archive", archive),
        ("archive checksum", checksum),
        ("artifact file list", file_list),
        ("command evidence", command_file),
    ):
        if not is_regular_file_within(path, evidence_root):
            errors.append(
                f"{workflow} {label} is missing or escapes the evidence root: {path}"
            )

    expected_command = branch.get("VALIDATION_COMMAND")
    if is_regular_file_within(command_file, evidence_root):
        try:
            command_text = command_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{workflow} command evidence is unreadable: {exc}")
        else:
            if not isinstance(expected_command, str) or command_text != expected_command + "\n":
                errors.append(
                    f"{workflow} command.txt does not contain the exact validation command"
                )

    file_count: Optional[int] = None
    raw_count = branch.get("ARTIFACT_FILE_COUNT")
    if raw_count is None or not re.fullmatch(r"[1-9][0-9]*", raw_count):
        errors.append(
            f"{workflow} ARTIFACT_FILE_COUNT={raw_count!r}; expected a positive integer"
        )
    else:
        file_count = int(raw_count)
    listed_files: list[str] = []
    if is_regular_file_within(file_list, evidence_root):
        try:
            listed_files = file_list.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            errors.append(f"{workflow} artifact file list is unreadable: {exc}")
        else:
            if not listed_files:
                errors.append(f"{workflow} artifact file list is empty")
            if listed_files != sorted(set(listed_files)):
                errors.append(
                    f"{workflow} artifact file list is not sorted and unique"
                )
            unsafe = [entry for entry in listed_files if not safe_relative_archive_entry(entry)]
            if unsafe:
                errors.append(
                    f"{workflow} artifact file list contains unsafe paths: {unsafe!r}"
                )
            if file_count is not None and file_count != len(listed_files):
                errors.append(
                    f"{workflow} artifact file count/list mismatch: "
                    f"branch={file_count} list={len(listed_files)}"
                )

    recorded_digest: Optional[str] = None
    calculated_digest: Optional[str] = None
    if is_regular_file_within(checksum, evidence_root):
        try:
            checksum_lines = checksum.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            errors.append(f"{workflow} archive checksum is unreadable: {exc}")
        else:
            match = (
                SHA256_RE.fullmatch(checksum_lines[0])
                if len(checksum_lines) == 1
                else None
            )
            if match is None:
                errors.append(
                    f"{workflow} archive checksum must be one sha256sum-format line"
                )
            else:
                recorded_digest = match.group(1)
                if match.group(2) != expected_remote_archive:
                    errors.append(
                        f"{workflow} archive checksum names {match.group(2)!r}; "
                        f"expected {expected_remote_archive!r}"
                    )
    if is_regular_file_within(archive, evidence_root):
        try:
            calculated_digest = sha256_file(archive)
        except OSError as exc:
            errors.append(f"{workflow} artifact archive is unreadable: {exc}")
        if recorded_digest is not None and calculated_digest != recorded_digest:
            errors.append(
                f"{workflow} artifact archive SHA-256 mismatch: "
                f"recorded={recorded_digest} calculated={calculated_digest}"
            )
        try:
            with tarfile.open(archive, mode="r:") as bundle:
                members = bundle.getmembers()
                archived_files = [member.name for member in members if member.isfile()]
        except (OSError, tarfile.TarError) as exc:
            errors.append(f"{workflow} artifact archive is not a readable tar: {exc}")
        else:
            special_members = [member.name for member in members if not member.isfile()]
            if special_members:
                errors.append(
                    f"{workflow} artifact archive contains non-regular members: "
                    f"{special_members!r}"
                )
            if archived_files != listed_files:
                errors.append(
                    f"{workflow} artifact archive/file-list mismatch: "
                    f"archive={archived_files!r} list={listed_files!r}"
                )

    return {
        "archive_relative_path": f"results/{workflow}/small-artifacts.tar",
        "archive_sha256": calculated_digest,
        "recorded_archive_sha256": recorded_digest,
        "file_count": file_count,
        "members": listed_files,
    }, errors


def validate_orchestration_evidence(
    args: argparse.Namespace,
    simulation_worktree: dict[str, Any],
    fpv_worktree: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Validate the final driver's raw evidence and return observed provenance."""

    errors: list[str] = []
    if not FULL_SHA_RE.fullmatch(args.candidate_sha):
        errors.append("candidate SHA must be the exact lowercase 40-hex commit")
    if not ATTEMPT_TOKEN_RE.fullmatch(args.attempt_token):
        errors.append(f"orchestration attempt token is unsafe: {args.attempt_token!r}")
    if not RUN_TOKEN_RE.fullmatch(args.run_token):
        errors.append(f"orchestration run token is unsafe: {args.run_token!r}")

    evidence_root = args.evidence_root
    try:
        if evidence_root.is_symlink() or not evidence_root.is_dir():
            raise OSError("not a directory or is a symlink")
        resolved_root = evidence_root.resolve(strict=True)
    except OSError as exc:
        resolved_root = evidence_root
        errors.append(f"Wave B evidence root is unavailable: {exc}")

    paths = {
        "orchestration": evidence_root / "orchestration.env",
        "simulation_preparation": evidence_root / "preparation" / "simulation.env",
        "fpv_preparation": evidence_root / "preparation" / "fpv.env",
        "simulation_branch": evidence_root / "results" / "simulation" / "branch.env",
        "fpv_branch": evidence_root / "results" / "fpv" / "branch.env",
    }
    schemas = {
        "orchestration": ORCHESTRATION_KEYS,
        "simulation_preparation": PREPARATION_KEYS,
        "fpv_preparation": PREPARATION_KEYS,
        "simulation_branch": BRANCH_KEYS,
        "fpv_branch": BRANCH_KEYS,
    }
    raw: dict[str, dict[str, str]] = {}
    raw_digests: dict[str, Optional[str]] = {}
    for name, path in paths.items():
        values, load_errors = load_env_evidence(
            path, name.replace("_", " "), schemas[name], evidence_root
        )
        raw[name] = values
        errors.extend(load_errors)
        try:
            raw_digests[name] = (
                sha256_file(path)
                if is_regular_file_within(path, evidence_root)
                else None
            )
        except OSError as exc:
            raw_digests[name] = None
            errors.append(f"{name.replace('_', ' ')} SHA-256 failed: {exc}")

    orchestration = raw["orchestration"]
    sim_prep = raw["simulation_preparation"]
    fpv_prep = raw["fpv_preparation"]
    sim_branch = raw["simulation_branch"]
    fpv_branch = raw["fpv_branch"]

    candidate12 = args.candidate_sha[:12]
    sim_path = f"{WORKTREE_ROOT}/tmp_gpu_blk_run_{candidate12}_sanity_{args.attempt_token}"
    fpv_path = f"{WORKTREE_ROOT}/tmp_gpu_fpv_run_{candidate12}_{args.attempt_token}"
    remote_result_root = f"{REMOTE_EVIDENCE_ROOT}/final-result-{args.run_token}"
    sim_run_id = f"wave-b-final-{args.run_token}-simulation"
    fpv_run_id = f"wave-b-final-{args.run_token}-fpv"
    sim_task_dir = (
        f"{sim_path}/private/tmp/to_persist/blk-run-remote/{sim_run_id}"
    )
    fpv_task_dir = (
        f"{fpv_path}/private/tmp/to_persist/jaspergold-rhel8-fpv/{fpv_run_id}"
    )
    expected_fpv_command = fpv_execution_command(fpv_task_dir)
    expected_orchestration = {
        "SCHEMA_VERSION": "1",
        "WAVE": "B",
        "HOST": "rhel8-VM",
        "CANDIDATE_SHA": args.candidate_sha,
        "CANDIDATE_SHA12": candidate12,
        "ATTEMPT_TOKEN": args.attempt_token,
        "WORKTREE_ROOT": WORKTREE_ROOT,
        "RUN_TOKEN": args.run_token,
        "RESULT_ROOT": remote_result_root,
        "SIMULATION_WORKTREE": sim_path,
        "FPV_WORKTREE": fpv_path,
        "SIMULATION_RUN_ID": sim_run_id,
        "FPV_RUN_ID": fpv_run_id,
        "PREPARATION_MODE": "serial",
        "BRANCH_LAUNCH_MODE": "parallel",
        "START_ALL_BEFORE_WAIT": "1",
        "COLLECT_ALL_BRANCHES": "1",
        "SIMULATION_COMMAND": SIMULATION_COMMAND,
        "FPV_COMMAND": expected_fpv_command,
        "TASK_DIRS_CREATED_AFTER_PREPARATION": "1",
        "SIMULATION_TASK_DIR": sim_task_dir,
        "FPV_TASK_DIR": fpv_task_dir,
        "SERIAL_PREPARATION_VERIFIED": "1",
        "STARTED_BRANCHES": "simulation,fpv",
        "ALL_BRANCHES_LAUNCHED_BEFORE_FIRST_WAIT": "1",
        "SIMULATION_BRANCH_STATUS": "0",
        "FPV_BRANCH_STATUS": "0",
        "COLLECTED_BRANCHES": "simulation,fpv",
        "ALL_BRANCHES_COLLECTED": "1",
        "WAVE_B_DRIVER_STATUS": "PASS",
    }
    errors.extend(
        require_env_values(orchestration, expected_orchestration, "orchestration")
    )
    if orchestration.get("SIMULATION_BRANCH_STATUS") != str(args.simulation_status):
        errors.append("simulation CLI status contradicts orchestration evidence")
    if orchestration.get("FPV_BRANCH_STATUS") != str(args.fpv_status):
        errors.append("fpv CLI status contradicts orchestration evidence")

    errors.extend(
        require_env_values(
            sim_prep,
            {
                "LABEL": "simulation",
                "WORKTREE": sim_path,
                "CANDIDATE_SHA": args.candidate_sha,
                "PREPARATION_STATUS": "0",
            },
            "simulation preparation",
        )
    )
    errors.extend(
        require_env_values(
            fpv_prep,
            {
                "LABEL": "fpv",
                "WORKTREE": fpv_path,
                "CANDIDATE_SHA": args.candidate_sha,
                "PREPARATION_STATUS": "0",
            },
            "fpv preparation",
        )
    )

    branch_specs = {
        "simulation": (
            sim_branch,
            sim_path,
            sim_run_id,
            sim_task_dir,
            SIMULATION_COMMAND,
        ),
        "fpv": (fpv_branch, fpv_path, fpv_run_id, fpv_task_dir, expected_fpv_command),
    }
    for workflow, (branch, worktree, run_id, task_dir, command) in branch_specs.items():
        expected_archive = f"{remote_result_root}/results/{workflow}/small-artifacts.tar"
        errors.extend(
            require_env_values(
                branch,
                {
                    "SCHEMA_VERSION": "1",
                    "WAVE": "B",
                    "WORKFLOW": workflow,
                    "CANDIDATE_SHA": args.candidate_sha,
                    "ATTEMPT_TOKEN": args.attempt_token,
                    "RUN_TOKEN": args.run_token,
                    "WORKTREE": worktree,
                    "RUN_ID": run_id,
                    "TASK_DIR": task_dir,
                    "VALIDATION_COMMAND": command,
                    "RUNNER_STATUS": "0",
                    "ARTIFACT_ARCHIVE": expected_archive,
                    "ARTIFACT_ARCHIVE_STATUS": "0",
                },
                f"{workflow} branch",
            )
        )

    sim_prep_start = validate_epoch_utc_pair(
        sim_prep,
        "PREPARATION_STARTED_EPOCH_NS",
        "PREPARATION_STARTED_UTC",
        "simulation preparation",
        errors,
    )
    sim_prep_finish = validate_epoch_utc_pair(
        sim_prep,
        "PREPARATION_FINISHED_EPOCH_NS",
        "PREPARATION_FINISHED_UTC",
        "simulation preparation",
        errors,
    )
    fpv_prep_start = validate_epoch_utc_pair(
        fpv_prep,
        "PREPARATION_STARTED_EPOCH_NS",
        "PREPARATION_STARTED_UTC",
        "fpv preparation",
        errors,
    )
    fpv_prep_finish = validate_epoch_utc_pair(
        fpv_prep,
        "PREPARATION_FINISHED_EPOCH_NS",
        "PREPARATION_FINISHED_UTC",
        "fpv preparation",
        errors,
    )
    both_prepared = parse_positive_decimal(
        orchestration,
        "BOTH_PREPARATIONS_COMPLETE_EPOCH_NS",
        "orchestration",
        errors,
    )
    sim_launch = parse_positive_decimal(
        orchestration, "SIMULATION_LAUNCH_EPOCH_NS", "orchestration", errors
    )
    fpv_launch = parse_positive_decimal(
        orchestration, "FPV_LAUNCH_EPOCH_NS", "orchestration", errors
    )
    first_wait = parse_positive_decimal(
        orchestration, "WAIT_BEGAN_EPOCH_NS", "orchestration", errors
    )
    coordinator_finish = validate_epoch_utc_pair(
        orchestration,
        "COORDINATOR_FINISHED_EPOCH_NS",
        "COORDINATOR_FINISHED_UTC",
        "orchestration",
        errors,
    )
    chronology = (
        sim_prep_start,
        sim_prep_finish,
        fpv_prep_start,
        fpv_prep_finish,
        both_prepared,
        sim_launch,
        fpv_launch,
        first_wait,
    )
    if all(value is not None for value in chronology):
        (
            sim_prep_start_value,
            sim_prep_finish_value,
            fpv_prep_start_value,
            fpv_prep_finish_value,
            both_prepared_value,
            sim_launch_value,
            fpv_launch_value,
            first_wait_value,
        ) = (int(value) for value in chronology)
        if not (
            sim_prep_start_value < sim_prep_finish_value
            <= fpv_prep_start_value < fpv_prep_finish_value
            <= both_prepared_value <= sim_launch_value
            <= fpv_launch_value < first_wait_value
        ):
            errors.append(
                "orchestration chronology does not prove serial preparation "
                "followed by both launches before the first wait"
            )

    branch_times: dict[str, dict[str, Optional[int]]] = {}
    for workflow, (branch, _, _, _, _) in branch_specs.items():
        started = validate_epoch_utc_pair(
            branch,
            "BRANCH_STARTED_EPOCH_NS",
            "BRANCH_STARTED_UTC",
            f"{workflow} branch",
            errors,
        )
        validation_finished = validate_epoch_utc_pair(
            branch,
            "VALIDATION_FINISHED_EPOCH_NS",
            "VALIDATION_FINISHED_UTC",
            f"{workflow} branch",
            errors,
        )
        finished = validate_epoch_utc_pair(
            branch,
            "BRANCH_FINISHED_EPOCH_NS",
            "BRANCH_FINISHED_UTC",
            f"{workflow} branch",
            errors,
        )
        launch = sim_launch if workflow == "simulation" else fpv_launch
        ordered = [both_prepared, launch, started, validation_finished, finished, coordinator_finish]
        if all(value is not None for value in ordered):
            (
                prepared_value,
                launch_value,
                started_value,
                validation_finished_value,
                finished_value,
                coordinator_finish_value,
            ) = (int(value) for value in ordered)
            if not (
                prepared_value <= launch_value <= started_value
                < validation_finished_value <= finished_value
                <= coordinator_finish_value
            ):
                errors.append(f"{workflow} branch timestamps contradict its launch/lifecycle")
        branch_times[workflow] = {
            "started_epoch_ns": started,
            "validation_finished_epoch_ns": validation_finished,
            "finished_epoch_ns": finished,
        }

    sim_pid = parse_positive_decimal(
        orchestration, "SIMULATION_COORDINATOR_PID", "orchestration", errors
    )
    fpv_pid = parse_positive_decimal(
        orchestration, "FPV_COORDINATOR_PID", "orchestration", errors
    )
    if sim_pid is not None and fpv_pid is not None and sim_pid == fpv_pid:
        errors.append("simulation and fpv coordinator PIDs are identical")

    archives: dict[str, dict[str, Any]] = {}
    for workflow, (branch, _, _, _, _) in branch_specs.items():
        expected_archive = f"{remote_result_root}/results/{workflow}/small-artifacts.tar"
        archive_evidence, archive_errors = validate_archive_evidence(
            evidence_root, workflow, branch, expected_archive
        )
        archives[workflow] = archive_evidence
        errors.extend(archive_errors)

    if simulation_worktree.get("path") != sim_path:
        errors.append("simulation normalized worktree contradicts final-driver evidence")
    if fpv_worktree.get("path") != fpv_path:
        errors.append("fpv normalized worktree contradicts final-driver evidence")

    observed_orchestration = {
        "branch_launch_mode": orchestration.get("BRANCH_LAUNCH_MODE"),
        "start_all_before_wait": orchestration.get("START_ALL_BEFORE_WAIT") == "1",
        "collect_all_branches": orchestration.get("COLLECT_ALL_BRANCHES") == "1",
        "started_branches": (orchestration.get("STARTED_BRANCHES") or "").split(","),
        "collected_branches": (orchestration.get("COLLECTED_BRANCHES") or "").split(","),
        "attempt_token": orchestration.get("ATTEMPT_TOKEN"),
    }
    evidence = {
        "schema_version": 1,
        "provenance_mode": "REMOTE_FINAL_DRIVER_EVIDENCE",
        "local_evidence_root": str(resolved_root),
        "remote_result_root": orchestration.get("RESULT_ROOT"),
        "run_token": orchestration.get("RUN_TOKEN"),
        "worktree_root": orchestration.get("WORKTREE_ROOT"),
        "raw_env_sha256": raw_digests,
        "branch_times": branch_times,
        "archives": archives,
        "verified": not errors,
    }
    return observed_orchestration, evidence, errors


def canonical_summary_for_comparison(
    summary: dict[str, Any], branch: str
) -> dict[str, Any]:
    """Remove only local materialization paths before provenance comparison."""

    result = copy.deepcopy(summary)
    if branch == "simulation":
        result.pop("source_log", None)
        result.pop("artifacts_dir", None)
        test_evidence = result.get("test_evidence")
        if isinstance(test_evidence, dict):
            test_evidence.pop("source", None)
        for failure in result.get("failures", []):
            if isinstance(failure, dict):
                failure.pop("source", None)
    else:
        result.pop("source", None)
        concurrency = result.get("concurrency")
        if isinstance(concurrency, dict):
            for key in ("source", "process_samples_source", "process_details_source"):
                concurrency.pop(key, None)
    return result


def read_json_object(path: Path, label: str) -> tuple[dict[str, Any], list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [f"{label} is unreadable: {exc}"]
    if not isinstance(value, dict):
        return {}, [f"{label} is not a JSON object"]
    return value, []


def extract_regular_archive(
    archive: Path,
    destination: Path,
    expected_members: list[str],
    label: str,
) -> list[str]:
    errors: list[str] = []
    try:
        destination.mkdir(parents=True, exist_ok=False)
        with tarfile.open(archive, mode="r:") as bundle:
            members = bundle.getmembers()
            names = [member.name for member in members]
            if names != expected_members:
                errors.append(
                    f"{label} extraction member list changed after archive validation"
                )
                return errors
            for member in members:
                if not member.isfile() or not safe_relative_archive_entry(member.name):
                    errors.append(
                        f"{label} refuses non-regular or unsafe member {member.name!r}"
                    )
                    continue
                source = bundle.extractfile(member)
                if source is None:
                    errors.append(f"{label} cannot read member {member.name!r}")
                    continue
                target = destination.joinpath(*PurePosixPath(member.name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    except (OSError, tarfile.TarError) as exc:
        errors.append(f"{label} extraction failed: {exc}")
    return errors


def parse_status_marker(path: Path, key: str, label: str) -> tuple[Optional[int], list[str]]:
    errors: list[str] = []
    if not is_regular_file_within(path, path.parents[2]):
        return None, [f"{label} is missing: {path}"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, [f"{label} is unreadable: {exc}"]
    matches = re.findall(rf"(?m)^{re.escape(key)}=([0-9]+)$", text)
    if len(matches) != 1:
        errors.append(f"{label} must contain exactly one {key}=<status> marker")
        return None, errors
    return int(matches[0]), errors


def parse_unique_text_marker(
    path: Path, key: str, label: str
) -> tuple[Optional[str], list[str]]:
    if not is_regular_file_within(path, path.parents[2]):
        return None, [f"{label} is missing: {path}"]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, [f"{label} is unreadable: {exc}"]
    matches = re.findall(rf"(?m)^{re.escape(key)}=([^\r\n]+)$", text)
    if len(matches) != 1:
        return None, [f"{label} must contain exactly one {key}=<value> marker"]
    return matches[0], []


def validate_five_minute_proof_limit(
    run_log_path: Path, archive_root: Path
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        if not is_regular_file_within(run_log_path, archive_root):
            raise OSError("not a contained regular file")
        run_log = run_log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"verified": False}, [f"fpv run-limit evidence is unreadable: {exc}"]

    task_limits = re.findall(
        r"Identified\s+([A-Za-z0-9_.-]+)\s+with run limit\s+([1-9][0-9]*[smh])",
        run_log,
    )
    highest_limits = re.findall(
        r"Highest run limit for this step is\s+([0-9]{2})h\s+"
        r"([0-9]{2})m\s+([0-9]{2})s",
        run_log,
    )
    total_limits = re.findall(
        r"Total time limit calculated is:\s+([0-9]{2})h\s+"
        r"([0-9]{2})m\s+([0-9]{2})s",
        run_log,
    )
    marker_matches = list(
        re.finditer(
            r"LOCAL_FPV_CONCURRENCY:\s+max_local_jobs=6\s+"
            r"per_engine_max_local_jobs=2",
            run_log,
        )
    )
    post_marker_log = run_log[marker_matches[-1].end() :] if marker_matches else ""
    effective_seconds = [
        int(value)
        for value in re.findall(
            r"(?m)^.*?\btime_limit\s+=\s+([0-9]+)s\s*$",
            post_marker_log,
        )
    ]

    if task_limits != [("prj_prove_all", "5m")]:
        errors.append(
            "fpv run log does not uniquely identify prj_prove_all with run limit 5m"
        )
    if highest_limits != [("00", "05", "00")]:
        errors.append("fpv run log does not uniquely report highest run limit 00h 05m 00s")
    if total_limits != [("00", "05", "00")]:
        errors.append("fpv run log does not uniquely report total time limit 00h 05m 00s")
    if not marker_matches:
        errors.append("fpv run-limit evidence lacks the concurrency wrapper marker")
    if not effective_seconds or any(value != 300 for value in effective_seconds):
        errors.append(
            "fpv post-wrapper effective time_limit settings are missing or not all 300s"
        )

    return {
        "verified": not errors,
        "prove_task": task_limits[0][0] if len(task_limits) == 1 else None,
        "requested_limit": task_limits[0][1] if len(task_limits) == 1 else None,
        "highest_limit": (
            "00h 05m 00s" if highest_limits == [("00", "05", "00")] else None
        ),
        "total_limit": (
            "00h 05m 00s" if total_limits == [("00", "05", "00")] else None
        ),
        "post_wrapper_time_limit_seconds": effective_seconds,
    }, errors


def run_normalizer(
    command: list[str], output_json: Path, log_path: Path, label: str
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_path.write_text(completed.stdout, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {}, [f"{label} could not run: {exc}"]
    if not output_json.is_file():
        errors.append(
            f"{label} produced no JSON (status={completed.returncode}); see {log_path}"
        )
        return {}, errors
    summary, load_errors = read_json_object(output_json, label)
    errors.extend(load_errors)
    if completed.returncode not in (0, 1, 2):
        errors.append(
            f"{label} returned unsupported status {completed.returncode}; see {log_path}"
        )
    return summary, errors


def validate_driver_payload(
    args: argparse.Namespace,
    sibling_root: Path,
    simulation_extracted_root: Optional[Path],
    simulation_task_rel: str,
    fpv_extracted_root: Optional[Path],
    fpv_task_rel: str,
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    required_names = (
        "run_wave_b_remote.sh",
        "run_branch_remote.sh",
        "setup_worktree.sh",
        "run_blk_run.sh",
        "run_fpv.sh",
        FPV_CONFIG_ASSET,
        "capture_up_to_five_cex_vcd.tcl",
        "count_run_jg_proof_processes.awk",
        "summarize_fpv_results.py",
    )
    payload_root = args.evidence_root / "driver-payload"
    manifest_path = args.evidence_root / "payload.sha256"
    manifest: dict[str, str] = {}
    try:
        if not is_regular_file_within(manifest_path, args.evidence_root):
            raise OSError("not a contained regular file")
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return manifest, [f"driver payload manifest is unreadable: {exc}"]
    expected_remote_prefix = (
        f"{REMOTE_EVIDENCE_ROOT}/final-driver-{args.run_token}/payload/"
    )
    for line_number, line in enumerate(lines, 1):
        match = SHA256_RE.fullmatch(line)
        if match is None:
            errors.append(
                f"driver payload manifest line {line_number} is not sha256sum format"
            )
            continue
        digest, remote_path = match.groups()
        if not remote_path.startswith(expected_remote_prefix):
            errors.append(
                f"driver payload manifest path is outside exact run: {remote_path!r}"
            )
            continue
        name = remote_path.removeprefix(expected_remote_prefix)
        if "/" in name or name not in required_names:
            errors.append(f"driver payload manifest has unexpected member {name!r}")
            continue
        if name in manifest:
            errors.append(f"driver payload manifest repeats {name}")
            continue
        manifest[name] = digest
    if set(manifest) != set(required_names):
        errors.append(
            "driver payload manifest members mismatch: "
            f"actual={sorted(manifest)} expected={sorted(required_names)}"
        )

    canonical_sources = {
        "setup_worktree.sh": sibling_root
        / "setup-gpu-repo-rhel8/scripts/setup_worktree.sh",
        "run_blk_run.sh": sibling_root / "blk-run-remote/scripts/run_blk_run.sh",
        "run_fpv.sh": sibling_root / "jaspergold-rhel8-fpv/scripts/run_fpv.sh",
        FPV_CONFIG_ASSET: sibling_root
        / "jaspergold-rhel8-fpv/assets"
        / FPV_CONFIG_ASSET,
        "capture_up_to_five_cex_vcd.tcl": sibling_root
        / "jaspergold-rhel8-fpv/assets/capture_up_to_five_cex_vcd.tcl",
        "count_run_jg_proof_processes.awk": sibling_root
        / "jaspergold-rhel8-fpv/scripts/count_run_jg_proof_processes.awk",
        "summarize_fpv_results.py": sibling_root
        / "jaspergold-rhel8-fpv/scripts/summarize_fpv_results.py",
    }
    for name in required_names:
        payload_file = payload_root / name
        if not is_regular_file_within(payload_file, args.evidence_root):
            errors.append(f"collected driver payload is missing {name}")
            continue
        digest = sha256_file(payload_file)
        if manifest.get(name) != digest:
            errors.append(
                f"collected driver payload {name} SHA-256 does not match manifest"
            )
        trusted_driver_digest = TRUSTED_FINAL_DRIVER_SHA256.get(name)
        if trusted_driver_digest is not None and digest != trusted_driver_digest:
            errors.append(
                f"collected driver payload {name} differs from trusted final driver"
            )
        canonical = canonical_sources.get(name)
        if canonical is not None:
            if canonical.is_symlink() or not canonical.is_file():
                errors.append(f"trusted staged payload source is missing: {canonical}")
            elif sha256_file(canonical) != digest:
                errors.append(
                    f"collected driver payload {name} differs from staged executable"
                )
    cache_asset = payload_root / FPV_CONFIG_ASSET
    if is_regular_file_within(cache_asset, args.evidence_root):
        try:
            cache_asset_text = cache_asset.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"campaign prove-cache config is unreadable: {exc}")
        else:
            required_config_fragments = (
                f'"{FPV_CONFIG_INCLUDE}":',
                "proofmaster:\n        enable: false",
                "prove_cache:\n        load: false\n        save: false",
            )
            for fragment in required_config_fragments:
                if fragment not in cache_asset_text:
                    errors.append(
                        "campaign prove-cache config lacks required exact setting: "
                        f"{fragment!r}"
                    )
    if simulation_extracted_root is not None:
        archived_runner = (
            simulation_extracted_root / simulation_task_rel / "run_blk_run.sh"
        )
        if not is_regular_file_within(archived_runner, simulation_extracted_root):
            errors.append("simulation archive lacks its executed run_blk_run.sh")
        elif manifest.get("run_blk_run.sh") != sha256_file(archived_runner):
            errors.append(
                "simulation archived run_blk_run.sh differs from driver payload manifest"
            )
    if fpv_extracted_root is not None:
        fpv_task_root = fpv_extracted_root / fpv_task_rel
        ownership_marker = fpv_task_root / ".wave-b-final-driver-token"
        try:
            ownership_token = ownership_marker.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"fpv archived task ownership marker is unreadable: {exc}")
        else:
            if ownership_token != args.run_token + "\n":
                errors.append("fpv archived task ownership marker has the wrong run token")
        for name in (
            "run_fpv.sh",
            FPV_CONFIG_ASSET,
            "capture_up_to_five_cex_vcd.tcl",
            "count_run_jg_proof_processes.awk",
            "summarize_fpv_results.py",
        ):
            archived_file = fpv_task_root / name
            if not is_regular_file_within(archived_file, fpv_extracted_root):
                errors.append(f"fpv archive lacks its executed {name}")
            elif manifest.get(name) != sha256_file(archived_file):
                errors.append(
                    f"fpv archived {name} differs from driver payload manifest"
                )
    return manifest, errors


def bind_summaries_to_run_artifacts(
    args: argparse.Namespace,
    orchestration_evidence: dict[str, Any],
    supplied_simulation: dict[str, Any],
    supplied_fpv: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
    """Recompute both summaries only from members of the validated archives."""

    errors: list[str] = []
    evidence_root = args.evidence_root
    candidate12 = args.candidate_sha[:12]
    sim_worktree = (
        f"{WORKTREE_ROOT}/tmp_gpu_blk_run_{candidate12}_sanity_{args.attempt_token}"
    )
    fpv_worktree = f"{WORKTREE_ROOT}/tmp_gpu_fpv_run_{candidate12}_{args.attempt_token}"
    sim_run_id = f"wave-b-final-{args.run_token}-simulation"
    fpv_run_id = f"wave-b-final-{args.run_token}-fpv"
    sim_task_rel = f"private/tmp/to_persist/blk-run-remote/{sim_run_id}"
    fpv_task_rel = f"private/tmp/to_persist/jaspergold-rhel8-fpv/{fpv_run_id}"

    gate_derived_root = evidence_root / "gate-derived"
    try:
        if gate_derived_root.exists() and (
            gate_derived_root.is_symlink() or not gate_derived_root.is_dir()
        ):
            raise OSError("gate-derived exists but is not a real directory")
        gate_derived_root.mkdir(exist_ok=True)
        resolved_evidence_root = evidence_root.resolve(strict=True)
        if not gate_derived_root.resolve(strict=True).is_relative_to(
            resolved_evidence_root
        ):
            raise OSError("gate-derived escapes the evidence root")
        gate_run_root = gate_derived_root / (
            f"{args.run_token}-{os.getpid()}-{time.time_ns()}"
        )
        gate_run_root.mkdir(exist_ok=False)
        if not gate_run_root.resolve(strict=True).is_relative_to(
            resolved_evidence_root
        ):
            raise OSError("derived run directory escapes the evidence root")
    except OSError as exc:
        provenance = {
            "schema_version": 1,
            "mode": "RECOMPUTED_FROM_VALIDATED_ARCHIVES",
            "derived_root": None,
            "verified": False,
        }
        return {}, {}, provenance, [f"cannot create contained gate derivation: {exc}"]
    extracted: dict[str, Path] = {}
    for workflow in ("simulation", "fpv"):
        archive_info = orchestration_evidence.get("archives", {}).get(workflow, {})
        members = archive_info.get("members")
        if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
            errors.append(f"{workflow} validated archive member list is unavailable")
            continue
        archive = evidence_root / "results" / workflow / "small-artifacts.tar"
        destination = gate_run_root / workflow / "worktree"
        errors.extend(
            extract_regular_archive(
                archive, destination, members, f"{workflow} artifact archive"
            )
        )
        extracted[workflow] = destination

    sim_root = extracted.get("simulation")
    fpv_root = extracted.get("fpv")
    required_simulation = [
        f"{sim_task_rel}/.wave-b-final-driver-token",
        f"{sim_task_rel}/run_blk_run.sh",
        f"{sim_task_rel}/metadata.env",
        f"{sim_task_rel}/exit-status",
        f"{sim_task_rel}/run.log",
        "verification/tb_deploy/tb_tex/sim2/regression.json",
        "verification/tb_deploy/tb_tex/sim2/logs_tests/cache.sqlite",
    ]
    required_fpv = [
        f"{fpv_task_rel}/run.log",
        f"{fpv_task_rel}/proof-process-samples.rpt",
        f"{fpv_task_rel}/proof-process-details.tsv",
        f"{fpv_task_rel}/work/fts_run_tex_flt/proof_report.json",
        f"{fpv_task_rel}/work/fts_run_tex_flt/fpv_property_summary.json",
        f"{fpv_task_rel}/work/fts_run_tex_flt/run.cmd",
    ]
    for workflow, root, required in (
        ("simulation", sim_root, required_simulation),
        ("fpv", fpv_root, required_fpv),
    ):
        if root is None:
            continue
        for member in required:
            path = root.joinpath(*PurePosixPath(member).parts)
            if not is_regular_file_within(path, root):
                errors.append(f"{workflow} archive lacks required run-bound member {member}")

    if sim_root is not None:
        token_path = sim_root / sim_task_rel / ".wave-b-final-driver-token"
        try:
            if token_path.read_text(encoding="utf-8") != args.run_token + "\n":
                errors.append("simulation task ownership token does not match run token")
        except (OSError, UnicodeError) as exc:
            errors.append(f"simulation task ownership token is unreadable: {exc}")
        metadata_path = sim_root / sim_task_rel / "metadata.env"
        metadata, metadata_errors = load_env_evidence(
            metadata_path,
            "simulation task metadata",
            {"WORKTREE", "RUN_ID", "REGRESSION", "TB_DIR", "SIM_DIR", "BLK_RUN_OPTIONS"},
            sim_root,
        )
        errors.extend(metadata_errors)
        errors.extend(
            require_env_values(
                metadata,
                {
                    "WORKTREE": sim_worktree,
                    "RUN_ID": sim_run_id,
                    "REGRESSION": "sanity",
                    "TB_DIR": f"{sim_worktree}/verification/tb_deploy/tb_tex",
                    "SIM_DIR": f"{sim_worktree}/verification/tb_deploy/tb_tex/sim2",
                    "BLK_RUN_OPTIONS": (
                        "--build-clean --sanity --set-lsf-mem-limit 12000 "
                        "--no-bsub --no-bsub-build --worker=local --max-jobs 2"
                    ),
                },
                "simulation task metadata",
            )
        )
        try:
            if (sim_root / sim_task_rel / "exit-status").read_text(encoding="utf-8") != "0\n":
                errors.append("simulation archived exit-status is not zero")
        except (OSError, UnicodeError) as exc:
            errors.append(f"simulation archived exit-status is unreadable: {exc}")

    sim_console = evidence_root / "results" / "simulation" / "remote-console.log"
    fpv_console = evidence_root / "results" / "fpv" / "remote-console.log"
    sim_console_status, marker_errors = parse_status_marker(
        sim_console, "REMOTE_BLK_RUN_STATUS", "simulation remote console"
    )
    errors.extend(marker_errors)
    fpv_ftrun_status, marker_errors = parse_status_marker(
        fpv_console, "FTRUN_STATUS", "fpv remote console"
    )
    errors.extend(marker_errors)
    if sim_console_status != 0:
        errors.append(f"simulation remote console status={sim_console_status!r}; expected 0")
    if fpv_ftrun_status != 0:
        errors.append(f"fpv FTRUN_STATUS={fpv_ftrun_status!r}; expected 0")

    expected_fpv_markers = {
        "FPV_CONFIG_FRAGMENT": f"{fpv_worktree}/{fpv_task_rel}/{FPV_CONFIG_ASSET}",
        "FPV_CONFIG_INCLUDE": FPV_CONFIG_INCLUDE,
        "FPV_PROOF_CACHE_MODE": "DISABLED",
        "FPV_FTRUN_INVOCATION": (
            f"{fpv_worktree}/{fpv_task_rel}/ftrun-invocation.rpt"
        ),
    }
    observed_fpv_markers: dict[str, Optional[str]] = {}
    for marker, expected in expected_fpv_markers.items():
        observed, marker_errors = parse_unique_text_marker(
            fpv_console, marker, "fpv remote console"
        )
        observed_fpv_markers[marker] = observed
        errors.extend(marker_errors)
        if observed is not None and observed != expected:
            errors.append(
                f"fpv remote console {marker}={observed!r}; expected {expected!r}"
            )

    sibling_root = Path(__file__).resolve().parents[2]
    sim_tool = sibling_root / "blk-run-remote" / "scripts" / "summarize_blk_run.py"
    fpv_tool = sibling_root / "jaspergold-rhel8-fpv" / "scripts" / "summarize_fpv_results.py"
    for label, tool in (("simulation normalizer", sim_tool), ("fpv normalizer", fpv_tool)):
        if tool.is_symlink() or not tool.is_file():
            errors.append(f"{label} is unavailable: {tool}")
    payload_manifest, payload_errors = validate_driver_payload(
        args, sibling_root, sim_root, sim_task_rel, fpv_root, fpv_task_rel
    )
    errors.extend(payload_errors)

    recomputed_simulation: dict[str, Any] = {}
    if sim_root is not None and sim_tool.is_file():
        sim_json = gate_run_root / "simulation-summary.json"
        sim_report = gate_run_root / "simulation-summary.rpt"
        recomputed_simulation, normalizer_errors = run_normalizer(
            [
                sys.executable,
                str(sim_tool),
                "--log",
                str(sim_root / sim_task_rel / "run.log"),
                "--artifacts-dir",
                str(sim_root / "verification/tb_deploy/tb_tex"),
                "--json-output",
                str(sim_json),
                "--text-output",
                str(sim_report),
                "--status",
                str(sim_console_status if sim_console_status is not None else 255),
                "--candidate-sha",
                args.candidate_sha,
                "--host",
                "rhel8-VM",
                "--worktree",
                sim_worktree,
                "--regression",
                "sanity",
            ],
            sim_json,
            gate_run_root / "simulation-normalizer.log",
            "run-bound simulation normalizer",
        )
        errors.extend(normalizer_errors)

    recomputed_fpv: dict[str, Any] = {}
    fpv_proof_limit_evidence: dict[str, Any] = {"verified": False}
    if fpv_root is not None and fpv_tool.is_file():
        fpv_json = gate_run_root / "fpv-summary.json"
        fpv_report = gate_run_root / "fpv-summary.rpt"
        fpv_base = fpv_root / fpv_task_rel
        fpv_proof_limit_evidence, proof_limit_errors = (
            validate_five_minute_proof_limit(fpv_base / "run.log", fpv_root)
        )
        errors.extend(proof_limit_errors)
        archived_fpv_path = fpv_base / "work/fts_run_tex_flt/fpv_property_summary.json"
        archived_fpv, archived_errors = read_json_object(
            archived_fpv_path, "archived remote fpv summary"
        )
        errors.extend(archived_errors)
        fpv_normalizer_command = [
            sys.executable,
            str(fpv_tool),
            "--input",
            str(fpv_base / "work/fts_run_tex_flt/proof_report.json"),
            "--text-output",
            str(fpv_report),
            "--json-output",
            str(fpv_json),
            "--ftrun-status",
            str(fpv_ftrun_status if fpv_ftrun_status is not None else 255),
            "--candidate-sha",
            args.candidate_sha,
            "--host",
            "rhel8-VM",
            "--worktree",
            fpv_worktree,
            "--jobs",
            "6",
            "--proof-limit",
            "5m",
            "--cex-save-limit",
            "5",
            "--run-log",
            str(fpv_base / "run.log"),
            "--process-samples",
            str(fpv_base / "proof-process-samples.rpt"),
        ]
        archived_concurrency = archived_fpv.get("concurrency")
        if isinstance(archived_concurrency, dict) and archived_concurrency.get(
            "process_details_source"
        ) is not None:
            fpv_normalizer_command.extend(
                ["--process-details", str(fpv_base / "proof-process-details.tsv")]
            )
        recomputed_fpv, normalizer_errors = run_normalizer(
            fpv_normalizer_command,
            fpv_json,
            gate_run_root / "fpv-normalizer.log",
            "run-bound fpv normalizer",
        )
        errors.extend(normalizer_errors)
        if archived_fpv and recomputed_fpv and (
            canonical_summary_for_comparison(archived_fpv, "fpv")
            != canonical_summary_for_comparison(recomputed_fpv, "fpv")
        ):
            errors.append("archived remote fpv summary differs from run-bound recomputation")

    if supplied_simulation and recomputed_simulation and (
        canonical_summary_for_comparison(supplied_simulation, "simulation")
        != canonical_summary_for_comparison(recomputed_simulation, "simulation")
    ):
        errors.append("supplied simulation summary differs from run-bound recomputation")
    if supplied_fpv and recomputed_fpv and (
        canonical_summary_for_comparison(supplied_fpv, "fpv")
        != canonical_summary_for_comparison(recomputed_fpv, "fpv")
    ):
        errors.append("supplied fpv summary differs from run-bound recomputation")

    actual_run_cmd = ""
    recorded_ftrun_invocation = ""
    effective_config_sha256: Optional[str] = None
    if fpv_root is not None:
        expected_run_cmd = fpv_execution_command(f"{fpv_worktree}/{fpv_task_rel}")
        run_cmd_path = fpv_root / fpv_task_rel / "work/fts_run_tex_flt/run.cmd"
        try:
            actual_run_cmd = run_cmd_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            errors.append(f"fpv archived run.cmd is unreadable: {exc}")
        if actual_run_cmd != expected_run_cmd:
            errors.append(
                f"fpv actual run.cmd={actual_run_cmd!r}; expected {expected_run_cmd!r}"
            )

        invocation_path = fpv_root / fpv_task_rel / "ftrun-invocation.rpt"
        try:
            recorded_ftrun_invocation = invocation_path.read_text(
                encoding="utf-8"
            ).strip()
        except (OSError, UnicodeError) as exc:
            errors.append(f"fpv archived ftrun invocation is unreadable: {exc}")
        if recorded_ftrun_invocation != expected_run_cmd:
            errors.append(
                "fpv recorded ftrun invocation="
                f"{recorded_ftrun_invocation!r}; expected {expected_run_cmd!r}"
            )

        effective_config_path = (
            fpv_root / fpv_task_rel / "work/fts_run_tex_flt/config.json"
        )
        effective_config, config_errors = read_json_object(
            effective_config_path, "fpv effective FTRun config"
        )
        errors.extend(config_errors)
        if effective_config.get("target_name") != "tex_flt":
            errors.append(
                "fpv effective config target_name="
                f"{effective_config.get('target_name', 'MISSING')!r}; "
                "expected 'tex_flt'"
            )
        try:
            effective_config_sha256 = sha256_file(effective_config_path)
        except OSError:
            effective_config_sha256 = None
        jg_config: Any = effective_config
        for key in ("target", "tool_config", "jg"):
            if isinstance(jg_config, dict):
                jg_config = jg_config.get(key)
            else:
                jg_config = None
        expected_effective_settings = {
            "proofmaster.enable": False,
            "prove_cache.load": False,
            "prove_cache.save": False,
            "local_prove_cache_engines": False,
        }
        observed_effective_settings: dict[str, Any] = {}
        if not isinstance(jg_config, dict):
            errors.append("fpv effective config lacks target.tool_config.jg")
        else:
            for dotted_key, expected in expected_effective_settings.items():
                observed: Any = jg_config
                for part in dotted_key.split("."):
                    observed = observed.get(part) if isinstance(observed, dict) else None
                observed_effective_settings[dotted_key] = observed
                if observed is not expected:
                    errors.append(
                        f"fpv effective config {dotted_key}={observed!r}; "
                        f"expected {expected!r}"
                    )
    else:
        observed_effective_settings = {}

    provenance = {
        "schema_version": 1,
        "mode": "RECOMPUTED_FROM_VALIDATED_ARCHIVES",
        "derived_root": str(gate_run_root.resolve()),
        "simulation_summary_sha256": (
            hashlib.sha256(
                (json.dumps(recomputed_simulation, sort_keys=True) + "\n").encode()
            ).hexdigest()
            if recomputed_simulation
            else None
        ),
        "fpv_summary_sha256": (
            hashlib.sha256(
                (json.dumps(recomputed_fpv, sort_keys=True) + "\n").encode()
            ).hexdigest()
            if recomputed_fpv
            else None
        ),
        "fpv_actual_run_command": actual_run_cmd or None,
        "fpv_recorded_ftrun_invocation": recorded_ftrun_invocation or None,
        "fpv_console_config_markers": observed_fpv_markers,
        "fpv_effective_config_sha256": effective_config_sha256,
        "fpv_effective_cache_settings": observed_effective_settings,
        "fpv_proof_limit_evidence": fpv_proof_limit_evidence,
        "payload_sha256": payload_manifest,
        "verified": not errors,
    }
    return recomputed_simulation, recomputed_fpv, provenance, errors


def validate_worktree_identity(
    result: dict[str, Any],
    branch: str,
    candidate_sha: str,
    regression: Optional[str] = None,
) -> tuple[dict[str, Any], list[str]]:
    """Independently bind a retained path to branch, candidate, and attempt."""

    candidate_sha12 = candidate_sha[:12].lower()
    if branch == "simulation":
        assert regression is not None
        prefix = f"{WORKTREE_ROOT}/tmp_gpu_blk_run_{candidate_sha12}_{regression}"
        workflow = "blk-run"
    else:
        prefix = f"{WORKTREE_ROOT}/tmp_gpu_fpv_run_{candidate_sha12}"
        workflow = "fpv"
    path = result.get("worktree")
    match = (
        re.fullmatch(
            rf"{re.escape(prefix)}(?:_(?P<attempt>[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}))?",
            path,
        )
        if isinstance(path, str)
        else None
    )
    errors: list[str] = []
    attempt_token: Optional[str] = None
    if match is None:
        errors.append(
            f"{branch} worktree={path!r}; expected isolated exact-candidate path "
            f"{prefix}[_ATTEMPT_TOKEN]"
        )
    else:
        attempt_token = match.group("attempt")
    identity: dict[str, Any] = {
        "schema_version": 1,
        "validated": match is not None,
        "path": path,
        "workflow": workflow,
        "candidate_sha": candidate_sha,
        "candidate_sha12": candidate_sha12,
        "attempt_token": attempt_token,
    }
    if regression is not None:
        identity["regression"] = regression
    claimed = result.get("worktree_identity")
    if claimed is not None and claimed != identity:
        errors.append(
            f"{branch} normalized worktree identity does not match the retained path"
        )
    return identity, errors


def load_branch(path: Optional[Path], branch: str, candidate: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if path is None:
        # The authoritative summaries are recomputed from the validated branch
        # archives. A supplied summary is only an optional drift cross-check.
        return {}, []
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"branch": branch, "classification": "ERROR"}, [f"{branch} summary unreadable: {exc}"]
    if not isinstance(result, dict):
        return {"branch": branch, "classification": "ERROR"}, [f"{branch} summary is not an object"]
    if result.get("schema_version") != 1:
        errors.append(f"{branch} schema version is not 1")
    if result.get("wave") != "B":
        errors.append(f"{branch} summary identifies wave={result.get('wave')!r}")
    if result.get("branch") != branch:
        errors.append(f"{branch} summary identifies branch={result.get('branch')!r}")
    if result.get("candidate_sha") != candidate:
        errors.append(f"{branch} candidate does not match {candidate}")
    return result, errors


def is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_simulation_tests(
    simulation: dict[str, Any],
    canonical: Any,
    expected_worktree: str,
) -> list[str]:
    """Validate the collected blk_run SQLite ledger independently of its claim."""
    errors: list[str] = []
    if simulation.get("test_records_verified") is not True:
        errors.append(
            "simulation test_records_verified="
            f"{simulation.get('test_records_verified', 'MISSING')!r}; expected True"
        )

    evidence = simulation.get("test_evidence")
    if not isinstance(evidence, dict):
        errors.append("simulation per-test evidence is missing")
        evidence = {}
    elif set(evidence) != SIMULATION_TEST_EVIDENCE_KEYS:
        errors.append(
            "simulation per-test evidence schema mismatch: "
            f"keys={sorted(evidence)} expected={sorted(SIMULATION_TEST_EVIDENCE_KEYS)}"
        )

    if evidence.get("verified") is not True:
        errors.append(
            "simulation per-test evidence verified="
            f"{evidence.get('verified', 'MISSING')!r}; expected True"
        )
    if evidence.get("evidence_errors") != []:
        errors.append(
            "simulation per-test evidence errors="
            f"{evidence.get('evidence_errors', 'MISSING')!r}"
        )
    source = evidence.get("source")
    if not isinstance(source, str) or not source.endswith("/sim2/logs_tests/cache.sqlite"):
        errors.append(
            "simulation per-test evidence source is not a collected "
            f"sim2/logs_tests/cache.sqlite path: {source!r}"
        )
    cache_schema = evidence.get("schema_version")
    if not isinstance(cache_schema, str) or not cache_schema.strip():
        errors.append(
            f"simulation cache.sqlite schema_version={cache_schema!r}; expected nonempty text"
        )

    status_counts = evidence.get("status_counts")
    if not isinstance(status_counts, dict):
        errors.append("simulation per-test status counts are missing")
        status_counts = {}
    elif set(status_counts) != set(SIMULATION_TEST_STATUSES):
        errors.append(
            "simulation per-test status-count schema mismatch: "
            f"keys={sorted(status_counts)} expected={list(SIMULATION_TEST_STATUSES)}"
        )
    for status in SIMULATION_TEST_STATUSES:
        if not is_nonnegative_int(status_counts.get(status)):
            errors.append(
                f"simulation per-test status count {status}="
                f"{status_counts.get(status, 'MISSING')!r}; expected a nonnegative integer"
            )

    tests = simulation.get("tests")
    if not isinstance(tests, list) or not tests:
        errors.append("simulation per-test records are missing or empty")
        tests = []
    record_count = evidence.get("record_count")
    if not is_nonnegative_int(record_count) or record_count == 0:
        errors.append(
            f"simulation per-test record_count={record_count!r}; expected a positive integer"
        )
    if is_nonnegative_int(record_count) and record_count != len(tests):
        errors.append(
            "simulation per-test record count/list mismatch: "
            f"evidence={record_count} records={len(tests)}"
        )

    if isinstance(canonical, dict):
        canonical_total = canonical.get("total")
        if is_nonnegative_int(record_count) and record_count != canonical_total:
            errors.append(
                "simulation per-test/canonical total mismatch: "
                f"records={record_count} canonical={canonical_total!r}"
            )
        for status in SIMULATION_TEST_STATUSES:
            canonical_count = canonical.get(status.lower())
            if status_counts.get(status) != canonical_count:
                errors.append(
                    f"simulation per-test/canonical {status} mismatch: "
                    f"tests={status_counts.get(status, 'MISSING')!r} "
                    f"canonical={canonical_count!r}"
                )

    observed_counts = {status: 0 for status in SIMULATION_TEST_STATUSES}
    identities: set[tuple[str, int]] = set()
    ordering_keys: list[tuple[str, int]] = []
    for index, record in enumerate(tests):
        label = f"simulation test record {index}"
        if not isinstance(record, dict):
            errors.append(f"{label} is not an object")
            continue
        if set(record) != SIMULATION_TEST_RECORD_KEYS:
            errors.append(
                f"{label} schema mismatch: keys={sorted(record)} "
                f"expected={sorted(SIMULATION_TEST_RECORD_KEYS)}"
            )

        name = record.get("name")
        seed = record.get("seed")
        status = record.get("status")
        substatus = record.get("substatus")
        remote_base_file = record.get("remote_base_file")
        replay_command = record.get("replay_command")
        name_valid = isinstance(name, str) and bool(name.strip())
        seed_valid = is_nonnegative_int(seed)
        if not name_valid:
            errors.append(f"{label} has invalid name={name!r}")
        elif not name.endswith("__sanity"):
            errors.append(f"{label} name is not a sanity test: {name!r}")
        if not seed_valid:
            errors.append(f"{label} has invalid seed={seed!r}")
        if status not in SIMULATION_TEST_STATUSES:
            errors.append(f"{label} has invalid status={status!r}")
        else:
            observed_counts[status] += 1
        if substatus is not None and not isinstance(substatus, str):
            errors.append(f"{label} has invalid substatus={substatus!r}")
        if (
            not isinstance(remote_base_file, str)
            or ".." in PurePosixPath(remote_base_file).parts
            or PurePosixPath(remote_base_file).parts[
                : len(PurePosixPath(expected_worktree).parts)
            ]
            != PurePosixPath(expected_worktree).parts
            or remote_base_file == expected_worktree
        ):
            errors.append(
                f"{label} remote_base_file is outside the retained worktree: "
                f"{remote_base_file!r}"
            )

        replay_tokens: list[str] = []
        if not isinstance(replay_command, str) or not replay_command.strip():
            errors.append(f"{label} has invalid replay_command={replay_command!r}")
        else:
            try:
                replay_tokens = shlex.split(replay_command)
            except ValueError as exc:
                errors.append(f"{label} replay_command is not shell-parseable: {exc}")
        if replay_tokens:
            if replay_tokens[0] != "blk_val":
                errors.append(f"{label} replay command does not invoke blk_val")
            seed_tokens = {f"--seed={seed}"} if seed_valid else set()
            if seed_valid:
                seed_tokens.add(str(seed))
            seed_present = f"--seed={seed}" in replay_tokens if seed_valid else False
            if seed_valid and "--seed" in replay_tokens:
                seed_index = replay_tokens.index("--seed")
                seed_present = (
                    seed_index + 1 < len(replay_tokens)
                    and replay_tokens[seed_index + 1] in seed_tokens
                )
            if seed_valid and not seed_present:
                errors.append(f"{label} replay command does not preserve seed {seed}")
            if name_valid and name not in replay_tokens:
                errors.append(f"{label} replay command does not preserve test {name}")

        if name_valid and seed_valid:
            identity = (name, seed)
            if identity in identities:
                errors.append(f"simulation per-test identity is duplicated: {name} seed={seed}")
            identities.add(identity)
            ordering_keys.append(identity)

    if ordering_keys != sorted(ordering_keys):
        errors.append("simulation per-test records are not deterministically name/seed ordered")
    if observed_counts != status_counts:
        errors.append(
            "simulation per-test record/status-count mismatch: "
            f"records={observed_counts} evidence={status_counts}"
        )
    return errors


def main() -> int:
    args = parse_args()
    simulation, sim_errors = load_branch(args.simulation_summary, "simulation", args.candidate_sha)
    fpv, fpv_errors = load_branch(args.fpv_summary, "fpv", args.candidate_sha)
    errors = sim_errors + fpv_errors
    candidate12 = args.candidate_sha[:12]
    simulation_identity_source = simulation or {
        "worktree": (
            f"{WORKTREE_ROOT}/tmp_gpu_blk_run_"
            f"{candidate12}_sanity_{args.attempt_token}"
        )
    }
    fpv_identity_source = fpv or {
        "worktree": f"{WORKTREE_ROOT}/tmp_gpu_fpv_run_{candidate12}_{args.attempt_token}"
    }
    simulation_worktree, simulation_worktree_errors = validate_worktree_identity(
        simulation_identity_source, "simulation", args.candidate_sha, "sanity"
    )
    fpv_worktree, fpv_worktree_errors = validate_worktree_identity(
        fpv_identity_source, "fpv", args.candidate_sha
    )
    errors.extend(simulation_worktree_errors)
    errors.extend(fpv_worktree_errors)
    for branch, identity in (
        ("simulation", simulation_worktree),
        ("fpv", fpv_worktree),
    ):
        if identity["attempt_token"] != args.attempt_token:
            errors.append(
                f"{branch} worktree attempt token="
                f"{identity['attempt_token']!r}; expected orchestration token "
                f"{args.attempt_token!r}"
            )
    orchestration, orchestration_evidence, orchestration_errors = (
        validate_orchestration_evidence(
            args, simulation_worktree, fpv_worktree
        )
    )
    errors.extend(orchestration_errors)
    (
        bound_simulation,
        bound_fpv,
        summary_provenance,
        provenance_errors,
    ) = bind_summaries_to_run_artifacts(
        args, orchestration_evidence, simulation, fpv
    )
    errors.extend(provenance_errors)
    orchestration_evidence["summary_provenance"] = summary_provenance
    orchestration_evidence["verified"] = bool(
        orchestration_evidence.get("verified")
        and summary_provenance.get("verified")
    )
    if bound_simulation:
        simulation = bound_simulation
    if bound_fpv:
        fpv = bound_fpv
    simulation_worktree, bound_simulation_identity_errors = validate_worktree_identity(
        simulation, "simulation", args.candidate_sha, "sanity"
    )
    fpv_worktree, bound_fpv_identity_errors = validate_worktree_identity(
        fpv, "fpv", args.candidate_sha
    )
    errors.extend(bound_simulation_identity_errors)
    errors.extend(bound_fpv_identity_errors)
    if args.simulation_status != 0:
        errors.append(f"simulation wrapper status={args.simulation_status}")
    if args.fpv_status != 0:
        errors.append(f"fpv wrapper status={args.fpv_status}")
    if simulation.get("classification") != "PASS":
        errors.append(f"simulation classification={simulation.get('classification', 'MISSING')}")
    if simulation.get("command_status") != 0:
        errors.append(f"simulation command status={simulation.get('command_status', 'MISSING')}")
    if simulation.get("command") != SIMULATION_COMMAND:
        errors.append(
            f"simulation command={simulation.get('command', 'MISSING')!r}; "
            f"expected {SIMULATION_COMMAND!r}"
        )
    if simulation.get("failure_count") != 0:
        errors.append(f"simulation failure count={simulation.get('failure_count', 'MISSING')}")
    simulation_contract = {
        "host": "rhel8-VM",
        "regression": "sanity",
        "recorded_candidate_sha": args.candidate_sha,
        "regression_overall_status": "PASS",
        "failure_details_complete": True,
    }
    for key, expected in simulation_contract.items():
        if simulation.get(key) != expected:
            errors.append(
                f"simulation {key}={simulation.get(key, 'MISSING')!r}; expected {expected!r}"
            )
    if simulation.get("evidence_errors") != []:
        errors.append(
            f"simulation evidence errors={simulation.get('evidence_errors', 'MISSING')!r}"
        )
    if simulation.get("failures") != []:
        errors.append("simulation failure detail list is not empty")
    terminal = simulation.get("terminal_counts")
    canonical = simulation.get("regression_counts")
    if not isinstance(terminal, dict) or not isinstance(canonical, dict):
        errors.append("simulation terminal/canonical counts are missing")
    else:
        for key in ("pass", "fail", "abort", "skip"):
            if terminal.get(key) != canonical.get(key):
                errors.append(
                    f"simulation terminal/canonical {key} mismatch: "
                    f"{terminal.get(key, 'MISSING')!r}/{canonical.get(key, 'MISSING')!r}"
                )
        canonical_total = canonical.get("total")
        count_values = [canonical.get(key) for key in ("pass", "fail", "abort", "skip")]
        if (
            not isinstance(canonical_total, int)
            or isinstance(canonical_total, bool)
            or canonical_total <= 0
            or any(not isinstance(value, int) or isinstance(value, bool) for value in count_values)
            or sum(count_values) != canonical_total
        ):
            errors.append("simulation canonical totals are missing, empty, or inconsistent")
    errors.extend(
        validate_simulation_tests(
            simulation,
            canonical,
            simulation_worktree["path"]
            if isinstance(simulation_worktree["path"], str)
            else "",
        )
    )
    if fpv.get("classification") != "PASS":
        errors.append(f"fpv classification={fpv.get('classification', 'MISSING')}")
    if fpv.get("command_status") != 0:
        errors.append(f"fpv command status={fpv.get('command_status', 'MISSING')}")
    if fpv.get("command") != FPV_SUMMARY_COMMAND:
        errors.append(
            f"fpv command={fpv.get('command', 'MISSING')!r}; "
            f"expected {FPV_SUMMARY_COMMAND!r}"
        )
    if fpv.get("failure_count") != 0 or fpv.get("cex_count") != 0:
        errors.append(
            f"fpv failure/cex count={fpv.get('failure_count', 'MISSING')}/"
            f"{fpv.get('cex_count', 'MISSING')}"
        )
    fpv_contract = {
        "host": "rhel8-VM",
        "jobs": 6,
        "proof_limit": "5m",
        "cex_save_limit": 5,
        "individual_cex_stop": "UNVERIFIED_GAP",
        "execution_evidence": "PROPERTIES_PROCESSED",
    }
    for key, expected in fpv_contract.items():
        if fpv.get(key) != expected:
            errors.append(f"fpv {key}={fpv.get(key, 'MISSING')!r}; expected {expected!r}")
    if fpv.get("ftrun_status") != 0:
        errors.append(f"fpv ftrun status={fpv.get('ftrun_status', 'MISSING')}")
    if fpv.get("failures") != []:
        errors.append("fpv failure detail list is not empty")

    # FTRun -slots limits proof-engine jobs, not every Jasper OS process.
    # Require marker + post-hook IPF031 + ProofGrid usable-level evidence and
    # detailed process-role telemetry proving that ordinary engines stayed at
    # or below six. ProofMaster/cache and controller processes remain separately
    # reported raw-CPU diagnostics and never get relabeled as proof slots.
    if fpv.get("concurrency_verified") is not True:
        errors.append(
            "fpv concurrency_verified="
            f"{fpv.get('concurrency_verified', 'MISSING')!r}; expected True"
        )
    concurrency = fpv.get("concurrency")
    if not isinstance(concurrency, dict):
        errors.append("fpv concurrency evidence is missing")
    else:
        concurrency_contract = {
            "verified": True,
            "status": "VERIFIED",
            "requested_jobs": 6,
            "requested_proof_job_slots": 6,
            "configured_max_local_jobs": 6,
            "configured_per_engine_max_local_jobs": 2,
            "effective_max_jobs": 6,
            "effective_proof_job_slots": 6,
            "proofgrid_mode": "local",
            "proof_job_slot_cap_verified": True,
            "verification_basis": (
                "WRAPPER_MARKER_IPF031_PROOFGRID_USABLE_LEVEL_AND_"
                "ORDINARY_PROOF_ENGINE_PEAK"
            ),
            "raw_process_count_authoritative": False,
            "raw_total_cpu_worker_count_authoritative": False,
            "raw_process_conservative_envelope": 7,
            "raw_process_conservative_envelope_applies": False,
            "process_details_available": True,
            "process_detail_role_schema_version": 2,
            "ordinary_proof_engine_peak_within_limit": True,
            "proof_cache_workers_count_toward_proof_job_slots": False,
            "evidence_errors": [],
        }
        for key, expected in concurrency_contract.items():
            if concurrency.get(key) != expected:
                errors.append(
                    f"fpv concurrency {key}="
                    f"{concurrency.get(key, 'MISSING')!r}; expected {expected!r}"
                )
        effective_per_engine = concurrency.get("effective_per_engine_max_jobs")
        if (
            not isinstance(effective_per_engine, int)
            or isinstance(effective_per_engine, bool)
            or not 1 <= effective_per_engine <= 6
        ):
            errors.append(
                "fpv concurrency effective_per_engine_max_jobs="
                f"{effective_per_engine!r}; expected an integer from 1 to 6"
            )
        proof_threads = concurrency.get("proof_threads_observed")
        if (
            not isinstance(proof_threads, int)
            or isinstance(proof_threads, bool)
            or proof_threads < 1
        ):
            errors.append(
                "fpv concurrency proof_threads_observed="
                f"{proof_threads!r}; expected a positive integer"
            )
        usable_peak = concurrency.get("proofgrid_usable_level_peak")
        if (
            not isinstance(usable_peak, int)
            or isinstance(usable_peak, bool)
            or not 1 <= usable_peak <= 6
        ):
            errors.append(
                "fpv concurrency proofgrid_usable_level_peak="
                f"{usable_peak!r}; expected an integer from 1 to 6"
            )
        usable_levels = concurrency.get("proofgrid_usable_levels")
        if (
            not isinstance(usable_levels, list)
            or not usable_levels
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
                or value > 6
                for value in usable_levels
            )
        ):
            errors.append(
                f"fpv concurrency proofgrid_usable_levels={usable_levels!r}; "
                "expected nonempty integers from 0 to 6"
            )
        else:
            positive_usable_levels = [value for value in usable_levels if value > 0]
            if not positive_usable_levels:
                errors.append("fpv concurrency has no positive ProofGrid usable level")
            elif usable_peak != max(positive_usable_levels):
                errors.append(
                    "fpv concurrency ProofGrid usable peak/list are inconsistent"
                )
        ipf031 = concurrency.get("ipf031")
        if not isinstance(ipf031, list) or not ipf031:
            errors.append("fpv concurrency IPF031 proof-thread evidence is missing")
        elif proof_threads != len(ipf031):
            errors.append(
                "fpv concurrency proof_threads_observed/IPF031 count are inconsistent"
            )
        positive_samples = concurrency.get("positive_process_samples")
        if (
            not isinstance(positive_samples, int)
            or isinstance(positive_samples, bool)
            or positive_samples < 1
        ):
            errors.append(
                "fpv concurrency positive_process_samples="
                f"{positive_samples!r}; expected a positive integer"
            )
        else:
            peak = concurrency.get("peak_run_scoped_jg_proof_processes")
            if (
                not isinstance(peak, int)
                or isinstance(peak, bool)
                or peak < 1
            ):
                errors.append(
                    "fpv raw run-scoped jg_proof peak is missing or invalid "
                    f"(peak={peak!r})"
                )
            ordinary_peak = concurrency.get("peak_ordinary_proof_engine_processes")
            if (
                not isinstance(ordinary_peak, int)
                or isinstance(ordinary_peak, bool)
                or not 1 <= ordinary_peak <= 6
            ):
                errors.append(
                    "fpv ordinary proof-engine peak is missing or exceeds six "
                    f"(peak={ordinary_peak!r})"
                )
            if concurrency.get("peak_signature_proofgrid_engine_processes") != ordinary_peak:
                errors.append(
                    "fpv ordinary proof-engine peak/compatibility alias are inconsistent"
                )
            cache_peak = concurrency.get("peak_proof_cache_worker_processes")
            controller_peak = concurrency.get(
                "peak_controller_or_other_jg_proof_processes"
            )
            for label, value in (
                ("proof-cache worker", cache_peak),
                ("controller/other", controller_peak),
            ):
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or value < 0
                ):
                    errors.append(f"fpv {label} process peak is invalid: {value!r}")
            if (
                isinstance(cache_peak, int)
                and not isinstance(cache_peak, bool)
                and cache_peak != 0
            ):
                errors.append(
                    "fpv proof-cache worker peak is nonzero despite the mandatory "
                    f"cache-disabled campaign config (peak={cache_peak})"
                )
            raw_total_peak = concurrency.get("peak_raw_total_cpu_worker_processes")
            if raw_total_peak != peak:
                errors.append("fpv raw total CPU-worker/process peaks are inconsistent")
            expected_raw_within = (
                isinstance(peak, int) and not isinstance(peak, bool) and peak <= 6
            )
            if concurrency.get("process_peak_within_limit") is not expected_raw_within:
                errors.append("fpv raw process within-limit diagnostic is inconsistent")
            if (
                concurrency.get("raw_total_cpu_worker_peak_within_limit")
                is not expected_raw_within
            ):
                errors.append("fpv raw total CPU-worker diagnostic is inconsistent")
            raw_classification = concurrency.get("raw_process_peak_classification")
            above_cap = concurrency.get("raw_process_samples_above_job_cap")
            if raw_classification == "WITHIN_PROOF_JOB_CAP":
                if not isinstance(peak, int) or isinstance(peak, bool) or peak > 6 or above_cap != 0:
                    errors.append("fpv raw WITHIN_PROOF_JOB_CAP evidence is inconsistent")
            elif raw_classification == "PROOF_CACHE_WORKER_OVERHEAD":
                if (
                    not isinstance(peak, int)
                    or isinstance(peak, bool)
                    or peak <= 6
                    or not isinstance(cache_peak, int)
                    or isinstance(cache_peak, bool)
                    or cache_peak < 1
                    or not isinstance(above_cap, int)
                    or isinstance(above_cap, bool)
                    or above_cap < 1
                ):
                    errors.append("fpv prove-cache worker distinction is inconsistent")
            elif raw_classification == "CONTROLLER_OR_OTHER_OVERHEAD":
                if (
                    not isinstance(peak, int)
                    or isinstance(peak, bool)
                    or peak <= 6
                    or not isinstance(controller_peak, int)
                    or isinstance(controller_peak, bool)
                    or controller_peak < 1
                    or not isinstance(above_cap, int)
                    or isinstance(above_cap, bool)
                    or above_cap < 1
                ):
                    errors.append("fpv controller/other process distinction is inconsistent")
            else:
                errors.append(
                    "fpv raw process classification="
                    f"{raw_classification!r}; expected a verified diagnostic class"
                )
    assertions = fpv.get("assertions")
    if not isinstance(assertions, dict):
        errors.append("fpv assertion evidence is missing")
    else:
        total_assertions = assertions.get("total")
        if (
            not isinstance(total_assertions, int)
            or isinstance(total_assertions, bool)
            or total_assertions <= 0
        ):
            errors.append(f"fpv assertion total={total_assertions!r}; expected a positive integer")
        if assertions.get("failed") != 0:
            errors.append(f"fpv assertion failures={assertions.get('failed', 'MISSING')}")
        if assertions.get("unclassified") != 0:
            errors.append(
                f"fpv unclassified assertion count={assertions.get('unclassified', 'MISSING')}"
            )
        status_counts = assertions.get("status_counts")
        if not isinstance(status_counts, dict):
            errors.append("fpv assertion status counts are missing")
        else:
            allowed_statuses = {
                "total",
                "proven",
                "bounded_proven_auto",
                "bounded_proven_user",
                "marked_proven",
                "cex",
                "ar_cex",
                "error",
                "undetermined",
                "unprocessed",
                "processing",
            }
            unexpected_statuses = sorted(set(status_counts) - allowed_statuses)
            if unexpected_statuses:
                errors.append(
                    f"fpv assertion status counts have unknown keys: {unexpected_statuses}"
                )
            categorized = []
            for key, value in status_counts.items():
                if key == "total":
                    continue
                if not is_nonnegative_int(value):
                    errors.append(
                        f"fpv assertion status {key}={value!r}; expected nonnegative integer"
                    )
                else:
                    categorized.append(value)
            if (
                len(categorized) != len(status_counts) - 1
                or status_counts.get("total") != total_assertions
                or sum(categorized) != total_assertions
            ):
                errors.append("fpv assertion status counts are incomplete or inconsistent")
            computed_passed = sum(
                status_counts.get(key, 0)
                for key in (
                    "proven",
                    "bounded_proven_auto",
                    "bounded_proven_user",
                    "marked_proven",
                )
                if is_nonnegative_int(status_counts.get(key, 0))
            )
            computed_failed = sum(
                status_counts.get(key, 0)
                for key in ("cex", "ar_cex", "error")
                if is_nonnegative_int(status_counts.get(key, 0))
            )
            computed_cex = sum(
                status_counts.get(key, 0)
                for key in ("cex", "ar_cex")
                if is_nonnegative_int(status_counts.get(key, 0))
            )
            computed_unresolved = sum(
                status_counts.get(key, 0)
                for key in ("undetermined", "unprocessed", "processing")
                if is_nonnegative_int(status_counts.get(key, 0))
            )
            for label, actual, expected in (
                ("passed", assertions.get("passed"), computed_passed),
                ("failed", assertions.get("failed"), computed_failed),
                ("unresolved", assertions.get("unresolved"), computed_unresolved),
                ("cex_count", fpv.get("cex_count"), computed_cex),
                ("failure_count", fpv.get("failure_count"), computed_failed),
            ):
                if actual != expected:
                    errors.append(
                        f"fpv assertion-derived {label}={actual!r}; expected {expected}"
                    )

    worktree_evidence = {
        "schema_version": 1,
        "attempt_token": args.attempt_token,
        "simulation": simulation_worktree,
        "fpv": fpv_worktree,
    }
    classification = "PASS" if not errors else "FAIL"
    result = {
        "schema_version": 1,
        "wave": "B",
        "classification": classification,
        "candidate_sha": args.candidate_sha,
        "attempt_token": args.attempt_token,
        "run_token": args.run_token,
        "gate_errors": errors,
        "orchestration": orchestration,
        "orchestration_evidence": orchestration_evidence,
        "worktree_evidence": worktree_evidence,
        "branches": {"simulation": simulation, "fpv": fpv},
    }
    fpv_concurrency_report = (
        fpv.get("concurrency") if isinstance(fpv.get("concurrency"), dict) else {}
    )
    lines = [
        "GPU VALIDATION CAMPAIGN — WAVE B",
        f"Classification: {classification}",
        f"Candidate: {args.candidate_sha}",
        "Orchestration: parallel; start-all-before-wait=true; "
        "collect-all-branches=true",
        f"Attempt token: {args.attempt_token}",
        f"Run token: {args.run_token}",
        "Orchestration evidence: "
        f"verified={orchestration_evidence.get('verified', False)} "
        f"root={orchestration_evidence.get('local_evidence_root', 'UNKNOWN')}",
        "Started branches: simulation,fpv",
        "Collected branches: simulation,fpv",
        f"Simulation: status={args.simulation_status} classification={simulation.get('classification', 'MISSING')}",
        f"FPV: status={args.fpv_status} classification={fpv.get('classification', 'MISSING')}",
        f"Simulation failures: {simulation.get('failure_count', 'UNKNOWN')}",
        "Simulation per-test ledger: "
        f"verified={simulation.get('test_records_verified', 'UNKNOWN')} "
        f"records={len(simulation.get('tests', [])) if isinstance(simulation.get('tests'), list) else 'UNKNOWN'}",
        f"FPV failures/CEXs: {fpv.get('failure_count', 'UNKNOWN')}/{fpv.get('cex_count', 'UNKNOWN')}",
        f"FPV completeness: {fpv.get('proof_completeness', 'UNKNOWN')}",
        f"FPV individual-CEX stop: {fpv.get('individual_cex_stop', 'UNKNOWN')}",
        "FPV effective proof-job slots: "
        f"{fpv_concurrency_report.get('effective_proof_job_slots', 'UNKNOWN')}",
        "FPV ProofGrid usable-level peak: "
        f"{fpv_concurrency_report.get('proofgrid_usable_level_peak', 'UNKNOWN')}",
        "FPV ordinary proof-engine process peak (slot-authoritative): "
        f"{fpv_concurrency_report.get('peak_ordinary_proof_engine_processes', 'UNKNOWN')}",
        "FPV prove-cache worker process peak (diagnostic): "
        f"{fpv_concurrency_report.get('peak_proof_cache_worker_processes', 'UNKNOWN')}",
        "FPV raw jg_proof process peak (diagnostic): "
        f"{fpv_concurrency_report.get('peak_run_scoped_jg_proof_processes', 'UNKNOWN')}",
        "FPV raw process classification: "
        f"{fpv_concurrency_report.get('raw_process_peak_classification', 'UNKNOWN')}",
        f"Simulation worktree: {simulation_worktree['path'] or 'UNKNOWN'}",
        f"FPV worktree: {fpv_worktree['path'] or 'UNKNOWN'}",
    ]
    for error in errors:
        lines.append(f"  GATE_ERROR: {error}")
    for url in simulation.get("eap_triage_urls", []):
        lines.append(f"  EAP: {url}")
    for failure in simulation.get("failures", []):
        lines.append(
            "  FAILURE: test={test} seed={seed} signature={signature}".format(
                test=failure.get("test") or "UNKNOWN",
                seed=failure.get("seed") or "UNKNOWN",
                signature=failure.get("signature") or "UNKNOWN",
            )
        )
    for failure in fpv.get("failures", []):
        lines.append(
            "  FPV_FAILURE: status={status} property={name} location={location}".format(
                status=failure.get("status") or "UNKNOWN",
                name=failure.get("name") or "UNKNOWN",
                location=failure.get("location") or "UNKNOWN",
            )
        )

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.text_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.text_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"WAVE_B_SUMMARY_JSON={args.json_output}")
    print(f"WAVE_B_SUMMARY_REPORT={args.text_output}")
    return 0 if classification == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
