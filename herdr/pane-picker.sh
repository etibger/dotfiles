#!/bin/bash

set -euo pipefail

PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
export PATH

for dependency in fzf jq nc; do
  command -v "$dependency" >/dev/null 2>&1 || {
    printf 'pane picker requires %s\n' "$dependency" >&2
    exit 1
  }
done

focus_pane() {
  local pane_id=$1
  local socket_path=$2

  jq -nc --arg pane_id "$pane_id" \
    '{id: "pane-picker:focus", method: "pane.focus", params: {pane_id: $pane_id}}' \
    | nc -U "$socket_path" \
    | jq -e --arg pane_id "$pane_id" \
      '.result.type == "pane_info" and .result.pane.pane_id == $pane_id' >/dev/null
}

herdr_bin=${HERDR_BIN_PATH:-herdr}
workspace_id=${HERDR_ACTIVE_WORKSPACE_ID:?missing active Herdr workspace}
tab_id=${HERDR_ACTIVE_TAB_ID:?missing active Herdr tab}
active_pane_id=${HERDR_ACTIVE_PANE_ID:?missing active Herdr pane}
socket_path=${HERDR_SOCKET_PATH:?missing Herdr socket}
export HERDR_SOCKET_PATH

panes_json=$("$herdr_bin" pane list --workspace "$workspace_id")
layout_json=$("$herdr_bin" pane layout --pane "$active_pane_id")

rows=$(printf '%s\n%s\n' "$panes_json" "$layout_json" | jq -sr --arg tab "$tab_id" '
  .[0].result.panes as $inventory
  | (.[1].result.layout.panes | sort_by(.rect.y, .rect.x) | to_entries[])
  | . as $entry
  | ($entry.key + 1) as $position
  | $entry.value as $geometry
  | ($inventory[] | select(.pane_id == $geometry.pane_id and .tab_id == $tab))
  | [
      .pane_id,
      (if .focused then "●" else " " end),
      ("[\($position)]"),
      (.label // .terminal_title_stripped // .agent // "shell"),
      (.agent_status // "unknown"),
      ((.foreground_cwd // .cwd // "") | split("/") | last)
    ]
  | @tsv
')

pane_count=0
while IFS= read -r _; do
  ((pane_count += 1))
done <<< "$rows"

number_limit=$((pane_count < 9 ? pane_count : 9))
number_bindings=
for ((position = 1; position <= number_limit; position += 1)); do
  [[ -z "$number_bindings" ]] || number_bindings+=,
  number_bindings+="${position}:pos(${position})+accept"
done

selected=$(printf '%s\n' "$rows" | fzf \
  --delimiter=$'\t' \
  --with-nth=2.. \
  --layout=reverse \
  --border=rounded \
  --info=inline \
  --prompt='pane › ' \
  --header="1-${number_limit} jump · type to filter · enter focus · esc cancel" \
  --bind="$number_bindings" \
  --preview='"${HERDR_BIN_PATH:-herdr}" pane read {1} --source visible --lines 30 2>/dev/null' \
  --preview-window='down,60%,border-top') || exit 0

pane_id=${selected%%$'\t'*}
[[ -n "$pane_id" && "$pane_id" != "$active_pane_id" ]] || exit 0

# Herdr's overlay contract preserves a synchronous focus request on child exit.
focus_pane "$pane_id" "$socket_path"
