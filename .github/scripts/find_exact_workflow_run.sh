#!/usr/bin/env bash
set -euo pipefail

repo="${1:?repository is required}"
workflow="${2:?workflow is required}"
title="${3:?exact display title is required}"
head_sha="${4:?head SHA is required}"
attempts="${FIND_RUN_ATTEMPTS:-60}"
run_event="${FIND_RUN_EVENT:-workflow_dispatch}"
[[ "$attempts" =~ ^[1-9][0-9]*$ ]] || { echo "FIND_RUN_ATTEMPTS must be a positive integer" >&2; exit 2; }

for attempt in $(seq 1 "$attempts"); do
  # Request identity is the exact, correlation-bearing title plus the expected
  # workflow head. Full pagination avoids last-N loss; no local-clock lower bound
  # can hide a child when the runner clock is skewed.
  api_args=(-f per_page=100)
  [ "$run_event" = "*" ] || api_args+=(-f "event=$run_event")
  if ! rows="$(TITLE="$title" HEAD_SHA="$head_sha" gh api --paginate -X GET \
    "repos/$repo/actions/workflows/$workflow/runs" "${api_args[@]}" \
    --jq '.workflow_runs[] | select(.display_title == env.TITLE and (env.HEAD_SHA == "*" or .head_sha == env.HEAD_SHA)) | (.id|tostring)')"; then
    echo "workflow-run listing failed; refusing to interpret it as zero matches" >&2
    exit 2
  fi
  matches="$(printf '%s\n' "$rows" | awk 'NF && !seen[$0]++')"
  count="$(printf '%s\n' "$matches" | awk 'NF' | wc -l | tr -d ' ')"
  if [ "$count" -eq 1 ]; then
    printf '%s\n' "$matches"
    exit 0
  fi
  if [ "$count" -gt 1 ]; then
    echo "Multiple workflow runs match the exact dispatch identity" >&2
    exit 3
  fi
  [ "$attempt" -eq "$attempts" ] || sleep 10
done

echo "No workflow run matched the exact dispatch identity" >&2
exit 1
