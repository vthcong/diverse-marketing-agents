#!/bin/bash
# Claude Code pipes a JSON blob about the session to stdin; whatever this script prints becomes the status line.
input=$(cat)

model=$(echo "$input" | jq -r '.model.display_name // "?"')
effort=$(echo "$input" | jq -r '.effort.level // empty')
dir=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // "."')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')

branch=$(git -C "$dir" branch --show-current 2>/dev/null)

line="$model"
[ -n "$effort" ] && line="$line ($effort)"
[ -n "$branch" ] && line="$line | $branch"
[ -n "$used" ] && line="$line | ctx $(printf '%.0f' "$used")%"
[ -n "$cost" ] && line="$line | \$$(printf '%.2f' "$cost")"
echo "$line"
