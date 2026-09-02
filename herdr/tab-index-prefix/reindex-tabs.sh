#!/usr/bin/env bash

set -u

herdr_bin=${HERDR_BIN_PATH:-herdr}
nc_bin=${HERDR_NC_PATH:-nc}
state_dir=${HERDR_PLUGIN_STATE_DIR:?HERDR_PLUGIN_STATE_DIR is required}
socket_path=${HERDR_SOCKET_PATH:?HERDR_SOCKET_PATH is required}
lock_dir=$state_dir/reindex.lock
socket_key=$(printf '%s' "$socket_path" | cksum | awk '{print $1}')
history_file=$state_dir/tab-positions-$socket_key.json

for dependency in jq "$nc_bin"; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'tab-index-prefix: %s is required\n' "$dependency" >&2
    exit 1
  fi
done

mkdir -p "$state_dir" || exit 1
for _ in {1..40}; do
  if mkdir "$lock_dir" 2>/dev/null; then
    lock_acquired=1
    break
  fi
  sleep 0.05
done
if [[ ${lock_acquired:-0} != 1 ]]; then
  exit 0
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

move_tab() {
  local tab_id=$1
  local insert_index=$2
  local response

  response=$(
    jq -nc --arg tab_id "$tab_id" --argjson insert_index "$insert_index" \
      '{id: "tab-index-prefix:move", method: "tab.move", params: {tab_id: $tab_id, insert_index: $insert_index}}' |
      "$nc_bin" -U "$socket_path"
  ) || return 1

  printf '%s\n' "$response" | jq -e 'has("result") and (has("error") | not)' >/dev/null
}

replace_closed_position() {
  local closed_tab_id=${1:-}
  local workspace_id=${2:-}
  local closed_index previous_count current_json current_count
  local created_json created_tab_id insert_index

  [[ -r $history_file ]] || return 0
  if [[ -z $closed_tab_id || -z $workspace_id ]]; then
    [[ -n ${HERDR_PLUGIN_EVENT_JSON:-} ]] || return 0
    closed_tab_id=$(printf '%s\n' "$HERDR_PLUGIN_EVENT_JSON" | jq -r '.data.tab_id // .tab_id // empty')
    workspace_id=$(printf '%s\n' "$HERDR_PLUGIN_EVENT_JSON" | jq -r '.data.workspace_id // .workspace_id // empty')
  fi
  [[ -n $closed_tab_id && -n $workspace_id ]] || return 0

  closed_index=$(jq -r --arg tab_id "$closed_tab_id" '(.tabs // .)[$tab_id].index // empty' "$history_file")
  previous_count=$(jq -r --arg tab_id "$closed_tab_id" '(.tabs // .)[$tab_id].tab_count // empty' "$history_file")
  [[ $closed_index =~ ^[0-9]+$ && $previous_count =~ ^[0-9]+$ ]] || return 0

  # Closing the final tab leaves no positional gap to preserve.
  ((closed_index < previous_count)) || return 0

  current_json=$("$herdr_bin" tab list --workspace "$workspace_id" 2>/dev/null) || return 0
  if printf '%s\n' "$current_json" | jq -e --arg tab_id "$closed_tab_id" \
    '.result.tabs[] | select(.tab_id == $tab_id)' >/dev/null; then
    return 0
  fi
  current_count=$(printf '%s\n' "$current_json" | jq -r '.result.tabs | length')
  ((current_count == previous_count - 1)) || return 0

  created_json=$(
    "$herdr_bin" tab create --workspace "$workspace_id" --label "$closed_index" --no-focus 2>/dev/null
  ) || return 0
  created_tab_id=$(printf '%s\n' "$created_json" | jq -r '.result.tab.tab_id // empty')
  [[ -n $created_tab_id ]] || return 0

  insert_index=$((closed_index - 1))
  if ! move_tab "$created_tab_id" "$insert_index"; then
    "$herdr_bin" tab close "$created_tab_id" >/dev/null 2>&1 || true
    return 1
  fi
}

replace_exited_pane_position() {
  local pane_id workspace_id closed_tab_id

  [[ -r $history_file && -n ${HERDR_PLUGIN_EVENT_JSON:-} ]] || return 0
  pane_id=$(printf '%s\n' "$HERDR_PLUGIN_EVENT_JSON" | jq -r '.data.pane_id // .pane_id // empty')
  workspace_id=$(printf '%s\n' "$HERDR_PLUGIN_EVENT_JSON" | jq -r '.data.workspace_id // .workspace_id // empty')
  [[ -n $pane_id && -n $workspace_id ]] || return 0

  closed_tab_id=$(jq -r --arg pane_id "$pane_id" '.panes[$pane_id] // empty' "$history_file")
  [[ -n $closed_tab_id ]] || return 0
  replace_closed_position "$closed_tab_id" "$workspace_id"
}

save_position_history() {
  local current_state previous_state merged_state workspace_id tab_json pane_json

  current_state=$(
    while IFS= read -r workspace_id; do
      [[ -n $workspace_id ]] || continue
      tab_json=$("$herdr_bin" tab list --workspace "$workspace_id" 2>/dev/null) || continue
      pane_json=$("$herdr_bin" pane list --workspace "$workspace_id" 2>/dev/null) || continue
      jq -nc --arg workspace_id "$workspace_id" --argjson tab_response "$tab_json" --argjson pane_response "$pane_json" '
        $tab_response.result.tabs as $tabs
        | {
            tabs: reduce ($tabs | to_entries[]) as $entry ({};
              .[$entry.value.tab_id] = {
                workspace_id: $workspace_id,
                index: ($entry.key + 1),
                tab_count: ($tabs | length)
              }),
            panes: reduce $pane_response.result.panes[] as $pane ({};
              .[$pane.pane_id] = $pane.tab_id)
          }
      '
    done < <(
      "$herdr_bin" workspace list 2>/dev/null |
        jq -r '.result.workspaces[].workspace_id'
    )
  ) || return 1

  current_state=$(printf '%s\n' "$current_state" | jq -s '
    reduce .[] as $state ({tabs: {}, panes: {}};
      .tabs += $state.tabs | .panes += $state.panes)
  ') || return 1
  previous_state='{"tabs":{},"panes":{}}'
  if [[ -r $history_file ]]; then
    previous_state=$(jq 'if has("tabs") then . else {tabs: ., panes: {}} end' "$history_file") || return 1
  fi
  merged_state=$(printf '%s\n%s\n' "$previous_state" "$current_state" | jq -s '
    {tabs: (.[0].tabs * .[1].tabs), panes: (.[0].panes * .[1].panes)}
  ') || return 1
  printf '%s\n' "$merged_state" > "$history_file.new" && mv "$history_file.new" "$history_file"
}

# A close event can arrive before the closing tab disappears from tab.list.
case ${HERDR_PLUGIN_EVENT:-} in
  tab.closed)
    sleep 0.1
    replace_closed_position || true
    ;;
  pane.exited)
    sleep 0.1
    replace_exited_pane_position || true
    ;;
esac

workspace_json=$("$herdr_bin" workspace list 2>/dev/null) || exit 0

while IFS= read -r workspace_id; do
  [[ -n $workspace_id ]] || continue
  tab_json=$("$herdr_bin" tab list --workspace "$workspace_id" 2>/dev/null) || continue

  while IFS=$'\t' read -r index tab_id label; do
    [[ -n $tab_id ]] || continue

    if [[ $label == "$index" || $label == "$index "* ]]; then
      continue
    fi

    if [[ $label =~ ^[0-9]+$ ]]; then
      desired=$index
    else
      base=$(printf '%s\n' "$label" | sed -E 's/^[0-9]+[[:space:]]+//')
      desired=$index
      [[ -n $base ]] && desired="$index $base"
    fi

    "$herdr_bin" tab rename "$tab_id" "$desired" >/dev/null 2>&1 || true
  done < <(
    printf '%s\n' "$tab_json" |
      jq -r '.result.tabs | to_entries[] | [(.key + 1), .value.tab_id, .value.label] | @tsv'
  )
done < <(
  printf '%s\n' "$workspace_json" |
    jq -r '.result.workspaces[].workspace_id'
)

save_position_history
