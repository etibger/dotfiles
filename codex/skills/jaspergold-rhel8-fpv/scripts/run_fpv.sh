#!/usr/bin/env bash
set -euo pipefail

worktree=
run_id=
target=tex_flt
jobs=6
proof_limit=30m
prove_task=prj_prove_all
config_fragment=
cex_property_glob=
campaign_no_prove_cache=0

usage() {
  printf 'Usage: %s --worktree PATH --run-id ID [--target NAME] [--jobs N] [--proof-limit 30m] [--config-fragment YAML] [--campaign-no-prove-cache] [--cex-property-glob GLOB]\n' "$0" >&2
}

while (($#)); do
  case "$1" in
    --worktree) worktree=${2:?missing value}; shift 2 ;;
    --run-id) run_id=${2:?missing value}; shift 2 ;;
    --target) target=${2:?missing value}; shift 2 ;;
    --jobs) jobs=${2:?missing value}; shift 2 ;;
    --proof-limit) proof_limit=${2:?missing value}; shift 2 ;;
    --prove-task) prove_task=${2:?missing value}; shift 2 ;;
    --config-fragment) config_fragment=${2:?missing value}; shift 2 ;;
    --campaign-no-prove-cache) campaign_no_prove_cache=1; shift ;;
    --cex-property-glob) cex_property_glob=${2:?missing value}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ $worktree =~ ^/home/tibger01/projects/fornjot/tmp_gpu_fpv_run_[0-9a-f]{12}(_[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$ ]] || {
  printf 'Rejected worktree: %s\n' "$worktree" >&2
  exit 2
}
[[ $run_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
  printf 'Rejected run ID: %s\n' "$run_id" >&2
  exit 2
}
[[ $target =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
  printf 'Rejected target: %s\n' "$target" >&2
  exit 2
}
[[ $prove_task =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
  printf 'Rejected prove task: %s\n' "$prove_task" >&2
  exit 2
}
[[ $jobs =~ ^[1-9][0-9]*$ && $jobs -le 64 ]] || {
  printf 'Jobs must be an integer from 1 to 64.\n' >&2
  exit 2
}
[[ $proof_limit =~ ^[1-9][0-9]*(s|m|h)$ ]] || {
  printf 'Proof limit must be a positive duration such as 60s, 10m, or 2h.\n' >&2
  exit 2
}
if [[ -n $cex_property_glob ]]; then
  [[ $cex_property_glob =~ ^[A-Za-z0-9_.*?:/-]+$ ]] || {
    printf 'Rejected CEX property glob.\n' >&2
    exit 2
  }
fi

formal_dir="$worktree/verification/formal/fb_tex_flt"
task_dir="$worktree/private/tmp/to_persist/jaspergold-rhel8-fpv/$run_id"
wrapper="$task_dir/capture_up_to_five_cex_vcd.tcl"
report_tool="$task_dir/summarize_fpv_results.py"
process_counter="$task_dir/count_run_jg_proof_processes.awk"
report_venv="$task_dir/report-venv"
report_uv_cache="$task_dir/uv-cache"
report_python="$report_venv/bin/python"
run_work="$task_dir/work"
log="$task_dir/run.log"
proof_process_samples="$task_dir/proof-process-samples.rpt"
proof_process_details="$task_dir/proof-process-details.tsv"
campaign_cache_fragment="$task_dir/disable_campaign_prove_cache.yaml"
campaign_cache_include=validation_campaign_disable_prove_cache
ftrun_invocation="$task_dir/ftrun-invocation.rpt"
config_include_record=NONE
proof_cache_mode=DEFAULT
monitor_pid=

stop_proof_process_monitor() {
  if [[ -n $monitor_pid ]]; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
    monitor_pid=
  fi
}
trap stop_proof_process_monitor EXIT

[[ -f $formal_dir/sourceme ]] || { printf 'Missing formal sourceme.\n' >&2; exit 1; }
[[ -f $wrapper ]] || { printf 'Missing bounded CEX-capture wrapper: %s\n' "$wrapper" >&2; exit 1; }
[[ -f $report_tool ]] || { printf 'Missing FPV report tool: %s\n' "$report_tool" >&2; exit 1; }
[[ -f $process_counter ]] || { printf 'Missing proof-process counter: %s\n' "$process_counter" >&2; exit 1; }
if ((campaign_no_prove_cache)); then
  [[ -z $config_fragment ]] || {
    printf '%s\n' '--campaign-no-prove-cache cannot be combined with --config-fragment.' >&2
    exit 2
  }
  [[ -f $campaign_cache_fragment ]] || {
    printf 'Missing campaign prove-cache fragment: %s\n' "$campaign_cache_fragment" >&2
    exit 1
  }
  config_fragment=$campaign_cache_fragment
  config_include_record=$campaign_cache_include
  proof_cache_mode=DISABLED
fi
mkdir -p "$run_work" "$report_uv_cache"

cd "$formal_dir"
set +u
source ./sourceme
set -u

command -v uv >/dev/null || {
  printf 'Missing uv after sourcing the formal environment.\n' >&2
  exit 1
}
command -v python3.12 >/dev/null || {
  printf 'Missing repository-standard python3.12 after sourcing the formal environment.\n' >&2
  exit 1
}
if [[ ! -x $report_python ]]; then
  UV_CACHE_DIR="$report_uv_cache" uv venv "$report_venv" \
    --python python3.12 --no-python-downloads
fi
[[ $($report_python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') == 3.12 ]] || {
  printf 'FPV report environment is not Python 3.12: %s\n' "$report_python" >&2
  exit 1
}

if [[ -n $config_fragment ]]; then
  config_fragment=$(realpath "$config_fragment")
  [[ $config_fragment == "$task_dir/"* && -f $config_fragment ]] || {
    printf 'Config fragment must be a file inside the task directory.\n' >&2
    exit 2
  }
  export BLKFORMAL_CONFIG="${BLKFORMAL_CONFIG:-} $config_fragment"
fi

base_tcl=${TB_HOME:-$formal_dir}/scripts/flt.tcl
[[ -f $base_tcl ]] || base_tcl="$formal_dir/scripts/flt.tcl"
[[ -f $base_tcl ]] || { printf 'Missing target Tcl.\n' >&2; exit 1; }

export FPV_MAX_JOBS=$jobs
export FPV_PROOF_LIMIT=$proof_limit
export FTRUN_BASE_TCL=$base_tcl
export FTRUN_RUN_LIMIT=$proof_limit
export FTRUN_PROVE_TASK=$prove_task
if [[ -n $cex_property_glob ]]; then
  export FTRUN_CEX_PROPERTY_GLOB=$cex_property_glob
fi

ftrun_args=("$target")
if ((campaign_no_prove_cache)); then
  ftrun_args+=(-include "$campaign_cache_include")
fi
ftrun_args+=(
  -tcl "$wrapper"
  -local
  -batch
  -auto_run
  -slots "$jobs"
  -save on_failure
)
printf 'ftrun' >"$ftrun_invocation"
printf ' %q' "${ftrun_args[@]}" >>"$ftrun_invocation"
printf '\n' >>"$ftrun_invocation"

printf 'FPV_WORKTREE=%s\n' "$worktree"
printf 'FPV_TARGET=%s\n' "$target"
printf 'FPV_MAX_JOBS=%s\n' "$jobs"
printf 'FPV_PROOF_LIMIT=%s\n' "$proof_limit"
printf 'FPV_RUN_DIR=%s\n' "$run_work"
printf 'FPV_CONFIG_FRAGMENT=%s\n' "${config_fragment:-NONE}"
printf 'FPV_CONFIG_INCLUDE=%s\n' "$config_include_record"
printf 'FPV_PROOF_CACHE_MODE=%s\n' "$proof_cache_mode"
printf 'FPV_FTRUN_INVOCATION=%s\n' "$ftrun_invocation"
printf 'FPV_CEX_PROPERTY_GLOB=%s\n' "${cex_property_glob:-FIRST_CEX}"
printf 'FPV_REPORT_PYTHON=%s\n' "$report_python"
printf 'FPV_REPORT_UV_CACHE=%s\n' "$report_uv_cache"
printf 'FPV_CEX_SAVE_LIMIT=5\n'
printf 'FPV_INDIVIDUAL_CEX_STOP=UNVERIFIED_GAP\n'
printf 'FPV_PROOF_PROCESS_SAMPLES=%s\n' "$proof_process_samples"
printf 'FPV_PROOF_PROCESS_DETAILS=%s\n' "$proof_process_details"

cd "$run_work"
proof_dir="$run_work/fts_run_$target"
: >"$proof_process_samples"
printf 'epoch\tpid\tppid\tstate\tpcpu\tetimes\tcomm\trole\targs\n' \
  >"$proof_process_details"
set +e
(
  while true; do
    epoch=$(date +%s)
    count=$(ps -eo pid=,ppid=,state=,pcpu=,etimes=,comm=,args= | \
      awk -v needle="$proof_dir" -v sample_epoch="$epoch" \
        -v details_file="$proof_process_details" -f "$process_counter")
    printf '%s %s\n' "$epoch" "${count:-0}" >>"$proof_process_samples"
    sleep 1
  done
) &
monitor_pid=$!
ftrun "${ftrun_args[@]}" 2>&1 | tee "$log"
run_status=${PIPESTATUS[0]}
stop_proof_process_monitor
set -e

printf 'FTRUN_STATUS=%s\n' "$run_status"
printf 'RUN_LOG=%s\n' "$log"
report_status=0
candidate_sha=$(git -C "$worktree" rev-parse --verify 'HEAD^{commit}')
"$report_python" "$report_tool" \
  --input "$proof_dir/proof_report.json" \
  --text-output "$proof_dir/fpv_property_summary.rpt" \
  --json-output "$proof_dir/fpv_property_summary.json" \
  --ftrun-status "$run_status" \
  --candidate-sha "$candidate_sha" \
  --host rhel8-VM \
  --worktree "$worktree" \
  --jobs "$jobs" \
  --proof-limit "$proof_limit" \
  --cex-save-limit 5 \
  --run-log "$log" \
  --process-samples "$proof_process_samples" \
  --process-details "$proof_process_details" || report_status=$?
printf 'FPV_REPORT_STATUS=%s\n' "$report_status"
case "$report_status" in
  0) printf 'FPV_CONCURRENCY_VERIFICATION=VERIFIED\n' ;;
  2) printf 'FPV_CONCURRENCY_VERIFICATION=UNVERIFIED\n' ;;
  *) printf 'FPV_CONCURRENCY_VERIFICATION=UNAVAILABLE\n' ;;
esac
rg --files "$run_work" -g '*.vcd' -g '*.rpt' -g 'verification_results.json' \
  -g '*.tsv' -g 'proof_report.json' -g 'fpv_property_summary.json' \
  -g 'run.cmd' -g 'args.json' || true
if (( run_status != 0 )); then
  exit "$run_status"
fi
# The summary tool returns 2 after writing its artifacts when the wrapper
# marker/effective IPF031/ProofGrid usable-level evidence is missing, or the
# ordinary proof-engine peak exceeds the requested slots. Cache/helper workers
# remain diagnostic. Propagate the summary status so an unverified run cannot
# look successful.
exit "$report_status"
