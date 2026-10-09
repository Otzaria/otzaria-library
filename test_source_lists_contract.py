"""רשימת המקורות של שלב ה-prepare חייבת להתאים ל-BOOK_ROOTS.

sync_and_merge_folders.py (SourcesBooks.csv) מחזיק רשימת תיקיות משלו; מקור שנארז
ל-otzaria_latest.zip אבל חסר בה נעלם מ-SourcesBooks.csv.

הסקריפט רץ בעת הייבוא, ולכן הרשימות נקראות ב-ast ולא ב-import.
"""

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent

# שורשי ספריא ב-BOOK_ROOTS ריקים מאז 2ed56e69 (ספרי ספריא נוצרים ב-SeforimLibrary
# מה-API, ואינם קבצים במאגר). הם היחידים שמותר להשמיט מהרשימות.
EMPTY_SEFARIA_ROOTS = {
    "sefariaToOtzaria/sefaria_export/ספרים/אוצריא",
    "sefariaToOtzaria/sefaria_api/ספרים/אוצריא",
}


def assigned_literal(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path.name}: no top-level `{name} = ...`")


BOOK_ROOTS = assigned_literal(REPO / "manual_links_packaging.py", "BOOK_ROOTS")


class SourceListsMatchBookRootsTest(unittest.TestCase):
    def assert_matches_book_roots(self, script: str):
        folders = assigned_literal(REPO / script, "folders")
        self.assertEqual(len(folders), len(set(folders)), f"{script}: duplicate folder")
        self.assertEqual(
            sorted(set(folders)),
            sorted(set(BOOK_ROOTS) - EMPTY_SEFARIA_ROOTS),
            f"{script}: `folders` must list every BOOK_ROOTS entry (except the empty Sefaria roots)",
        )

    def test_sources_books_csv_covers_every_packaged_root(self):
        self.assert_matches_book_roots("sync_and_merge_folders.py")

    def test_every_sources_books_root_has_a_source_name(self):
        # בלי מפתח, עמודת "תיקיית המקור" נופלת בשקט לשם התיקייה הגולמי.
        folders = assigned_literal(REPO / "sync_and_merge_folders.py", "folders")
        mapping = assigned_literal(REPO / "sync_and_merge_folders.py", "mapping")
        missing = sorted({Path(f).parts[0] for f in folders} - set(mapping))
        self.assertEqual(missing, [], "sync_and_merge_folders.py: `mapping` has no source name for these roots")


if __name__ == "__main__":
    unittest.main()
