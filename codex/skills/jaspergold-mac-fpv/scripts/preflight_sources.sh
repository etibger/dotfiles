#!/usr/bin/env bash
set -Eeuo pipefail

repo=/gpu
candidate=
output=
log=

usage() {
  cat >&2 <<'EOF'
Usage: preflight_sources.sh --repo /gpu --candidate FULL_SHA --output FILE --log FILE

Serialize design source generation and publish the barrier required by both
Wave A Mac executors.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

while (($#)); do
  case "$1" in
    --repo) (($# >= 2)) || die 'Missing value for --repo.'; repo=$2; shift 2 ;;
    --candidate) (($# >= 2)) || die 'Missing value for --candidate.'; candidate=${2,,}; shift 2 ;;
    --output) (($# >= 2)) || die 'Missing value for --output.'; output=$2; shift 2 ;;
    --log) (($# >= 2)) || die 'Missing value for --log.'; log=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown argument: $1" ;;
  esac
done

[[ $candidate =~ ^[0-9a-f]{40}$ ]] || die '--candidate must be a full SHA.'
[[ -n $output && -n $log ]] || die '--output and --log are required.'
repo=$(git -c core.fsmonitor=false -C "$repo" rev-parse --show-toplevel) || die 'Cannot resolve repository.'
repo=$(cd "$repo" && pwd -P)
actual=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify 'HEAD^{commit}')
[[ $actual == "$candidate" ]] || die "Candidate mismatch: expected=$candidate actual=$actual"
mkdir -p "$(dirname "$output")" "$(dirname "$log")"
output_parent=$(cd "$(dirname "$output")" && pwd -P)
log_parent=$(cd "$(dirname "$log")" && pwd -P)
case "$output_parent/" in "$repo/private/tmp/to_persist/"*) ;; *) die 'Manifest must be below repository private/tmp/to_persist.' ;; esac
case "$log_parent/" in "$repo/private/tmp/to_persist/"*) ;; *) die 'Log must be below repository private/tmp/to_persist.' ;; esac
[[ ! -e $output ]] || die "Refusing to overwrite source-preflight manifest: $output"

set +e
(
  export NO_COMPONENTS_CHECK=1
  export NO_VM_COMPONENT_UPDATE=1
  cd "$repo/design"
  set +u
  source ./sourceme
  set -u
  cd logical
  printf 'SOURCE_PREFLIGHT_COMMAND=make sources\n'
  make sources
) 2>&1 | tee "$log"
preflight_status=${PIPESTATUS[0]}
set -e
((preflight_status == 0)) || exit "$preflight_status"

after=$(git -c core.fsmonitor=false -C "$repo" rev-parse --verify 'HEAD^{commit}')
[[ $after == "$candidate" ]] || die 'Candidate changed during source generation.'
cat >"$output" <<EOF
SCHEMA_VERSION=1
STATUS=PASS
CANDIDATE_SHA=$candidate
COMMAND=design/logical/make_sources
SERIALIZED_BARRIER=1
COMPLETED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LOG=$log
EOF
printf 'SOURCE_PREFLIGHT_MANIFEST=%s\n' "$output"
