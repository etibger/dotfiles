#!/usr/bin/env bash
set -Eeuo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly summarizer="$script_dir/summarize_sanity.py"

repo=/gpu
candidate=
source_preflight=
output_dir=
expected_pattern=legal_hdr_return_addr

usage() {
  cat >&2 <<'EOF'
Usage: run_sanity.sh --repo /gpu --candidate FULL_SHA \
  --source-preflight FILE --output-dir PATH \
  [--expected-pattern REGEX]

Run the fixed seed-1 test_mix_all_tiny__sanity command inside the GPU
xcelium_jaspergold_blkformal devcontainer.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

manifest_value() {
  local key=$1
  sed -n "s/^${key}=//p" "$source_preflight" | tail -n 1
}

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; repo=$2; shift 2 ;;
    --candidate) (($# >= 2)) || die 'Missing value for --candidate.'; candidate=${2,,}; shift 2 ;;
    --source-preflight) (($# >= 2)) || die 'Missing value for --source-preflight.'; source_preflight=$2; shift 2 ;;
    --output-dir) (($# >= 2)) || die 'Missing value for --output-dir.'; output_dir=$2; shift 2 ;;
    --expected-pattern) (($# >= 2)) || die 'Missing value for --expected-pattern.'; expected_pattern=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ $candidate =~ ^[0-9a-f]{40}$ ]] || die '--candidate must be a full SHA.'
[[ -n $source_preflight && -n $output_dir ]] || die 'Preflight and output paths are required.'
repo=$(git -c core.fsmonitor=false -C "$repo" rev-parse --show-toplevel) || die 'Cannot resolve repository.'
repo=$(cd "$repo" && pwd -P)
actual=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify 'HEAD^{commit}')
[[ $actual == "$candidate" ]] || die "Candidate mismatch: expected=$candidate actual=$actual"
source_preflight=$(realpath "$source_preflight") || die 'Cannot resolve source-preflight manifest.'
case "$source_preflight" in
  "$repo/private/tmp/to_persist/"*) ;;
  *) die 'Source-preflight manifest must be below repository private/tmp/to_persist.' ;;
esac
[[ $(manifest_value STATUS) == PASS ]] || die 'Source generation preflight did not pass.'
[[ $(manifest_value SERIALIZED_BARRIER) == 1 ]] || die 'Source generation barrier is missing.'
[[ $(manifest_value CANDIDATE_SHA) == "$candidate" ]] || die 'Source-preflight candidate does not match.'
[[ $(manifest_value COMMAND) == design/logical/make_sources ]] || die 'Source-preflight command identity does not match.'

mkdir -p "$output_dir"
output_dir=$(cd "$output_dir" && pwd -P)
case "$output_dir/" in
  "$repo/private/tmp/to_persist/"*) ;;
  *) die 'Output directory must be below repository private/tmp/to_persist.' ;;
esac
[[ ! -e $output_dir/summary.json ]] || die 'Refusing to overwrite retained simulation summary.'
run_dir="$output_dir/run"
[[ ! -e $run_dir/.blk_setup ]] || die 'Refusing to reuse an initialized simulation directory.'
mkdir -p "$run_dir"
driver_log="$output_dir/driver.log"
printf '%s\n' "blk_val --build-clean --storage-services elk=n --set-lsf-mem-limit 12000 --no-bsub --no-bsub-build --dfs batch --bo 8x_mtcs --seed 1 --plusarg '+tex_trace_shim +tex_checkers_enable=all' test_mix_all_tiny__sanity" \
  >"$output_dir/command.txt"

set +e
(
  export NO_COMPONENTS_CHECK=1
  export NO_VM_COMPONENT_UPDATE=1
  cd "$repo/verification/tb_deploy/tb_tex"
  set +u
  source ./sourceme
  set -u
  cd "$run_dir"
  blk_setup
  blk_val --build-clean --storage-services elk=n \
    --set-lsf-mem-limit 12000 --no-bsub --no-bsub-build \
    --dfs batch --bo 8x_mtcs --seed 1 \
    --plusarg "+tex_trace_shim +tex_checkers_enable=all" \
    test_mix_all_tiny__sanity
) 2>&1 | tee "$driver_log"
command_status=${PIPESTATUS[0]}
set -e

shopt -s nullglob
test_logs=("$run_dir"/logs_tests/xlm__test_mix_all_tiny__sanity__s1__*.log)
test_log="$output_dir/missing-test.log"
error_json="$output_dir/missing-error.json"
blk_status_code=125
if ((${#test_logs[@]} == 1)); then
  test_log=${test_logs[0]}
  candidate_error=${test_log%.log}_error.json
  [[ -f $candidate_error ]] && error_json=$candidate_error
  set +e
  (
    cd "$run_dir"
    blk_status "$test_log"
  ) >"$output_dir/blk-status.log" 2>&1
  blk_status_code=$?
  set -e
elif ((${#test_logs[@]} > 1)); then
  printf 'Ambiguous batch logs:\n' >"$output_dir/blk-status.log"
  printf '%s\n' "${test_logs[@]}" >>"$output_dir/blk-status.log"
else
  printf 'No batch log matched the fixed test and seed.\n' >"$output_dir/blk-status.log"
fi

python3 "$summarizer" \
  --test-log "$test_log" --error-json "$error_json" \
  --driver-log "$driver_log" --json-output "$output_dir/summary.json" \
  --text-output "$output_dir/summary.txt" --command-status "$command_status" \
  --blk-status "$blk_status_code" --candidate "$candidate" \
  --expected-pattern "$expected_pattern"
cat >"$output_dir/status.env" <<EOF
SCHEMA_VERSION=1
BRANCH=simulation
CANDIDATE_SHA=$candidate
COMMAND_STATUS=$command_status
BLK_STATUS=$blk_status_code
SUMMARY_JSON=$output_dir/summary.json
EOF
printf 'SIMULATION_SUMMARY_JSON=%s\n' "$output_dir/summary.json"
