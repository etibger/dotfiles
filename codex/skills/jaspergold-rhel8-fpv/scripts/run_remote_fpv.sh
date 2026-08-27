#!/usr/bin/env bash
set -Eeuo pipefail

readonly local_repo=/Users/tibger01/Projects/Fornjot/c_gpu
readonly remote_host=rhel8-VM
readonly remote_candidate_ref_prefix=fpv-candidate
readonly formal_target=tex_flt
readonly remote_worktree_root=/home/tibger01/projects/fornjot
readonly max_jobs=10
readonly min_proof_seconds=60
readonly max_proof_seconds=86400

readonly skills_root=/Users/tibger01/.config/codex/skills
readonly transfer_script="$skills_root/transfer-git-commit-to-rhel8/scripts/transfer_candidate.sh"
readonly setup_script="$skills_root/setup-gpu-repo-rhel8/scripts/setup_worktree.sh"
readonly remove_script="$skills_root/setup-gpu-repo-rhel8/scripts/remove_worktree.sh"
readonly local_jasper_wrapper="$skills_root/jaspergold-local-fpv/assets/stop_on_first_cex_vcd.tcl"
readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly remote_runner="$script_dir/run_fpv.sh"
readonly report_tool="$script_dir/summarize_fpv_results.py"

commit=
jobs=6
proof_limit=30m
dry_run=0
recovery_worktree=

usage() {
  cat <<'EOF'
Usage: run_remote_fpv.sh --commit SHA [--jobs N] [--proof-limit DURATION] [--dry-run]

Run the fixed fb_tex_flt/tex_flt workflow on rhel8-VM. The requested commit
must be the current HEAD of /Users/tibger01/Projects/Fornjot/c_gpu.

Options:
  --commit SHA           Candidate commit (7-40 hexadecimal characters)
  --jobs N               FTRun slot cap, 1-10 (default: 6)
  --proof-limit DURATION Active proof limit, 1m-24h (default: 30m)
  --dry-run              Validate locally and print the resolved plan
  -h, --help             Show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

report_retained_worktree() {
  local status=$?
  if ((status != 0)) && [[ -n $recovery_worktree ]]; then
    printf 'RECOVERY_WORKTREE=%s\n' "$recovery_worktree" >&2
  fi
}

trap report_retained_worktree EXIT

while (($#)); do
  case "$1" in
    --commit)
      (($# >= 2)) || die 'Missing value for --commit.'
      commit=$2
      shift 2
      ;;
    --jobs)
      (($# >= 2)) || die 'Missing value for --jobs.'
      jobs=$2
      shift 2
      ;;
    --proof-limit)
      (($# >= 2)) || die 'Missing value for --proof-limit.'
      proof_limit=$2
      shift 2
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n $commit ]] || die '--commit is required.'
[[ $commit =~ ^[0-9A-Fa-f]{7,40}$ ]] || die '--commit must be a 7-40 digit hexadecimal SHA.'
[[ $jobs =~ ^[1-9][0-9]*$ ]] || die '--jobs must be an integer.'
jobs_value=$((10#$jobs))
((jobs_value <= max_jobs)) || die "--jobs must be no greater than $max_jobs."
jobs=$jobs_value

[[ $proof_limit =~ ^([1-9][0-9]*)(s|m|h)$ ]] ||
  die '--proof-limit must be a positive duration such as 60s, 30m, or 2h.'
proof_value=$((10#${BASH_REMATCH[1]}))
proof_unit=${BASH_REMATCH[2]}
case "$proof_unit" in
  s) proof_seconds=$proof_value ;;
  m) proof_seconds=$((proof_value * 60)) ;;
  h) proof_seconds=$((proof_value * 3600)) ;;
esac
((proof_seconds >= min_proof_seconds && proof_seconds <= max_proof_seconds)) ||
  die '--proof-limit must be between 1 minute and 24 hours.'

[[ -d $local_repo/.git ]] || die "Fixed local repository is unavailable: $local_repo"
for required_file in \
  "$transfer_script" \
  "$setup_script" \
  "$remove_script" \
  "$local_jasper_wrapper" \
  "$remote_runner" \
  "$report_tool"; do
  [[ -f $required_file ]] || die "Required workflow file is missing: $required_file"
done
[[ -x $transfer_script ]] || die "Transfer helper is not executable: $transfer_script"

candidate=$(git -C "$local_repo" rev-parse --verify "$commit^{commit}") ||
  die "Cannot resolve candidate commit: $commit"
head_sha=$(git -C "$local_repo" rev-parse --verify 'HEAD^{commit}')
[[ $candidate == "$head_sha" ]] ||
  die "Requested commit is not current HEAD (requested=$candidate HEAD=$head_sha)."

short_sha=${candidate:0:12}
remote_candidate_ref="$remote_candidate_ref_prefix-$short_sha"
expected_worktree="$remote_worktree_root/tmp_gpu_fpv_run_$short_sha"
ssh_options=(
  -o BatchMode=yes
  -o ConnectTimeout=15
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=4
)

if ((dry_run)); then
  transfer_output=$("$transfer_script" \
    --repo "$local_repo" \
    --host "$remote_host" \
    --remote-ref "$remote_candidate_ref" \
    --dry-run)
  printf '%s\n' "$transfer_output"
  printf 'MODE=DRY_RUN\n'
  printf 'LOCAL_REPO=%s\n' "$local_repo"
  printf 'CANDIDATE_SHA=%s\n' "$candidate"
  printf 'REMOTE_HOST=%s\n' "$remote_host"
  printf 'REMOTE_CANDIDATE_REF=%s\n' "$remote_candidate_ref"
  printf 'REMOTE_WORKTREE=%s\n' "$expected_worktree"
  printf 'FPV_TARGET=%s\n' "$formal_target"
  printf 'FPV_JOBS=%s\n' "$jobs"
  printf 'FPV_PROOF_LIMIT=%s\n' "$proof_limit"
  exit 0
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
run_id="fb-tex-flt-$short_sha-$proof_limit-$timestamp-$$"
local_artifact_dir="$local_repo/private/tmp/jaspergold-rhel8-fpv/$run_id"
mkdir -p "$local_artifact_dir"

printf 'RUN_ID=%s\n' "$run_id"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"
printf 'Transferring candidate %s to %s.\n' "$candidate" "$remote_host"
set +e
"$transfer_script" \
  --repo "$local_repo" \
  --host "$remote_host" \
  --remote-ref "$remote_candidate_ref" 2>&1 | tee "$local_artifact_dir/transfer.log"
transfer_status=${PIPESTATUS[0]}
set -e
((transfer_status == 0)) || die "Candidate transfer failed with status $transfer_status."

transferred_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/transfer.log")
closest_ref=$(awk -F= '$1 == "CLOSEST_ORIGIN_REF" { value=$2 } END { print value }' \
  "$local_artifact_dir/transfer.log")
[[ $transferred_sha == "$candidate" ]] ||
  die "Transferred SHA mismatch (expected=$candidate actual=${transferred_sha:-MISSING})."
if [[ $closest_ref != UNKNOWN ]]; then
  [[ $closest_ref =~ ^origin/[A-Za-z0-9][A-Za-z0-9._/-]*$ && $closest_ref != *..* ]] ||
    die "Transfer helper returned an unsafe origin ref: $closest_ref"
fi

printf 'Preparing isolated RHEL8 worktree %s.\n' "$expected_worktree"
setup_args=(--candidate-ref "$remote_candidate_ref")
if [[ $closest_ref != UNKNOWN ]]; then
  setup_args+=(--base-ref "$closest_ref")
fi
set +e
ssh "${ssh_options[@]}" "$remote_host" bash -s -- "${setup_args[@]}" \
  < "$setup_script" 2>&1 | tee "$local_artifact_dir/setup.log"
setup_status=${PIPESTATUS[0]}
set -e
((setup_status == 0)) || die "Remote worktree setup failed with status $setup_status."

worktree=$(awk -F= '$1 == "WORKTREE" { value=$2 } END { print value }' \
  "$local_artifact_dir/setup.log")
prepared_sha=$(awk -F= '$1 == "CANDIDATE_SHA" { value=$2 } END { print value }' \
  "$local_artifact_dir/setup.log")
[[ $worktree == "$expected_worktree" ]] ||
  die "Remote worktree mismatch (expected=$expected_worktree actual=${worktree:-MISSING})."
[[ $prepared_sha == "$candidate" ]] ||
  die "Prepared SHA mismatch (expected=$candidate actual=${prepared_sha:-MISSING})."
recovery_worktree=$worktree

remote_task_dir="$worktree/private/tmp/jaspergold-rhel8-fpv/$run_id"
printf 'Staging the bounded FPV runner in %s.\n' "$remote_task_dir"
ssh "${ssh_options[@]}" "$remote_host" mkdir -p "$remote_task_dir"
scp "${ssh_options[@]}" \
  "$local_jasper_wrapper" \
  "$remote_runner" \
  "$report_tool" \
  "$remote_host:$remote_task_dir/"

printf 'Starting %s with %s slots and a %s active proof limit.\n' \
  "$formal_target" "$jobs" "$proof_limit"
set +e
ssh "${ssh_options[@]}" "$remote_host" \
  bash "$remote_task_dir/run_fpv.sh" \
  --worktree "$worktree" \
  --run-id "$run_id" \
  --target "$formal_target" \
  --jobs "$jobs" \
  --proof-limit "$proof_limit" 2>&1 | tee "$local_artifact_dir/remote-session.log"
proof_status=${PIPESTATUS[0]}
set -e
printf 'REMOTE_FPV_STATUS=%s\n' "$proof_status"

printf 'Collecting proof reports, logs, replay commands, and VCDs.\n'
set +e
"$script_dir/collect_artifacts.sh" \
  --repo "$local_repo" \
  --host "$remote_host" \
  --worktree "$worktree" \
  --run-id "$run_id" 2>&1 | tee "$local_artifact_dir/collect.log"
collect_status=${PIPESTATUS[0]}
set -e
if ((collect_status != 0)); then
  die "Artifact collection failed with status $collect_status; the worktree was retained."
fi

[[ -s $local_artifact_dir/run.log ]] || {
  die 'Collected run.log is missing or empty; the worktree was retained.'
}
summary_rpt=$(find "$local_artifact_dir" -type f -name fpv_property_summary.rpt -size +0c -print -quit)
summary_json=$(find "$local_artifact_dir" -type f -name fpv_property_summary.json -size +0c -print -quit)
if [[ -z $summary_rpt || -z $summary_json ]]; then
  die 'Required property summaries are missing or empty; the worktree was retained.'
fi

printf 'FPV_SUMMARY_REPORT=%s\n' "$summary_rpt"
printf 'FPV_SUMMARY_JSON=%s\n' "$summary_json"
sed -n '1,240p' "$summary_rpt"

printf 'Removing the verified, artifact-preserved worktree %s.\n' "$worktree"
set +e
ssh "${ssh_options[@]}" "$remote_host" bash -s -- \
  --worktree "$worktree" --yes < "$remove_script" 2>&1 |
  tee "$local_artifact_dir/cleanup.log"
cleanup_status=${PIPESTATUS[0]}
set -e
if ((cleanup_status != 0)); then
  die "Guarded worktree cleanup failed with status $cleanup_status."
fi

recovery_worktree=
printf 'REMOTE_WORKTREE_REMOVED=%s\n' "$worktree"
printf 'LOCAL_ARTIFACT_DIR=%s\n' "$local_artifact_dir"
if ((proof_status != 0)); then
  die "Remote FPV runner returned status $proof_status; see the collected summary and logs."
fi
printf 'REMOTE_FPV_COMPLETE=1\n'
