# -*- coding: utf-8 -*-
"""Offline contract tests for the ForDB name validator.

The audited cycle (33987355439) shipped seven warning lines every run:
three `book_renames.csv` rows that never matched a book, and thirteen
`generations.csv` titles skipped by `SeedGenerations`.  All of them passed
`validate_fordb_book_names.py` because every check there compares in the
*sanitized* space (`sanitize_title` deletes quotes), while the real consumers
(`applyGenerations`, `renameBookTitle`, `applyMetadata`) compare `book.title`
with an exact string equality.  These tests pin the two checks that close that
gap, and run entirely offline: no Sefaria API, no seforim.db.
"""

import json
import os
import unittest

import validate_fordb_book_names as validator


GERESH = "׳"
GERSHAYIM = "״"


class DbTitleTest(unittest.TestCase):
    """`db_title` must mirror Generator.normalizeHebrewLabel + normalizeBookTitle."""

    def test_quote_forms_fold_to_gershayim(self):
        cases = {
            'הגהות הב"ח על מסכת ברכות': "הגהות הב" + GERSHAYIM + "ח על מסכת ברכות",
            "חידושי ופירושי מהרי''ק": "חידושי ופירושי מהרי" + GERSHAYIM + "ק",
            "נר שמואל ח" + GERESH + GERESH + "א": "נר שמואל ח" + GERSHAYIM + "א",
            "מדרש אלפ''א ביתו''ת": "מדרש אלפ" + GERSHAYIM + "א ביתו" + GERSHAYIM + "ת",
        }
        for raw, expected in cases.items():
            self.assertEqual(validator.db_title(raw), expected, raw)

    def test_curly_quotes_and_backtick_are_normalized(self):
        self.assertEqual(validator.db_title("תוספות רי”ד"), "תוספות רי" + GERSHAYIM + "ד")
        self.assertEqual(validator.db_title("ר’ סעדיה"), "ר' סעדיה")
        self.assertEqual(validator.db_title("ר`ן"), "ר" + GERESH + "ן")

    def test_whitespace_is_collapsed_and_trimmed(self):
        self.assertEqual(validator.db_title("  ראש יוסף על  ברכות "), "ראש יוסף על ברכות")

    def test_non_ascii_whitespace_survives_the_collapse(self):
        """Kotlin's `"\\s+".toRegex()` is java.util.regex without
        UNICODE_CHARACTER_CLASS, so it never matches NBSP.  A Unicode-aware `\\s`
        here would invent a title the generator cannot produce, and
        `find_spelling_drift` would then demand a spelling the DB cannot hold."""
        nbsp = "\u00a0"
        self.assertEqual(validator.db_title("שער" + nbsp + "המלך"), "שער" + nbsp + "המלך")
        # ASCII runs on either side still collapse; the NBSP between them does not.
        self.assertEqual(
            validator.db_title("שער  " + nbsp + "  המלך"), "שער " + nbsp + " המלך"
        )
        # Kotlin's trim() (isWhitespace || isSpaceChar) and Python's strip() both do
        # treat NBSP as an edge space, so the two agree there and nothing is needed.
        self.assertEqual(validator.db_title(nbsp + "שער המלך" + nbsp), "שער המלך")

    def test_tanakh_special_case(self):
        self.assertEqual(validator.db_title("תנך"), "תנ" + GERSHAYIM + "ך")
        self.assertEqual(validator.db_title('תנ"ך'), "תנ" + GERSHAYIM + "ך")

    def test_gershayim_and_geresh_survive_untouched(self):
        # normalizeHebrewLabel does NOT strip Hebrew punctuation - unlike
        # sanitize_title, which builds the file name.
        title = "הגהות הגרי" + GERSHAYIM + "ב על אבות דרבי נתן"
        self.assertEqual(validator.db_title(title), title)
        self.assertNotEqual(validator.sanitize_title(title), title)


class SpellingDriftTest(unittest.TestCase):
    def setUp(self):
        self.packaged = {
            validator.sanitize_title("הגהות הב" + GERSHAYIM + "ח על מסכת ברכות"): {
                "הגהות הב" + GERSHAYIM + "ח על מסכת ברכות"
            },
            validator.sanitize_title("נר שמואל ח" + GERSHAYIM + "א"): {"נר שמואל ח" + GERSHAYIM + "א"},
            "ambiguous": {"א", "ב"},
        }

    def test_ascii_quote_spelling_is_reported_with_the_required_form(self):
        drift = validator.find_spelling_drift(
            [("שורה 1303", 'הגהות הב"ח על מסכת ברכות')], self.packaged
        )
        self.assertEqual(
            drift,
            [("שורה 1303", 'הגהות הב"ח על מסכת ברכות', "הגהות הב" + GERSHAYIM + "ח על מסכת ברכות")],
        )

    def test_exact_spelling_is_accepted(self):
        entries = [("שורה 1", "נר שמואל ח" + GERSHAYIM + "א")]
        self.assertEqual(validator.find_spelling_drift(entries, self.packaged), [])

    def test_unknown_and_empty_names_are_ignored(self):
        entries = [("שורה 1", "ספר שאינו בספרייה"), ("שורה 2", ""), ("שורה 3", None)]
        self.assertEqual(validator.find_spelling_drift(entries, self.packaged), [])

    def test_ambiguous_keys_are_skipped(self):
        # Two packaged files with the same sanitized key: the required spelling is
        # not knowable, and find_packaged_duplicates already reports the collision.
        self.assertEqual(validator.find_spelling_drift([("x", "ambiguous")], self.packaged), [])


class DeadRenameTest(unittest.TestCase):
    # The exact strings from the audited run: the ForDB source lost the gershayim
    # of רד"ק when Sefaria's punctuated heTitle became the book title.
    STALE_SOURCE = "רדק על דברי הימים א" + GERESH
    LIVE_TITLE = 'רד"ק על דברי הימים א' + GERESH

    def test_punctuation_only_variant_is_reported_as_dead(self):
        dead = validator.find_dead_renames(
            [(2, self.STALE_SOURCE, "רדק על דברי הימים א")], {self.LIVE_TITLE}
        )
        self.assertEqual(dead, [(2, self.STALE_SOURCE, "רדק על דברי הימים א", self.LIVE_TITLE)])

    def test_live_source_is_accepted(self):
        pairs = [(5, "חומת אנך על דברי הימים א'", "חומת אנך על דברי הימים א")]
        self.assertEqual(validator.find_dead_renames(pairs, {"חומת אנך על דברי הימים א'"}), [])

    def test_already_applied_rename_is_accepted(self):
        pairs = [(5, "חומת אנך על דברי הימים א'", "חומת אנך על דברי הימים א")]
        self.assertEqual(validator.find_dead_renames(pairs, {"חומת אנך על דברי הימים א"}), [])

    def test_a_partial_title_list_never_accuses(self):
        # No variant to name => stay silent. SEFARIA_FETCH=0 leaves only the
        # packaged Otzaria titles, and a partial list must not invent failures.
        self.assertEqual(validator.find_dead_renames([(2, self.STALE_SOURCE, "x")], set()), [])


class RepositoryForDbTest(unittest.TestCase):
    """The committed ForDB inputs, against the committed book tree."""

    @classmethod
    def setUpClass(cls):
        cls.packaged = validator.packaged_db_titles()

    def test_the_book_tree_is_visible(self):
        # git ls-tree reads the commit, so this holds on a sparse/blobless checkout.
        self.assertGreater(len(self.packaged), 1000)

    def test_book_renames_use_the_packaged_spelling(self):
        pairs = validator.load_rename_pairs()
        entries = [(f"שורה {line} (מקור)", old) for line, old, _new in pairs]
        entries += [(f"שורה {line} (יעד)", new) for line, _old, new in pairs]
        self.assertEqual(validator.find_spelling_drift(entries, self.packaged), [])

    def test_generations_titles_use_the_packaged_spelling(self):
        header, rows = validator.read_csv_rows(validator.GENERATIONS, has_header=True)
        index = validator.col_index(header, "שם ספר")
        entries = [
            (f"שורה {line}", row[index]) for line, row in enumerate(rows, start=2) if len(row) > index
        ]
        self.assertEqual(validator.find_spelling_drift(entries, self.packaged), [])

    def test_book_moves_use_the_packaged_spelling(self):
        header, rows = validator.read_csv_rows(validator.BOOK_MOVES, has_header=True)
        index = validator.col_index(header, "name")
        entries = [
            (f"שורה {line}", row[index]) for line, row in enumerate(rows, start=2) if len(row) > index
        ]
        self.assertEqual(validator.find_spelling_drift(entries, self.packaged), [])

    def test_fordb_metadata_uses_the_packaged_spelling(self):
        records = validator.read_json(validator.FORDB_METADATA)
        entries = [(f"רשומה {idx}", entry.get("title")) for idx, entry in enumerate(records)]
        self.assertEqual(validator.find_spelling_drift(entries, self.packaged), [])

    def test_no_rename_is_dead_against_the_packaged_titles(self):
        # Offline half of check 8: a rename of an *Otzaria* book must name a real
        # packaged title. Sefaria-side rows need the live catalogue and are skipped
        # here by construction (find_dead_renames stays silent without a variant).
        titles = set()
        for candidates in self.packaged.values():
            titles |= candidates
        self.assertEqual(validator.find_dead_renames(validator.load_rename_pairs(), titles), [])


class PackagedRootsContractTest(unittest.TestCase):
    """DB_BOOK_PREFIXES must stay equal to the roots that build otzaria_latest.zip."""

    def test_db_book_prefixes_match_manual_links_packaging(self):
        packaging = os.path.join(validator.REPO_ROOT, "manual_links_packaging.py")
        if not os.path.exists(packaging):
            self.skipTest("manual_links_packaging.py is outside the workflow's sparse checkout")
        namespace = {}
        with open(packaging, encoding="utf-8") as handle:
            source = handle.read()
        start = source.index("BOOK_ROOTS = (")
        end = source.index(")", start) + 1
        exec(compile(source[start:end], packaging, "exec"), namespace)  # noqa: S102
        self.assertEqual(
            tuple(root + "/" for root in namespace["BOOK_ROOTS"]),
            validator.DB_BOOK_PREFIXES,
        )

    def test_the_dicta_side_archive_is_excluded(self):
        # otzaria_dicta_latest.zip (DictaToOtzaria/לא ערוך) is a separate release
        # asset; manual-generate-release downloads only the asset named in
        # otzaria_release_provenance.json, so those books never reach the DB.
        self.assertTrue(any(p.startswith("DictaToOtzaria/לא ערוך/") for p in validator.PACKAGED_PREFIXES))
        self.assertFalse(any(p.startswith("DictaToOtzaria/לא ערוך/") for p in validator.DB_BOOK_PREFIXES))


class SanitizeStillMatchesFileNamesTest(unittest.TestCase):
    """sanitize_title keeps its old job: matching, not spelling."""

    def test_sanitize_is_quote_insensitive_but_db_title_is_not(self):
        ascii_form = 'הגהות הב"ח על מסכת ברכות'
        hebrew_form = "הגהות הב" + GERSHAYIM + "ח על מסכת ברכות"
        self.assertEqual(validator.sanitize_title(ascii_form), validator.sanitize_title(hebrew_form))
        self.assertNotEqual(validator.db_title(ascii_form), ascii_form)
        self.assertEqual(validator.db_title(ascii_form), hebrew_form)


if __name__ == "__main__":
    unittest.main()
