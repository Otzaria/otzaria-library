"""Offline regression tests: invalid corrections must not alter converter outputs."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import post_convert_fixes as P


def converter(source, filename, name):
    directory = REPO / source / "סקריפטים"
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location(name, directory / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TE = converter("ToratEmetToOtzaria", "te_convert.py", "te_write_test")
OY = converter("OnYourWayToOtzaria", "ובלכתך_בדרך.py", "oy_write_test")
OR = converter("OraytaToOtzaria", "orayta_convert.py", "or_write_test")
# The Ben-Yehuda converter (split_footnotes.write_book) moved to Otzaria/book-sources with its
# own copy of these checks: Ben-YehudaToOtzaria/סקריפטים/test_library_paths.py.
# The wiki converter (demo_part_2.write_book) moved to Otzaria/book-sources with its
# own copy of these checks: wikisourceToOtzaria/סקריפטים/test_demo_part_2_writes.py.


class OutputSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.book = self.root / "ספר.txt"
        self.notes = self.root / "הערות על ספר.txt"
        self.links_dir = self.root / "links"
        self.links_dir.mkdir()
        self.links = self.links_dir / "ספר_links.json"
        for n, path in enumerate((self.book, self.notes, self.links)):
            path.write_text(f"EXISTING OUTPUT {n}\n", encoding="utf-8")
        self.before = {p: p.read_bytes() for p in (self.book, self.notes, self.links)}

    def rules(self, target, old="עוגן", new="מתוקן"):
        (self.source / P.FILE_NAME).write_text(
            "book\told\tnew\tnote\n" + f"{target}\t{old}\t{new}\tregression\n", encoding="utf-8")
        P._cache.pop(str(self.source / P.FILE_NAME), None)

    def unchanged(self):
        self.assertEqual({p: p.read_bytes() for p in self.before}, self.before)

    def torat_emet(self, text):
        source = self.root / "input.txt"
        source.write_text("&UniqueId=1&CosmeticsType=\n$ ספר\n" + text, encoding="cp1255")
        with patch.object(TE, "SOURCE_DIR", str(self.source)), patch.object(sys, "argv", [
                "te_convert.py", source.name, "--src", str(self.root), "-o", str(self.book)]):
            TE.main()

    def onyourway(self, text):
        source = self.root / "input.xml"
        source.write_text(f'<book n="ספר"><chap n="א"><p>{text}</p></chap></book>', encoding="utf-8")
        with patch.object(OY, "SOURCE_DIR", str(self.source)):
            OY.convert_file(str(source), str(self.book), "ספר")

    def grouped(self, module, text="עוגן", notes="עוגן"):
        with patch.object(OR, "SOURCE_DIR", str(self.source)):
            OR.write_book(str(self.book), ["<h1>ספר</h1>", text], [(2, notes)], str(self.links_dir))

    def test_single_book_errors_preserve_existing_output(self):
        self.rules("ספר")
        for writer in (self.torat_emet, self.onyourway):
            for text in ("טקסט אחר", "עוגן עוגן"):
                with self.subTest(writer=writer.__name__, text=text), self.assertRaises(P.PostConvertFixError):
                    writer(text)
                self.unchanged()

    def test_single_book_errors_do_not_create_output(self):
        self.book.unlink()
        self.rules("ספר")
        for writer in (self.torat_emet, self.onyourway):
            with self.subTest(writer=writer.__name__), self.assertRaises(P.PostConvertFixError):
                writer("טקסט אחר")
            self.assertFalse(self.book.exists())

    def test_single_book_success_writes_corrected_text(self):
        self.rules("ספר")
        for writer in (self.torat_emet, self.onyourway):
            with self.subTest(writer=writer.__name__):
                writer("עוגן")
                self.assertIn("מתוקן", self.book.read_text(encoding="utf-8"))
                self.assertNotIn("עוגן", self.book.read_text(encoding="utf-8"))

    def test_main_book_errors_preserve_all_outputs(self):
        self.rules("ספר")
        for module in (OR,):
            for text in ("טקסט אחר", "עוגן עוגן"):
                with self.subTest(module=module.__name__, text=text), self.assertRaises(P.PostConvertFixError):
                    self.grouped(module, text=text)
                self.unchanged()

    def test_notes_errors_preserve_main_notes_and_links(self):
        self.rules("הערות על ספר")
        for module in (OR,):
            for notes in ("טקסט אחר", "עוגן עוגן"):
                with self.subTest(module=module.__name__, notes=notes), self.assertRaises(P.PostConvertFixError):
                    self.grouped(module, notes=notes)
                self.unchanged()

    def test_notes_errors_do_not_create_partial_output(self):
        for path in self.before:
            path.unlink()
        self.rules("הערות על ספר")
        for module in (OR,):
            with self.subTest(module=module.__name__), self.assertRaises(P.PostConvertFixError):
                self.grouped(module, notes="טקסט אחר")
            for path in self.before:
                self.assertFalse(path.exists(), path)

    def test_grouped_success_corrects_notes_and_writes_links(self):
        self.rules("הערות על ספר")
        for module in (OR,):
            with self.subTest(module=module.__name__):
                self.grouped(module)
                self.assertIn("עוגן", self.book.read_text(encoding="utf-8"))
                self.assertIn("מתוקן", self.notes.read_text(encoding="utf-8"))
                self.assertNotIn("עוגן", self.notes.read_text(encoding="utf-8"))
                self.assertEqual(json.loads(self.links.read_text(encoding="utf-8"))[0]["line_index_1"], 3)

    def test_orayta_standalone_notes_error_preserves_output(self):
        self.rules("הערות על ספר")
        with patch.object(OR, "SOURCE_DIR", str(self.source)), self.assertRaises(P.PostConvertFixError):
            OR.write_editor_notes(str(self.book), [(2, "טקסט אחר")], str(self.links_dir))
        self.unchanged()


if __name__ == "__main__":
    unittest.main()
