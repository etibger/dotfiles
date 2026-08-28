#!/usr/bin/env bash
set -Eeuo pipefail

readonly default_local_repo=/Users/tibger01/Projects/Fornjot/a_gpu
readonly default_host=rhel8-VM
readonly remote_candidate_ref_prefix=blk-run-candidate
readonly remote_worktree_root=/home/tibger01/projects/fornjot
readonly fixed_max_jobs=2
readonly fixed_lsf_mem_limit=12000

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly skills_root="${CODEX_SKILLS_ROOT:-$(cd "$script_dir/../.." && pwd -P)}"
readonly transfer_script="$skills_root/transfer-git-commit-to-rhel8/scripts/transfer_candidate.sh"
readonly setup_script="$skills_root/setup-gpu-repo-rhel8/scripts/setup_worktree.sh"
readonly remote_runner="$script_dir/run_blk_run.sh"
readonly collect_script="$script_dir/collect_artifacts.sh"
readonly summarize_script="$script_dir/summarize_blk_run.py"

local_repo=$default_local_repo
commit=
regression=
host=$default_host
dry_run=0
recovery_worktree=

usage() {
  cat <<'EOF'
Usage: run_remote_blk_run.sh --commit SHA --regression sanity|smoke|nightly
                             [--repo PATH] [--host rhel8-VM] [--dry-run]

Run an isolated tb_tex blk_run regression and retain its worktree. The fixed
command uses build-clean, a 12000 MB LSF memory limit, no bsub for build or
run, local workers, max-jobs 2, and no max-fail override.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

report_retained_worktree() {
  local status=$?
  if ((status != 0)) && [[ -n $recovery_worktree ]]; then
    printf 'RETAINED_WORKTREE=%s\n' "$recovery_worktree" >&2
  fi
}
trap report_retained_worktree EXIT

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; local_repo=$2; shift 2 ;;
    --commit) (($# >= 2)) || die 'Missing value for --commit.'; commit=$2; shift 2 ;;
    --regression) (($# >= 2)) || die 'Missing value for --regression.'; regression=$2; shift 2 ;;
    --host) (($# >= 2)) || die 'Missing value for --host.'; host=$2; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "Unknown argument: $1" ;;
  esac
done

[[ -n $commit ]] || die '--commit is required.'
[[ $commit =~ ^[0-9A-Fa-f]{7,40}$ ]] || die '--commit must be a 7-40 digit hexadecimal SHA.'
case "$regression" in
  sanity|smoke|nightly) ;;
  *) die '--regression must be sanity, smoke, or nightly.' ;;
esac
[[ $host == "$default_host" ]] || die "Unsupported host: $host (supported: $default_host)."

local_repo=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --show-toplevel) ||
  die "Local repository is unavailable: $local_repo"
for required_file in \
  "$transfer_script" \
  "$setup_script" \
  "$remote_runner" \
  "$collect_script" \
  "$summarize_script"; do
  [[ -f $required_file ]] || die "Required workflow file is missing: $required_file"
done
[[ -x $transfer_script ]] || die "Transfer helper is not executable: $transfer_script"

candidate=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --verify "$commit^{commit}") ||
  die "Cannot resolve candidate commit: $commit"
head_sha=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --verify 'HEAD^{commit}')
[[ $candidate == "$head_sha" ]] ||
  die "Requested commit is not current HEAD (requested=$candidate HEAD=$head_sha)."

short_sha=${candidate:0:12}
remote_candidate_ref="$remote_candidate_ref_prefix-$short_sha"
expected_worktree="$remote_worktree_root/tmp_gpu_blk_run_${short_sha}_${regression}"
local_artifact_root="$local_repo/private/tmp/to_persist/blk-run-remote"
ssh_options=(
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=4
)

if ((dry_run)); then
  "$transfer_script" --repo "$local_repo" --host "$host" \
    --remote-ref "$remote_candidate_ref" --dry-run
  printf 'MODE=DRY_RUN\n'
  printf 'LOCAL_REPO=%s\n' "$local_repo"
  printf 'CANDIDATE_SHA=%s\n' "$candidate"
  printf 'REMOTE_HOST=%s\n' "$host"
  printf 'REMOTE_CANDIDATE_REF=%s\n' "$remote_candidate_ref"
  printf 'REMOTE_HANDOFF_REPO=/home/tibger01/projects/fornjot/push_gpu\n'
  printf 'REMOTE_WORKTREE=%s\n' "$expected_worktree"
  printf 'REGRESSION=%s\n' "$regression"
  printf 'BLK_RUN_MAX_JOBS=%s\n' "$fixed_max_jobs"
  printf 'BLK_RUN_COMMAND=blk_run --build-clean --%s --set-lsf-mem-limit %s --no-bsub --no-bsub-build --worker=local --max-jobs %s\n' \
    "$regression" "$fixed_lsf_mem_limit" "$fixed_max_jobs"
  printf 'WORKTREE_POLICY=retain\n'
  printf 'LOCAL_ARTIFACT_ROOT=%s\n' "$local_artifact_root"
  exit 0
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="tb-tex-${regression}-${short_sha}-${timestamp}-$$"
local_artifact_dir="$local_artifact_root/$run_id"
mkdir -p "$local_artifact_dir"

printf 'RUN_ID=%s\n' "$run_id"
printf 'REMOTE_HOST=%s\n' "$host"
printf 'REGRESSION=%s\n' "$regression"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"

printf 'Transferring candidate %s to the RHEL8 push_gpu handoff.\n' "$candidate"
set +e
"$transfer_script" --repo "$local_repo" --host "$host" \
  --remote-ref "$remote_candidate_ref" 2>&1 | tee "$local_artifact_dir/transfer.log"
transfer_status=${PIPESTATUS[0]}
set -e
((transfer_status == 0)) || die "Candidate transfer failed with status $transfer_status."

transferred_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/transfer.log")
[[ $transferred_sha == "$candidate" ]] ||
  die "Transferred SHA mismatch (expected=$candidate actual=${transferred_sha:-MISSING})."

printf 'Preparing isolated worktree %s.\n' "$expected_worktree"
set +e
ssh "${ssh_options[@]}" "$host" bash -s -- \
  --workflow blk-run \
  --regression "$regression" \
  --candidate-ref "$remote_candidate_ref" \
  <"$setup_script" 2>&1 | tee "$local_artifact_dir/setup.log"
setup_status=${PIPESTATUS[0]}
set -e

worktree=$(awk -F= '$1 == "WORKTREE" { value=$2 } END { print value }' \
  "$local_artifact_dir/setup.log")
prepared_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/setup.log")
if [[ $worktree == "$expected_worktree" ]]; then
  recovery_worktree=$worktree
fi
((setup_status == 0)) || die "Remote worktree setup failed with status $setup_status."
[[ $worktree == "$expected_worktree" ]] ||
  die "Remote worktree mismatch (expected=$expected_worktree actual=${worktree:-MISSING})."
[[ $prepared_sha == "$candidate" ]] ||
  die "Prepared SHA mismatch (expected=$candidate actual=${prepared_sha:-MISSING})."
recovery_worktree=$worktree

remote_task_dir="$worktree/private/tmp/to_persist/blk-run-remote/$run_id"
printf 'Staging the remote runner in %s.\n' "$remote_task_dir"
ssh "${ssh_options[@]}" "$host" mkdir -p "$remote_task_dir"
scp "${ssh_options[@]}" "$remote_runner" "$host:$remote_task_dir/"

printf 'Starting the %s regression with max-jobs %s.\n' "$regression" "$fixed_max_jobs"
set +e
ssh "${ssh_options[@]}" "$host" \
  bash "$remote_task_dir/run_blk_run.sh" \
  --worktree "$worktree" \
  --run-id "$run_id" \
  --regression "$regression" 2>&1 | tee "$local_artifact_dir/remote-session.log"
blk_run_status=${PIPESTATUS[0]}
set -e
printf 'REMOTE_BLK_RUN_STATUS=%s\n' "$blk_run_status"

printf 'Collecting console output and small regression result files.\n'
set +e
"$collect_script" --repo "$local_repo" --host "$host" \
  --worktree "$worktree" --run-id "$run_id" --regression "$regression" \
  2>&1 | tee "$local_artifact_dir/collect.log"
collect_status=${PIPESTATUS[0]}
set -e
((collect_status == 0)) ||
  die "Artifact collection failed with status $collect_status; the worktree was retained."
[[ -s $local_artifact_dir/run.log ]] ||
  die 'Collected run.log is missing or empty; the worktree was retained.'

summary_json="$local_artifact_dir/simulation-summary.json"
summary_report="$local_artifact_dir/simulation-summary.rpt"
python3 "$summarize_script" \
  --log "$local_artifact_dir/run.log" \
  --artifacts-dir "$local_artifact_dir" \
  --json-output "$summary_json" \
  --text-output "$summary_report" \
  --status "$blk_run_status" \
  --candidate-sha "$candidate" \
  --host "$host" \
  --worktree "$worktree" \
  --regression "$regression"
classification=$(awk -F': ' '$1 == "Classification" { value=$2 } END { print value }' \
  "$summary_report")

printf 'RETAINED_WORKTREE=%s\n' "$worktree"
printf 'SIMULATION_SUMMARY_JSON=%s\n' "$summary_json"
printf 'SIMULATION_SUMMARY_REPORT=%s\n' "$summary_report"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"
if ((blk_run_status != 0)); then
  die "Remote blk_run returned status $blk_run_status; all available evidence was collected."
fi
[[ $classification == PASS ]] ||
  die "Remote blk_run classification is ${classification:-MISSING}; inspect the retained worktree and summary."
printf 'REMOTE_BLK_RUN_COMPLETE=1\n'
