#!/usr/bin/env bash
# Print the tag of the newest final SeforimLibrary release that really carries a database.
#
# A release that is not a pre-release is not necessarily a DB release: the vector QA
# releases (vectors-qa491-*) were published as final and hold only gates.json and
# *.oxv.zst. Taking the first final release failed every gate that needs the DB
# ("no assets match the file pattern", jq exit 4). A usable release has the full DB
# asset by the producer's naming contract, build_provenance.json and the allocator state.
set -euo pipefail

tool=${1:?usage: select_released_db_tag.sh <seforim-tool> [repo]}
repo=${2:-Otzaria/SeforimLibrary}
limit=${SELECT_RELEASE_LIMIT:-100}
# shellcheck source=/dev/null
. "$tool/.github/scripts/db_asset_names.sh"

tags=$(gh release list -R "$repo" --exclude-pre-releases --exclude-drafts -L "$limit" \
  --json tagName -q '.[].tagName')
while IFS= read -r tag; do
  [ -n "$tag" ] || continue
  assets=$(gh release view "$tag" -R "$repo" --json assets) || {
    echo "skipping $tag: release assets could not be read" >&2; continue; }
  jq -e '[.assets[].name] as $names
         | ($names | index("build_provenance.json")) != null
           and ($names | index("seforim.db.buildstate.zst")) != null' <<<"$assets" >/dev/null || {
    echo "skipping $tag: no build_provenance.json / seforim.db.buildstate.zst" >&2; continue; }
  jq -e "$FULL_DB_ASSET_JQ | .name // empty" <<<"$assets" >/dev/null || {
    echo "skipping $tag: no full-DB asset" >&2; continue; }
  echo "$tag"
  exit 0
done <<<"$tags"
echo "::error::no final release of $repo (newest $limit checked) carries a seforim DB" >&2
exit 1
