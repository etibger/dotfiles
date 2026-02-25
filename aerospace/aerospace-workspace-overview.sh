#!/usr/bin/env bash
# aerospace-workspace-by-ws.sh
# Print a compact "Workspace N: App1, App2" summary using AeroSpace --format output.
# Works with bash or zsh.

set -euo pipefail

AERO="${AERO:-aerospace}"
FMT='%{window-id} | %{workspace} | %{app-name} | %{window-title}'

command -v "$AERO" >/dev/null 2>&1 || {
  echo "ERROR: '$AERO' not found in PATH. Install AeroSpace or set AERO to its binary." >&2
  exit 2
}

# Get formatted listing. If it fails, show a helpful message.
if ! raw="$($AERO list-windows --all --format "$FMT" 2>/dev/null)"; then
  echo "ERROR: failed to run: $AERO list-windows --all --format \"$FMT\"" >&2
  echo "Check AeroSpace is running and that the CLI supports --format." >&2
  exit 3
fi

# If no lines, exit gracefully
if [[ -z "${raw//[[:space:]]/}" ]]; then
  echo "No windows found."
  exit 0
fi

# Helpers: trim (bash-compatible)
trim() {
  local s="$*"
  # remove leading/trailing whitespace
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

declare -A seen_ws_app   # keys: "ws|app" -> 1 (for dedupe)
declare -A ws_list_str   # keys: ws -> comma-separated list of apps (in insertion order)
workspaces_order=()      # keep encountered workspaces (to preserve order if desired)

# Parse lines
while IFS= read -r line; do
  # ignore empty lines
  [[ -z "${line//[[:space:]]/}" ]] && continue

  # split by '|' into 4 parts (id | workspace | app | title)
  IFS='|' read -r raw_id raw_ws raw_app raw_title <<< "$line"

  id="$(trim "$raw_id")"
  ws="$(trim "$raw_ws")"
  app="$(trim "$raw_app")"
  # title="$(trim "$raw_title")"   # not used in summary but kept for possible extension

  # fallback if workspace empty
  if [[ -z "$ws" ]]; then
    ws="unknown"
  fi

  # dedupe per workspace/app
  key="${ws}|${app}"
  if [[ -z "${seen_ws_app[$key]:-}" ]]; then
    seen_ws_app[$key]=1
    if [[ -z "${ws_list_str[$ws]:-}" ]]; then
      ws_list_str[$ws]="$app"
      workspaces_order+=("$ws")
    else
      ws_list_str[$ws]="${ws_list_str[$ws]}, $app"
    fi
  fi
done <<< "$raw"

# Prepare final order: numeric workspaces sorted if possible, otherwise keep encountered order.
# Build list of unique workspaces
unique_ws=()
declare -A seen_tmp
for w in "${workspaces_order[@]}"; do
  if [[ -z "${seen_tmp[$w]:-}" ]]; then
    unique_ws+=("$w")
    seen_tmp[$w]=1
  fi
done

# If all workspace keys look numeric, sort numerically; otherwise preserve order but dedupe.
all_numeric=true
for w in "${unique_ws[@]}"; do
  if ! [[ "$w" =~ ^[0-9]+$ ]]; then
    all_numeric=false
    break
  fi
done

if $all_numeric; then
  # sort numerically and print
  IFS=$'\n' sorted_ws=($(printf "%s\n" "${unique_ws[@]}" | sort -n))
  unset IFS
else
  sorted_ws=("${unique_ws[@]}")
fi

# Print grouped summary
for ws in "${sorted_ws[@]}"; do
  apps="${ws_list_str[$ws]}"
  # if you want workspace names like "Workspace 1" for numeric values, otherwise print as-is
  if [[ "$ws" =~ ^[0-9]+$ ]]; then
    printf 'Workspace %s: %s\n' "$ws" "$apps"
  else
    printf '%s: %s\n' "$ws" "$apps"
  fi
done
