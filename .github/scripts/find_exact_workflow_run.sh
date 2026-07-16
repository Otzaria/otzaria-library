#!/usr/bin/env bash
set -euo pipefail

repo="${1:?repository is required}"
workflow="${2:?workflow is required}"
title="${3:?exact display title is required}"
head_sha="${4:?head SHA is required}"
dispatched_at="${5:?dispatch timestamp is required}"

for _ in {1..60}; do
  mapfile -t matches < <(
    gh run list -R "$repo" -w "$workflow" --event workflow_dispatch --limit 100 \
      --json databaseId,displayTitle,headSha,createdAt,event \
      --jq ".[] | select(.displayTitle == \"$title\" and .headSha == \"$head_sha\" and .createdAt >= \"$dispatched_at\") | .databaseId"
  )
  if [[ ${#matches[@]} -eq 1 ]]; then
    printf '%s\n' "${matches[0]}"
    exit 0
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    echo "Multiple workflow runs match the exact dispatch identity" >&2
    exit 1
  fi
  sleep 10
done

echo "No workflow run matched the exact dispatch identity" >&2
exit 1
