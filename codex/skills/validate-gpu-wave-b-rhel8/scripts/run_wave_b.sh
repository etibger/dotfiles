#!/usr/bin/env bash
set -Eeuo pipefail

readonly default_local_repo=/Users/tibger01/Projects/Fornjot/a_gpu
readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly skills_root="${CODEX_SKILLS_ROOT:-$(cd "$script_dir/../.." && pwd -P)}"
readonly simulation_runner="$skills_root/blk-run-remote/scripts/run_remote_blk_run.sh"
readonly fpv_runner="$skills_root/jaspergold-rhel8-fpv/scripts/run_remote_fpv.sh"
readonly gate_tool="$script_dir/gate_wave_b.py"

local_repo=$default_local_repo
commit=
run_id=
attempt_token=
dry_run=0

usage() {
  cat >&2 <<'EOF'
Usage: run_wave_b.sh --commit SHA [--repo PATH] [--run-id ID]
                     [--attempt-token TOKEN] [--dry-run]

Launch RHEL8 tb_tex sanity and five-minute fb_tex_flt concurrently, wait for
both, collect both summaries, and gate Wave B. Remote worktrees are retained.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; local_repo=$2; shift 2 ;;
    --commit) (($# >= 2)) || die 'Missing value for --commit.'; commit=$2; shift 2 ;;
    --run-id) (($# >= 2)) || die 'Missing value for --run-id.'; run_id=$2; shift 2 ;;
    --attempt-token) (($# >= 2)) || die 'Missing value for --attempt-token.'; attempt_token=$2; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ -n $commit ]] || die '--commit is required.'
[[ $commit =~ ^[0-9A-Fa-f]{7,40}$ ]] || die '--commit must be a 7-40 digit hexadecimal SHA.'
if [[ -n $run_id ]]; then
  [[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die 'Rejected run ID.'
fi
if [[ -n $attempt_token ]]; then
  [[ $attempt_token =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] ||
    die 'Rejected attempt token.'
  export WAVE_B_ATTEMPT_TOKEN=$attempt_token
fi
for required_file in "$simulation_runner" "$fpv_runner" "$gate_tool"; do
  [[ -f $required_file ]] || die "Required Wave B file is missing: $required_file"
done

local_repo=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --show-toplevel) ||
  die "Local repository is unavailable: $local_repo"
candidate=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --verify "$commit^{commit}") ||
  die "Cannot resolve candidate: $commit"
head_sha=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --verify 'HEAD^{commit}')
[[ $candidate == "$head_sha" ]] ||
  die "Wave B candidate must be current HEAD (candidate=$candidate HEAD=$head_sha)."
if ! git -c core.fsmonitor=false -C "$local_repo" diff --quiet --ignore-submodules=all -- ||
   ! git -c core.fsmonitor=false -C "$local_repo" diff --cached --quiet --ignore-submodules=all --; then
  die 'Tracked changes exist; Wave B requires a committed candidate.'
fi
if ((!dry_run)); then
  die 'Live generic launch is disabled: it cannot produce final-driver raw orchestration evidence. Use the audited candidate-specific final driver, collect its result and payload directories, then invoke gate_wave_b.py directly.'
fi

short_sha=${candidate:0:12}
if [[ -z $run_id ]]; then
  run_id="wave-b-${short_sha}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
artifact_dir="$local_repo/private/tmp/to_persist/validation-campaign/wave-b/$run_id"
[[ ! -e $artifact_dir ]] || die "Wave B artifact directory already exists: $artifact_dir"
mkdir -p "$artifact_dir"

simulation_log="$artifact_dir/simulation-orchestrator.log"
fpv_log="$artifact_dir/fpv-orchestrator.log"
simulation_status_file="$artifact_dir/simulation.status"
fpv_status_file="$artifact_dir/fpv.status"

simulation_command=(
  "$simulation_runner"
  --repo "$local_repo"
  --commit "$candidate"
  --regression sanity
)
fpv_command=(
  "$fpv_runner"
  --repo "$local_repo"
  --commit "$candidate"
  --jobs 6
  --proof-limit 5m
  --campaign-no-prove-cache
)
if ((dry_run)); then
  simulation_command+=(--dry-run)
  fpv_command+=(--dry-run)
fi

run_branch() {
  local label=$1
  local log=$2
  local status_file=$3
  shift 3
  local status
  set +e
  "$@" 2>&1 | tee "$log" | sed -u "s/^/[$label] /"
  status=${PIPESTATUS[0]}
  set -e
  printf '%s\n' "$status" >"$status_file"
}

printf 'WAVE_B_STATUS=launching_parallel_branches\n'
printf 'WAVE_B_CANDIDATE=%s\n' "$candidate"
printf 'WAVE_B_ARTIFACT_DIR=%s\n' "$artifact_dir"
printf 'WAVE_B_ATTEMPT_TOKEN=%s\n' "${attempt_token:-NONE}"
run_branch simulation "$simulation_log" "$simulation_status_file" \
  "${simulation_command[@]}" &
simulation_pid=$!
run_branch fpv "$fpv_log" "$fpv_status_file" "${fpv_command[@]}" &
fpv_pid=$!
printf 'WAVE_B_BRANCH_LAUNCH_MODE=parallel\n'
printf 'WAVE_B_START_ALL_BEFORE_WAIT=1\n'
printf 'WAVE_B_STARTED_BRANCHES=simulation,fpv\n'

set +e
wait "$simulation_pid"
simulation_wait_status=$?
wait "$fpv_pid"
fpv_wait_status=$?
set -e

[[ -s $simulation_status_file ]] || printf '%s\n' "$simulation_wait_status" >"$simulation_status_file"
[[ -s $fpv_status_file ]] || printf '%s\n' "$fpv_wait_status" >"$fpv_status_file"
simulation_status=$(<"$simulation_status_file")
fpv_status=$(<"$fpv_status_file")
printf 'WAVE_B_STATUS=both_branches_finished\n'
printf 'WAVE_B_COLLECT_ALL_BRANCHES=1\n'
printf 'WAVE_B_COLLECTED_BRANCHES=simulation,fpv\n'
printf 'SIMULATION_WRAPPER_STATUS=%s\n' "$simulation_status"
printf 'FPV_WRAPPER_STATUS=%s\n' "$fpv_status"

if ((dry_run)); then
  {
    printf 'GPU VALIDATION CAMPAIGN — WAVE B DRY RUN\n'
    printf 'Candidate: %s\n' "$candidate"
    printf 'Attempt token: %s\n' "${attempt_token:-NONE}"
    printf 'Simulation wrapper status: %s\n' "$simulation_status"
    printf 'FPV wrapper status: %s\n' "$fpv_status"
    printf 'No SSH, transfer, or remote mutation was performed.\n'
  } | tee "$artifact_dir/wave-b-plan.rpt"
  ((simulation_status == 0 && fpv_status == 0)) || exit 1
  printf 'WAVE_B_DRY_RUN_COMPLETE=1\n'
  exit 0
fi

simulation_summary=$(awk -F= '$1 == "SIMULATION_SUMMARY_JSON" { value=$2 } END { print value }' "$simulation_log")
fpv_summary=$(awk -F= '$1 == "FPV_SUMMARY_JSON" { value=$2 } END { print value }' "$fpv_log")
gate_args=(
  --candidate-sha "$candidate"
  --simulation-status "$simulation_status"
  --fpv-status "$fpv_status"
  --json-output "$artifact_dir/wave-b-summary.json"
  --text-output "$artifact_dir/wave-b-summary.rpt"
)
if [[ -n $attempt_token ]]; then
  gate_args+=(--attempt-token "$attempt_token")
fi
if [[ -n $simulation_summary ]]; then
  gate_args+=(--simulation-summary "$simulation_summary")
fi
if [[ -n $fpv_summary ]]; then
  gate_args+=(--fpv-summary "$fpv_summary")
fi

printf 'WAVE_B_STATUS=evaluating_gate\n'
set +e
python3 "$gate_tool" "${gate_args[@]}"
gate_status=$?
set -e
printf 'WAVE_B_GATE_STATUS=%s\n' "$gate_status"
printf 'WAVE_B_ARTIFACT_DIR=%s\n' "$artifact_dir"
exit "$gate_status"
