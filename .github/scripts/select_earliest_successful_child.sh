#!/usr/bin/env bash
# The one canonical-child rule, shared by reconcile_sagas.sh and by
# saga-continue.yml stage S2.  Two runs can already share one exact dispatch
# identity and nothing can merge them back into one, so both halves of that
# decision must name the same winner: a reconciler that adopts one child while
# S2 refuses every set larger than one wedges the saga forever.
#
# Reads exact-title workflow runs on stdin as
# `databaseId<TAB>created_at<TAB>status<TAB>conclusion` and prints the earliest
# terminal success.  created_at is RFC3339, so the lexicographic sort is
# chronological; the databaseId only breaks a tie between equal instants.
# Exit 1 means no delivery of this identity has succeeded yet: each caller
# decides what that means for it, but neither ever picks a different winner.
set -euo pipefail
canonical=$(awk -F'\t' 'NF && !seen[$1]++' \
  | sort -t$'\t' -k2,2 -k1,1n \
  | awk -F'\t' '$3=="completed" && $4=="success" && !found++ {print $1}')
[ -n "$canonical" ] || exit 1
[[ "$canonical" =~ ^[1-9][0-9]*$ ]] || {
  echo "canonical child is not a databaseId" >&2; exit 2; }
printf '%s\n' "$canonical"
