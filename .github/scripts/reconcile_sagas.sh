#!/usr/bin/env bash
# Recover callbacks lost between repositories. Every decision is derived from a
# strict saga-state release plus exact child titles; payloads are lookup keys only.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=${SAGA_REPO:-Otzaria/otzaria-library}
SINCE=${SAGA_SINCE:-$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ)}
RETIRED_SAGAS_FILE=${SAGA_RETIRED_FILE:-"$HERE/retired_sagas.txt"}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FAILURES=0
# One failed delivery is retried once for transient infrastructure faults.  Any
# second failure is an operator-action state, not a reason to wake the account
# every fifteen minutes with another identical failure.
MAX_RERUN_ATTEMPTS=${SAGA_MAX_RERUN_ATTEMPTS:-2}
# Saga roots created before this instant used Actions artifacts for their state.
# They cannot satisfy the Release contract and must not poison every scheduled
# reconciliation tick after the migration. New roots remain fail-closed.
STATE_RELEASE_ROLLOUT_AT=${SAGA_STATE_RELEASE_ROLLOUT_AT:-2026-08-13T23:25:42Z}
# The reconciler was introduced together with the durable saga-state handoff.
# Successful workflow runs from before that rollout used the old synchronous
# protocol and legitimately have no saga-state handoff.  A rewritten Git
# history can also make an otherwise valid historical root `diverged` from
# this marker.  In either case, never auto-recover it: that would create a
# duplicate saga from a foreign control-plane history.  Post-rollout roots on
# the current lineage still require their state release below.
STATE_CONTRACT_COMMIT=${SAGA_STATE_CONTRACT_COMMIT:-d887f442b3c358da28e62506fae9df3f7c931700}
CONTROL_HEAD=$(git rev-parse HEAD)
[[ "$CONTROL_HEAD" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::cannot resolve reconciler control head"; exit 2; }
[[ "$STATE_CONTRACT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::SAGA_STATE_CONTRACT_COMMIT must be a full commit SHA"; exit 2; }
[[ "$MAX_RERUN_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || {
  echo "::error::SAGA_MAX_RERUN_ATTEMPTS must be a positive integer"; exit 2; }
[[ "$STATE_RELEASE_ROLLOUT_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
  echo "::error::SAGA_STATE_RELEASE_ROLLOUT_AT must be an RFC3339 UTC instant"; exit 2; }
if [ -f "$RETIRED_SAGAS_FILE" ]; then
  awk '
    /^[[:space:]]*(#|$)/ { next }
    !/^[1-9][0-9]*$/ {
      printf "::error::invalid retired saga id at %s:%d\n", FILENAME, NR > "/dev/stderr"
      bad=1
    }
    END { exit bad ? 1 : 0 }
  ' "$RETIRED_SAGAS_FILE" || exit 2
fi

if ! RUNS=$(gh api --paginate -X GET "repos/$REPO/actions/workflows/sync-manual-links.yml/runs" \
  -f event=workflow_dispatch -f created=">=$SINCE" -f per_page=100 \
  --jq ".workflow_runs[] | select(.status==\"completed\" and .conclusion==\"success\" and .created_at >= \"$STATE_RELEASE_ROLLOUT_AT\") | (.id|tostring)"); then
  echo "::error::cannot list saga roots"
  exit 1
fi
RUNS=$(printf '%s\n' "$RUNS" | awk 'NF && !seen[$0]++')

find_child() {
  local repo="$1" workflow="$2" title="$3" head="$4"
  FIND_RUN_ATTEMPTS=1 bash "$HERE/find_exact_workflow_run.sh" "$repo" "$workflow" "$title" "$head"
}

# A Seforim run has two identities: the immutable source_commit in its signed
# result and the workflow control head in GitHub run metadata.  A hotfix may
# advance the latter while an expensive build is active.  Accept only control
# heads that descend from the signed payload pin; prefer an already successful
# delivery, otherwise require exactly one active delivery.  If all deliveries
# are terminal failures, return the newest exact child so the bounded retry
# policy below can act on it instead of treating it as missing forever.
find_seforim_child() {
  local title="$1" payload="$2" rows allowed relation id status conclusion head successes active failed count
  if ! rows=$(TITLE="$title" gh api --paginate -X GET \
      "repos/Otzaria/SeforimLibrary/actions/workflows/manual-generate-release.yml/runs" \
      -f event=workflow_dispatch -f per_page=100 \
      --jq '.workflow_runs[] | select(.display_title==env.TITLE) | [(.id|tostring),.status,(.conclusion//"-"),.head_sha] | @tsv'); then
    echo "::error::cannot list exact Seforim children" >&2
    return 2
  fi
  rows=$(printf '%s\n' "$rows" | awk -F'\t' 'NF && !seen[$1]++')
  allowed=""
  while IFS=$'\t' read -r id status conclusion head; do
    [ -n "$id" ] || continue
    relation=$(gh api "repos/Otzaria/SeforimLibrary/compare/$payload...$head" --jq .status) || return 2
    case "$relation" in
      identical|ahead) allowed+="$id"$'\t'"$status"$'\t'"$conclusion"$'\t'"$head"$'\n' ;;
    esac
  done <<< "$rows"
  successes=$(printf '%s' "$allowed" | awk -F'\t' '$2=="completed" && $3=="success" {print $1}')
  if [ -n "$successes" ]; then
    printf '%s\n' "$successes" | sort -n | tail -1
    return 0
  fi
  active=$(printf '%s' "$allowed" | awk -F'\t' '$2 ~ /^(requested|waiting|pending|queued|in_progress)$/ {print $1}')
  count=$(printf '%s\n' "$active" | awk 'NF' | wc -l | tr -d ' ')
  if [ "$count" -eq 1 ]; then
    printf '%s\n' "$active"
    return 0
  fi
  if [ "$count" -gt 1 ]; then
    echo "::error::multiple active Seforim children descend from the pinned payload; refusing to guess" >&2
    return 3
  fi
  failed=$(printf '%s' "$allowed" | awk -F'\t' '$2=="completed" && $3!="success" {print $1}')
  if [ -n "$failed" ]; then
    # At-least-once callbacks may have produced several failed attempts of the
    # same signed child.  The newest databaseId is the sole retry candidate;
    # never manufacture a second child run.
    printf '%s\n' "$failed" | sort -n | tail -1
    return 0
  fi
  return 1
}

dispatch_continuation() {
  local stage="$1" corr="$2" saga="$3" saga_attempt="$4" child="$5"
  gh workflow run saga-continue.yml -R "$REPO" \
    -f stage="$stage" -f correlation_id="$corr" -f saga_run_id="$saga" \
    -f saga_run_attempt="$saga_attempt" -f child_run_id="$child"
}

# Return a stage to service without creating an unbounded queue of identical
# recovery callbacks every 15 minutes.  Re-run one failed databaseId; keep one
# active run; dispatch only when the fully-paginated exact-title query proves none.
ensure_continuation() {
  local stage="$1" corr="$2" saga="$3" saga_attempt="$4" child="$5" title rows count rid run_attempt
  title="saga-continue stage=$stage correlation=$corr"
  if ! rows=$(TITLE="$title" HEAD_SHA="$CONTROL_HEAD" gh api --paginate -X GET \
      "repos/$REPO/actions/workflows/saga-continue.yml/runs" -f per_page=100 \
      --jq '.workflow_runs[] | select(.display_title==env.TITLE and .head_sha==env.HEAD_SHA) | [(.id|tostring),.status,(.conclusion//""),(.run_attempt|tostring)] | @tsv'); then
    echo "::error::cannot list exact $stage continuation runs"
    return 1
  fi
  rows=$(printf '%s\n' "$rows" | awk -F'\t' 'NF && !seen[$1]++')
  count=$(printf '%s\n' "$rows" | awk 'NF' | wc -l | tr -d ' ')
  if [ "$count" -eq 0 ]; then
    dispatch_continuation "$stage" "$corr" "$saga" "$saga_attempt" "$child"
    return
  fi
  if printf '%s\n' "$rows" | awk -F'\t' '$2 ~ /^(requested|waiting|pending|queued|in_progress)$/ {found=1} END{exit !found}'; then
    echo "an exact $stage continuation is already active"
    return 0
  fi
  if printf '%s\n' "$rows" | awk -F'\t' '$2=="completed" && $3=="success" {found=1} END{exit !found}'; then
    # Re-running a successful callback with the same immutable inputs cannot
    # create the missing product. Pause this exact saga instead of producing a
    # scheduled failure forever; a deliberately dispatched recovery will be
    # discovered normally on the next tick.
    echo "::warning::exact continuation succeeded but its downstream stage product is missing; saga is paused for operator recovery"
    return 0
  fi
  if printf '%s\n' "$rows" | awk -F'\t' '$2!="completed" {bad=1} END{exit bad}'; then :; else
    echo "::error::an exact continuation has an unknown status"
    return 1
  fi
  # At-least-once callbacks can legitimately leave more than one failed delivery.
  # They represent the same canonical stage under the same mutex; rerun the newest
  # databaseId deterministically instead of adding yet another run.
  rid=$(printf '%s\n' "$rows" | cut -f1 | sort -n | tail -1)
  run_attempt=$(printf '%s\n' "$rows" | awk -F'\t' -v rid="$rid" '$1==rid {print $4}')
  [[ "$run_attempt" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::invalid run_attempt for continuation $rid"; return 1; }
  if [ "$run_attempt" -ge "$MAX_RERUN_ATTEMPTS" ]; then
    echo "::warning::continuation $rid exhausted the bounded $MAX_RERUN_ATTEMPTS-attempt recovery budget; awaiting operator recovery"
    return 0
  fi
  gh run rerun "$rid" -R "$REPO"
  echo "reran failed continuation $rid for $stage"
}

rerun_failed_child() {
  local repo="$1" rid="$2" label="$3" attempt
  attempt=$(gh api "repos/$repo/actions/runs/$rid" --jq .run_attempt) || return 1
  [[ "$attempt" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::$label $rid returned an invalid run_attempt"; return 1; }
  if [ "$attempt" -ge "$MAX_RERUN_ATTEMPTS" ]; then
    # The exact failed child and its log remain available. Returning success
    # prevents this scheduled reconciler from emitting the same notification
    # forever; any further recovery must be intentional.
    echo "::warning::$label $rid exhausted the bounded $MAX_RERUN_ATTEMPTS-attempt recovery budget; awaiting operator recovery"
    return 0
  fi
  gh run rerun "$rid" -R "$repo"
  echo "reran failed $label $rid (next attempt $((attempt+1)))"
}

for saga_run in $RUNS; do
  if [ -f "$RETIRED_SAGAS_FILE" ] &&
      grep -Fxq "$saga_run" "$RETIRED_SAGAS_FILE"; then
    echo "retired saga=$saga_run skipped by explicit operator tombstone"
    continue
  fi
  if ! saga_meta=$(gh api "repos/$REPO/actions/runs/$saga_run" \
      --jq 'select(.status=="completed" and .conclusion=="success" and (.run_attempt|type)=="number" and .run_attempt>=1 and (.head_sha|type)=="string") | [.head_sha,.run_attempt,.display_title] | @tsv'); then
    echo "::warning::cannot resolve current attempt for saga $saga_run"; FAILURES=$((FAILURES+1)); continue
  fi
  IFS=$'\t' read -r saga_head saga_attempt saga_title <<< "$saga_meta"
  [[ "$saga_head" =~ ^[0-9a-f]{40}$ ]] || {
    echo "::error::invalid head SHA for saga $saga_run"; FAILURES=$((FAILURES+1)); continue; }
  [[ "$saga_attempt" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::invalid current attempt for saga $saga_run"; FAILURES=$((FAILURES+1)); continue; }
  if ! contract_relation=$(gh api "repos/$REPO/compare/$STATE_CONTRACT_COMMIT...$saga_head" --jq .status); then
    echo "::error::cannot establish saga-state contract ancestry for saga $saga_run"
    FAILURES=$((FAILURES+1)); continue
  fi
  case "$contract_relation" in
    identical|ahead) ;;
    behind|diverged)
      echo "legacy saga=$saga_run is outside the durable saga-state lineage ($contract_relation); skipped"
      continue ;;
    *)
      echo "::error::saga $saga_run head is not on the durable saga-state lineage ($contract_relation)"
      FAILURES=$((FAILURES+1)); continue ;;
  esac
  corr=${saga_title#sync-manual-links correlation=}
  [ "$corr" != "$saga_title" ] || { echo "::error::saga $saga_run title has no correlation"; FAILURES=$((FAILURES+1)); continue; }
  correlation_sha=$(printf '%s' "$corr" | sha256sum | cut -d' ' -f1)
  release_tag="saga-state-$correlation_sha-attempt-$saga_attempt"
  state_dir="$TMP/$saga_run"
  mkdir "$state_dir"
  gh release download "$release_tag" -R "$REPO" -p saga-state.json -p saga-state.sha256 -D "$state_dir" || {
    FAILURES=$((FAILURES+1)); continue; }
  if ! python3 "$HERE/saga_contract.py" --directory "$state_dir" \
      --expected-run-id "$saga_run" --expected-run-attempt "$saga_attempt" \
      --expected-correlation "$corr"; then
    FAILURES=$((FAILURES+1)); continue
  fi
  expected_release="saga-state-$(jq -r .correlation_sha256 "$state_dir/saga-state.json")-attempt-$saga_attempt"
  if [ "$release_tag" != "$expected_release" ]; then
    echo "::error::saga $saga_run state release tag disagrees with its canonical identity"
    FAILURES=$((FAILURES+1)); continue
  fi
  expected=$(jq -r .expected_links_commit "$state_dir/saga-state.json")
  tool=$(jq -r .seforim_tool_commit "$state_dir/saga-state.json")

  # A successful S2 continuation is the durable completion marker.
  completion_title="saga-continue stage=seforim-published correlation=$corr"
  if ! completed=$(TITLE="$completion_title" gh api --paginate -X GET \
      "repos/$REPO/actions/workflows/saga-continue.yml/runs" -f per_page=100 \
      --jq '.workflow_runs[] | select(.display_title==env.TITLE and .status=="completed" and .conclusion=="success") | .id'); then
    FAILURES=$((FAILURES+1)); continue
  fi
  [ -z "$completed" ] || { echo "complete saga=$saga_run correlation=$corr"; continue; }

  ot_title="update-library mode=links_sync_mode correlation=$corr"
  set +e
  ot_run=$(find_child "$REPO" update-library.yml "$ot_title" '*')
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 1 ]; then
      gh workflow run update-library.yml -R "$REPO" -f mode=links_sync_mode \
        -f expected_links_commit="$expected" -f correlation_id="$corr" \
        -f saga_run_id="$saga_run" -f saga_run_attempt="$saga_attempt" || FAILURES=$((FAILURES+1))
      echo "redispatched missing Otzaria child for saga $saga_run"
      continue
    fi
    FAILURES=$((FAILURES+1)); continue
  fi
  ot_state=$(gh api "repos/$REPO/actions/runs/$ot_run" --jq '.status+":"+(.conclusion//"")') || {
    FAILURES=$((FAILURES+1)); continue; }
  case "$ot_state" in
    requested:*|waiting:*|pending:*|queued:*|in_progress:*) continue ;;
    completed:success) ;;
    *) rerun_failed_child "$REPO" "$ot_run" "Otzaria child" || FAILURES=$((FAILURES+1)); continue ;;
  esac

  sef_title="manual-generate-release correlation=$corr"
  set +e
  sef_run=$(find_seforim_child "$sef_title" "$tool")
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 1 ]; then
      ensure_continuation otzaria-published "$corr" "$saga_run" "$saga_attempt" "$ot_run" || FAILURES=$((FAILURES+1))
      echo "recovered S1 callback for saga $saga_run"
      continue
    fi
    FAILURES=$((FAILURES+1)); continue
  fi
  sef_state=$(gh api "repos/Otzaria/SeforimLibrary/actions/runs/$sef_run" --jq '.status+":"+(.conclusion//"")') || {
    FAILURES=$((FAILURES+1)); continue; }
  case "$sef_state" in
    requested:*|waiting:*|pending:*|queued:*|in_progress:*) ;;
    completed:success)
      ensure_continuation seforim-published "$corr" "$saga_run" "$saga_attempt" "$sef_run" || FAILURES=$((FAILURES+1))
      echo "recovered S2 callback for saga $saga_run" ;;
    *) rerun_failed_child Otzaria/SeforimLibrary "$sef_run" "Seforim child" || FAILURES=$((FAILURES+1)) ;;
  esac
done

[ "$FAILURES" -eq 0 ] || { echo "::error::$FAILURES saga reconciliation failure(s)"; exit 1; }
echo "saga reconciliation complete"
