#!/usr/bin/env bash
set -euo pipefail

herdr_bin=${HERDR_BIN_PATH:-herdr}
workspace_id=${HERDR_ACTIVE_WORKSPACE_ID:?missing active Herdr workspace}

printf 'New tab name: '
IFS= read -r label || exit 0

args=(tab create --workspace "$workspace_id" --cwd "$HOME" --focus)
if [[ -n $label ]]; then
  args+=(--label "$label")
fi

"$herdr_bin" "${args[@]}" >/dev/null
