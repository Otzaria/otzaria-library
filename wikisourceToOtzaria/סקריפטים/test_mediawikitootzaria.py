"""בדיקות לבאגי ההמרה של mediawikitootzaria. הרצה: python test_mediawikitootzaria.py"""
import sys
import types
import unittest

# wikiexpand (תלוי ב-pywikibot) נדרש רק להרחבת תבניות עם template_dict, שהבדיקות לא משתמשות בה
if "wikiexpand" not in sys.modules:
    try:
        import wikiexpand  # noqa: F401
    except ImportError:
        _we = types.ModuleType("wikiexpand")
        _we.expand = types.ModuleType("wikiexpand.expand")
        _we.expand.ExpansionContext = object
        _we.expand.templates = types.ModuleType("wikiexpand.expand.templates")
        _we.expand.templates.TemplateDict = dict
        sys.modules.update({"wikiexpand": _we, "wikiexpand.expand": _we.expand,
                            "wikiexpand.expand.templates": _we.expand.templates})

from mediawikitootzaria import mediawikitohtml, templates  # noqa: E402

templates.replacement_dict = templates.wikisource_replacement_dict


def convert(wikitext: str) -> str:
    text = mediawikitohtml.media_wiki_list_to_html(wikitext)
    text = mediawikitohtml.wikitext_to_html(text)
    text, _ = templates.remove_templates(text)
    return mediawikitohtml.fix_new_lines(text)


class TestMediawikiToOtzaria(unittest.TestCase):
    def test_link_without_pipe_keeps_following_text(self):
        self.assertEqual(convert("[[א]] טקסט [[ב|ג]] סוף"), "א טקסט ג סוף")

    def test_piped_link_with_brackets_in_text(self):
        self.assertEqual(convert("([[ב/ג|(ס\"ט) [ס\"ח] ע\"ב]])"), "((ס\"ט) [ס\"ח] ע\"ב)")

    def test_line_break_template_survives(self):
        self.assertEqual(convert("שורה{{ש}}שורה"), "שורה<br>שורה")

    def test_indent_is_not_numbered_list(self):
        out = convert("פתיחה\n: פסקה א\n: פסקה ב\n:: פנימית")
        self.assertNotIn("<ol>", out)
        self.assertEqual(out.strip().split("\n"),["פתיחה", "פסקה א", "פסקה ב", "פנימית"])

    def test_numbered_and_bullet_lists_unchanged(self):
        self.assertIn("<ol>", convert("# א\n# ב"))
        self.assertIn("<ul>", convert("* א\n* ב"))

    def test_source_reference_gets_parentheses(self):
        self.assertEqual(convert("{{ממ|ב\"ק דף ב}}"), "(ב\"ק דף ב)")
        self.assertEqual(convert("א{{ממ|}}ב"), "אב")

    def test_font_and_colour_keep_only_text(self):
        self.assertEqual(convert("{{גופן|5|דרוגולין|'''כותרת'''}}"), "<b>כותרת</b>")
        self.assertEqual(convert("{{צבע גופן|אפור|הגה\"ה}}"), "הגה\"ה")

    def test_anchor_does_not_duplicate(self):
        self.assertEqual(convert("{{עוגן|אלא2|אלא}} כך"), "אלא כך")
        self.assertEqual(convert("{{עוגן|ב.}}נשרף"), "נשרף")

    def test_none_entry_is_dropped(self):
        self.assertEqual(convert("א {{כותרת רצה|טקסט}} ב"), "א  ב")
        self.assertEqual(convert("א {{ניווט ספר|קודם|הבא}} ב"), "א  ב")

    def test_unmapped_template_keeps_only_text(self):
        self.assertEqual(convert("{{תבנית לא מוכרת|5|גודל=3|טקסט}}"), "טקסט")

    def test_margin_note_is_marked(self):
        self.assertEqual(convert("א {{ביאור|הגהה}} ב"), "א <small>[הגהה]</small> ב")

    def test_footnote(self):
        text, notes = templates.remove_templates("א{{הערה|הערה ראשונה}} ב")
        self.assertEqual(text, 'א<sup style="color: gray;">1</sup> ב')
        self.assertEqual(notes, {1: "הערה ראשונה"})


    def test_footnote_with_equals_sign_keeps_text(self):
        _, notes = templates.remove_templates("א{{הערה|ראה שם a=b}} ב")
        self.assertEqual(notes, {1: "ראה שם a=b"})

    def test_multi_paragraph_margin_note_keeps_paragraphs(self):
        out = convert("א {{תוספת|x|פסקה א{{ש}}\n\nפסקה ב\n\nפסקה ג}} ב")
        self.assertEqual(out.strip().split("\n"),
                         ["א <small>[פסקה א</small>", "<small>פסקה ב</small>", "<small>פסקה ג]</small> ב"])

    def test_margin_note_single_paragraph(self):
        self.assertEqual(convert("א {{תוספת|x|טקסט}} ב"), "א <small>[טקסט]</small> ב")

    def test_piped_link_with_bracket_in_target(self):
        self.assertEqual(convert("א [[דף]ב/ג#ד|טקסט]] ב"), "א טקסט ב")


if __name__ == "__main__":
    unittest.main()
