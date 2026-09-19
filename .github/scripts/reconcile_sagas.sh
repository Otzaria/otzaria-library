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
# Set for every root below; helpers name the saga they are acting on.
SAGA_REF=
# `run_started_at` of the root's current attempt, set beside SAGA_REF below.
# A re-run of the root resets it, which is exactly the boundary the continuation
# lookup needs: see ensure_continuation.
SAGA_ATTEMPT_STARTED_AT=
# The newest export cycle this tick has proven complete, and the root that proved
# it.  Each cycle rebuilds and republishes the whole library, so an unfinished
# cycle older than a finished one has no product it could still deliver, and
# reconciling it can only re-alert: that is what turned one abandoned 2026-08-30
# cycle into 55 consecutive red ticks across eight days until an operator
# hand-wrote a tombstone for it.
#
# A cycle's age is the Sefaria export run its correlation names, never the root
# run id.  Re-dispatching a root is routine here, so an operator re-running an
# older cycle after a newer one finished would give the older cycle the higher
# root id -- and silence the newer cycle that is genuinely stuck.  Comparing the
# export run instead makes that inversion impossible; a cycle whose age cannot be
# read is never treated as superseded.
SUPERSEDING_CYCLE=
SUPERSEDING_SAGA=
# How many older cycles this tick skipped, reported once at the end.
SUPERSEDED=0
# One failed delivery is retried once for transient infrastructure faults.  Any
# second failure is an operator-action state that no further rerun can clear,
# so it is reported as a failure and stays visible until an operator acts.  The
# budget counts deliveries, never wall time: GitHub runs this schedule about
# eight times a day (median gap ~3 h), not the 96 times the cron asks for.
MAX_RERUN_ATTEMPTS=${SAGA_MAX_RERUN_ATTEMPTS:-2}
# An operator-action state is announced, then left alone.  Every tick used to fail
# for as long as such a state lasted -- about eight red runs a day, each one a
# notification, for a condition the first had already reported and that no tick
# can change.  Now the tick fails only while the stuck run concluded less than
# ALERT_WINDOW_HOURS ago; after that the saga stays named in a warning annotation and in
# the tail count, without failing.  An operator rerun that fails again moves the
# run's conclusion and re-opens the window.  The window must outlast the widest
# gap between delivered ticks (median ~3 h), or a state could go quiet before any
# tick had failed for it.  A conclusion time that cannot be read alerts.
ALERT_WINDOW_HOURS=${SAGA_ALERT_WINDOW_HOURS:-12}
# A single incomplete listing must never be read as "the child does not exist":
# that false negative is what dispatched a duplicate Otzaria child on
# 2026-09-02, and no tick can reduce two children back to one.  Absence is only
# believed after this many re-reads (10 s apart) of the run list.  At ~8 ticks a
# day the next tick is hours away, so a minute of retries here is cheap.
FIND_CHILD_ATTEMPTS=${SAGA_FIND_CHILD_ATTEMPTS:-6}
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
[[ "$STATE_CONTRACT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo "::error::SAGA_STATE_CONTRACT_COMMIT must be a full commit SHA"; exit 2; }
[[ "$MAX_RERUN_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || {
  echo "::error::SAGA_MAX_RERUN_ATTEMPTS must be a positive integer"; exit 2; }
[[ "$ALERT_WINDOW_HOURS" =~ ^[1-9][0-9]*$ ]] || {
  echo "::error::SAGA_ALERT_WINDOW_HOURS must be a positive integer"; exit 2; }
ALERT_CUTOFF=${SAGA_ALERT_CUTOFF:-$(date -u -d "$ALERT_WINDOW_HOURS hours ago" +%Y-%m-%dT%H:%M:%SZ)}
[[ "$ALERT_CUTOFF" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
  echo "::error::SAGA_ALERT_CUTOFF must be an RFC3339 UTC instant"; exit 2; }
# Operator-action states past their alert window, reported once at the end.
QUIETED=0
[[ "$FIND_CHILD_ATTEMPTS" =~ ^[1-9][0-9]*$ ]] || {
  echo "::error::SAGA_FIND_CHILD_ATTEMPTS must be a positive integer"; exit 2; }
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
# Newest first, explicitly.  Run ids are assigned in creation order, and the
# supersession rule must reach a finished cycle before the older cycles it
# overtook; that order is never inherited from the listing endpoint.
RUNS=$(printf '%s\n' "$RUNS" | awk 'NF && !seen[$0]++' | sort -rn)

# Every failure and warning must name the saga it belongs to: this watchdog is
# read as a list of annotations, not by reconstructing loop order from the log.
saga_ref() {
  printf 'saga=%s (https://github.com/%s/actions/runs/%s)' "$1" "$REPO" "$1"
}

find_child() {
  local repo="$1" workflow="$2" title="$3" head="$4"
  FIND_RUN_ATTEMPTS="$FIND_CHILD_ATTEMPTS" \
    bash "$HERE/find_exact_workflow_run.sh" "$repo" "$workflow" "$title" "$head"
}

# Two runs can already share one exact dispatch identity, and nothing here can
# merge them back into one.  Failing every tick forever only hides the sagas that
# do need an operator, so apply the same precedence find_seforim_child applies
# below: the earliest terminal success, which is the one rule saga-continue S2
# also applies through select_earliest_successful_child.sh, so the two halves of
# this decision can never name different winners; otherwise the single active
# delivery, adopted without rerunning anything; otherwise, while several are
# still active, refuse to guess and leave it to an operator; otherwise the newest
# terminal failure, so the bounded rerun acts on the current control head instead
# of replaying a stale run beside a live one.  The listing is narrowed by the
# same dispatch event the lookup script uses, or the two could disagree about how
# many children exist.  Never delete or cancel the losers; just say once which
# run this saga is reconciled against.
resolve_duplicate_child() {
  local repo="$1" workflow="$2" title="$3" rows canonical active failed count duplicates rc=0
  if ! rows=$(TITLE="$title" gh api --paginate -X GET \
      "repos/$repo/actions/workflows/$workflow/runs" -f event=workflow_dispatch -f per_page=100 \
      --jq '.workflow_runs[] | select(.display_title==env.TITLE) | [(.id|tostring),.created_at,.status,(.conclusion//"-")] | @tsv'); then
    echo "::error::$SAGA_REF: cannot list the duplicate exact children" >&2
    return 1
  fi
  rows=$(printf '%s\n' "$rows" | awk -F'\t' 'NF && !seen[$1]++' | sort -t$'\t' -k2,2 -k1,1n)
  duplicates=$(printf '%s\n' "$rows" | cut -f1 | paste -sd, -)
  canonical=$(printf '%s\n' "$rows" | bash "$HERE/select_earliest_successful_child.sh") || rc=$?
  case "$rc" in
    0) ;;
    1) canonical="" ;;
    *) echo "::error::$SAGA_REF: cannot apply the canonical child rule to its duplicates" >&2
       return 1 ;;
  esac
  if [ -z "$canonical" ]; then
    active=$(printf '%s\n' "$rows" | awk -F'\t' '$3 ~ /^(requested|waiting|pending|queued|in_progress)$/ {print $1}')
    count=$(printf '%s\n' "$active" | awk 'NF' | wc -l | tr -d ' ')
    if [ "$count" -gt 1 ]; then
      # Adopting one live delivery while another is still writing, or rerunning
      # either of them, can only manufacture a third child of the same identity.
      echo "::error::$SAGA_REF: duplicate exact children $duplicates are still active; refusing to guess" >&2
      return 1
    fi
    if [ "$count" -eq 1 ]; then
      canonical="$active"
    else
      failed=$(printf '%s\n' "$rows" | awk -F'\t' '$3=="completed" && $4!="success" {print $1}')
      canonical=$(printf '%s\n' "$failed" | awk 'NF' | sort -n | tail -1)
    fi
  fi
  [[ "$canonical" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::$SAGA_REF: cannot choose a canonical child among its duplicates" >&2
    return 1; }
  echo "::warning::$SAGA_REF: duplicate exact children $duplicates; reconciled against canonical child $canonical" >&2
  printf '%s\n' "$canonical"
}

# The Otzaria child is the only run this reconciler creates, so it is the only
# place that can manufacture a duplicate.  Dispatch only when the bounded retry
# above and a second listing that is not narrowed by the dispatch event both
# prove the child absent.  Prints the canonical child id, or nothing when a
# child has just been dispatched and has nothing to reconcile yet.
ensure_otzaria_child() {
  local title="$1" expected="$2" corr="$3" saga="$4" saga_attempt="$5" run rc
  set +e
  run=$(find_child "$REPO" update-library.yml "$title" '*')
  rc=$?
  set -e
  case "$rc" in
    0) printf '%s\n' "$run"; return 0 ;;
    3) resolve_duplicate_child "$REPO" update-library.yml "$title"; return ;;
    1) ;;
    *) echo "::error::$SAGA_REF: cannot list its exact Otzaria child" >&2; return 1 ;;
  esac
  set +e
  run=$(FIND_RUN_EVENT='*' FIND_RUN_ATTEMPTS=1 \
    bash "$HERE/find_exact_workflow_run.sh" "$REPO" update-library.yml "$title" '*')
  rc=$?
  set -e
  case "$rc" in
    0) printf '%s\n' "$run"; return 0 ;;
    3) resolve_duplicate_child "$REPO" update-library.yml "$title"; return ;;
    1) ;;
    *) echo "::error::$SAGA_REF: cannot confirm its Otzaria child is missing" >&2; return 1 ;;
  esac
  gh workflow run update-library.yml -R "$REPO" -f mode=links_sync_mode \
    -f expected_links_commit="$expected" -f correlation_id="$corr" \
    -f saga_run_id="$saga" -f saga_run_attempt="$saga_attempt" >&2 || {
    echo "::error::$SAGA_REF: cannot redispatch its missing Otzaria child" >&2; return 1; }
  echo "redispatched missing Otzaria child for $SAGA_REF" >&2
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
    echo "::error::$SAGA_REF: cannot list exact Seforim children" >&2
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
    echo "::error::$SAGA_REF: multiple active Seforim children descend from the pinned payload; refusing to guess" >&2
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
# recovery callbacks, one per delivered tick.  Re-run one failed databaseId; keep
# one active run; dispatch only when the fully-paginated exact-title query proves none.
#
# Identity is the exact title plus the root attempt the continuation belongs to.
#
# The title alone already carries the stage and the immutable correlation id, and
# the completion marker in the scan loop has always matched on it alone.  What it
# does not carry is the root's run_attempt, which saga-continue itself asserts
# against the root run.  That matters only here, because `gh run rerun` replays a
# run's ORIGINAL inputs: re-running a continuation left over from attempt N while
# the root now sits at attempt N+1 replays saga_run_attempt=N, fails that
# assertion again, and burns the bounded budget into a permanent red tick.  Five
# roots in this repository have run at attempt>1, the newest at attempt 6.
#
# So the rows are cut at the root's current `run_started_at`, which a re-run
# resets: a continuation older than that belongs to a superseded attempt and must
# be replaced by a fresh dispatch carrying the current one, never re-run.
#
# This replaces a narrowing by the reconciler's own checkout SHA, which cut on an
# axis with no relation to the saga: it hid every continuation delivered before
# the last push to main -- this repository moves HEAD several times a day -- so a
# stage that had already succeeded read as absent and was dispatched a second
# time.  2026-08-14T06:03Z re-delivered an S1 callback that had arrived normally
# at 01:31Z the same morning, inside the same root attempt.
ensure_continuation() {
  local stage="$1" corr="$2" saga="$3" saga_attempt="$4" child="$5" title rows count rid run_attempt concluded
  title="saga-continue stage=$stage correlation=$corr"
  if ! rows=$(TITLE="$title" SINCE="$SAGA_ATTEMPT_STARTED_AT" gh api --paginate -X GET \
      "repos/$REPO/actions/workflows/saga-continue.yml/runs" -f per_page=100 \
      --jq '.workflow_runs[] | select(.display_title==env.TITLE and .created_at>=env.SINCE) | [(.id|tostring),.status,(.conclusion//""),(.run_attempt|tostring),(.updated_at//"")] | @tsv'); then
    echo "::error::$SAGA_REF: cannot list exact $stage continuation runs"
    return 1
  fi
  rows=$(printf '%s\n' "$rows" | awk -F'\t' 'NF && !seen[$1]++')
  count=$(printf '%s\n' "$rows" | awk 'NF' | wc -l | tr -d ' ')
  if [ "$count" -eq 0 ]; then
    dispatch_continuation "$stage" "$corr" "$saga" "$saga_attempt" "$child" || {
      echo "::error::$SAGA_REF: cannot dispatch its $stage continuation"; return 1; }
    return 0
  fi
  if printf '%s\n' "$rows" | awk -F'\t' '$2 ~ /^(requested|waiting|pending|queued|in_progress)$/ {found=1} END{exit !found}'; then
    echo "an exact $stage continuation is already active"
    return 2
  fi
  if printf '%s\n' "$rows" | awk -F'\t' '$2=="completed" && $3=="success" {found=1} END{exit !found}'; then
    # Re-running a successful callback with the same immutable inputs cannot
    # create the missing product. Pause this exact saga instead of producing a
    # scheduled failure forever; a deliberately dispatched recovery will be
    # discovered normally on the next tick.
    echo "::warning::$SAGA_REF: exact continuation succeeded but its downstream stage product is missing; saga is paused for operator recovery"
    return 2
  fi
  if printf '%s\n' "$rows" | awk -F'\t' '$2!="completed" {bad=1} END{exit bad}'; then :; else
    echo "::error::$SAGA_REF: an exact continuation has an unknown status"
    return 1
  fi
  # At-least-once callbacks can legitimately leave more than one failed delivery.
  # They represent the same canonical stage under the same mutex; rerun the newest
  # databaseId deterministically instead of adding yet another run.
  rid=$(printf '%s\n' "$rows" | cut -f1 | sort -n | tail -1)
  run_attempt=$(printf '%s\n' "$rows" | awk -F'\t' -v rid="$rid" '$1==rid {print $4}')
  [[ "$run_attempt" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::$SAGA_REF: invalid run_attempt for continuation $rid"; return 1; }
  if [ "$run_attempt" -ge "$MAX_RERUN_ATTEMPTS" ]; then
    concluded=$(printf '%s\n' "$rows" | awk -F'\t' -v rid="$rid" '$1==rid {print $5}')
    if past_alert_window "$concluded"; then
      # 2: reported, nothing delivered -- the caller neither counts nor logs it.
      echo "::warning::$SAGA_REF: continuation $rid exhausted the bounded $MAX_RERUN_ATTEMPTS-attempt recovery budget at $concluded; still awaiting operator recovery (alert window of ${ALERT_WINDOW_HOURS}h passed)"
      QUIETED=$((QUIETED+1))
      return 2
    fi
    echo "::error::$SAGA_REF: continuation $rid exhausted the bounded $MAX_RERUN_ATTEMPTS-attempt recovery budget; awaiting operator recovery"
    return 1
  fi
  gh run rerun "$rid" -R "$REPO"
  echo "reran failed continuation $rid for $stage"
}

# True when a stuck run concluded before the alert window: the state has been
# announced and is now only reported.  Lexical order is time order for the fixed
# RFC3339 UTC shape, and anything that is not that shape is treated as fresh.
past_alert_window() {
  [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] &&
    [[ "$1" < "$ALERT_CUTOFF" ]]
}

rerun_failed_child() {
  local repo="$1" rid="$2" label="$3" meta attempt concluded
  meta=$(gh api "repos/$repo/actions/runs/$rid" --jq '[(.run_attempt|tostring),(.updated_at//"")] | @tsv') || {
    echo "::error::$SAGA_REF: cannot read the run attempt of $label $rid"; return 1; }
  IFS=$'\t' read -r attempt concluded <<< "$meta"
  [[ "$attempt" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::$SAGA_REF: $label $rid returned an invalid run_attempt"; return 1; }
  if [ "$attempt" -ge "$MAX_RERUN_ATTEMPTS" ]; then
    # No further rerun can clear this: the child needs an operator.  Report it
    # as a failure naming the saga, its root run and the stuck child.  A
    # watchdog that stays green over a saga nobody is recovering is useless --
    # but one that is red all week over a state it already announced gets muted,
    # which is worse.  So: red inside the alert window, named ever after.
    if past_alert_window "$concluded"; then
      echo "::warning::$SAGA_REF: $label $rid exhausted the bounded $MAX_RERUN_ATTEMPTS-attempt recovery budget at $concluded; still awaiting operator recovery (alert window of ${ALERT_WINDOW_HOURS}h passed)"
      QUIETED=$((QUIETED+1))
      return 0
    fi
    echo "::error::$SAGA_REF: $label $rid exhausted the bounded $MAX_RERUN_ATTEMPTS-attempt recovery budget; awaiting operator recovery"
    return 1
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
  SAGA_REF=$(saga_ref "$saga_run")
  if ! saga_meta=$(gh api "repos/$REPO/actions/runs/$saga_run" \
      --jq 'select(.status=="completed" and .conclusion=="success" and (.run_attempt|type)=="number" and .run_attempt>=1 and (.head_sha|type)=="string" and (.run_started_at|type)=="string") | [.head_sha,.run_attempt,.run_started_at,.display_title] | @tsv'); then
    echo "::warning::$SAGA_REF: cannot resolve its current attempt"; FAILURES=$((FAILURES+1)); continue
  fi
  IFS=$'\t' read -r saga_head saga_attempt SAGA_ATTEMPT_STARTED_AT saga_title <<< "$saga_meta"
  # A migrate run re-issues lineage under operator control: it publishes no saga state
  # and dispatches no publisher, so it is not a saga root and has nothing to reconcile.
  case "$saga_title" in
    "sync-manual-links migrate correlation="*)
      echo "migrate run=$saga_run is not a saga root; skipped"; continue ;;
  esac
  [[ "$saga_head" =~ ^[0-9a-f]{40}$ ]] || {
    echo "::error::$SAGA_REF: invalid head SHA"; FAILURES=$((FAILURES+1)); continue; }
  [[ "$saga_attempt" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::$SAGA_REF: invalid current attempt"; FAILURES=$((FAILURES+1)); continue; }
  # An unparsable instant would silently widen the continuation lookup back to
  # every attempt this saga ever had, so it is fail-closed like the rest.
  [[ "$SAGA_ATTEMPT_STARTED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
    echo "::error::$SAGA_REF: invalid start instant for its current attempt"; FAILURES=$((FAILURES+1)); continue; }

  corr=${saga_title#sync-manual-links correlation=}
  [ "$corr" != "$saga_title" ] || { echo "::error::$SAGA_REF: title has no correlation"; FAILURES=$((FAILURES+1)); continue; }
  saga_cycle=${corr#sefaria:}
  saga_cycle=${saga_cycle%%:*}
  [[ "$saga_cycle" =~ ^[1-9][0-9]*$ ]] || {
    echo "::error::$SAGA_REF: its correlation names no export cycle"; FAILURES=$((FAILURES+1)); continue; }

  # A successful S2 continuation is the durable completion marker.  It is read
  # before the lineage compare and the saga-state download below because a
  # finished saga has nothing left to reconcile, and re-proving its state costs a
  # compare call, a release download and a contract check on every one of the ~8
  # ticks a day GitHub delivers -- for a scan window 90 days wide, over a pipeline
  # that runs once a week.
  completion_title="saga-continue stage=seforim-published correlation=$corr"
  if ! completed=$(TITLE="$completion_title" gh api --paginate -X GET \
      "repos/$REPO/actions/workflows/saga-continue.yml/runs" -f per_page=100 \
      --jq '.workflow_runs[] | select(.display_title==env.TITLE and .status=="completed" and .conclusion=="success") | .id'); then
    echo "::error::$SAGA_REF: cannot list its completion continuations"
    FAILURES=$((FAILURES+1)); continue
  fi
  if [ -n "$completed" ]; then
    echo "complete saga=$saga_run correlation=$corr"
    if [ -z "$SUPERSEDING_CYCLE" ] || [ "$saga_cycle" -gt "$SUPERSEDING_CYCLE" ]; then
      SUPERSEDING_CYCLE=$saga_cycle
      SUPERSEDING_SAGA=$saga_run
    fi
    continue
  fi
  # Unfinished, but older than a cycle that finished.  Nothing recovered here can
  # still reach a user, while an operator-action state this reconciler cannot
  # clear would re-alert on every tick until a human edits a file.  A stuck cycle
  # that is still the newest one is the case an operator must see, and it stays a
  # hard failure below.
  if [ -n "$SUPERSEDING_CYCLE" ] && [ "$saga_cycle" -lt "$SUPERSEDING_CYCLE" ]; then
    # Named with its URL and counted in the tail line: silencing a cycle must not
    # also make it unfindable.  Until now the error that repeated here was what
    # eventually moved an operator to retire and clean up an abandoned cycle.
    echo "superseded $SAGA_REF: export cycle $saga_cycle is older than completed cycle $SUPERSEDING_CYCLE (saga=$SUPERSEDING_SAGA); skipped"
    SUPERSEDED=$((SUPERSEDED+1))
    continue
  fi
  if ! contract_relation=$(gh api "repos/$REPO/compare/$STATE_CONTRACT_COMMIT...$saga_head" --jq .status); then
    echo "::error::$SAGA_REF: cannot establish its saga-state contract ancestry"
    FAILURES=$((FAILURES+1)); continue
  fi
  case "$contract_relation" in
    identical|ahead) ;;
    behind|diverged)
      echo "legacy saga=$saga_run is outside the durable saga-state lineage ($contract_relation); skipped"
      continue ;;
    *)
      echo "::error::$SAGA_REF: head is not on the durable saga-state lineage ($contract_relation)"
      FAILURES=$((FAILURES+1)); continue ;;
  esac
  correlation_sha=$(printf '%s' "$corr" | sha256sum | cut -d' ' -f1)
  release_tag="saga-state-$correlation_sha-attempt-$saga_attempt"
  state_dir="$TMP/$saga_run"
  mkdir "$state_dir"
  gh release download "$release_tag" -R "$REPO" -p saga-state.json -p saga-state.sha256 -D "$state_dir" || {
    echo "::error::$SAGA_REF: cannot download its saga-state release $release_tag"
    FAILURES=$((FAILURES+1)); continue; }
  if ! python3 "$HERE/saga_contract.py" --directory "$state_dir" \
      --expected-run-id "$saga_run" --expected-run-attempt "$saga_attempt" \
      --expected-correlation "$corr"; then
    echo "::error::$SAGA_REF: its saga-state release fails the contract check"
    FAILURES=$((FAILURES+1)); continue
  fi
  expected_release="saga-state-$(jq -r .correlation_sha256 "$state_dir/saga-state.json")-attempt-$saga_attempt"
  if [ "$release_tag" != "$expected_release" ]; then
    echo "::error::$SAGA_REF: state release tag disagrees with its canonical identity"
    FAILURES=$((FAILURES+1)); continue
  fi
  expected=$(jq -r .expected_links_commit "$state_dir/saga-state.json")
  tool=$(jq -r .seforim_tool_commit "$state_dir/saga-state.json")

  ot_title="update-library mode=links_sync_mode correlation=$corr"
  set +e
  ot_run=$(ensure_otzaria_child "$ot_title" "$expected" "$corr" "$saga_run" "$saga_attempt")
  rc=$?
  set -e
  [ "$rc" -eq 0 ] || { FAILURES=$((FAILURES+1)); continue; }
  # An empty id means a child was just dispatched: it has nothing to reconcile yet.
  [ -n "$ot_run" ] || continue
  ot_state=$(gh api "repos/$REPO/actions/runs/$ot_run" --jq '.status+":"+(.conclusion//"")') || {
    echo "::error::$SAGA_REF: cannot read the state of Otzaria child $ot_run"
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
      set +e
      ensure_continuation otzaria-published "$corr" "$saga_run" "$saga_attempt" "$ot_run"
      rc=$?
      set -e
      # 2 is "already reported, and nothing was delivered": an active continuation
      # or a stage paused for an operator.  Calling either of those "recovered"
      # is how a log reads as a working watchdog while the saga stands still.
      case "$rc" in
        0) echo "recovered S1 callback for $SAGA_REF" ;;
        2) ;;
        *) FAILURES=$((FAILURES+1)) ;;
      esac
      continue
    fi
    echo "::error::$SAGA_REF: cannot resolve a single exact Seforim child"
    FAILURES=$((FAILURES+1)); continue
  fi
  sef_state=$(gh api "repos/Otzaria/SeforimLibrary/actions/runs/$sef_run" --jq '.status+":"+(.conclusion//"")') || {
    echo "::error::$SAGA_REF: cannot read the state of Seforim child $sef_run"
    FAILURES=$((FAILURES+1)); continue; }
  case "$sef_state" in
    requested:*|waiting:*|pending:*|queued:*|in_progress:*) ;;
    completed:success)
      set +e
      ensure_continuation seforim-published "$corr" "$saga_run" "$saga_attempt" "$sef_run"
      rc=$?
      set -e
      # 2 is "already reported, and nothing was delivered": an active continuation
      # or a stage paused for an operator.  Calling either of those "recovered"
      # is how a log reads as a working watchdog while the saga stands still.
      case "$rc" in
        0) echo "recovered S2 callback for $SAGA_REF" ;;
        2) ;;
        *) FAILURES=$((FAILURES+1)) ;;
      esac ;;
    *) rerun_failed_child Otzaria/SeforimLibrary "$sef_run" "Seforim child" || FAILURES=$((FAILURES+1)) ;;
  esac
done

[ "$SUPERSEDED" -eq 0 ] || echo "$SUPERSEDED unfinished saga(s) skipped as overtaken by a completed cycle"
[ "$QUIETED" -eq 0 ] || echo "$QUIETED saga(s) still await operator recovery past the ${ALERT_WINDOW_HOURS}h alert window (see the warnings above)"
[ "$FAILURES" -eq 0 ] || { echo "::error::$FAILURES saga reconciliation failure(s)"; exit 1; }
echo "saga reconciliation complete"
