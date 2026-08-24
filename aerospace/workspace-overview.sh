#!/bin/bash

ANCHOR="aerospace_overview"

# Remove old generated popup items, if any.
sketchybar --query bar \
  | jq -r '.items[] | select(startswith("aerospace_overview.ws."))' \
  | while read -r item; do
      sketchybar --remove "$item"
    done

# AeroSpace 0.21.x:
# --all cannot be combined with --empty no,
# so use --monitor all instead.
workspaces=$(aerospace list-workspaces --monitor all --empty no)

for ws in $workspaces; do

    heading="$ANCHOR.ws.$ws"

    sketchybar --add item "$heading" popup."$ANCHOR" \
      --set "$heading" \
        icon="Workspace $ws" \
        icon.font="SF Pro:Bold:14.0" \
        label.drawing=off \
        background.drawing=on \
        background.corner_radius=5 \
        click_script="aerospace workspace '$ws'; sketchybar --set $ANCHOR popup.drawing=off"

    i=0

    while IFS='|' read -r app title; do
        app=$(echo "$app" | xargs)
        title=$(echo "$title" | xargs)

        [ -z "$app" ] && continue

        i=$((i + 1))

        if [ ${#title} -gt 55 ]; then
            title="${title:0:52}..."
        fi

        item="$ANCHOR.ws.$ws.window.$i"

        sketchybar --add item "$item" popup."$ANCHOR" \
          --set "$item" \
            icon="$app" \
            icon.font="SF Pro:Semibold:12.0" \
            icon.width=130 \
            icon.align=left \
            label="$title" \
            label.font="SF Pro:Regular:12.0" \
            label.width=350 \
            label.align=left

    done < <(
        aerospace list-windows --workspace "$ws" \
          --format '%{app-name}|%{window-title}'
    )

done

sketchybar --set "$ANCHOR" popup.drawing=toggle
