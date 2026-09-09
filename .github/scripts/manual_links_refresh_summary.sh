#!/usr/bin/env bash
# Turn one ManualLinksRefresh report into the few lines CI actually needs, and
# decide whether the link trees are provably byte-identical to the worktree.
#
# The refresh itself prints four result lines (status, lineage digest, two temp
# paths).  Every count that makes the stage auditable - anchors, records, files,
# refs, payload acceptance, packaging collisions, the tool-commit move - lives in
# manual_links_refresh_report.json and used to reach nobody, so the cycle-33987355439
# audit had to download a release asset to answer "what did the 818s stage do?".
# This is deliberately a summary: the per-record detail arrays are printed bounded,
# the way the tool itself bounds them.
#
# usage: manual_links_refresh_summary.sh REPORT DECISION [TOOL_CHECKOUT]
#   REPORT         manual_links_refresh_report.json written by the tool
#   DECISION       written `true` only when the report proves the tool rewrote no
#                  link file at all, `false` otherwise
#   TOOL_CHECKOUT  optional SeforimLibrary clone, used only to count how many tool
#                  commits the refresh crossed
set -euo pipefail

report=${1:?report path required}
decision=${2:?decision file required}
tool_checkout=${3:-}

# Detail lines are capped here as well as in the tool: a full corpus can relocate
# thousands of anchors, and a log nobody can read is the problem being fixed.
UNRELOCATABLE_DETAIL=20
RELOCATION_DETAIL=10

jq -e 'type == "object" and has("status") and has("files") and has("output_lineage")' \
  "$report" > /dev/null || {
  echo "::error::manual-links refresh report is unusable: $report"
  exit 2
}

# How far the tool moved under this refresh.  Only reported when both commits are
# present in the checkout, so a shallow or absent clone silently drops the count
# instead of failing the stage over a log line.
crossed=""
input_tool="$(jq -r '.input_lineage.seforim_tool_commit // ""' "$report")"
output_tool="$(jq -r '.output_lineage.seforim_tool_commit // ""' "$report")"
if [ -n "$tool_checkout" ] && [ -n "$input_tool" ] && [ "$input_tool" != "$output_tool" ] &&
    git -C "$tool_checkout" cat-file -e "$input_tool^{commit}" 2> /dev/null &&
    git -C "$tool_checkout" cat-file -e "$output_tool^{commit}" 2> /dev/null; then
  crossed="$(git -C "$tool_checkout" rev-list --count "$input_tool..$output_tool" 2> /dev/null || true)"
fi

jq -r '
  def n(x): if x == null then "?" else (x | tostring) end;
  "manual-links: status=\(n(.status)) mode=\(n(.mode))"
  + " · payloads \(n(.reader.payloads_loaded)) loaded/\(n(.reader.payloads_accepted)) accepted/\(n(.reader.payloads_blacklisted)) blacklisted"
  + " · anchors \(n(.anchors.checked)) checked, \(n(.anchors.drifted)) drifted, \(n(.anchors.relocated)) relocated, \(n(.anchors.unrelocatable)) unrelocatable (cap \(n(.anchors.unrelocatable_cap)))"
  + " · records \(n(.records.scanned)) scanned, \(n(.records.shifted)) shifted, \(n(.records.enriched)) enriched, \(n(.records.anchors_context_filled)) context-filled"
  + " · files \(n(.files.scanned)) scanned, \(n(.files.changed)) changed, \(n(.files.renamed)) renamed"
  + " · refs \(n(.refs.missing)) missing, \(n(.refs.renamed)) renamed, \(n(.refs.duplicate)) duplicate"
  + " · packaging collisions \(n(.packaging_collisions))"
' "$report"

jq -r --arg crossed "$crossed" '
  def short(x): if (x | type) == "string" then x[0:7] else "?" end;
  def moved(a; b): if a == b then "unchanged" else "changed" end;
  if .input_lineage == null then
    "manual-links lineage: bootstrap (no input lineage)"
    + " · sefaria \(.output_lineage.sefaria.tag)"
    + " · tool \(short(.output_lineage.seforim_tool_commit))"
  else
    "manual-links lineage: sefaria \(.input_lineage.sefaria.tag) -> \(.output_lineage.sefaria.tag)"
    + " · tool \(short(.input_lineage.seforim_tool_commit)) -> \(short(.output_lineage.seforim_tool_commit))"
    + (if $crossed == "" then "" else " (\($crossed) commit(s) crossed)" end)
    + " · config \(moved(.input_lineage.config_sha256; .output_lineage.config_sha256))"
    + " · packaged tree \(moved(.input_lineage.packaged_links_tree_sha256; .output_lineage.packaged_links_tree_sha256))"
    + " · source tree \(moved(.input_lineage.source_links_tree_sha256; .output_lineage.source_links_tree_sha256))"
  end
' "$report"

drifted="$(jq -r '.anchors.drifted // 0' "$report")"
relocated="$(jq -r '.anchors.relocated // 0' "$report")"
unrelocatable="$(jq -r '.anchors.unrelocatable // 0' "$report")"
collisions="$(jq -r '.packaging_collisions // 0' "$report")"
blacklisted="$(jq -r '.reader.payloads_blacklisted // 0' "$report")"
failures="$(jq -r '(.failures // []) | length' "$report")"

if [ "$drifted" != 0 ]; then
  echo "::warning::manual-links: $drifted anchor(s) drifted"
fi

if [ "$collisions" != 0 ]; then
  echo "::warning::manual-links: $collisions packaging collision(s) - two link files flatten onto one packaged path"
fi

if [ "$unrelocatable" != 0 ]; then
  echo "::warning::manual-links: $unrelocatable record anchor(s) could not be re-anchored (cap $(jq -r '.anchors.unrelocatable_cap // "?"' "$report"))"
  jq -r --argjson limit "$UNRELOCATABLE_DETAIL" '
    (.records.anchors_unrelocatable // [])[0:$limit][]
    | "::warning::manual-links unrelocatable anchor: \(.file)[\(.record_index)] ref_1=\(.ref_1) line_index=\(.line_index_1) start=\(.start) reason=\(.reason)"
  ' "$report"
  listed="$(jq -r --argjson limit "$UNRELOCATABLE_DETAIL" \
    '((.records.anchors_unrelocatable // []) | length) as $l | if $l > $limit then $limit else $l end' "$report")"
  if [ "$unrelocatable" -gt "$listed" ]; then
    echo "::warning::manual-links: $((unrelocatable - listed)) further unrelocatable anchor(s) not listed; the full set is in the refresh report release asset"
  fi
fi

if [ "$relocated" != 0 ]; then
  echo "manual-links: $relocated anchor(s) re-anchored against the new corpus"
  jq -r --argjson limit "$RELOCATION_DETAIL" '
    (.records.anchors_relocations // [])[0:$limit][]
    | "manual-links relocated anchor: \(.file)[\(.record_index)] ref_1=\(.ref_1) start \(.old_start) -> \(.new_start) via=\(.strategy)"
  ' "$report"
  listed="$(jq -r --argjson limit "$RELOCATION_DETAIL" \
    '((.records.anchors_relocations // []) | length) as $l | if $l > $limit then $limit else $l end' "$report")"
  if [ "$relocated" -gt "$listed" ]; then
    echo "manual-links: $((relocated - listed)) further relocation(s) not listed; the full set is in the refresh report release asset"
  fi
fi

if [ "$blacklisted" != 0 ]; then
  # DROP-1: intentional (SefariaBlacklists), but the report schema carries the
  # count only - naming the books needs a tool change, not a workflow change.
  echo "manual-links: $blacklisted Sefaria payload(s) blacklisted; the report carries the count only, not the titles"
fi

if [ "$failures" != 0 ]; then
  echo "::warning::manual-links: the report lists $failures failure entr(ies)"
  jq -r '(.failures // [])[0:20][] | "::warning::manual-links failure: \(tostring)"' "$report"
fi

# copyConfiguredRoots seeds the output from the worktree byte for byte, and only
# persistChangedDocuments (files.changed) and the two rename paths (files.renamed)
# touch it afterwards - so changed=0 and renamed=0 prove the output tree equals the
# worktree tree.  Both lineage digests are required to agree as well, so any doubt
# (a bootstrap with no input lineage, a missing digest) takes the full sync path.
files_changed="$(jq -r '.files.changed // -1' "$report")"
files_renamed="$(jq -r '.files.renamed // -1' "$report")"
digests_unchanged="$(jq -r '
  if (.input_lineage != null)
    and ((.output_lineage.packaged_links_tree_sha256 | type) == "string")
    and ((.output_lineage.source_links_tree_sha256 | type) == "string")
    and (.input_lineage.packaged_links_tree_sha256 == .output_lineage.packaged_links_tree_sha256)
    and (.input_lineage.source_links_tree_sha256 == .output_lineage.source_links_tree_sha256)
  then "true" else "false" end
' "$report")"

if [ "$files_changed" = 0 ] && [ "$files_renamed" = 0 ] && [ "$digests_unchanged" = true ]; then
  printf 'true\n' > "$decision"
  echo "manual-links: no link file was rewritten or renamed and both tree digests are unchanged; staging manual_links_lineage.json only"
else
  printf 'false\n' > "$decision"
  echo "manual-links: link trees moved (changed=$files_changed renamed=$files_renamed digests_unchanged=$digests_unchanged); syncing every present links root"
fi
