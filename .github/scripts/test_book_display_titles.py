"""book_display_titles: the same titles as SeforimLibrary's BookDisplayTitles (Otzaria/otzaria#2766)."""
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import book_display_titles as bdt

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
TITLES = bdt.BookDisplayTitles.from_file(os.path.join(REPO_ROOT, bdt.ACRONYMS_PATH))


class DisplayTitleTest(unittest.TestCase):
    """The cases of OtzariaBookDisplayTitleTest.kt, same inputs and outputs."""

    def test_the_whole_heading_is_taken_when_it_is_the_stem_with_gershayim(self):
        self.assertEqual("שו״ת באר מרדכי", TITLES.display_title("שות באר מרדכי", 'שו"ת באר מרדכי'))
        self.assertEqual("מהר״ם שיק תרי״ג מצות חלק א",
                         TITLES.display_title("מהרם שיק תריג מצות חלק א", 'מהר"ם שיק תרי"ג מצות חלק א'))
        self.assertEqual("דרושי הצל״ח", TITLES.display_title("דרושי הצלח", "דרושי הצל”ח"))

    def test_acronym_words_of_the_heading_fill_their_words_of_the_stem(self):
        self.assertEqual("חידושי מהר״י מינץ", TITLES.display_title("חידושי מהרי מינץ", 'חידושים מהר"י מינץ'))
        # A quoted word of the heading is not an acronym.
        self.assertEqual("ספר שלום", TITLES.display_title("ספר שלום", '"שלום" ספר'))

    def test_curated_acronyms_fill_the_stem_without_evidence_in_the_book(self):
        self.assertEqual("דברי שאול עה״ת ומגילות", TITLES.display_title("דברי שאול עהת ומגילות", "דברי שאול"))
        self.assertEqual("חידושי הריטב״א על הש״ס", TITLES.display_title("חידושי הריטבא על השס", None))
        self.assertEqual("דבש תמר (פירוש המשניות להרמב״ם)",
                         TITLES.display_title("דבש תמר (פירוש המשניות להרמבם)", None))
        self.assertEqual("חידושי הר״ן על שבת [מיוחס להריטב״א]",
                         TITLES.display_title("חידושי הרן על שבת [מיוחס להריטבא]", 'חידושי הר"ן על שבת [מיוחס להריטבא]'))

    def test_curated_acronyms_also_fill_words_the_whole_heading_left_bare(self):
        self.assertEqual("שו״ת פני יצחק ח״ב", TITLES.display_title("שות פני יצחק חב", 'שות פני יצחק ח"ב'))

    def test_ambiguous_words_are_left_alone(self):
        for stem in ("קול הרמז", "שבות יעקב", "דעת תורה", "שי למורא", "מר דרור", "שולחן ערוך יוד",
                     "פירוש החסיד יעבץ על אבות"):
            with self.subTest(stem=stem):
                self.assertEqual(stem, TITLES.display_title(stem, None))

    def test_a_heading_that_changes_more_than_quote_marks_is_ignored(self):
        self.assertEqual("ספר חדש", TITLES.display_title("ספר חדש", 'ספר חדש מהר"ם'))
        # Its acronym words still apply one by one.
        self.assertEqual("שו״ת באר מרדכי", TITLES.display_title("שות באר מרדכי", 'שו"ת באר מרדכי השלם'))

    def test_the_title_only_ever_gains_quote_marks(self):
        self.assertTrue(bdt.only_adds_quote_marks("שו״ת א", "שות א"))
        self.assertTrue(bdt.only_adds_quote_marks('שו"ת א', "שות א"))
        self.assertFalse(bdt.only_adds_quote_marks("שו״ת ב", "שות א"))
        self.assertFalse(bdt.only_adds_quote_marks("שו״ת", "שות א"))
        # A mark the stem had must stay.
        self.assertFalse(bdt.only_adds_quote_marks("ר חיים", "ר' חיים"))
        # A curated form that is not the word plus gershayim never applies.
        self.assertEqual("שות א", bdt.BookDisplayTitles(["שו״תים"]).display_title("שות א", None))
        with self.assertRaises(ValueError):
            bdt.BookDisplayTitles(["שות"])


class FirstHeadingTest(unittest.TestCase):
    """Generator.firstHeadingOf: the first <h1> among the first ten lines, as plain text."""

    def heading(self, text, complete=True):
        return bdt.first_heading(bdt.first_lines(text.encode("utf-8"), complete=complete))

    def test_bom_tags_entities_footnotes_and_diacritics(self):
        line = ('﻿<h1>שו&quot;ת <b>בְּאֵר</b> מרדכי<sup class="footnote-marker">1</sup>'
                '<i class="footnote">הערה <i>פנימית</i></i></h1>\nשורה')
        self.assertEqual('שו"ת באר מרדכי', self.heading(line))

    def test_maqaf_whitespace_and_escaped_ampersand(self):
        self.assertEqual("בית־אל".replace("־", " ") + " &amp; עוד", self.heading("<H1>  בית־אל  & עוד </H1>"))

    def test_only_the_first_ten_lines_and_level_one(self):
        self.assertIsNone(self.heading("<h2>שו\"ת</h2>\n" + "שורה\n" * 9 + "<h1>מאוחר</h1>"))
        self.assertEqual("ראשון", self.heading("מחבר\r\n<h2>x</h2>\r<h1>ראשון</h1>\n<h1>שני</h1>"))

    def test_a_prefix_drops_its_unfinished_line(self):
        self.assertEqual(["א", "ב"], bdt.first_lines("א\nב\r\nג".encode("utf-8"), complete=False))
        self.assertEqual(["א"], bdt.first_lines("א\nב\r".encode("utf-8"), complete=False))
        self.assertEqual(["א", "ב", "ג"], bdt.first_lines("א\nב\r\nג".encode("utf-8")))


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True, capture_output=True).stdout.decode()


class HeadReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.invalid")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "commit.gpgsign", "false")
        self.path = "MoreBooks/ספרים/אוצריא/שות/שות באר מרדכי.txt"
        os.makedirs(os.path.join(self.root, os.path.dirname(self.path)))
        with open(os.path.join(self.root, self.path), "wb") as handle:
            handle.write('<h1>שו"ת באר מרדכי</h1>\nרבי מרדכי\n'.encode("utf-8"))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "x")
        self.cache = os.path.join(self.root, "heads.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_local_blobs_and_caches_them_by_blob_id(self):
        reader = bdt.HeadReader(self.root, cache_path=self.cache)
        titles = bdt.display_titles(self.root, "HEAD", [self.path, "MoreBooks/missing.txt"], reader)
        self.assertEqual({self.path: "שו״ת באר מרדכי"}, titles)
        self.assertEqual(1, reader.stats["local"])
        again = bdt.HeadReader(self.root, cache_path=self.cache)
        self.assertEqual({self.path: 'שו"ת באר מרדכי'}, again.headings("HEAD", [self.path]))
        self.assertEqual(1, again.stats["cached"])

    def test_a_missing_blob_is_read_by_range_until_its_heading_is_settled(self):
        data = ("מחבר\n" * 3 + '<h1>שו"ת באר מרדכי</h1>\n' + "טקסט\n" * 50).encode("utf-8")
        calls = []

        def fetch(url, size):
            calls.append((url, size))
            return data[:size], size >= len(data)

        reader = bdt.HeadReader(self.root, cache_path=self.cache, fetch_range=fetch)
        blobs = bdt.tree_blobs(self.root, "HEAD")
        oid = blobs[self.path]
        reader._http_sources = lambda ref, tree: [("owner/repo", "c0ffee", lambda: blobs)]
        with patch.object(bdt, "RANGE_START", 16):
            self.assertEqual([], reader._read_http("HEAD", blobs, {self.path: oid}, [oid]))
        self.assertEqual('שו"ת באר מרדכי', reader.cache[oid])
        self.assertEqual([16, 128], [size for _url, size in calls])
        self.assertTrue(calls[0][0].startswith("https://raw.githubusercontent.com/owner/repo/c0ffee/MoreBooks/"))

    def test_a_source_whose_tree_holds_another_blob_is_not_asked(self):
        reader = bdt.HeadReader(self.root, cache_path=self.cache, fetch_range=lambda url, size: self.fail(url))
        blobs = bdt.tree_blobs(self.root, "HEAD")
        oid = blobs[self.path]
        reader._http_sources = lambda ref, tree: [("owner/repo", "c0ffee", lambda: {self.path: "0" * 40})]
        self.assertEqual([oid], reader._read_http("HEAD", blobs, {self.path: oid}, [oid]))


class AcronymsFileTest(unittest.TestCase):
    """ForDB/title_acronyms.txt is shared with the generator; an ordinary word in it renames books."""

    AMBIGUOUS = ("שבות", "הרמז", "דעת", "שי", "מר", "יוד", "יעבץ", "מהראש")

    def entries(self):
        with open(os.path.join(REPO_ROOT, bdt.ACRONYMS_PATH), encoding="utf-8") as handle:
            lines = [line.strip() for line in handle.read().splitlines()]
        return [line for line in lines if line and not line.startswith("#")]

    def test_every_entry_is_one_hebrew_word_with_gershayim_before_its_last_letter(self):
        entries = self.entries()
        self.assertGreater(len(entries), 10)
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertRegex(entry, "^[א-ת]+״[א-ת]$")

    def test_no_duplicates_and_no_ambiguous_word(self):
        bare = [bdt.strip_quote_marks(entry) for entry in self.entries()]
        self.assertEqual(len(bare), len(set(bare)))
        for word in self.AMBIGUOUS:
            with self.subTest(word=word):
                self.assertNotIn(word, bare)

    def test_it_ships_at_the_root_of_the_fordb_archive(self):
        import fordb_archive
        self.assertIn("ForDB/title_acronyms.txt", fordb_archive.SHIPPED)
        if os.path.isdir(os.path.join(REPO_ROOT, "ForDB")):
            from pathlib import Path
            self.assertIn("ForDB/title_acronyms.txt", fordb_archive.archive_paths(Path(REPO_ROOT)))


if __name__ == "__main__":
    unittest.main()
