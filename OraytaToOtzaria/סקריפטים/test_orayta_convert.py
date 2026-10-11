"""replace_editor_comments: a ")" at the end of an editor comment stays in the text only when it
closes a parenthesis that the text opened and does not close by itself."""
import re
import unittest

from orayta_convert import norm_chars, replace_editor_comments, text_escape


def comment(body):
    return f'<span class="c">\rYeshayahu Hollander\r2020-01-01T00:00:00{body}</span>'


def run(text):
    return re.sub(r"<[^<>]*>", "", replace_editor_comments(text, []))


class EditorCommentParenTest(unittest.TestCase):
    def test_closing_paren_kept_for_open_paren(self):
        self.assertEqual(run("a (b" + comment("english note.)") + " c"), "a (b.) c")

    def test_stray_close_earlier_does_not_hide_open_paren(self):
        # a stray ")" earlier in the paragraph used to balance the count and drop the real one
        self.assertEqual(run("x) y (b" + comment("note)") + " c"), "x) y (b) c")

    def test_balanced_text_drops_comment_paren(self):
        self.assertEqual(run("a (b) c" + comment("note)") + " d"), "a (b) c d")

    def test_text_closing_after_comment_keeps_comment_paren_out(self):
        text = "a (b" + comment("note (M. K)") + ")</span> c"
        self.assertEqual(run(text), "a (b) c")


class NormCharsTest(unittest.TestCase):
    def test_junk_invisibles_removed(self):
        for ch in ("\N{ZERO WIDTH SPACE}", "\N{LEFT-TO-RIGHT MARK}", "\N{RIGHT-TO-LEFT MARK}",
                   "\N{POP DIRECTIONAL FORMATTING}", "\N{ZERO WIDTH NO-BREAK SPACE}", "\N{SOFT HYPHEN}", "\x02"):
            self.assertEqual(norm_chars(f"\N{HEBREW LETTER ALEF}{ch}\N{HEBREW LETTER BET}"),
                             "\N{HEBREW LETTER ALEF}\N{HEBREW LETTER BET}")

    def test_zwj_kept_only_before_a_point(self):
        self.assertEqual(norm_chars("\N{HEBREW LETTER VAV}\N{ZERO WIDTH JOINER}\N{HEBREW LETTER VAV}"),
                         "\N{HEBREW LETTER VAV}\N{HEBREW LETTER VAV}")
        s = "\N{HEBREW LETTER VAV}\N{ZERO WIDTH JOINER}\N{HEBREW POINT HOLAM}"
        self.assertEqual(norm_chars(s), s)

    def test_symbol_font_private_use_mapped(self):
        self.assertEqual(norm_chars("a. \uf0acb \uf047,"), "a. \u2190b \u0393,")

    def test_odd_spaces_collapse_to_one_space(self):
        self.assertEqual(norm_chars("a\N{EM SPACE}\N{EM SPACE} b\tc\N{NO-BREAK SPACE}d"), "a b c d")
        self.assertEqual(norm_chars("a  b"), "a  b")

    def test_double_apostrophe_becomes_gershayim(self):
        self.assertEqual(text_escape("\N{HEBREW LETTER AYIN}''\N{HEBREW LETTER SHIN}"),
                         '\N{HEBREW LETTER AYIN}"\N{HEBREW LETTER SHIN}')


if __name__ == "__main__":
    unittest.main()
