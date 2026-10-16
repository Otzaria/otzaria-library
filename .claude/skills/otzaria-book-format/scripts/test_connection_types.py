"""Connection types written by to_otzaria.py and accepted by validate_sidecars.py.

Run: python3 -m unittest -v test_connection_types   (from this directory)
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


to_otzaria = _load("to_otzaria")
validate_sidecars = _load("validate_sidecars")
ICL = HERE.parents[1] / "otzaria-db-linker" / "scripts" / "insert_commentary_link.py"


class SplitFootnotesTests(unittest.TestCase):
    LINES = ['<h1>T</h1>',
             'a<sup class="footnote-marker">1</sup><i class="footnote">n1</i> b'
             '<sup class="footnote-marker">2</sup><i class="footnote">n2</i>']

    def test_links_are_base_named_footnotes(self):
        out, notes, links = to_otzaria.split_footnotes(self.LINES)
        self.assertEqual(notes, ["n1", "n2"])
        self.assertEqual([(e["line_index_1"], e["line_index_2"], e["Conection Type"]) for e in links],
                         [(2, 1, "footnotes"), (2, 2, "footnotes")])
        self.assertNotIn("footnote-marker", out[1])

    @unittest.skipUnless(ICL.exists(), "otzaria-db-linker engine not present")
    def test_generator_stores_them_base_to_notes_as_footnotes(self):
        spec = importlib.util.spec_from_file_location("icl", ICL)
        icl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(icl)
        base = "Base"
        notes = "הערות על " + base
        for base_is_base in (True, False):  # either way: as written, FOOTNOTES
            self.assertEqual(icl.plan_storage("FOOTNOTES", base, base_is_base, notes, False),
                             (False, "FOOTNOTES"))


class ValidateSidecarsTypeTests(unittest.TestCase):
    def check(self, ctype):
        validate_sidecars.errors.clear()
        validate_sidecars.warnings.clear()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp, "X_links.json")
            p.write_text(json.dumps([{"line_index_1": 1, "line_index_2": 1, "heRef_2": "x",
                                      "path_2": "הערות על X.txt", "Conection Type": ctype}]),
                         encoding="utf-8")
            validate_sidecars.check_links(p, None, None, None)
        return list(validate_sidecars.errors), list(validate_sidecars.warnings)

    def test_space_and_underscore_spellings_are_the_same_type(self):
        for ctype in ("mesorat hashas", "mesorat_hashas", "ein mishpat / ner mitsvah", "ein_mishpat",
                      "related passage", "related_passage", "footnote", "super commentary",
                      "sifrei mitzvot", "sifrei_mitzvot", "quotation_auto_tanakh", "none", ""):
            self.assertEqual(self.check(ctype), ([], []), ctype)

    def test_trap_spellings_are_errors_and_unknown_warns(self):
        for ctype in ("sifrei mitsvot", "sifrei_mitsvot", "note", "notes"):
            errors, _warnings = self.check(ctype)
            self.assertEqual(len(errors), 1, ctype)
        errors, warnings = self.check("no_such_type")
        self.assertEqual((len(errors), len(warnings)), (0, 1))


class CompanionMergeContractTests(unittest.TestCase):
    """issue otzaria-library#200: a broken contract left the notes standalone, silently."""

    def run_check(self, notes_name, notes_lines, base_line="a<sup>1</sup> b"):
        validate_sidecars.errors.clear()
        validate_sidecars.warnings.clear()
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp, "X.txt")
            book.write_text("<h1>X</h1>\n" + base_line, encoding="utf-8")
            target = Path(tmp, notes_name + ".txt")
            target.write_text("\n".join(notes_lines), encoding="utf-8")
            links = Path(tmp, "X_links.json")
            links.write_text(json.dumps([{"line_index_1": 2, "line_index_2": 2, "heRef_2": "x",
                                          "path_2": target.name, "Conection Type": "footnotes"}]),
                             encoding="utf-8")
            validate_sidecars.check_links(links, book, target, None)
        return list(validate_sidecars.errors), list(validate_sidecars.warnings)

    def test_valid_pair_passes(self):
        self.assertEqual(self.run_check("הערות על X", ["<h1>הערות על X</h1>", "<sup>1</sup> n"]), ([], []))

    def test_other_name_warns(self):
        _, warnings = self.run_check("הערות במספרים על X", ["<h1>T</h1>", "<sup>1</sup> n"])
        self.assertEqual(len(warnings), 1)

    def test_unlinked_credit_line_fails(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "<sup>1</sup> n", "© credit"])
        self.assertEqual(len(errors), 1)

    def test_italic_note_fails(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "<sup>1</sup> <i>n</i>"])
        self.assertEqual(len(errors), 1)

    def test_base_with_inline_footnotes_fails(self):
        errors, _ = self.run_check("הערות על X", ["<h1>T</h1>", "<sup>1</sup> n"],
                                   base_line='a<sup class="footnote-marker">1</sup><i class="footnote">n</i>')
        self.assertEqual(len(errors), 1)


# Characters Kotlin's String.trim() removes (Character.isWhitespace || isSpaceChar),
# measured on the JVM against SeforimLibrary's ConnectionType.fromKnownStringOrNull.
# Notably NOT U+0085 (str.strip() removes it), U+200B, U+FEFF.
KOTLIN_TRIM_BMP = {0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0xa0, 0x1680,
              0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008,
              0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000}


class NormalizeCtypeKotlinTrimTests(unittest.TestCase):
    def test_trim_matches_kotlin_over_the_bmp(self):
        norm = validate_sidecars.normalize_ctype
        for cp in range(0x10000):
            if 0xD800 <= cp <= 0xDFFF:
                continue
            c = chr(cp)
            for s in (c + "source", "source" + c):
                self.assertEqual(norm(s) == "source", cp in KOTLIN_TRIM_BMP, hex(cp))

    def test_null_is_empty_like_the_generator(self):
        self.assertEqual(validate_sidecars.normalize_ctype(None), "")


if __name__ == "__main__":
    unittest.main()
