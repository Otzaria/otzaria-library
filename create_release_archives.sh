#!/usr/bin/env bash
#
# create_release_archives.sh
# ---------------------------
# גרסה מקומית של שלב הדחיסה הראשי מתוך .github/workflows/update-library.yml
# יוצר בדיוק את הקובץ:
#   * otzaria_latest.zip   (אוצריא + links מכל המקורות, שומר את תיקיית-האב)
# ומייצר קודם את files_manifest.json שנדחס לתוכו (יחד עם metadata.json).
#
# שימוש:
#   ./create_release_archives.sh
#
set -euo pipefail
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# שורש הריפו = התיקייה שבה הסקריפט יושב (מקביל ל-$GITHUB_WORKSPACE)
WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKSPACE"

# רשימת המקורות (זהה ל-YAML)
OTZARIA_SRCS=(
  "Ben-YehudaToOtzaria/ספרים/אוצריא"
  "DictaToOtzaria/ערוך/ספרים/אוצריא"
  "OnYourWayToOtzaria/ספרים/אוצריא"
  "OraytaToOtzaria/ספרים/אוצריא"
  "tashmaToOtzaria/ספרים/אוצריא"
  "sefariaToOtzaria/sefaria_export/ספרים/אוצריא"
  "sefariaToOtzaria/sefaria_api/ספרים/אוצריא"
  "MoreBooks/ספרים/אוצריא"
  "wikiJewishBooksToOtzaria/ספרים/אוצריא"
  "wikisourceToOtzaria/ספרים/אוצריא"
  "ToratEmetToOtzaria/ספרים/אוצריא"
  "pninimToOtzaria/ספרים/אוצריא"
  "National-LibraryToOtzaria/ספרים/אוצריא"
)

LINKS_SRCS=(
  "Ben-YehudaToOtzaria/links"
  "DictaToOtzaria/ערוך/links"
  "OnYourWayToOtzaria/links"
  "OraytaToOtzaria/links"
  "tashmaToOtzaria/links"
  "sefariaToOtzaria/sefaria_export/links"
  "sefariaToOtzaria/sefaria_api/links"
  "MoreBooks/links"
  "wikiJewishBooksToOtzaria/links"
  "wikisourceToOtzaria/links"
  "ToratEmetToOtzaria/links"
  "pninimToOtzaria/links"
  "National-LibraryToOtzaria/links"
)

# מקורות ה-manifest של אוצריא (זהה ל-YAML: קודם כל תיקיות הספרים, אח"כ ה-links)
MANIFEST_BOOK_SRCS=(
  "Ben-YehudaToOtzaria/ספרים/אוצריא"
  "DictaToOtzaria/ערוך/ספרים/אוצריא"
  "OnYourWayToOtzaria/ספרים/אוצריא"
  "OraytaToOtzaria/ספרים/אוצריא"
  "tashmaToOtzaria/ספרים/אוצריא"
  "sefariaToOtzaria/sefaria_export/ספרים/אוצריא"
  "sefariaToOtzaria/sefaria_api/ספרים/אוצריא"
  "MoreBooks/ספרים/אוצריא"
  "ToratEmetToOtzaria/ספרים/אוצריא"
  "wikisourceToOtzaria/ספרים/אוצריא"
  "wikiJewishBooksToOtzaria/ספרים/אוצריא"
  "pninimToOtzaria/ספרים/אוצריא"
  "National-LibraryToOtzaria/ספרים/אוצריא"
)

# תאימות: sha256sum או shasum (macOS)
if command -v sha256sum >/dev/null 2>&1; then
  sha256() { sha256sum "$1" | cut -d" " -f1; }
else
  sha256() { shasum -a 256 "$1" | cut -d" " -f1; }
fi

# sed בתוך המקום (BSD/macOS מול GNU)
sed_inplace() {
  if sed --version >/dev/null 2>&1; then
    sed -i "$@"
  else
    sed -i '' "$@"
  fi
}

emit_manifest_dir() {
  # מוסיף שורות "path": {"hash": "..."}, לכל קובץ תחת תיקייה נתונה
  local dir="$1" out="$2"
  [ -d "$dir" ] || return 0
  find "$dir" -type f ! -path "./.git/*" ! -path "./.github/*" 2>/dev/null |
    while IFS= read -r file; do
      local path="${file#./}"
      printf '"%s": {"hash": "%s"},\n' "$path" "$(sha256 "$file")"
    done >> "$out"
}

########################################
# 1. יצירת files_manifest.json
########################################
echo "Generating files_manifest.json ..."
echo "{" > files_manifest.json
if [ -f "./metadata.json" ]; then
  printf '"metadata.json": {"hash": "%s"},\n' "$(sha256 ./metadata.json)" >> files_manifest.json
fi
for d in "${MANIFEST_BOOK_SRCS[@]}"; do emit_manifest_dir "$d" files_manifest.json; done
for d in "${LINKS_SRCS[@]}";        do emit_manifest_dir "$d" files_manifest.json; done
sed_inplace '$ s/,$//' files_manifest.json
echo "}" >> files_manifest.json

########################################
# 2. otzaria_latest.zip
########################################
echo "Creating otzaria_latest.zip (keeping subfolders)..."
rm -f "$WORKSPACE/otzaria_latest.zip"

for src in "${OTZARIA_SRCS[@]}" "${LINKS_SRCS[@]}"; do
  if [ -d "$src" ]; then
    echo "  + $src"
    parent="$(dirname "$src")"
    folder="$(basename "$src")"
    ( cd "$parent" && zip -qr "$WORKSPACE/otzaria_latest.zip" "$folder" )
  fi
done

zip -q "$WORKSPACE/otzaria_latest.zip" files_manifest.json metadata.json || true

echo ""
echo "סיום. הקובץ שנוצר בשורש הריפו:"
ls -lh "$WORKSPACE/otzaria_latest.zip"
