import json
import tempfile
import unittest
from pathlib import Path

from linker.dibur_matcher import (
    LINK_ENTRY_KEYS,
    Line,
    MatchResult,
    apply_manual_overrides,
    assess_best_match,
    detect_super_commentary_opener,
    expand_abbreviations,
    extract_fresh_quote,
    load_manual_overrides,
    match_citing_book,
    normalize_book_title,
    self_check_super_commentary,
)


class TextNormalizationTests(unittest.TestCase):
    def test_common_abbreviations_expand_as_whole_tokens(self):
        text = expand_abbreviations('ה"נ דא"כ ב"ש')
        self.assertEqual(text, "הכא נמי דאם כן בית שמאי")

    def test_book_title_quote_variants_share_heref_lookup_key(self):
        self.assertEqual(normalize_book_title('רש"י על יבמות'), normalize_book_title('רש״י על יבמות'))

    def test_short_bold_quote_extends_to_colon(self):
        quote = extract_fresh_quote("<b>ותיפוק</b> לי' משום יבמה לשוק: פירוש")
        self.assertEqual(quote, "ותיפוק לי' משום יבמה לשוק")

    def test_bold_boundary_prevents_commentary_leak(self):
        quote = extract_fresh_quote("<b>לחברתה</b> <b>לעולם</b><b>:</b> הנה ביאור ארוך")
        self.assertEqual(quote, "לחברתה לעולם")

    def test_combined_bold_super_opener_is_visible(self):
        opener = detect_super_commentary_opener("<b>בתוס' ד\"ה פתיחה</b> ביאור", None)
        self.assertEqual(opener, ("tosafot", "פתיחה ביאור"))

    def test_plain_shem_before_combined_bold_super_opener_is_visible(self):
        opener = detect_super_commentary_opener('שם <b>ברש"י</b> ד"ה פתיחה', None)
        self.assertEqual(opener, ("rashi", "פתיחה"))


class ConfidenceTests(unittest.TestCase):
    def test_one_word_anchor_is_sent_to_review(self):
        candidates = [Line(10, None, "דף א.", "ותיפוק לי משום דודתו")]
        assessment = assess_best_match("ותיפוק", candidates)
        self.assertTrue(assessment.needs_review)
        self.assertIn("anchor has fewer than two informative tokens", assessment.review_reasons)

    def test_exact_multiword_lemma_can_be_auto_accepted(self):
        candidates = [Line(10, None, "דף א.", "נמי מותר בהחלט")]
        assessment = assess_best_match("נמי מותר בהחלט", candidates)
        self.assertFalse(assessment.needs_review)
        self.assertEqual(assessment.evidence, "exact_lemma")


class MatchingRegressionTests(unittest.TestCase):
    def test_shem_plus_short_bold_quote_uses_fresh_full_dibur(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            citing = root / "citing.txt"
            target = root / "target.txt"
            citing.write_text(
                '<h1>מפרש</h1>\n<h2>דף א.</h2>\n'
                '<b>גמרא</b> פתיחה מיוחדת:\n'
                '<b>שם</b> <b>ה"נ</b> אפשר: ביאור\n',
                encoding="utf-8",
            )
            target.write_text(
                '<h1>בסיס</h1>\n<h2>דף א.</h2>\n'
                'פתיחה מיוחדת\nהכא נמי אפשר\n',
                encoding="utf-8",
            )
            result = match_citing_book(str(citing), "בסיס", str(target))
            by_line = {entry["line_index_1"]: entry for entry in result.entries}
            self.assertEqual(by_line[4]["line_index_2"], 4)

    def test_bare_dh_typed_as_base_is_disclosed_for_semantic_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            citing = Path(tmp) / "citing.txt"
            citing.write_text(
                '<h1>מפרש</h1>\n<h2>דף א.</h2>\n<b>בד"ה</b> פתיחה: ביאור\n',
                encoding="utf-8",
            )
            entry = {
                "line_index_1": 3,
                "line_index_2": 3,
                "heRef_2": "בסיס א, א",
                "path_2": "בסיס.txt",
                "Conection Type": "commentary",
            }
            self.assertEqual(self_check_super_commentary(str(citing), [entry], set()), [3])


class OverrideTests(unittest.TestCase):
    def test_override_replaces_guess_and_clears_review_state(self):
        entry = {
            "line_index_1": 3,
            "line_index_2": 9,
            "heRef_2": "בסיס א, א",
            "path_2": "בסיס.txt",
            "Conection Type": "commentary",
        }
        result = MatchResult(
            entries=[{**entry, "line_index_2": 2}],
            low_confidence=[(3, "weak")],
            unresolved=[(3, "missing")],
            review_items=[{"line_index_1": 3}],
        )
        apply_manual_overrides(result, {3: entry}, citing_line_count=3)
        self.assertEqual(result.entries, [entry])
        self.assertEqual(result.low_confidence, [])
        self.assertEqual(result.unresolved, [])
        self.assertEqual(result.review_items, [])

    def test_override_file_requires_exact_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "overrides.json"
            path.write_text(json.dumps({"3": {"line_index_1": 3}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manual_overrides(str(path))
            self.assertEqual(len(LINK_ENTRY_KEYS), 5)


if __name__ == "__main__":
    unittest.main()
