"""post_convert_fixes: החלה מעוגנת, אידמפוטנטית ונכשלת בקול, וקובצי התיקונים של המקורות תקינים."""

import glob
import os
import tempfile
import unittest

import post_convert_fixes as P

REPO = os.path.dirname(os.path.abspath(__file__))


def fix(old, new, book="ספר"):
    return P.Fix(book, old, new, "", "t:1")


class ApplyText(unittest.TestCase):
    def test_replaces_unique_anchor(self):
        self.assertEqual(P.apply_text("נותן לךאלא יאמר", [fix("לךאלא", "לך אלא")]), "נותן לך אלא יאמר")

    def test_idempotent(self):
        fixes = [fix("לךאלא", "לך אלא")]
        once = P.apply_text("נותן לךאלא יאמר", fixes)
        self.assertEqual(P.apply_text(once, fixes), once)

    def test_old_contained_in_new_is_idempotent(self):
        fixes = [fix("הולנדר", "הולנדר זצ\"ל")]
        once = P.apply_text("ישעיהו הולנדר.", fixes)
        self.assertEqual(once, "ישעיהו הולנדר זצ\"ל.")
        self.assertEqual(P.apply_text(once, fixes), once)

    def test_missing_anchor_fails(self):
        with self.assertRaisesRegex(P.PostConvertFixError, "חסר"):
            P.apply_text("טקסט אחר", [fix("לךאלא", "לך אלא")])

    def test_ambiguous_anchor_fails(self):
        with self.assertRaisesRegex(P.PostConvertFixError, "2 פעמים"):
            P.apply_text("לךאלא ושוב לךאלא", [fix("לךאלא", "לך אלא")])

    def test_multiline_fix(self):
        self.assertEqual(P.apply_text("א\nב\nב\nג", [fix("ב\nב\n", "ב\n")]), "א\nב\nג")


class LoadAndFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.src = self.dir.name
        P._cache.clear()

    def tearDown(self):
        self.dir.cleanup()
        P._cache.clear()

    def write_tsv(self, body):
        with open(os.path.join(self.src, P.FILE_NAME), "w", encoding="utf-8", newline="\n") as f:
            f.write("book\told\tnew\tnote\n" + body)

    def test_escapes_and_comments(self):
        self.write_tsv("# הערה\nספר\tא\\nב\tא ב\tקומיט\n")
        self.assertEqual(P.apply_book(self.src, "ספר.txt", "א\nב"), "א ב")
        self.assertEqual(P.apply_book(self.src, "ספר אחר", "א\nב"), "א\nב")

    def test_bad_rows_fail(self):
        for body in ("ספר\tא\n", "ספר\tא\tא\t\n", "ספר\tא\\x\tב\t\n"):
            P._cache.clear()
            self.write_tsv(body)
            with self.assertRaises(P.PostConvertFixError):
                P.fixes_for_source(self.src)

    def test_no_file_is_no_fixes(self):
        self.assertEqual(P.apply_book(self.src, "ספר", "טקסט"), "טקסט")

    def test_apply_file_and_check(self):
        self.write_tsv("ספר\tלךאלא\tלך אלא\t\n")
        books = os.path.join(self.src, "ספרים", "אוצריא", "הלכה")
        os.makedirs(books)
        path = os.path.join(books, "ספר.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("נותן לךאלא יאמר")
        self.assertEqual(P.check(self.src), ["%s:2: התיקון לא מוחל בספר שבמאגר" % os.path.join(self.src, P.FILE_NAME)])
        self.assertTrue(P.apply_file(self.src, path))
        self.assertFalse(P.apply_file(self.src, path))
        self.assertEqual(P.check(self.src), [])

    def test_check_includes_unsorted_books(self):
        self.write_tsv("ספר\tלךאלא\tלך אלא\t\n")
        books = os.path.join(self.src, "ספרים", "לא ממויין", "מקרא")
        os.makedirs(books)
        path = os.path.join(books, "ספר.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("נותן לךאלא יאמר")
        self.assertEqual(len(P.check(self.src)), 1)
        self.assertTrue(P.apply_file(self.src, path))
        self.assertEqual(P.check(self.src), [])

    def test_check_excludes_irrelevant_books(self):
        self.write_tsv("ספר\tלךאלא\tלך אלא\t\n")
        books = os.path.join(self.src, "ספרים", "לא רלוונטי", "מקרא")
        os.makedirs(books)
        path = os.path.join(books, "ספר.txt")
        with open(path, "w", encoding="utf-8") as f:
            # If this excluded copy were scanned, the already-fixed text would
            # make check() pass and conceal the missing real source book.
            f.write("נותן לך אלא יאמר")
        self.assertEqual(
            P.check(self.src),
            [f"{os.path.join(self.src, P.FILE_NAME)}:2: הספר 'ספר' נמצא 0 פעמים במקור"],
        )

    def test_books_roots_are_an_explicit_allowlist(self):
        expected = [
            os.path.join(self.src, "ספרים", "אוצריא"),
            os.path.join(self.src, "ספרים", "לא ממויין"),
            os.path.join(self.src, "ערוך", "ספרים", "אוצריא"),
            os.path.join(self.src, "ערוך", "ספרים", "לא ממויין"),
        ]
        for root in expected:
            os.makedirs(root)
        os.makedirs(os.path.join(self.src, "ספרים", "לא רלוונטי"))
        os.makedirs(os.path.join(self.src, "ערוך", "ספרים", "לא רלוונטי"))
        self.assertEqual(P.books_root(self.src), expected)


class SourceFiles(unittest.TestCase):
    def test_every_source_file_loads(self):
        files = glob.glob(os.path.join(REPO, "*", P.FILE_NAME))
        for path in files:
            with self.subTest(path=path):
                fixes = P.load(path)
                self.assertTrue(fixes)

    def test_jeremiah_fix_targets_the_packaged_orayta_copy(self):
        source = os.path.join(REPO, "OraytaToOtzaria")
        packaged = os.path.join(source, "ספרים", "אוצריא", "מקרא", "נביאים", "ירמיה.txt")
        excluded = os.path.join(source, "ספרים", "לא ממויין", "מקרא", "נביאים", "ירמיה.txt")
        self.assertTrue(os.path.isfile(packaged))
        self.assertFalse(os.path.exists(excluded))
        self.assertIn("ירמיה", P.fixes_for_source(source))
        self.assertEqual(P.check(source), [])


if __name__ == "__main__":
    unittest.main()
