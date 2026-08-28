#!/usr/bin/env bash
set -Eeuo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly skill_dir="$(cd "$script_dir/.." && pwd -P)"
readonly wrapper="$skill_dir/assets/save_up_to_five_cex.tcl"
readonly summarizer="$script_dir/summarize_fpv.py"

repo=/gpu
candidate=
source_preflight=
output_dir=
expected_property=legal_hdr_return_addr

usage() {
  cat >&2 <<'EOF'
Usage: run_fpv.sh --repo /gpu --candidate FULL_SHA --source-preflight FILE \
  --output-dir PATH [--expected-property REGEX]
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
    --expected-property) (($# >= 2)) || die 'Missing value for --expected-property.'; expected_property=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ $candidate =~ ^[0-9a-f]{40}$ ]] || die '--candidate must be a full SHA.'
[[ -n $source_preflight && -n $output_dir ]] || die 'Preflight and output paths are required.'
[[ -f $wrapper && -f $summarizer ]] || die 'FPV support files are missing.'
repo=$(git -c core.fsmonitor=false -C "$repo" rev-parse --show-toplevel) || die 'Cannot resolve repository.'
repo=$(cd "$repo" && pwd -P)
actual=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify 'HEAD^{commit}')
[[ $actual == "$candidate" ]] || die "Candidate mismatch: expected=$candidate actual=$actual"
source_preflight=$(realpath "$source_preflight") || die 'Cannot resolve source-preflight manifest.'
case "$source_preflight" in "$repo/private/tmp/to_persist/"*) ;; *) die 'Preflight manifest is outside private/tmp/to_persist.' ;; esac
[[ $(manifest_value STATUS) == PASS ]] || die 'Source generation preflight did not pass.'
[[ $(manifest_value SERIALIZED_BARRIER) == 1 ]] || die 'Source generation barrier is missing.'
[[ $(manifest_value CANDIDATE_SHA) == "$candidate" ]] || die 'Source-preflight candidate does not match.'
[[ $(manifest_value COMMAND) == design/logical/make_sources ]] || die 'Source-preflight command identity does not match.'

mkdir -p "$output_dir"
output_dir=$(cd "$output_dir" && pwd -P)
case "$output_dir/" in "$repo/private/tmp/to_persist/"*) ;; *) die 'Output directory is outside private/tmp/to_persist.' ;; esac
[[ ! -e $output_dir/summary.json ]] || die 'Refusing to overwrite retained FPV summary.'
build_dir="$output_dir/fts_run_tex_flt"
[[ ! -e $build_dir ]] || die "Refusing to reuse FPV build directory: $build_dir"
log="$output_dir/ftrun.log"
formal_dir="$repo/verification/formal/fb_tex_flt"

cat >"$output_dir/command.txt" <<EOF
FTRUN_RUN_LIMIT=10m ftrun tex_flt -tcl $wrapper -build_dir $build_dir -local -batch -auto_run -slots 4 -save on_failure
EOF

set +e
(
  export NO_COMPONENTS_CHECK=1
  export NO_VM_COMPONENT_UPDATE=1
  cd "$formal_dir"
  set +u
  source ./sourceme
  set -u
  export FTRUN_BASE_TCL="${TB_HOME:-$formal_dir}/scripts/flt.tcl"
  [[ -f $FTRUN_BASE_TCL ]] || export FTRUN_BASE_TCL="$formal_dir/scripts/flt.tcl"
  export FTRUN_RUN_LIMIT=10m
  export FTRUN_PROVE_TASK=prj_prove_all
  ftrun tex_flt -tcl "$wrapper" -build_dir "$build_dir" \
    -local -batch -auto_run -slots 4 -save on_failure
) 2>&1 | tee "$log"
ftrun_status=${PIPESTATUS[0]}
set -e

python3 "$summarizer" \
  --proof-report "$build_dir/proof_report.json" --run-dir "$build_dir" \
  --log "$log" --json-output "$output_dir/summary.json" \
  --text-output "$output_dir/summary.txt" --ftrun-status "$ftrun_status" \
  --candidate "$candidate" --expected-property "$expected_property"
cat >"$output_dir/status.env" <<EOF
SCHEMA_VERSION=1
BRANCH=fpv
CANDIDATE_SHA=$candidate
FTRUN_STATUS=$ftrun_status
PROOF_LIMIT=10m
SLOTS=4
SAVED_CEX_LIMIT=5
STOP_AFTER_CEX_IMPLEMENTED=0
SUMMARY_JSON=$output_dir/summary.json
EOF
printf 'FPV_SUMMARY_JSON=%s\n' "$output_dir/summary.json"
