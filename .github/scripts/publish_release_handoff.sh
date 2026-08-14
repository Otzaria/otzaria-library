#!/usr/bin/env bash
# Publish an exact immutable file set as a non-draft pre-release.
set -euo pipefail
tag=${1:?tag required}; title=${2:?title required}; target=${3:?target required}; shift 3
[ "$#" -gt 0 ]; [[ "$tag" =~ ^[A-Za-z0-9._-]{1,240}$ ]]; [[ "$target" =~ ^[0-9a-f]{40}$ ]]
: "${GH_TOKEN:?GH_TOKEN required}"
for path in "$@"; do
  [ -f "$path" ]
  name=${path##*/}
  [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$ ]] || {
    echo "::error::release asset basename is unsafe or would be normalized by GitHub: $name"
    exit 2
  }
  [ "$(stat --format='%s' "$path")" -le 2147483647 ]
done
state="$RUNNER_TEMP/release-handoff-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}.json"
read_release() {
  gh api "repos/$GITHUB_REPOSITORY/releases/tags/$tag" --jq \
    '{isDraft:.draft,isPrerelease:.prerelease,targetCommitish:.target_commitish,assets:[.assets[]|{name,size,digest}]}'
}
if ! read_release > "$state" 2>/dev/null; then
  gh release create "$tag" --target "$target" --title "$title" \
    --notes "Immutable workflow handoff; consumers verify every digest." --prerelease || \
    read_release > "$state"
fi
check() {
  read_release > "$state"
  python3 - "$state" "$target" "$@" <<'PY'
import hashlib,json,sys
from pathlib import Path
v=json.loads(Path(sys.argv[1]).read_text()); target=sys.argv[2]; paths=list(map(Path,sys.argv[3:]))
if v.get('isDraft') is not False or v.get('isPrerelease') is not True or v.get('targetCommitish')!=target:
 raise SystemExit('handoff release identity differs')
remote=v.get('assets',[]); actual={a['name']:(a['size'],a.get('digest')) for a in remote}
if len(actual)!=len(remote) or len({p.name for p in paths})!=len(paths) or set(actual)-{p.name for p in paths}:
 raise SystemExit('handoff asset set differs')
for p in paths:
 expected=(p.stat().st_size,'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest())
 if p.name not in actual: print(p)
 elif actual[p.name][0]!=expected[0] or actual[p.name][1] not in (None,'',expected[1]):
  raise SystemExit('remote asset conflict: '+p.name)
PY
}
missing="$RUNNER_TEMP/release-handoff-missing-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}"
check "$@" > "$missing"
while IFS= read -r path; do [ -z "$path" ] || gh release upload "$tag" "$path"; done < "$missing"
for _ in $(seq 1 24); do
  check "$@" > "$missing"
  if [ ! -s "$missing" ] && python3 - "$state" "$@" <<'PY'
import hashlib,json,sys
from pathlib import Path
actual={a['name']:(a['size'],a.get('digest')) for a in json.loads(Path(sys.argv[1]).read_text())['assets']}
expected={}
for p in map(Path,sys.argv[2:]): expected[p.name]=(p.stat().st_size,'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest())
if actual!=expected: raise SystemExit(1)
PY
  then echo "Published immutable release handoff $tag"; exit 0; fi
  sleep 5
done
echo "::error::release handoff never became byte-exact"; exit 1
