#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_wave_a.py"
TIP = "f" * 40
BASE = "a" * 40
RUN_ID = "wave-a-test-run"
BRANCHES = ("aacr", "simulation", "fpv", "rhel8_lint")


def repository_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("cannot locate repository root")


TEST_TEMP_ROOT = repository_root() / "private/tmp/to_clean/validate-gpu-wave-a-tests"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_env(path: Path, values: dict[str, str], extra_lines=()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items())
        + "".join(f"{line}\n" for line in extra_lines),
        encoding="utf-8",
    )


class SummarizeWaveATests(unittest.TestCase):
    def execute(
        self,
        overrides=None,
        preflight_status="PASS",
        orchestration_overrides=None,
        marker_overrides=None,
        missing_markers=None,
        digest_overrides=None,
        duplicate_lines=(),
        mutate_summary_after_manifest=None,
        command_text_overrides=None,
        command_digest_overrides=None,
        mutate_command_after_manifest=None,
        command_binding=True,
        allow_legacy_command_evidence=False,
    ):
        overrides = overrides or {}
        orchestration_overrides = orchestration_overrides or {}
        marker_overrides = marker_overrides or {}
        missing_markers = missing_markers or set()
        digest_overrides = digest_overrides or {}
        command_text_overrides = command_text_overrides or {}
        command_digest_overrides = command_digest_overrides or {}
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as temporary:
            root = Path(temporary) / RUN_ID
            root.mkdir()
            preflight = root / "source-preflight.env"
            write_env(
                preflight,
                {
                    "SCHEMA_VERSION": "1",
                    "STATUS": preflight_status,
                    "SERIALIZED_BARRIER": "1",
                    "CANDIDATE_SHA": TIP,
                    "COMMAND": "design/logical/make_sources",
                    "COMPLETED_UTC": "2026-08-28T11:00:00.500Z",
                },
            )
            payloads = {
                "aacr": {
                    "schema_version": 1,
                    "wave": "A",
                    "branch": "aacr",
                    "candidate_sha": TIP,
                    "base_sha": BASE,
                    "tip_sha": TIP,
                    "range": f"{BASE}..{TIP}",
                    "execution_status": "COMPLETE",
                    "detection_status": "NOT_DETECTED",
                    "classification": "NO_FINDINGS",
                    "command_status": 0,
                },
                "simulation": {
                    "schema_version": 1,
                    "wave": "A",
                    "branch": "simulation",
                    "candidate_sha": TIP,
                    "execution_status": "COMPLETE",
                    "detection_status": "DETECTED",
                    "classification": "VALIDATION_DETECTED",
                    "attributable_detection": True,
                    "command": (
                        "blk_val --build-clean --storage-services elk=n "
                        "--set-lsf-mem-limit 12000 --no-bsub --no-bsub-build "
                        "--dfs batch --bo 8x_mtcs --seed 1 "
                        "--plusarg '+tex_trace_shim +tex_checkers_enable=all' "
                        "test_mix_all_tiny__sanity"
                    ),
                    "test": "test_mix_all_tiny__sanity",
                    "seed": 1,
                    "build_option": "8x_mtcs",
                    "dfs": "batch",
                    "waves": False,
                    "uvm_high": False,
                },
                "fpv": {
                    "schema_version": 1,
                    "wave": "A",
                    "branch": "fpv",
                    "candidate_sha": TIP,
                    "execution_status": "INFRASTRUCTURE_ERROR",
                    "detection_status": "DETECTED",
                    "classification": "VALIDATION_DETECTED_WITH_INFRA_LIMIT",
                    "attributable_detection": True,
                    "command": "ftrun tex_flt -local -batch -auto_run -slots 4 -save on_failure",
                    "target": "tex_flt",
                    "proof_limit": "10m",
                    "slots": 4,
                    "saved_cex_limit": 5,
                    "stop_after_cex_implemented": False,
                },
                "rhel8_lint": {
                    "schema_version": 1,
                    "wave": "A",
                    "branch": "rhel8_lint",
                    "candidate_sha": TIP,
                    "execution_status": "COMPLETE",
                    "detection_status": "DETECTED",
                    "classification": "VALIDATION_DETECTED",
                    "attributable_detection": True,
                    "command": "dcs_superlint superlint_8x/configuration_top.yaml",
                    "runner_status": 0,
                    "report_complete": True,
                },
            }
            for branch, changes in overrides.items():
                payloads[branch].update(changes)

            summary_rels = {
                branch: f"{branch.replace('_', '-')}/summary.json" for branch in BRANCHES
            }
            command_rels = {
                "aacr": "aacr/command.txt",
                "simulation": "simulation/command.txt",
                "fpv": "fpv/command.txt",
                "rhel8_lint": "logs/rhel8-lint.driver.log",
            }
            default_command_text = {
                "aacr": (
                    f"aacr-cli --target-sha {BASE}..{TIP} --deep-analysis-codex "
                    f"--no-caching --json-output {root / 'aacr/aacr.raw.json'} "
                    f"--output-file {root / 'aacr/aacr.txt'} "
                    f"--html-report {root / 'aacr/html'}\n"
                ),
                "simulation": (
                    "blk_val --build-clean --storage-services elk=n "
                    "--set-lsf-mem-limit 12000 --no-bsub --no-bsub-build "
                    "--dfs batch --bo 8x_mtcs --seed 1 "
                    "--plusarg '+tex_trace_shim +tex_checkers_enable=all' "
                    "test_mix_all_tiny__sanity\n"
                ),
                "fpv": (
                    "FTRUN_RUN_LIMIT=10m ftrun tex_flt -tcl "
                    "/codex-wave-a/jaspergold-mac-fpv/assets/save_up_to_five_cex.tcl "
                    f"-build_dir {root / 'fpv/fts_run_tex_flt'} "
                    "-local -batch -auto_run -slots 4 -save on_failure\n"
                ),
                "rhel8_lint": (
                    f"Transferring exact candidate {TIP} to custom ref "
                    f"refs/codex/validation-campaign/rhel8-lint/{TIP}.\n"
                    "LINT_COMMAND=dcs_superlint superlint_8x/configuration_top.yaml\n"
                    f"ATTEMPT_TOKEN={RUN_ID}\n"
                    "REMOTE_WORKTREE=/home/tibger01/projects/fornjot/"
                    f"tmp_gpu_lint_run_{TIP[:12]}_{RUN_ID}\n"
                    "RHEL8_LINT_DRIVER_STATUS=COMPLETE\n"
                ),
            }
            command_paths = {}
            command_digests = {}
            for branch, relative in command_rels.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    command_text_overrides.get(branch, default_command_text[branch]),
                    encoding="utf-8",
                )
                command_paths[branch] = path
                command_digests[branch] = digest(path)
            paths = {}
            digests = {}
            for branch, payload in payloads.items():
                path = root / summary_rels[branch]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
                paths[branch] = path
                digests[branch] = digest(path)

            orchestration_values = {
                "SCHEMA_VERSION": "2",
                "PROVENANCE_MODE": "LIVE_COORDINATOR",
                "RUN_ID": RUN_ID,
                "BASE_SHA": BASE,
                "TIP_SHA": TIP,
                "RANGE": f"{BASE}..{TIP}",
                "BRANCH_LAUNCH_MODE": "parallel",
                "START_ALL_BEFORE_WAIT": "1",
                "COLLECT_ALL_BRANCHES": "1",
                "STARTED_BRANCHES": ",".join(BRANCHES),
                "COLLECTED_BRANCHES": ",".join(BRANCHES),
                "COORDINATOR_STARTED_UTC": "2026-08-28T11:00:00Z",
                "ALL_BRANCHES_STARTED_UTC": "2026-08-28T11:00:05Z",
                "FIRST_COMPLETION_WAIT_UTC": "2026-08-28T11:00:05.500Z",
                "ALL_BRANCHES_COLLECTED_UTC": "2026-08-28T11:00:14Z",
                "SOURCE_PREFLIGHT_REL": "source-preflight.env",
                "SOURCE_PREFLIGHT_SHA256": digest(preflight),
            }
            for index, branch in enumerate(BRANCHES, start=1):
                prefix = branch.upper()
                attempt_id = f"{RUN_ID}.{branch}.1"
                marker_rels = {
                    "START": f"orchestration/{branch}.attempt-1.started.env",
                    "FINISH": f"orchestration/{branch}.attempt-1.finished.env",
                    "COLLECTION": f"orchestration/{branch}.attempt-1.collected.env",
                }
                branch_manifest_values = {
                        f"{prefix}_ATTEMPT_ID": attempt_id,
                        f"{prefix}_START_MARKER_REL": marker_rels["START"],
                        f"{prefix}_FINISH_MARKER_REL": marker_rels["FINISH"],
                        f"{prefix}_COLLECTION_MARKER_REL": marker_rels["COLLECTION"],
                        f"{prefix}_SUMMARY_REL": summary_rels[branch],
                        f"{prefix}_SUMMARY_SHA256": digest_overrides.get(
                            branch, digests[branch]
                        ),
                }
                if command_binding:
                    branch_manifest_values.update(
                        {
                        f"{prefix}_COMMAND_REL": command_rels[branch],
                        f"{prefix}_COMMAND_SHA256": command_digest_overrides.get(
                            branch, command_digests[branch]
                        ),
                        }
                    )
                orchestration_values.update(branch_manifest_values)
                common = {
                    "SCHEMA_VERSION": "1",
                    "PROVENANCE_MODE": "LIVE_COORDINATOR",
                    "RUN_ID": RUN_ID,
                    "ATTEMPT_ID": attempt_id,
                    "BRANCH": branch,
                    "BASE_SHA": BASE,
                    "TIP_SHA": TIP,
                    "RANGE": f"{BASE}..{TIP}",
                }
                marker_values = {
                    "START": {
                        **common,
                        "PID": str(1000 + index),
                        "STARTED_UTC": f"2026-08-28T11:00:0{index}Z",
                    },
                    "FINISH": {
                        **common,
                        "PID": str(1000 + index),
                        "EXIT_STATUS": "0",
                        "FINISHED_UTC": f"2026-08-28T11:00:0{index + 5}Z",
                    },
                    "COLLECTION": {
                        **common,
                        "SUMMARY_REL": summary_rels[branch],
                        "SUMMARY_SHA256": digests[branch],
                        "COLLECTED_UTC": f"2026-08-28T11:00:{index + 9:02d}Z",
                    },
                }
                if command_binding:
                    marker_values["COLLECTION"].update(
                        {
                            "COMMAND_REL": command_rels[branch],
                            "COMMAND_SHA256": command_digests[branch],
                        }
                    )
                for phase, values in marker_values.items():
                    values.update(marker_overrides.get((branch, phase), {}))
                    if (branch, phase) not in missing_markers:
                        write_env(root / marker_rels[phase], values)

            orchestration_values.update(orchestration_overrides)
            for key, value in orchestration_overrides.items():
                if value is None:
                    orchestration_values.pop(key, None)
            orchestration = root / "orchestration.env"
            write_env(orchestration, orchestration_values, duplicate_lines)
            if mutate_summary_after_manifest:
                paths[mutate_summary_after_manifest].write_text(
                    paths[mutate_summary_after_manifest].read_text(encoding="utf-8") + "\n",
                    encoding="utf-8",
                )
            if mutate_command_after_manifest:
                command_paths[mutate_command_after_manifest].write_text(
                    command_paths[mutate_command_after_manifest].read_text(encoding="utf-8")
                    + "# changed after collection\n",
                    encoding="utf-8",
                )

            output = root / "state.json"
            command = [
                sys.executable,
                str(SCRIPT),
                "--source-preflight",
                str(preflight),
                "--orchestration",
                str(orchestration),
                "--aacr",
                str(paths["aacr"]),
                "--simulation",
                str(paths["simulation"]),
                "--fpv",
                str(paths["fpv"]),
                "--rhel8-lint",
                str(paths["rhel8_lint"]),
                "--base",
                BASE,
                "--tip",
                TIP,
                "--json-output",
                str(output),
                "--text-output",
                str(root / "summary.txt"),
            ]
            if allow_legacy_command_evidence:
                command.append("--allow-legacy-command-evidence")
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            return completed, json.loads(output.read_text(encoding="utf-8"))

    def assert_blocked_for(self, state, text):
        self.assertEqual(state["gate"]["status"], "BLOCKED")
        self.assertTrue(
            any(text in reason for reason in state["gate"]["blocking_reasons"]),
            state["gate"]["blocking_reasons"],
        )

    def test_gate_accepts_complete_schema_v2_live_evidence(self):
        completed, state = self.execute(
            marker_overrides={
                ("aacr", "START"): {"STARTED_UTC": "2026-08-28T11:00:01.250Z"},
                ("aacr", "FINISH"): {"FINISHED_UTC": "2026-08-28T11:00:06.5Z"},
            }
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(state["gate"]["status"], "PASS")
        self.assertTrue(state["gate"]["next_wave_allowed"])
        self.assertEqual(state["orchestration"]["provenance_mode"], "LIVE_COORDINATOR")

    def test_legacy_or_missing_live_provenance_blocks(self):
        completed, state = self.execute(
            orchestration_overrides={"SCHEMA_VERSION": "1", "PROVENANCE_MODE": ""}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "live coordinator provenance")

    def test_wrong_orchestration_range_blocks(self):
        completed, state = self.execute(orchestration_overrides={"RANGE": f"{BASE}..{'e' * 40}"})
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "range does not equal base..tip")

    def test_aacr_summary_must_match_exact_range(self):
        completed, state = self.execute({"aacr": {"base_sha": "b" * 40}})
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "aacr: base")

    def test_branch_summary_candidate_must_match_tip(self):
        completed, state = self.execute(
            {"simulation": {"candidate_sha": "e" * 40}}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation: candidate does not equal tip")

    def test_missing_start_marker_blocks(self):
        completed, state = self.execute(missing_markers={("simulation", "START")})
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation start marker: manifest is missing")

    def test_reversed_finish_timestamp_blocks(self):
        completed, state = self.execute(
            marker_overrides={
                ("fpv", "FINISH"): {"FINISHED_UTC": "2026-08-28T10:59:59Z"}
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "fpv: finish timestamp precedes start")

    def test_collection_timestamp_before_finish_blocks(self):
        completed, state = self.execute(
            marker_overrides={
                ("rhel8_lint", "COLLECTION"): {
                    "COLLECTED_UTC": "2026-08-28T11:00:07Z"
                }
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "rhel8_lint: collection timestamp precedes finish")

    def test_selected_attempt_cannot_be_swapped_to_retry(self):
        completed, state = self.execute(
            marker_overrides={
                ("aacr", "COLLECTION"): {"ATTEMPT_ID": f"{RUN_ID}.aacr.retry-2"}
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "aacr collection marker: ATTEMPT_ID")

    def test_summary_mutated_after_collection_blocks(self):
        completed, state = self.execute(mutate_summary_after_manifest="simulation")
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation: summary SHA-256 does not match")

    def test_command_mutated_after_collection_blocks(self):
        completed, state = self.execute(mutate_command_after_manifest="fpv")
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "fpv: command SHA-256 does not match")

    def test_internally_hashed_wrong_commands_still_block(self):
        completed, state = self.execute(
            command_text_overrides={
                "aacr": (
                    f"aacr-cli --target-sha {BASE}..{TIP} --deep-analysis-codex "
                    "--json-output aacr.raw.json --output-file aacr.txt --html-report html\n"
                ),
                "simulation": "blk_val wrong_test --seed 999 --dfs native\n",
                "fpv": "FTRUN_RUN_LIMIT=1s ftrun wrong_target -slots 99\n",
                "rhel8_lint": "LINT_COMMAND=true\n",
            }
        )
        self.assertEqual(completed.returncode, 1)
        for branch in BRANCHES:
            self.assert_blocked_for(state, f"{branch} command evidence")

    def test_wrong_summary_executor_identity_blocks(self):
        completed, state = self.execute(
            {
                "simulation": {
                    "command": "blk_val wrong_test --seed 999",
                    "test": "wrong_test",
                    "seed": 999,
                    "dfs": "native",
                    "waves": True,
                },
                "fpv": {
                    "command": "ftrun wrong_target -slots 99",
                    "target": "wrong_target",
                    "proof_limit": "1s",
                    "slots": 99,
                },
                "rhel8_lint": {"command": "true"},
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation: seed")
        self.assert_blocked_for(state, "fpv: slots")
        self.assert_blocked_for(state, "rhel8_lint: command")

    def test_cli_summary_path_must_match_selected_path(self):
        completed, state = self.execute(
            orchestration_overrides={"SIMULATION_SUMMARY_REL": "fpv/summary.json"}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation: CLI summary path")

    def test_missing_summary_digest_blocks(self):
        completed, state = self.execute(digest_overrides={"rhel8_lint": ""})
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "rhel8_lint: summary SHA-256 is missing")

    def test_partial_command_binding_blocks(self):
        completed, state = self.execute(
            orchestration_overrides={"FPV_COMMAND_SHA256": None}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "raw command digest binding is partial")

    def test_missing_command_binding_blocks_without_explicit_legacy_mode(self):
        completed, state = self.execute(command_binding=False)
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "historical replay requires explicit legacy")

    def test_explicit_legacy_mode_still_validates_exact_raw_commands(self):
        completed, state = self.execute(
            command_binding=False, allow_legacy_command_evidence=True
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(state["gate"]["status"], "PASS")
        self.assertEqual(
            state["orchestration"]["command_binding_mode"],
            "explicit_legacy_raw_validation",
        )

    def test_explicit_legacy_mode_does_not_bypass_raw_command_contract(self):
        completed, state = self.execute(
            command_binding=False,
            allow_legacy_command_evidence=True,
            command_text_overrides={
                "simulation": "blk_val wrong_test --seed 999 --dfs native\n"
            },
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation command evidence")

    def test_duplicate_manifest_key_blocks(self):
        completed, state = self.execute(duplicate_lines=(f"TIP_SHA={TIP}",))
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "duplicate key TIP_SHA")

    def test_first_wait_before_last_start_blocks(self):
        completed, state = self.execute(
            orchestration_overrides={"FIRST_COMPLETION_WAIT_UTC": "2026-08-28T11:00:03Z"}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "first completion wait began before all branches started")

    def test_branch_finishing_before_all_started_blocks(self):
        completed, state = self.execute(
            marker_overrides={
                ("aacr", "FINISH"): {"FINISHED_UTC": "2026-08-28T11:00:04Z"}
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "aacr: selected attempt finished before all branches started")

    def test_nonzero_selected_branch_executor_blocks(self):
        completed, state = self.execute(
            marker_overrides={("simulation", "FINISH"): {"EXIT_STATUS": "7"}}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation: selected branch executor exited nonzero")

    def test_aacr_findings_are_not_required_but_completion_is(self):
        completed, state = self.execute(
            {"aacr": {"execution_status": "INFRASTRUCTURE_ERROR"}}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "aacr: review did not complete")

    def test_unattributed_detector_blocks(self):
        completed, state = self.execute(
            {
                "simulation": {
                    "detection_status": "UNKNOWN",
                    "attributable_detection": False,
                }
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "simulation")

    def test_source_preflight_failure_blocks(self):
        completed, state = self.execute(preflight_status="FAIL")
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "source_preflight")

    def test_incomplete_parallel_collection_attestation_blocks(self):
        completed, state = self.execute(
            orchestration_overrides={"COLLECTED_BRANCHES": "aacr,simulation,fpv"}
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "collected branch")

    def test_unattributed_fpv_oom_does_not_get_exception(self):
        completed, state = self.execute(
            {
                "fpv": {
                    "detection_status": "UNKNOWN",
                    "attributable_detection": False,
                    "classification": "UNATTRIBUTED_CEX",
                }
            }
        )
        self.assertEqual(completed.returncode, 1)
        self.assert_blocked_for(state, "fpv")


if __name__ == "__main__":
    unittest.main()
