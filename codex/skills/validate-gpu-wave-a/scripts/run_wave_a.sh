#!/usr/bin/env bash
set -Eeuo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly skill_dir="$(cd "$script_dir/.." && pwd -P)"
readonly sibling_root="$(cd "$skill_dir/.." && pwd -P)"
readonly combiner="$script_dir/summarize_wave_a.py"
readonly lint_normalizer="$script_dir/normalize_rhel8_lint.py"

repo=
base=
tip=
run_id=
image=gpu:devcontainer__xcelium_jaspergold_blkformal
simulation_pattern=legal_hdr_return_addr
fpv_pattern=legal_hdr_return_addr
lint_pattern=
rhel8_lint_runner=
dry_run=0
container=
container_started=0
aacr_pid=
simulation_pid=
fpv_pid=
lint_pid=
coordinator_started_utc=
all_branches_started_utc=
first_completion_wait_utc=
all_branches_collected_utc=
started_branches=
collected_branches=
branch_launch_mode=not_started
start_all_before_wait=0
collect_all_branches=1

usage() {
  cat >&2 <<'EOF'
Usage: run_wave_a.sh --repo PATH --base SHA --tip SHA \
  --lint-pattern REGEX [options]

Options:
  --run-id ID                  Retained run directory name
  --image IMAGE                Combined Xcelium/JasperGold devcontainer image
  --simulation-pattern REGEX   Expected candidate signature (default legal_hdr_return_addr)
  --fpv-pattern REGEX          Expected formal property (default legal_hdr_return_addr)
  --lint-pattern REGEX         Required expected lint-evidence signature
  --rhel8-lint-runner FILE     Override staged/installed RHEL8 runner discovery
  --dry-run                    Validate and print the non-mutating execution plan
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

utc_now() {
  python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))'
}

sha256_file() {
  python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
}

branch_prefix() {
  printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
}

branch_attempt_id() {
  printf '%s.%s.1' "$run_id" "$1"
}

branch_summary_rel() {
  printf '%s/summary.json' "${1//_/-}"
}

branch_command_rel() {
  case "$1" in
    aacr) printf 'aacr/command.txt' ;;
    simulation) printf 'simulation/command.txt' ;;
    fpv) printf 'fpv/command.txt' ;;
    rhel8_lint) printf 'logs/rhel8-lint.driver.log' ;;
    *) return 1 ;;
  esac
}

branch_marker_rel() {
  printf 'orchestration/%s.attempt-1.%s.env' "$1" "$2"
}

append_branch() {
  local current=$1
  local branch=$2
  if [[ -n $current ]]; then
    printf '%s,%s' "$current" "$branch"
  else
    printf '%s' "$branch"
  fi
}

stop_container() {
  if ((container_started)) && [[ -n $container ]]; then
    docker stop --time 5 "$container" >/dev/null 2>&1 || true
    container_started=0
  fi
}

on_signal() {
  local pid
  for pid in "$aacr_pid" "$simulation_pid" "$fpv_pid" "$lint_pid"; do
    [[ -n $pid ]] && kill "$pid" >/dev/null 2>&1 || true
  done
  stop_container
  exit 130
}
trap stop_container EXIT
trap on_signal HUP INT TERM

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; repo=$2; shift 2 ;;
    --base) (($# >= 2)) || die 'Missing value for --base.'; base=$2; shift 2 ;;
    --tip) (($# >= 2)) || die 'Missing value for --tip.'; tip=$2; shift 2 ;;
    --run-id) (($# >= 2)) || die 'Missing value for --run-id.'; run_id=$2; shift 2 ;;
    --image) (($# >= 2)) || die 'Missing value for --image.'; image=$2; shift 2 ;;
    --simulation-pattern) (($# >= 2)) || die 'Missing value for --simulation-pattern.'; simulation_pattern=$2; shift 2 ;;
    --fpv-pattern) (($# >= 2)) || die 'Missing value for --fpv-pattern.'; fpv_pattern=$2; shift 2 ;;
    --lint-pattern) (($# >= 2)) || die 'Missing value for --lint-pattern.'; lint_pattern=$2; shift 2 ;;
    --rhel8-lint-runner) (($# >= 2)) || die 'Missing value for --rhel8-lint-runner.'; rhel8_lint_runner=$2; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ -n $repo && -n $base && -n $tip && -n $lint_pattern ]] || {
  usage
  die '--repo, --base, --tip, and --lint-pattern are required.'
}
for command_name in git python3; do
  command -v "$command_name" >/dev/null || die "$command_name is unavailable."
done
repo=$(git -c core.fsmonitor=false -C "$repo" rev-parse --show-toplevel) || die 'Cannot resolve repository.'
repo=$(cd "$repo" && pwd -P)
base=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify "$base^{commit}") || die 'Cannot resolve base.'
tip=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify "$tip^{commit}") || die 'Cannot resolve tip.'
head_sha=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify 'HEAD^{commit}')
[[ $tip == "$head_sha" ]] || die "Tip must be current committed HEAD (tip=$tip HEAD=$head_sha)."
git -c core.fsmonitor=false -C "$repo" merge-base --is-ancestor "$base" "$tip" || die 'Base is not an ancestor of tip.'
git -c core.fsmonitor=false -C "$repo" diff --quiet --ignore-submodules=all -- || die 'Tracked unstaged changes exist.'
git -c core.fsmonitor=false -C "$repo" diff --cached --quiet --ignore-submodules=all -- || die 'Tracked staged changes exist.'

readonly aacr_runner="$sibling_root/aacr-range-review/scripts/run_aacr_range.sh"
readonly simulation_skill="$sibling_root/tb-tex-mac-sanity"
readonly simulation_runner=/codex-wave-a/tb-tex-mac-sanity/scripts/run_sanity.sh
readonly fpv_skill="$sibling_root/jaspergold-mac-fpv"
readonly preflight_runner=/codex-wave-a/jaspergold-mac-fpv/scripts/preflight_sources.sh
readonly fpv_runner=/codex-wave-a/jaspergold-mac-fpv/scripts/run_fpv.sh
[[ -x $aacr_runner ]] || die "AACR runner is missing or not executable: $aacr_runner"
[[ -d $simulation_skill && -d $fpv_skill ]] || die 'Mac executor skill directories are missing.'
[[ -f $combiner && -f $lint_normalizer ]] || die 'Coordinator normalizers are missing.'

if [[ -z $rhel8_lint_runner ]]; then
  for candidate_runner in \
    "$sibling_root/rhel8-lint/scripts/run_remote_lint.sh" \
    "$sibling_root/../rhel8-lint/scripts/run_remote_lint.sh"; do
    if [[ -x $candidate_runner ]]; then
      rhel8_lint_runner=$candidate_runner
      break
    fi
  done
fi
[[ -n $rhel8_lint_runner && -x $rhel8_lint_runner ]] || die 'RHEL8 lint runner was not found; use --rhel8-lint-runner.'
rhel8_lint_runner=$(cd "$(dirname "$rhel8_lint_runner")" && pwd -P)/$(basename "$rhel8_lint_runner")

if [[ -z $run_id ]]; then
  run_id="wave-a-${tip:0:12}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
fi
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] || die '--run-id contains unsafe characters.'
output_dir="$repo/private/tmp/to_persist/validation-campaign/wave-a/runs/$run_id"

if ((dry_run)); then
  printf 'MODE=DRY_RUN\n'
  printf 'RANGE=%s..%s\n' "$base" "$tip"
  printf 'OUTPUT_DIR=%s\n' "$output_dir"
  printf 'SOURCE_PREFLIGHT=serialized_design_logical_make_sources\n'
  printf 'CONCURRENCY=aacr,simulation,fpv,rhel8_lint\n'
  printf 'SIMULATION=test_mix_all_tiny__sanity_seed_1\n'
  printf 'FPV=tex_flt_10m_slots_4_saved_cex_limit_5_stop_cap_unimplemented\n'
  printf 'RHEL8_LINT_RUNNER=%s\n' "$rhel8_lint_runner"
  printf 'RHEL8_LINT_ATTEMPT_TOKEN=%s\n' "$run_id"
  printf 'EVIDENCE_SCHEMA=2_live_attempt_markers_summary_and_command_sha256\n'
  printf 'GATE=AACR_complete_plus_three_attributable_detectors\n'
  exit 0
fi

command -v docker >/dev/null || die 'docker is unavailable.'
[[ ! -e $output_dir ]] || die "Refusing to reuse retained Wave A run: $output_dir"
mkdir -p "$output_dir"/{aacr,simulation,fpv,rhel8-lint,logs,orchestration}
source_preflight="$output_dir/source-preflight.env"
source_preflight_log="$output_dir/source-preflight.log"
orchestration_manifest="$output_dir/orchestration.env"
status_file="$output_dir/STATUS.md"
coordinator_started_utc=$(utc_now)

write_orchestration_manifest() {
  local temporary_manifest="${orchestration_manifest}.tmp.$$"
  local preflight_digest=
  local branch prefix attempt_id summary_rel summary_file summary_digest
  local command_rel command_file command_digest
  [[ -f $source_preflight ]] && preflight_digest=$(sha256_file "$source_preflight")
  {
    printf 'SCHEMA_VERSION=2\n'
    printf 'PROVENANCE_MODE=LIVE_COORDINATOR\n'
    printf 'RUN_ID=%s\n' "$run_id"
    printf 'BASE_SHA=%s\n' "$base"
    printf 'TIP_SHA=%s\n' "$tip"
    printf 'RANGE=%s..%s\n' "$base" "$tip"
    printf 'BRANCH_LAUNCH_MODE=%s\n' "$branch_launch_mode"
    printf 'START_ALL_BEFORE_WAIT=%s\n' "$start_all_before_wait"
    printf 'COLLECT_ALL_BRANCHES=%s\n' "$collect_all_branches"
    printf 'STARTED_BRANCHES=%s\n' "$started_branches"
    printf 'COLLECTED_BRANCHES=%s\n' "$collected_branches"
    printf 'COORDINATOR_STARTED_UTC=%s\n' "$coordinator_started_utc"
    printf 'ALL_BRANCHES_STARTED_UTC=%s\n' "$all_branches_started_utc"
    printf 'FIRST_COMPLETION_WAIT_UTC=%s\n' "$first_completion_wait_utc"
    printf 'ALL_BRANCHES_COLLECTED_UTC=%s\n' "$all_branches_collected_utc"
    printf 'SOURCE_PREFLIGHT_REL=source-preflight.env\n'
    printf 'SOURCE_PREFLIGHT_SHA256=%s\n' "$preflight_digest"
    for branch in aacr simulation fpv rhel8_lint; do
      prefix=$(branch_prefix "$branch")
      attempt_id=$(branch_attempt_id "$branch")
      summary_rel=$(branch_summary_rel "$branch")
      summary_file="$output_dir/$summary_rel"
      summary_digest=
      [[ -f $summary_file ]] && summary_digest=$(sha256_file "$summary_file")
      command_rel=$(branch_command_rel "$branch")
      command_file="$output_dir/$command_rel"
      command_digest=
      [[ -f $command_file ]] && command_digest=$(sha256_file "$command_file")
      printf '%s_ATTEMPT_ID=%s\n' "$prefix" "$attempt_id"
      printf '%s_START_MARKER_REL=%s\n' "$prefix" "$(branch_marker_rel "$branch" started)"
      printf '%s_FINISH_MARKER_REL=%s\n' "$prefix" "$(branch_marker_rel "$branch" finished)"
      printf '%s_COLLECTION_MARKER_REL=%s\n' "$prefix" "$(branch_marker_rel "$branch" collected)"
      printf '%s_SUMMARY_REL=%s\n' "$prefix" "$summary_rel"
      printf '%s_SUMMARY_SHA256=%s\n' "$prefix" "$summary_digest"
      printf '%s_COMMAND_REL=%s\n' "$prefix" "$command_rel"
      printf '%s_COMMAND_SHA256=%s\n' "$prefix" "$command_digest"
    done
  } >"$temporary_manifest"
  mv "$temporary_manifest" "$orchestration_manifest"
}

write_start_marker() {
  local branch=$1
  local pid=$2
  local started_utc=$3
  local marker="$output_dir/$(branch_marker_rel "$branch" started)"
  local temporary_marker="${marker}.tmp.$BASHPID"
  cat >"$temporary_marker" <<EOF
SCHEMA_VERSION=1
PROVENANCE_MODE=LIVE_COORDINATOR
RUN_ID=$run_id
ATTEMPT_ID=$(branch_attempt_id "$branch")
BRANCH=$branch
BASE_SHA=$base
TIP_SHA=$tip
RANGE=$base..$tip
PID=$pid
STARTED_UTC=$started_utc
EOF
  mv "$temporary_marker" "$marker"
}

write_finish_marker() {
  local branch=$1
  local pid=$2
  local exit_status=$3
  local finished_utc=$4
  local marker="$output_dir/$(branch_marker_rel "$branch" finished)"
  local temporary_marker="${marker}.tmp.$BASHPID"
  cat >"$temporary_marker" <<EOF
SCHEMA_VERSION=1
PROVENANCE_MODE=LIVE_COORDINATOR
RUN_ID=$run_id
ATTEMPT_ID=$(branch_attempt_id "$branch")
BRANCH=$branch
BASE_SHA=$base
TIP_SHA=$tip
RANGE=$base..$tip
PID=$pid
EXIT_STATUS=$exit_status
FINISHED_UTC=$finished_utc
EOF
  mv "$temporary_marker" "$marker"
}

write_collection_marker() {
  local branch=$1
  local summary_rel=$2
  local summary_digest=$3
  local command_rel=$4
  local command_digest=$5
  local collected_utc=$6
  local marker="$output_dir/$(branch_marker_rel "$branch" collected)"
  local temporary_marker="${marker}.tmp.$BASHPID"
  cat >"$temporary_marker" <<EOF
SCHEMA_VERSION=1
PROVENANCE_MODE=LIVE_COORDINATOR
RUN_ID=$run_id
ATTEMPT_ID=$(branch_attempt_id "$branch")
BRANCH=$branch
BASE_SHA=$base
TIP_SHA=$tip
RANGE=$base..$tip
SUMMARY_REL=$summary_rel
SUMMARY_SHA256=$summary_digest
COMMAND_REL=$command_rel
COMMAND_SHA256=$command_digest
COLLECTED_UTC=$collected_utc
EOF
  mv "$temporary_marker" "$marker"
}

write_orchestration_manifest

cat >"$output_dir/run.env" <<EOF
SCHEMA_VERSION=1
WAVE=A
RUN_ID=$run_id
BASE_SHA=$base
TIP_SHA=$tip
RANGE=$base..$tip
IMAGE=$image
SIMULATION_PATTERN=$simulation_pattern
FPV_PATTERN=$fpv_pattern
LINT_PATTERN=$lint_pattern
EOF

local_user=$(id -un)
container="codex-wave-a-${tip:0:10}-$$"
docker_args=(
  run -d --rm --name "$container" --network bridge
  -v "$repo:/gpu"
  -v "$simulation_skill:/codex-wave-a/tb-tex-mac-sanity:ro"
  -v "$fpv_skill:/codex-wave-a/jaspergold-mac-fpv:ro"
  -e "USER=$local_user" -e "HOST_UID=$(id -u)" -e "HOST_GID=$(id -g)"
  -w /gpu
)
[[ -f ${HOME}/.netrc ]] && docker_args+=(-v "${HOME}/.netrc:/home/$local_user/.netrc:ro")
[[ -d ${HOME}/.config/arm-eap ]] && docker_args+=(-v "${HOME}/.config/arm-eap:/home/$local_user/.config/arm-eap:ro")
[[ -d ${HOME}/.config/gpuhwdevcontainer ]] && docker_args+=(-v "${HOME}/.config/gpuhwdevcontainer:/home/$local_user/.config/gpuhwdevcontainer:ro")
docker_args+=("$image" -lc 'trap "exit 0" TERM INT; while :; do sleep 3600 & wait $!; done')

printf 'Starting transient Wave A devcontainer %s.\n' "$container"
docker "${docker_args[@]}" >"$output_dir/logs/container-start.log" 2>&1
container_started=1
container_exec=(docker exec --user "$(id -u):$(id -g)" --env "HOME=/home/$local_user" --env "USER=$local_user" "$container" /bin/bash --login)

container_output=${output_dir#"$repo"}
container_output="/gpu$container_output"
printf 'Running the serialized make-sources barrier before either Mac branch.\n'
set +e
"${container_exec[@]}" "$preflight_runner" \
  --repo /gpu --candidate "$tip" \
  --output "$container_output/source-preflight.env" \
  --log "$container_output/source-preflight.log" \
  2>&1 | tee "$output_dir/logs/source-preflight-driver.log"
preflight_status=${PIPESTATUS[0]}
set -e
if ((preflight_status != 0)) || [[ ! -f $source_preflight ]]; then
  cat >"$source_preflight" <<EOF
SCHEMA_VERSION=1
STATUS=FAIL
CANDIDATE_SHA=$tip
COMMAND=design/logical/make_sources
SERIALIZED_BARRIER=1
EXIT_STATUS=$preflight_status
LOG=$source_preflight_log
EOF
  write_orchestration_manifest
  printf '# Wave A status\n\nSource generation: **FAILED**\n\nNo validation branch was launched.\n' >"$status_file"
  set +e
  python3 "$combiner" --source-preflight "$source_preflight" \
    --orchestration "$orchestration_manifest" \
    --aacr "$output_dir/aacr/summary.json" \
    --simulation "$output_dir/simulation/summary.json" \
    --fpv "$output_dir/fpv/summary.json" \
    --rhel8-lint "$output_dir/rhel8-lint/summary.json" \
    --base "$base" --tip "$tip" --json-output "$output_dir/state.json" \
    --text-output "$output_dir/summary.txt"
  set -e
  printf 'WAVE_A_STATUS_FILE=%s\n' "$status_file"
  exit 1
fi

launch_branch() {
  local branch=$1
  local exit_file=$2
  local log_file=$3
  local started_utc
  shift 3
  started_utc=$(utc_now)
  (
    branch_pid=$BASHPID
    set +e
    "$@" >"$log_file" 2>&1
    branch_status=$?
    printf '%s\n' "$branch_status" >"${exit_file}.tmp.$BASHPID"
    mv "${exit_file}.tmp.$BASHPID" "$exit_file"
    if ! write_finish_marker "$branch" "$branch_pid" "$branch_status" "$(utc_now)"; then
      printf 'Failed to publish the %s finish marker; Gate A will block.\n' "$branch" >>"$log_file"
    fi
    exit 0
  ) &
  launched_pid=$!
  write_start_marker "$branch" "$launched_pid" "$started_utc"
}

launch_branch aacr "$output_dir/logs/aacr.exit" "$output_dir/logs/aacr.driver.log" \
  "$aacr_runner" --repo "$repo" --base "$base" --tip "$tip" --output-dir "$output_dir/aacr"
aacr_pid=$launched_pid
started_branches=$(append_branch "$started_branches" aacr)
write_orchestration_manifest
launch_branch simulation "$output_dir/logs/simulation.exit" "$output_dir/logs/simulation.driver.log" \
  "${container_exec[@]}" "$simulation_runner" --repo /gpu --candidate "$tip" \
  --source-preflight "$container_output/source-preflight.env" \
  --output-dir "$container_output/simulation" --expected-pattern "$simulation_pattern"
simulation_pid=$launched_pid
started_branches=$(append_branch "$started_branches" simulation)
write_orchestration_manifest
launch_branch fpv "$output_dir/logs/fpv.exit" "$output_dir/logs/fpv.driver.log" \
  "${container_exec[@]}" "$fpv_runner" --repo /gpu --candidate "$tip" \
  --source-preflight "$container_output/source-preflight.env" \
  --output-dir "$container_output/fpv" --expected-property "$fpv_pattern"
fpv_pid=$launched_pid
started_branches=$(append_branch "$started_branches" fpv)
write_orchestration_manifest
launch_branch rhel8_lint "$output_dir/logs/rhel8-lint.exit" "$output_dir/logs/rhel8-lint.driver.log" \
  "$rhel8_lint_runner" --repo "$repo" --commit "$tip" --attempt-token "$run_id"
lint_pid=$launched_pid
started_branches=$(append_branch "$started_branches" rhel8_lint)
branch_launch_mode=parallel
start_all_before_wait=1
all_branches_started_utc=$(utc_now)
first_completion_wait_utc=$(utc_now)
write_orchestration_manifest

branch_state() {
  local exit_file=$1
  if [[ -f $exit_file ]]; then
    printf 'finished (executor exit %s)' "$(<"$exit_file")"
  else
    printf 'running'
  fi
}

write_status() {
  cat >"$status_file" <<EOF
# Wave A status

Candidate range: \`$base..$tip\`

- Source generation: complete (serialized barrier)
- AACR: $(branch_state "$output_dir/logs/aacr.exit")
- Mac simulation: $(branch_state "$output_dir/logs/simulation.exit")
- Mac FPV: $(branch_state "$output_dir/logs/fpv.exit")
- RHEL8 lint: $(branch_state "$output_dir/logs/rhel8-lint.exit")

Every branch is allowed to finish. Gate evaluation starts only after all four
results have been collected.
EOF
}

printf 'Wave A branches launched concurrently.\n'
printf 'WAVE_A_STATUS_FILE=%s\n' "$status_file"
while [[ ! -f $output_dir/logs/aacr.exit || ! -f $output_dir/logs/simulation.exit ||
         ! -f $output_dir/logs/fpv.exit || ! -f $output_dir/logs/rhel8-lint.exit ]]; do
  write_status
  sleep 10
done
write_status
wait "$aacr_pid" "$simulation_pid" "$fpv_pid" "$lint_pid"
stop_container

lint_runner_status=$(<"$output_dir/logs/rhel8-lint.exit")
if ! python3 "$lint_normalizer" \
  --driver-log "$output_dir/logs/rhel8-lint.driver.log" \
  --candidate "$tip" --expected-pattern "$lint_pattern" \
  --runner-status "$lint_runner_status" \
  --json-output "$output_dir/rhel8-lint/summary.json" \
  --text-output "$output_dir/rhel8-lint/summary.txt" \
  >"$output_dir/logs/rhel8-lint-normalize.log" 2>&1; then
  printf 'RHEL8 lint normalization failed; Gate A will block.\n' \
    >>"$output_dir/logs/rhel8-lint-normalize.log"
fi

record_collection() {
  local branch=$1
  local summary_rel summary_file summary_digest
  local command_rel command_file command_digest collected_utc
  summary_rel=$(branch_summary_rel "$branch")
  summary_file="$output_dir/$summary_rel"
  [[ -f $summary_file ]] || return 1
  summary_digest=$(sha256_file "$summary_file")
  command_rel=$(branch_command_rel "$branch")
  command_file="$output_dir/$command_rel"
  [[ -f $command_file ]] || return 1
  command_digest=$(sha256_file "$command_file")
  collected_utc=$(utc_now)
  write_collection_marker "$branch" "$summary_rel" "$summary_digest" \
    "$command_rel" "$command_digest" "$collected_utc"
  return 0
}

collected_branches=
for branch in aacr simulation fpv rhel8_lint; do
  if record_collection "$branch"; then
    collected_branches=$(append_branch "$collected_branches" "$branch")
  fi
done
if [[ $collected_branches == aacr,simulation,fpv,rhel8_lint ]]; then
  all_branches_collected_utc=$(utc_now)
fi
write_orchestration_manifest

set +e
python3 "$combiner" --source-preflight "$source_preflight" \
  --orchestration "$orchestration_manifest" \
  --aacr "$output_dir/aacr/summary.json" \
  --simulation "$output_dir/simulation/summary.json" \
  --fpv "$output_dir/fpv/summary.json" \
  --rhel8-lint "$output_dir/rhel8-lint/summary.json" \
  --base "$base" --tip "$tip" --json-output "$output_dir/state.json" \
  --text-output "$output_dir/summary.txt" | tee "$output_dir/logs/combine.log"
gate_status=${PIPESTATUS[0]}
set -e
cat "$output_dir/summary.txt" >"$status_file"
printf 'WAVE_A_STATUS_FILE=%s\n' "$status_file"
printf 'WAVE_A_SUMMARY_JSON=%s\n' "$output_dir/state.json"
exit "$gate_status"
