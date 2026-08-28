#!/usr/bin/env bash
set -Eeuo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly summarizer="$script_dir/summarize_aacr.py"

repo=
base=
tip=
output_dir=

usage() {
  cat >&2 <<'EOF'
Usage: run_aacr_range.sh --repo PATH --base SHA --tip SHA --output-dir PATH

Run AACR deep Codex analysis for one explicit committed base..tip range and
write durable raw plus normalized evidence below output-dir.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; repo=$2; shift 2 ;;
    --base) (($# >= 2)) || die 'Missing value for --base.'; base=$2; shift 2 ;;
    --tip) (($# >= 2)) || die 'Missing value for --tip.'; tip=$2; shift 2 ;;
    --output-dir) (($# >= 2)) || die 'Missing value for --output-dir.'; output_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ -n $repo && -n $base && -n $tip && -n $output_dir ]] || {
  usage
  die 'All arguments are required.'
}
command -v git >/dev/null || die 'git is unavailable.'
command -v aacr-cli >/dev/null || die 'aacr-cli is unavailable.'
[[ -f $summarizer ]] || die "Missing result summarizer: $summarizer"

repo=$(git -c core.fsmonitor=false -C "$repo" rev-parse --show-toplevel) ||
  die 'Cannot resolve repository.'
repo=$(cd "$repo" && pwd -P)
base=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify "$base^{commit}") ||
  die 'Cannot resolve base commit.'
tip=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify "$tip^{commit}") ||
  die 'Cannot resolve tip commit.'
git -c core.fsmonitor=false -C "$repo" merge-base --is-ancestor "$base" "$tip" ||
  die "Base is not an ancestor of tip: $base..$tip"

mkdir -p "$output_dir"
output_dir=$(cd "$output_dir" && pwd -P)
case "$output_dir/" in
  "$repo/private/tmp/to_persist/"*) ;;
  *) die 'Output directory must be below repository private/tmp/to_persist.' ;;
esac
[[ ! -e $output_dir/summary.json ]] ||
  die "Refusing to overwrite retained AACR result: $output_dir/summary.json"

raw_json="$output_dir/aacr.raw.json"
text_artifact="$output_dir/aacr.txt"
html_dir="$output_dir/html"
log="$output_dir/aacr.log"
summary_json="$output_dir/summary.json"
summary_text="$output_dir/summary.txt"
mkdir -p "$html_dir"
printf '%s\n' "aacr-cli --target-sha $base..$tip --deep-analysis-codex --no-caching --json-output $raw_json --output-file $text_artifact --html-report $html_dir" \
  >"$output_dir/command.txt"

set +e
(
  cd "$repo"
  aacr-cli --target-sha "$base..$tip" --deep-analysis-codex --no-caching \
    --json-output "$raw_json" --output-file "$text_artifact" \
    --html-report "$html_dir"
) 2>&1 | tee "$log"
command_status=${PIPESTATUS[0]}
set -e

summary_status=0
python3 "$summarizer" \
  --raw-json "$raw_json" --log "$log" --text-artifact "$text_artifact" \
  --html-dir "$html_dir" --json-output "$summary_json" \
  --text-output "$summary_text" --command-status "$command_status" \
  --base "$base" --tip "$tip" || summary_status=$?

cat >"$output_dir/status.env" <<EOF
SCHEMA_VERSION=1
BRANCH=aacr
BASE_SHA=$base
CANDIDATE_SHA=$tip
COMMAND_STATUS=$command_status
SUMMARY_STATUS=$summary_status
SUMMARY_JSON=$summary_json
EOF
printf 'AACR_SUMMARY_JSON=%s\n' "$summary_json"
printf 'AACR_COMMAND_STATUS=%s\n' "$command_status"
((summary_status == 0)) || exit "$summary_status"
((command_status == 0)) || exit "$command_status"
