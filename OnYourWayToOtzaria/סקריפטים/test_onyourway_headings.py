"""Heading levels in the OnYourWay converter (book/chap/p -> h1/h2/h3).

A first chap named like the book is skipped (it would duplicate h1), and the
p headings inside it are promoted to h2 so they don't jump from h1 to h3.
"""
import html as html_module
import importlib.util
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "onyourway_converter", os.path.join(_HERE, "ובלכתך_בדרך.py"))
conv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conv)


def headings(xml):
    html, title = conv.process_body_xml(xml)
    html = html_module.unescape(html)  # headings are inserted as text, as convert_file does
    return title, [(int(lvl), text) for lvl, text in re.findall(r"<h(\d)>(.*?)</h\d>", html)]


class HeadingLevelsTest(unittest.TestCase):
    def test_regular_chapters(self):
        title, hs = headings('<book n="Book"><chap n="C1"><p n="P1">x</p></chap></book>')
        self.assertEqual(title, "Book")
        self.assertEqual(hs, [(2, "C1"), (3, "P1")])

    def test_first_chap_named_like_book_is_skipped_and_its_p_promoted(self):
        _, hs = headings('<book n="Book"><chap n="Book"><p n="P1">x</p><p n="P2">y</p></chap>'
                         '<chap n="C2"><p n="P3">z</p></chap></book>')
        self.assertEqual(hs, [(2, "P1"), (2, "P2"), (2, "C2"), (3, "P3")])

    def test_later_chap_named_like_book_is_kept(self):
        _, hs = headings('<book n="Book"><chap n="C1"><p n="P1">x</p></chap>'
                         '<chap n="Book"><p n="P2">y</p></chap></book>')
        self.assertEqual(hs, [(2, "C1"), (3, "P1"), (2, "Book"), (3, "P2")])

    def test_p_directly_under_book_stays_h3(self):
        _, hs = headings('<book n="Book"><p n="P0">x</p></book>')
        self.assertEqual(hs, [(3, "P0")])

    def test_p_before_first_chap_stays_h3(self):
        _, hs = headings('<book n="Book"><p n="P0">x</p><chap n="Book"><p n="P1">y</p></chap></book>')
        self.assertEqual(hs, [(3, "P0"), (2, "P1")])

    def test_chap_nested_inside_skipped_chap(self):
        # Every p under the skipped chap is promoted, including those of a nested chap.
        _, hs = headings('<book n="Book"><chap n="Book"><p n="P1">x</p>'
                         '<chap n="Inner"><p n="P2">y</p></chap></chap></book>')
        self.assertEqual(hs, [(2, "P1"), (2, "Inner"), (2, "P2")])


class NormalizeCharsTest(unittest.TestCase):
    A, B = "\N{HEBREW LETTER AYIN}", "\N{HEBREW LETTER SHIN}"

    def test_gershayim(self):
        self.assertEqual(conv.normalize_chars(self.A + "''" + self.B), self.A + '"' + self.B)
        self.assertEqual(conv.normalize_chars(self.A + "'' " + self.B), self.A + "'' " + self.B)

    def test_opening_quote_after_a_prefix_letter_is_kept(self):
        q = "\N{HEBREW LETTER SHIN}''\N{HEBREW LETTER RESH}\N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH} \N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH}''"
        self.assertEqual(conv.normalize_chars(q), q)

    def test_invisibles_and_spaces(self):
        s = self.A + "\N{LEFT-TO-RIGHT MARK}\x9f\N{ZERO WIDTH JOINER}" + self.B + "\N{NO-BREAK SPACE} \t" + self.A
        self.assertEqual(conv.normalize_chars(s), self.A + self.B + " " + self.A)

    def test_zwj_before_a_point_kept(self):
        s = "\N{HEBREW LETTER VAV}\N{ZERO WIDTH JOINER}\N{HEBREW POINT HOLAM}"
        self.assertEqual(conv.normalize_chars(s), s)

    def test_newlines_kept(self):
        self.assertEqual(conv.normalize_chars("a\nb"), "a\nb")

    def test_symbol_font_arrow_mapped(self):
        self.assertEqual(conv.normalize_chars("a. \uf0ac b"), "a. \u2190 b")


if __name__ == "__main__":
    unittest.main()
