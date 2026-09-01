#!/bin/sh

set -eu

sample=$(/opt/homebrew/bin/tmux-mem-cpu-load \
  --interval 1 \
  --averages-count 3)

printf '%s\n' "$sample" | awk '
  function indicator(value, warning, critical) {
    if (value >= critical) return "🔴"
    if (value >= warning) return "🟡"
    return "🟢"
  }

  {
    memory = $1
    split(memory, memory_parts, "/")
    memory_used = memory_parts[1]
    memory_total = memory_parts[2]
    gsub(/[^0-9.]/, "", memory_used)
    gsub(/[^0-9.]/, "", memory_total)
    memory_percent = memory_total > 0 ? memory_used * 100 / memory_total : 0

    match($0, /\[[^]]*\]/)
    cpu_graph = substr($0, RSTART, RLENGTH)
    cpu = $(NF - 3)
    gsub(/%/, "", cpu)

    printf "%s MEM %s · %s CPU %s %.0f%% · LOAD %s %s %s\n", \
      indicator(memory_percent, 70, 85), memory, \
      indicator(cpu, 50, 80), cpu_graph, cpu, \
      $(NF - 2), $(NF - 1), $NF
  }
'
