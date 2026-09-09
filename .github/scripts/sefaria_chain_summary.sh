#!/usr/bin/env bash
# Print what the Sefaria release-chain verification actually walked.
#
# `sefaria_release_chain.py` downloads a release_metadata.json per hop, verifies
# every digest, then downloads and verifies a ~534MB archive - and prints nothing,
# so 33s of the sync job were invisible in cycle 33987355439 (audit OBS-2).  Every
# fact below is read back out of the verified chain-result.json, never re-derived.
#
# usage: sefaria_chain_summary.sh CHAIN_DIR
set -euo pipefail

chain_dir=${1:?chain directory required}
result="$chain_dir/chain-result.json"

# Long chains stay bounded: one hop per Sefaria release since the committed lineage.
HOP_DETAIL=10

jq -e 'type == "object" and has("target_tag") and has("archive")' "$result" > /dev/null || {
  echo "::error::sefaria chain result is unusable: $result"
  exit 2
}

jq -r --argjson limit "$HOP_DETAIL" '
  def short(x): if (x | type) == "string" then x[0:12] else "?" end;
  (.applied_changelog_chain // []) as $chain
  | [
      "sefaria chain: target \(.target_tag) metadata \(short(.target_metadata_sha256)) · \($chain | length) changelog hop(s) walked back to the committed lineage base"
    ]
    + (if ($chain | length) == 0 then
        ["sefaria chain: target already is the committed lineage base; no changelog hop to apply"]
      else
        [ $chain[0:$limit] | to_entries[]
          | "sefaria chain hop \(.key + 1)/\($chain | length): \(.value.previous.tag) -> \(.value.tag) via \(.value.changelog_name) sha256=\(short(.value.changelog_sha256)) metadata=\(short(.value.metadata_sha256))"
        ]
      end)
    + (if ($chain | length) > $limit then
        ["sefaria chain: \(($chain | length) - $limit) further hop(s) not listed"]
      else [] end)
    + [
      "sefaria chain: archive \(.archive.parts | length) part(s), \(.archive.size) byte(s), expected sha256 \(short(.archive.sha256))"
    ]
  | .[]
' "$result"
