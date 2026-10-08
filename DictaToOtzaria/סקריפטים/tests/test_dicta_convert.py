# -*- coding: utf-8 -*-
"""בדיקות לממיר דיקטה → אוצריא (dicta_convert.py) ולניקוי (dicta_clean.py).

הרצה (מכל תיקייה):
    python3 -m unittest discover -s "DictaToOtzaria/סקריפטים/tests" -v
    # או: python3 -m pytest "DictaToOtzaria/סקריפטים/tests"
ללא רשת וללא תלויות חיצוניות.
"""
import io
import os
import sys
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import dicta_convert as DC  # noqa: E402
import dicta_clean as CL    # noqa: E402

HEAD = "<html><head><meta charset='utf-8'></head><body dir='rtl'>"
TAIL = "</body></html>"


def span(text, *cls):
    if cls:
        return f'<span class="{" ".join(cls)}">{text}</span>'
    return f"<span>{text}</span>"


def new_page(*items):
    """פורמט library-1-0: items = (word, classes...) ; רווח בין מילים אוטומטי.

    ("~", ...) = רווח מפורש עם מחלקות (רווח מודגש בין מילים מודגשות).
    """
    out = []
    for i, it in enumerate(items):
        word, cls = it[0], it[1:]
        if word == "~":
            out.append(span(" ", *cls))
            continue
        out.append(span(word, *cls))
        nxt = items[i + 1][0] if i + 1 < len(items) else None
        if nxt not in ("~", None):
            out.append(span(" "))
    return HEAD + "".join(out) + TAIL


def old_page(spans_):
    """פורמט ישן: רשימת (text, classes) כפי שהם, עם class="" לריקים."""
    return HEAD + "".join(
        f'<span class="{" ".join(c)}">{t}</span>' for t, *c in spans_) + TAIL


def body(text):
    return text.split("\n")


class NewFormatSegmentation(unittest.TestCase):
    def test_paragraph_only_at_marked_paragraph(self):
        page = new_page(("אמר", "marked-paragraph"), ("רבא",), ("כך",),
                        ("והלכה", "marked-paragraph"), ("כמותו",))
        out = DC.convert_pages([page])
        self.assertEqual(out, "אמר רבא כך\nוהלכה כמותו\n")

    def test_bold_mid_paragraph_is_not_a_break(self):
        # באג 1: כל רצף מודגש פתח שורה חדשה
        page = new_page(("כמו", "marked-paragraph"), ("שכתב",), ("כסף", "bold"),
                        ("~", "bold"), ("משנה", "bold"), ("שם",), ("בפרק",))
        out = DC.convert_pages([page])
        self.assertEqual(out, "כמו שכתב <b>כסף משנה</b> שם בפרק\n")

    def test_bold_space_joins_run_nonbold_space_splits(self):
        page = HEAD + span("סימן", "bold", "marked-paragraph") + span(" ", "bold") \
            + span("א", "bold") + span(" ") + span("תוס'", "bold") + span(" ") \
            + span('ד"ה', "bold") + span(" ") + span("טקסט") + TAIL
        out = DC.convert_pages([page])
        self.assertEqual(out, "<b>סימן א</b> <b>תוס'</b> <b>ד\"ה</b> טקסט\n")

    def test_heading_is_own_line_h2_no_big(self):
        # באג 2: heading → <big> לכל מילה, ונדבק לשורה הקודמת
        page = new_page(("סוף", "marked-paragraph"), ("דבר.",),
                        ("סימן", "heading", "bold"), ("א", "heading"),
                        ("שאלה", "marked-paragraph"), ("היא",))
        out = DC.convert_pages([page])
        self.assertEqual(out, "סוף דבר.\n<h2>סימן א</h2>\nשאלה היא\n")
        self.assertNotIn("<big>", out)

    def test_heading_mid_sentence_becomes_inline_bold(self):
        # שם באות גדולה בתוך משפט ("…הגאון הגדול הרד"ד זצ"ל…") אינו כותרת
        page = new_page(("חיבור", "marked-paragraph"), ("הגאון",), ('הרד"ד', "heading"),
                        ('זצ"ל',), ("מלאסק", "heading"), ("שחיבר",), ("ספרים.",),
                        ("סימן", "heading", "marked-paragraph"), ("א", "heading"), ("שאלה",))
        self.assertEqual(DC.convert_pages([page]),
                         'חיבור הגאון <b>הרד"ד</b> זצ"ל <b>מלאסק</b> שחיבר ספרים.\n'
                         "<h2>סימן א</h2>\nשאלה\n")
        off = DC.ConvertOptions(inline_headings=False)
        self.assertIn('<h2>הרד"ד</h2>', DC.convert_pages([page], options=off))

    def test_heading_tag_none_keeps_plain_line(self):
        page = new_page(("סימן", "heading"), ("א", "heading"), ("שאלה",))
        out = DC.convert_pages([page], options=DC.ConvertOptions(heading_tag=None))
        self.assertEqual(out, "סימן א שאלה\n")

    def test_colon_quote_not_split_when_bold_lemma(self):
        # באג 3: כל ": " הפך לירידת שורה. עכשיו: לא בתוך למה מודגשת
        page = new_page(("מחצלת:", "bold", "marked-paragraph"), ("עשויה",), ("מחלף",))
        self.assertEqual(DC.convert_pages([page]), "<b>מחצלת:</b> עשויה מחלף\n")

    def test_colon_not_split_after_quote_intro_parens_or_inside_bold(self):
        # ": " שאינו סוף עניין נשאר באותה שורה (אותם כללים כמו colon_newline)
        quote = new_page(("וכתב", "marked-paragraph"), ('וז"ל:',), ("אין.",), ('עכ"ל',), ("ומה",))
        self.assertEqual(DC.convert_pages([quote]), 'וכתב וז"ל: אין. עכ"ל ומה\n')
        long_quote = new_page(("וכתב", "marked-paragraph"), ('וז"ל:',), ("אין",), ("לומר",))
        self.assertEqual(DC.convert_pages([long_quote]), 'וכתב וז"ל:\nאין לומר\n')
        dibbur = new_page(("ברור:", "marked-paragraph"), ('ד"ה',), ("ומה",))
        self.assertEqual(DC.convert_pages([dibbur]), 'ברור:\nד"ה ומה\n')
        paren = new_page(("כדאיתא", "marked-paragraph"), ("(שבת",), ("קיט:",), ('ד"ה',), ("ומה)",))
        self.assertEqual(DC.convert_pages([paren]), 'כדאיתא (שבת קיט: ד"ה ומה)\n')
        bold = new_page(("מחצלת:", "bold", "marked-paragraph"), ("עשויה", "bold"), ("מחלף",))
        self.assertEqual(DC.convert_pages([bold]).count("\n"), 1)

    def test_colon_end_of_matter_splits(self):
        page = new_page(("והוא", "marked-paragraph"), ("פשוט:",), ("ומה",), ("שהקשה",))
        self.assertEqual(DC.convert_pages([page]), "והוא פשוט:\nומה שהקשה\n")
        off = DC.ConvertOptions(split_colon=False)
        self.assertEqual(DC.convert_pages([page], options=off), "והוא פשוט: ומה שהקשה\n")

    def test_period_then_bold_splits(self):
        page = new_page(("בשם", "marked-paragraph"), ('ר"ת.',), ("דין", "bold"),
                        ("~", "bold"), ("אם", "bold"), ("נכתב",))
        self.assertEqual(DC.convert_pages([page]), 'בשם ר"ת.\n<b>דין אם</b> נכתב\n')

    def test_paragraph_continues_across_pages(self):
        p1 = new_page(("תחילת", "marked-paragraph"), ("המשפט",))
        p2 = new_page(("וסופו",), ("כאן.",))
        self.assertEqual(DC.convert_pages([p1, p2]), "תחילת המשפט וסופו כאן.\n")

    def test_page_starting_with_paragraph(self):
        p1 = new_page(("א.", "marked-paragraph"))
        p2 = new_page(("ב.", "marked-paragraph"))
        self.assertEqual(DC.convert_pages([p1, p2]), "א.\nב.\n")

    def test_marked_paragraph_on_space_ignored(self):
        page = HEAD + span("חלק", "heading", "bold") + span(" ", "bold", "marked-paragraph") \
            + span("יורה", "heading", "bold") + span(" ") + span("דעה", "heading") + TAIL
        self.assertEqual(DC.convert_pages([page]), "<h2>חלק יורה דעה</h2>\n")

    def test_entities_and_raw_lt(self):
        page = HEAD + span("א&amp;ב", "marked-paragraph") + span(" ") + span("דחמ<") \
            + span(" ") + span("סוף") + TAIL
        out = DC.convert_pages([page])
        self.assertEqual(out, "א&ב דחמ&lt; סוף\n")
        self.assertNotIn("&amp;", out)

    def test_invisible_chars_removed(self):
        page = new_page(("א‏ב", "marked-paragraph"), ("ג ד",))
        self.assertEqual(DC.convert_pages([page]), "אב ג ד\n")

    def test_header_lines_strip_display_name(self):
        page = new_page(("טקסט", "marked-paragraph"))
        out = DC.convert_pages([page], {"displayName": "שם הספר  ", "author": " מחבר "})
        self.assertEqual(out, "<h1>שם הספר</h1>\nמחבר\nטקסט\n")

    def test_flagged_sidecar(self):
        page = new_page(("אמר", "marked-paragraph"), ("רבה", "flagged", "edited"), ("כך",))
        res = DC.convert_book([page])
        self.assertEqual(res.text, "אמר רבה כך\n")
        self.assertEqual(res.flagged[0]["text"], "רבה")
        self.assertEqual(res.flagged[0]["line"], 1)
        self.assertEqual(res.flagged[0]["word"], 1)
        self.assertTrue(res.flagged[0]["edited"])

    def test_adjacent_spans_join_like_dicta_tokens(self):
        # "בעלי הנפש" / "יונת אלם": span ערוך עם רווח מוביל ובלי רווח אחריו. דיקטה עצמה
        # (ה־JSON של הדף וייצוא הטקסט) מציגה "ביןמטה" ו"שבה"א" — מילה אחת. הממיר לא
        # ממציא ולא מוחק רווחים: גבול span אינו גבול מילה.
        page = HEAD + span("לכתתיהן", "flagged", "edited", "marked-paragraph") \
            + span(" בין", "flagged", "edited") + span("מטה", "flagged") + span(" ") \
            + span("כי") + span(" ") + span("א'") + span(" ") + span("שב", "flagged", "edited") \
            + span("ה", "edited") + span('"א', "edited") + span(" ") + span("ראשונ'") + TAIL
        res = DC.convert_book([page])
        self.assertEqual(res.text, "לכתתיהן ביןמטה כי א' שבה\"א ראשונ'\n")
        # הניקוי משנה רק דרך כלל ה־OCR S ("ביןמטה" → "בין מטה", אות סופית באמצע מילה)
        self.assertIn(DC.finalize_text(res.text),
                      (res.text, res.text.replace("ביןמטה", "בין מטה")))

    def test_no_line_break_inside_a_word(self):
        # 156 ספרים: שורה נשברה בין שני spans צמודים — "אול" / "[א]ם", "השברים:" / ")**",
        # "י" / "תפאר" (כותרת) — ופיצלה מילה. בלי רווח ביניהם אין שבירה.
        page = HEAD + span("ראה", "marked-paragraph") + span(" ") + span("אול") \
            + span("[א]ם", "marked-paragraph") + span(" ") + span("השברים:") + span(")**") \
            + span(" ") + span("י", "heading") + span("תפאר") + span(" ") + span("סוף.") + TAIL
        out = DC.convert_pages([page])
        # הסימון על "[א]ם" המודבק פותח פסקה לפני המילה כולה
        self.assertEqual(out, "ראה\nאול[א]ם השברים:)** <b>י</b>תפאר סוף.\n")

    def test_paragraph_mark_on_glued_span_breaks_before_whole_word(self):
        # QA 3: "(" + "א)"[P] — הפסקה נבלעה; עכשיו השבירה לפני "(א)"
        page = HEAD + span("סוף.") + span(" ") + span("(") + span("א)", "marked-paragraph") \
            + span(" ") + span("התחלה") + TAIL
        self.assertEqual(DC.convert_pages([page]), "סוף.\n(א) התחלה\n")

    def test_structural_heading_mid_sentence_stays_heading(self):
        # QA 4: "…פרק עשירי פרק אחד עשר הזורק דף צו…" — כותרת אמיתית, לא הדגשה
        page = new_page(("סוף", "marked-paragraph"), ("פרק",), ("עשירי",), ("פרק", "heading"),
                        ("אחד", "heading"), ("עשר", "heading"), ("הזורק",), ("דף",))
        self.assertIn("<h2>פרק אחד עשר</h2>", DC.convert_pages([page]))

    def test_words_are_preserved_exactly(self):
        words = ["כ\"ז", "(דף", "ט\"ז),", "וא\"כ", "[נ\"ח]", "קשה:", "ועוד", "יש", "לומר."]
        items = [(words[0], "marked-paragraph")] + [(w,) for w in words[1:4]] \
            + [(words[4], "bold")] + [(w,) for w in words[5:]]
        out = DC.convert_pages([new_page(*items)])
        import re
        self.assertEqual(re.sub(r"<[^>]+>", " ", out).split(), words)


class OldFormatSegmentation(unittest.TestCase):
    def test_run_start_is_paragraph_and_trailing_newline_is_not(self):
        # השורה המודפסת הראשונה מסומנת כולה; \n בסוף השורה אינו פסקה
        spans_ = [("סוף", ""), (". ", ""),
                  ("ב", "marked-paragraph"), (") ", "marked-paragraph"),
                  ("מיני", "bold", "marked-paragraph"), (" ", "marked-paragraph"),
                  ("החיובים", "bold", "marked-paragraph"), (", ", "marked-paragraph"),
                  ("כמה", "marked-paragraph"), ("\n", ""),
                  ("מיני", ""), (" ", ""), ("חיובים", ""), (" ", ""), ("יש", ""), (". ", "")]
        res = DC.convert_book([old_page(spans_)])
        self.assertEqual(res.fmt, "line")
        self.assertEqual(res.text, "סוף.\nב) <b>מיני החיובים</b>, כמה מיני חיובים יש.\n")

    def test_newline_inside_run_starts_new_paragraph(self):
        # פסקה של שורה אחת (כותרת) ואחריה פסקה חדשה, באותו רצף מסומן
        spans_ = [("פרשת", "heading", "marked-paragraph"), (" ", "heading", "marked-paragraph"),
                  ("נח", "heading", "marked-paragraph"), ("\n", ""),
                  ("כי", "bold", "marked-paragraph"), (" ", "marked-paragraph"),
                  ("השחית", "marked-paragraph"), (" ", "marked-paragraph"),
                  ("כל", "marked-paragraph"), ("\n", ""), ("בשר", ""), (". ", "")]
        res = DC.convert_book([old_page(spans_)], options=DC.ConvertOptions(heading_tag=None))
        self.assertEqual(res.text, "פרשת נח\n<b>כי</b> השחית כל בשר.\n")

    def test_old_format_no_paragraph_inside_parentheses(self):
        # QA 2: " (" מסומן, "ע\"ב" מודבק ולא מסומן, ואחריו "ד\"ה)" מסומן — פסקה נפתחה בתוך הסוגריים
        spans_ = [("סוף", ""), (" ", ""), ("קודם", ""), (" (", "marked-paragraph"), ('ע"ב', ""),
                  (" ", "marked-paragraph"), ('ד"ה)', "marked-paragraph"), (" ", "marked-paragraph"),
                  ("מילה", "marked-paragraph"), (" ", "marked-paragraph"), ("שניה", "marked-paragraph"),
                  (" ", "marked-paragraph"), ("שלישית", "marked-paragraph"), ("\n", ""), ("המשך.", "")]
        out = DC.convert_pages([old_page(spans_)], options=DC.ConvertOptions(fmt="line"))
        self.assertEqual(out, 'סוף קודם\n(ע"ב ד"ה) מילה שניה שלישית המשך.\n')

    def test_old_format_bold_words_merge_without_bold_space(self):
        spans_ = [("א", "marked-paragraph"), (") ", "marked-paragraph"),
                  ("לקיחה", "bold", "marked-paragraph"), (" ", "marked-paragraph"),
                  ("ונטילה", "bold", "marked-paragraph"), (", ", "bold", "marked-paragraph"),
                  ("כי", "marked-paragraph"), (" ", "marked-paragraph"), ("כל", "marked-paragraph"),
                  (" ", "marked-paragraph"), ("אדם", "marked-paragraph"), ("\n", ""),
                  ("מתחייב", ""), (". ", "")]
        self.assertEqual(DC.convert_pages([old_page(spans_)]),
                         "א) <b>לקיחה ונטילה,</b> כי כל אדם מתחייב.\n")


class FormatDetection(unittest.TestCase):
    def test_detect(self):
        new = DC.parse_page(new_page(("א", "marked-paragraph"), ("ב",), ("ג", "marked-paragraph")))
        self.assertEqual(DC.detect_format([new]), "word")
        old = DC.parse_page(old_page([("א", "marked-paragraph"), (" ", "marked-paragraph"),
                                      ("ב", "marked-paragraph"), (" ", "marked-paragraph"),
                                      ("ג", "marked-paragraph"), (" ", ""), ("ד", "")]))
        self.assertEqual(DC.detect_format([old]), "line")


class PageOrderAndZip(unittest.TestCase):
    def test_page_sort_key_numeric_and_hyphenated_names(self):
        names = ["kesef-mishne-010__ocr_data.html", "kesef-mishne-9__ocr_data.html",
                 "kesef-mishne-100__ocr_data.html"]
        self.assertEqual(sorted(names, key=DC.page_sort_key),
                         ["kesef-mishne-9__ocr_data.html", "kesef-mishne-010__ocr_data.html",
                          "kesef-mishne-100__ocr_data.html"])

    def test_convert_zip_with_page_order(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("b-002__ocr_data.html", new_page(("שני", "marked-paragraph")))
            z.writestr("b-001__ocr_data.html", new_page(("ראשון", "marked-paragraph")))
        data = buf.getvalue()
        self.assertEqual(DC.convert_zip(data).text, "ראשון\nשני\n")
        # סדר מפורש מ־pages.json גובר
        self.assertEqual(DC.convert_zip(data, page_order=["b-002.zip", "b-001.zip"]).text,
                         "שני\nראשון\n")


class Metadata(unittest.TestCase):
    def test_print_year_variants(self):
        # באג 5: int(printYear) קרס על טווח
        self.assertEqual(DC.print_year_to_int("1925-1931"), 1925)
        self.assertEqual(DC.print_year_to_int(1889), 1889)
        self.assertEqual(DC.print_year_to_int("1913"), 1913)
        self.assertIsNone(DC.print_year_to_int(""))
        self.assertIsNone(DC.print_year_to_int(None))
        self.assertIsNone(DC.print_year_to_int("לא ידוע"))

    def test_build_metadata_range_and_strip(self):
        md = DC.build_metadata({"displayName": "ספר ", "author": " מחבר", "printYear": "1925-1931",
                                "category": "שו\"ת", "subcategory": "אחרונים"})
        self.assertEqual(md["title"], "ספר")
        self.assertEqual(md["author"], "מחבר")
        self.assertEqual(md["pubDate"], [1925])
        self.assertEqual(md["printYearRaw"], "1925-1931")
        self.assertEqual(md["heCategories"], ["שו\"ת", "אחרונים"])
        # QA 9: רווחים כפולים פנימיים מתכווצים כמו ב־<h1>
        self.assertEqual(DC.build_metadata({"displayName": "שם  הספר "})["title"], "שם הספר")
        md2 = DC.build_metadata({"displayName": "x"})
        self.assertEqual(md2["pubDate"], [])


class MergeBoldRuns(unittest.TestCase):
    def m(self, s, **kw):
        return CL.merge_bold_runs(s, **kw)

    def test_user_example(self):
        self.assertEqual(self.m("<b>הקדמת</b> <b>המחבר.</b> <b>בשפה</b> <b>רפה</b> <b>מדבר:</b>"),
                         "<b>הקדמת המחבר. בשפה רפה מדבר:</b>")

    def test_source_markers_stay_separate(self):
        s = "<b>תוס'</b> <b>ד\"ה ולא</b> קשה <b>רש\"י</b> <b>ד\"ה</b> <b>גמ'</b> <b>אמר רבא</b>"
        self.assertEqual(self.m(s), s)
        self.assertEqual(self.m(s, keep_markers=False),
                         "<b>תוס' ד\"ה ולא</b> קשה <b>רש\"י ד\"ה גמ' אמר רבא</b>")
        # סמן בתחילת הרצף הימני
        self.assertEqual(self.m("<b>סוף הלמה.</b> <b>בא\"ד</b> עוד"),
                         "<b>סוף הלמה.</b> <b>בא\"ד</b> עוד")

    def test_other_tags_not_crossed(self):
        for s in ("<big><b>x</b></big> <b>y</b>", "<b>x</b> <i>y</i> <b>z</b>",
                  "<b>x</b> <big><b>y</b></big>", "<h2><b>x</b></h2> <b>y</b>",
                  "<b>x</b> <a href=\"q\">y</a>"):
            self.assertEqual(self.m(s), s)

    def test_attributes_not_merged(self):
        s = '<b class="a">x</b> <b>y</b>'
        self.assertEqual(self.m(s), s)
        s2 = '<b>x</b> <b style="c">y</b>'
        self.assertEqual(self.m(s2), s2)

    def test_multiline_not_merged(self):
        self.assertEqual(self.m("<b>x</b>\n<b>y</b>"), "<b>x</b>\n<b>y</b>")

    def test_inner_spaces_and_adjacent(self):
        self.assertEqual(self.m("<b>x </b><b>y</b>"), "<b>x y</b>")
        self.assertEqual(self.m("<b>x</b>   <b> y</b>"), "<b>x y</b>")
        self.assertEqual(self.m("<b>א</b><b>ב</b>"), "<b>אב</b>")

    def test_entities_untouched(self):
        self.assertEqual(self.m("<b>a&amp;</b> <b>&lt;b</b>"), "<b>a&amp; &lt;b</b>")

    def test_non_whitespace_between_is_kept(self):
        s = "<b>x</b>, <b>y</b>"
        self.assertEqual(self.m(s), s)

    def test_nesting_stays_balanced(self):
        import re
        for s in ("<b>a <i>b</i></b> <b>c</b>", "<big><b>a</b> <b>b</b></big>"):
            r = self.m(s)
            self.assertEqual(len(re.findall("<b>", r)), len(re.findall("</b>", r)))
        self.assertEqual(self.m("<big><b>a</b> <b>b</b></big>"), "<big><b>a b</b></big>")

    def test_stats(self):
        st = {}
        self.m("<b>א.</b> <b>ב</b> <b>תוס'</b> <b>ג</b>", stats=st)
        self.assertEqual(st["merged"], 1)
        self.assertEqual(st["merged_after_sentence_end"], 1)
        self.assertEqual(st["kept_marker"], 2)

    def test_idempotent(self):
        s = "<b>הקדמת</b> <b>המחבר.</b> x <b>תוס'</b> <b>ד\"ה</b>"
        once = self.m(s)
        self.assertEqual(self.m(once), once)


class Cleaner(unittest.TestCase):
    def test_rule_f_keeps_punctuation(self):
        # yalkuthagershunishas1: "ע"ב:" יתום הוצמד לשורה הקודמת בלי הנקודותיים
        for ln in ('<b>ע"ב:</b>', '<b>ע"ב</b>:', 'ע"ב:'):
            out, _ = CL.clean_text("<h1>x</h1>\ny\nדף ב\n" + ln + "\nטקסט")
            self.assertEqual(out.split("\n")[2], 'דף ב ע"ב:')

    def test_rule_h_keeps_real_short_lemmas(self):
        # באג 6: H הסיר הדגשה מ"שם" / "ר'" / "כסף"
        for ln in ("<b>שם</b>", "<b>ר'</b>", "<b>כסף</b>"):
            text = "<h1>x</h1>\ny\n" + ln
            out, _ = CL.clean_text(text, enable={"H"})
            self.assertEqual(out, text)
        out, _ = CL.clean_text("<h1>x</h1>\ny\n<b>ל\"ה</b>", enable={"H"})
        self.assertEqual(out.split("\n")[2], "ל\"ה")

    def test_b_and_h_off_by_default(self):
        text = "<h1>x</h1>\ny\nטקסט בלי סוף\n<b>הלכות</b> <b>תשובה</b>\n<b>שם</b>"
        out, rep = CL.clean_text(text)
        self.assertEqual(out, "<h1>x</h1>\ny\nטקסט בלי סוף\n<b>הלכות תשובה</b>\n<b>שם</b>")
        self.assertIn("B", rep.skipped)
        self.assertIn("H", rep.skipped)

    def test_rule_b_protects_headings_and_short_bold_lines(self):
        text = "<h1>x</h1>\ny\n<b>הלכות</b> <b>תשובה</b>\n<b>פרק</b> ראשון\nמילה\n<b>המשך</b> הדבר."
        out, _ = CL.clean_text(text, enable={"B"})
        lines = out.split("\n")
        self.assertIn("<b>הלכות תשובה</b>", lines)
        self.assertIn("<b>פרק</b> ראשון", lines)
        self.assertIn("מילה <b>המשך</b> הדבר.", lines)

    def test_idempotent(self):
        text = "<h1>x</h1>\ny\n‏א  ב \n<b>ע\"א</b>\n<b>הקדמת</b> <b>המחבר</b>"
        once, _ = CL.clean_text(text)
        twice, _ = CL.clean_text(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
