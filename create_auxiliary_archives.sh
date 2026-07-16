#!/usr/bin/env bash
set -euo pipefail
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKSPACE"

python3 - <<'PY'
from pathlib import Path
from manual_links_packaging import PackagingError, write_reproducible_zip

source = Path("DictaToOtzaria/לא ערוך/ספרים")
if not source.is_dir():
    raise PackagingError(f"required Dicta source is absent: {source}")
write_reproducible_zip(source, Path("otzaria_dicta_latest.zip"))
PY

pdf_source="MoreBooks/ספרים/אוצריא/תלמוד בבלי"
[[ -d "$pdf_source" ]]
find "$pdf_source" -type f -iname '*.pdf' -print -quit | grep -q .

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
flat="$staging/תלמוד בבלי"
mkdir -p "$flat"
declare -A seen
while IFS= read -r -d '' pdf; do
  basename="$(basename "$pdf")"
  if [[ -n "${seen[$basename]:-}" ]]; then
    echo "Duplicate Bavli PDF basename: $basename" >&2
    echo "First: ${seen[$basename]}" >&2
    echo "Second: $pdf" >&2
    exit 1
  fi
  seen[$basename]="$pdf"
  cp "$pdf" "$flat/$basename"
done < <(find "$pdf_source" -type f -iname '*.pdf' -print0)

# Stable PAX metadata and sorted paths make this asset reproducible too.
tar --sort=name \
  --mtime='UTC 1970-01-01' \
  --owner=0 --group=0 --numeric-owner \
  --format=posix \
  --pax-option=delete=atime,delete=ctime \
  -C "$staging" \
  -cf - "תלמוד בבלי" \
  | zstd -f -19 -T0 -o talmud_bavli_latest.tar.zst

zstd -t --quiet talmud_bavli_latest.tar.zst
tar --use-compress-program=unzstd -tf talmud_bavli_latest.tar.zst >/dev/null
