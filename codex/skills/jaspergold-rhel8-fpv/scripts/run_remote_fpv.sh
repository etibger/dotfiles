#!/usr/bin/env bash
set -Eeuo pipefail

readonly default_local_repo=/Users/tibger01/Projects/Fornjot/a_gpu
readonly remote_host=rhel8-VM
readonly remote_candidate_ref_prefix=fpv-candidate
readonly formal_target=tex_flt
readonly remote_worktree_root=/home/tibger01/projects/fornjot
readonly max_jobs=10
readonly min_proof_seconds=60
readonly max_proof_seconds=86400
readonly cex_save_limit=5

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly skills_root="${CODEX_SKILLS_ROOT:-$(cd "$script_dir/../.." && pwd -P)}"
readonly transfer_script="$skills_root/transfer-git-commit-to-rhel8/scripts/transfer_candidate.sh"
readonly setup_script="$skills_root/setup-gpu-repo-rhel8/scripts/setup_worktree.sh"
readonly cex_capture_wrapper="$script_dir/../assets/capture_up_to_five_cex_vcd.tcl"
readonly campaign_cache_fragment="$script_dir/../assets/disable_campaign_prove_cache.yaml"
readonly remote_runner="$script_dir/run_fpv.sh"
readonly report_tool="$script_dir/summarize_fpv_results.py"
readonly process_counter="$script_dir/count_run_jg_proof_processes.awk"
readonly collect_script="$script_dir/collect_artifacts.sh"

local_repo=$default_local_repo
commit=
jobs=6
proof_limit=30m
dry_run=0
campaign_no_prove_cache=0
proof_cache_mode=DEFAULT
recovery_worktree=

usage() {
  cat <<'EOF'
Usage: run_remote_fpv.sh --commit SHA [--repo PATH] [--jobs N]
                         [--proof-limit DURATION]
                         [--campaign-no-prove-cache] [--dry-run]

Run fb_tex_flt/tex_flt on rhel8-VM with a hard proof time limit and at most
five saved CEX traces. A tested five-property early-stop mechanism remains a
known gap. The isolated worktree and large proof database remain on RHEL8.
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
    --jobs) (($# >= 2)) || die 'Missing value for --jobs.'; jobs=$2; shift 2 ;;
    --proof-limit) (($# >= 2)) || die 'Missing value for --proof-limit.'; proof_limit=$2; shift 2 ;;
    --campaign-no-prove-cache) campaign_no_prove_cache=1; proof_cache_mode=DISABLED; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "Unknown argument: $1" ;;
  esac
done

[[ -n $commit ]] || die '--commit is required.'
[[ $commit =~ ^[0-9A-Fa-f]{7,40}$ ]] || die '--commit must be a 7-40 digit hexadecimal SHA.'
[[ $jobs =~ ^[1-9][0-9]*$ ]] || die '--jobs must be an integer.'
jobs_value=$((10#$jobs))
((jobs_value <= max_jobs)) || die "--jobs must be no greater than $max_jobs."
jobs=$jobs_value

[[ $proof_limit =~ ^([1-9][0-9]*)(s|m|h)$ ]] ||
  die '--proof-limit must be a positive duration such as 60s, 5m, or 2h.'
proof_value=$((10#${BASH_REMATCH[1]}))
proof_unit=${BASH_REMATCH[2]}
case "$proof_unit" in
  s) proof_seconds=$proof_value ;;
  m) proof_seconds=$((proof_value * 60)) ;;
  h) proof_seconds=$((proof_value * 3600)) ;;
esac
((proof_seconds >= min_proof_seconds && proof_seconds <= max_proof_seconds)) ||
  die '--proof-limit must be between 1 minute and 24 hours.'

local_repo=$(git -c core.fsmonitor=false -C "$local_repo" rev-parse --show-toplevel) ||
  die "Local repository is unavailable: $local_repo"
for required_file in \
  "$transfer_script" \
  "$setup_script" \
  "$cex_capture_wrapper" \
  "$campaign_cache_fragment" \
  "$remote_runner" \
  "$report_tool" \
  "$process_counter" \
  "$collect_script"; do
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
expected_worktree="$remote_worktree_root/tmp_gpu_fpv_run_$short_sha"
local_artifact_root="$local_repo/private/tmp/to_persist/jaspergold-rhel8-fpv"
ssh_options=(
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=4
)

if ((dry_run)); then
  "$transfer_script" --repo "$local_repo" --host "$remote_host" \
    --remote-ref "$remote_candidate_ref" --dry-run
  printf 'MODE=DRY_RUN\n'
  printf 'LOCAL_REPO=%s\n' "$local_repo"
  printf 'CANDIDATE_SHA=%s\n' "$candidate"
  printf 'REMOTE_HOST=%s\n' "$remote_host"
  printf 'REMOTE_CANDIDATE_REF=%s\n' "$remote_candidate_ref"
  printf 'REMOTE_HANDOFF_REPO=/home/tibger01/projects/fornjot/push_gpu\n'
  printf 'REMOTE_WORKTREE=%s\n' "$expected_worktree"
  printf 'FPV_TARGET=%s\n' "$formal_target"
  printf 'FPV_JOBS=%s\n' "$jobs"
  printf 'FPV_LOCAL_PROOF_JOB_CAP=%s\n' "$jobs"
  printf 'FPV_CONCURRENCY_VERIFICATION=RUNTIME_REQUIRED\n'
  printf 'FPV_PROOF_LIMIT=%s\n' "$proof_limit"
  printf 'FPV_CEX_SAVE_LIMIT=%s\n' "$cex_save_limit"
  printf 'FPV_PROOF_CACHE_MODE=%s\n' "$proof_cache_mode"
  printf 'FPV_INDIVIDUAL_CEX_STOP=UNVERIFIED_GAP\n'
  printf 'WORKTREE_POLICY=retain\n'
  exit 0
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="fb-tex-flt-$short_sha-$proof_limit-$timestamp-$$"
local_artifact_dir="$local_artifact_root/$run_id"
mkdir -p "$local_artifact_dir"

printf 'RUN_ID=%s\n' "$run_id"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"
printf 'Transferring candidate %s to the RHEL8 push_gpu handoff.\n' "$candidate"
set +e
"$transfer_script" --repo "$local_repo" --host "$remote_host" \
  --remote-ref "$remote_candidate_ref" 2>&1 | tee "$local_artifact_dir/transfer.log"
transfer_status=${PIPESTATUS[0]}
set -e
((transfer_status == 0)) || die "Candidate transfer failed with status $transfer_status."

transferred_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/transfer.log")
[[ $transferred_sha == "$candidate" ]] ||
  die "Transferred SHA mismatch (expected=$candidate actual=${transferred_sha:-MISSING})."

printf 'Preparing isolated RHEL8 worktree %s.\n' "$expected_worktree"
set +e
ssh "${ssh_options[@]}" "$remote_host" bash -s -- \
  --candidate-ref "$remote_candidate_ref" \
  --workflow fpv \
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

remote_task_dir="$worktree/private/tmp/to_persist/jaspergold-rhel8-fpv/$run_id"
printf 'Staging the bounded FPV runner in %s.\n' "$remote_task_dir"
ssh "${ssh_options[@]}" "$remote_host" mkdir -p "$remote_task_dir"
scp "${ssh_options[@]}" \
  "$cex_capture_wrapper" \
  "$campaign_cache_fragment" \
  "$remote_runner" \
  "$report_tool" \
  "$process_counter" \
  "$remote_host:$remote_task_dir/"

printf 'Starting %s with a verified %s-local-proof-job target, %s hard proof time, and at most %s saved CEX traces.\n' \
  "$formal_target" "$jobs" "$proof_limit" "$cex_save_limit"
remote_run_args=(
  --worktree "$worktree"
  --run-id "$run_id"
  --target "$formal_target"
  --jobs "$jobs"
  --proof-limit "$proof_limit"
)
if ((campaign_no_prove_cache)); then
  remote_run_args+=(--campaign-no-prove-cache)
fi
set +e
ssh "${ssh_options[@]}" "$remote_host" \
  bash "$remote_task_dir/run_fpv.sh" \
  "${remote_run_args[@]}" 2>&1 | tee "$local_artifact_dir/remote-session.log"
proof_status=${PIPESTATUS[0]}
set -e
printf 'REMOTE_FPV_STATUS=%s\n' "$proof_status"

printf 'Collecting small proof reports and replay metadata; large databases and VCDs stay remote.\n'
set +e
"$collect_script" --repo "$local_repo" --host "$remote_host" \
  --worktree "$worktree" --run-id "$run_id" 2>&1 | tee "$local_artifact_dir/collect.log"
collect_status=${PIPESTATUS[0]}
set -e
((collect_status == 0)) ||
  die "Artifact collection failed with status $collect_status; the worktree was retained."

[[ -s $local_artifact_dir/run.log ]] ||
  die 'Collected run.log is missing or empty; the worktree was retained.'
summary_report=$(find "$local_artifact_dir" -type f -name fpv_property_summary.rpt -size +0c -print -quit)
summary_json=$(find "$local_artifact_dir" -type f -name fpv_property_summary.json -size +0c -print -quit)
[[ -n $summary_report && -n $summary_json ]] ||
  die 'Required FPV summaries are missing or empty; the worktree was retained.'

classification=$(awk -F': ' '$1 == "Classification" { value=$2 } END { print value }' "$summary_report")
printf 'RETAINED_WORKTREE=%s\n' "$worktree"
printf 'FPV_SUMMARY_REPORT=%s\n' "$summary_report"
printf 'FPV_SUMMARY_JSON=%s\n' "$summary_json"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"
sed -n '1,240p' "$summary_report"

if ((proof_status != 0)); then
  die "Remote FPV runner returned status $proof_status; all available evidence was collected."
fi
[[ $classification == PASS ]] ||
  die "Remote FPV classification is ${classification:-MISSING}; inspect the retained worktree and summary."
printf 'REMOTE_FPV_COMPLETE=1\n'
