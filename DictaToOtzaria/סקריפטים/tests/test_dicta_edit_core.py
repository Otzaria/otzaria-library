# -*- coding: utf-8 -*-
"""בדיקות רגרסיה לכלי "עריכת ספרים" (dicta_edit_core.py).

כל בדיקה כאן היא באג שפגע בספרים אמיתיים (ראש יוסף על פסחים/ביצה, שפת אמת על
פסחים ועוד) או תנאי שהכלים הישנים לא עמדו בו.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "עריכת ספרים"))

import dicta_edit_core as core  # noqa: E402

H = "<h1>ספר</h1>\nמחבר\n"


class Gematria(unittest.TestCase):
    def test_num_to_heb(self):
        self.assertEqual(core.num_to_heb(15), "טו")
        self.assertEqual(core.num_to_heb(16), "טז")
        self.assertEqual(core.num_to_heb(274), "רעד")
        self.assertEqual(core.num_to_heb(40, finals=True), "ם")

    def test_heb_to_num(self):
        self.assertEqual(core.heb_to_num('קי"א'), 111)
        self.assertEqual(core.heb_to_num("ט'"), 9)
        self.assertIsNone(core.heb_to_num("abc"))

    def test_is_number_word(self):
        self.assertTrue(core.is_number_word('<b>קי"א.</b>'))
        self.assertTrue(core.is_number_word("שמיני"))
        self.assertFalse(core.is_number_word("אמר"))
        self.assertFalse(core.is_number_word("ק", max_num=50))


class PageBHeaders(unittest.TestCase):
    def test_avoda_zara_untouched(self):
        # "עבודה זרה…" הפך ל"<h3>עמוד ב</h3>" + "ודה זרה…"
        text = H + "עבודה זרה היא כו'.\nעב טעם, ועוד.\nעמודים הרבה."
        new, n = core.create_page_b_headers(text)
        self.assertEqual(n, 0)
        self.assertEqual(new, text)

    def test_punctuation_preserved_and_gmara_not_duplicated(self):
        # "עמוד ב. בגמ' מתני' כו'." → "בגמ'  בגמ מתני כו"
        text = H + "עמוד ב. בגמ' מתני' כו'.\nע\"ב בא\"ד, ומ\"ש: (שם) [כו']."
        new, n = core.create_page_b_headers(text, level=3)
        self.assertEqual(n, 2)
        self.assertEqual(new.split("\n")[2:], [
            "<h3>עמוד ב</h3>", "בגמ' מתני' כו'.",
            "<h3>עמוד ב</h3>", "בא\"ד, ומ\"ש: (שם) [כו']."])

    def test_gmara_prefix_moves_after_heading(self):
        new, n = core.create_page_b_headers(H + "גמ' ע\"ב אמר רבא.")
        self.assertEqual(new.split("\n")[2:], ["<h3>עמוד ב</h3>", "גמ' אמר רבא."])

    def test_shem_and_tags(self):
        new, n = core.create_page_b_headers(H + "<b>שם</b> <b>ע\"ב</b> תוס' ד\"ה אמר.")
        self.assertEqual(n, 1)
        self.assertEqual(new.split("\n")[2:], ["<h3>עמוד ב</h3>", "תוס' ד\"ה אמר."])

    def test_existing_heading_untouched(self):
        text = H + "<h3>עמוד ב</h3>"
        self.assertEqual(core.create_page_b_headers(text), (text, 0))


class AddPageNumber(unittest.TestCase):
    def test_amud_marker_requires_quote(self):
        # ע"?[א-ב] אכל את "עב" של "עבודה"
        text = H + "<h2>דף ב</h2>\nעבודה זרה כו'."
        self.assertEqual(core.add_page_number(text), (text, 0))

    def test_dot_colon(self):
        text = H + "<h2>דף ב</h2>\nע\"א בגמ' כו'.\n<h2>דף ב</h2>\n<b>ע\"ב</b> תוס', ד\"ה."
        new, n = core.add_page_number(text)
        self.assertEqual(n, 2)
        self.assertEqual(new.split("\n")[2:], ["<h2>דף ב.</h2>", "בגמ' כו'.",
                                               "<h2>דף ב:</h2>", "תוס', ד\"ה."])

    def test_ayin_style(self):
        new, _ = core.add_page_number(H + "<h3>דף ג</h3>\nעמוד ב שם.", style="ayin")
        self.assertEqual(new.split("\n")[2:], ["<h3>דף ג ע\"ב</h3>", "שם."])


class CreateHeaders(unittest.TestCase):
    def test_daf_amud_kept(self):
        # "דף ב." ו"דף ב:" הפכו שניהם ל"דף ב"
        text = H + "דף ב. גמרא\nדף ב: תוס'\nדף ג ע\"ב רש\"י"
        new, n = core.create_headers(text, "דף")
        self.assertEqual(n, 3)
        self.assertEqual(new.split("\n")[2:], ["<h2>דף ב.</h2>", "גמרא", "<h2>דף ב:</h2>", "תוס'",
                                               "<h2>דף ג:</h2>", "רש\"י"])

    def test_reference_is_not_heading(self):
        text = H + "פרק ב דברכות אמרו כך.\nפרק ג\nהמשך"
        new, n = core.create_headers(text, "פרק")
        self.assertEqual(n, 1)
        self.assertEqual(new.split("\n")[2:], ["פרק ב דברכות אמרו כך.", "<h2>פרק ג</h2>", "המשך"])

    def test_bold_word_and_balanced_rest(self):
        new, n = core.create_headers(H + "<b>סימן א</b> שאלה <b>ששאל</b>", "סימן", level=3)
        self.assertEqual(new.split("\n")[2:], ["<h3>סימן א</h3>", "שאלה <b>ששאל</b>"])
        new, n = core.create_headers(H + "<b>סימן א ששאל</b> שאלה", "סימן", level=3)
        self.assertEqual(new.split("\n")[2:], ["<h3>סימן א</h3>", "<b>ששאל</b> שאלה"])

    def test_max_num(self):
        new, n = core.create_headers(H + "סימן קכ טקסט", "סימן", max_num=100)
        self.assertEqual(n, 0)


class SingleLetter(unittest.TestCase):
    def test_bold_mode_works(self):
        # "כמה סימונים": startswith("<b>") and startswith("</b>") — לא התקיים לעולם
        text = "<h1>x</h1>\n<b>א.</b> טקסט\n<b>ג)</b> עוד\n<b>שם.</b> עוד\nב. לא מודגש"
        new, n = core.single_letter_headers(text, suffixes=[".", ")"], bold_only=True,
                                            sequential=False)
        self.assertEqual(n, 2)  # א, ג — בלי רצף; "שם" (=340) לעולם לא כהתחלה
        self.assertEqual(new.split("\n")[1:4], ["<h3>א</h3>", "טקסט", "<h3>ג</h3>"])
        self.assertIn("<b>שם.</b> עוד", new)

    def test_non_bold_mode(self):
        text = "<h1>x</h1>\n(א) טקסט\n<b>(ב)</b> טקסט\n(ב) עוד"
        new, n = core.single_letter_headers(text, suffixes=")", prefixes="(", bold_only=False)
        self.assertEqual(n, 2)  # (ב) המודגש אינו מועמד
        self.assertEqual(new.split("\n")[1], "<h3>א</h3>")


class SingleLetterSequence(unittest.TestCase):
    def test_words_that_are_numbers_are_not_headings(self):
        # QA 5: <b>שם.</b> (=340), ר' / ה' / תו' הפכו לכותרות
        text = "<h1>x</h1>\n<b>א.</b> ראשון\n<b>שם.</b> כתב\n<b>ב.</b> שני"
        new, n = core.single_letter_headers(text, suffixes=".", bold_only=True)
        self.assertEqual(n, 2)
        self.assertIn("<b>שם.</b> כתב", new)
        text2 = "<h1>x</h1>\nר' יוחנן אמר\nא' ראשון\nה' אמר\nב' שני"
        new2, n2 = core.single_letter_headers(text2, suffixes="'", bold_only=False)
        self.assertEqual(n2, 2)
        self.assertIn("ר' יוחנן אמר", new2)
        self.assertIn("ה' אמר", new2)

    def test_restart_needs_following_bet(self):
        # "א' מהם" בגוף הטקסט אינו התחלת רצף, ואינו שובר רצף קיים (ג → ד)
        text = "<h1>x</h1>\nא' מהם אמר\nעוד\n<b>א.</b> x\n<b>ב.</b> y\n<b>ג.</b> z\nא. מהם\n<b>ד.</b> w"
        new, n = core.single_letter_headers(text, suffixes=".", bold_only=False)
        self.assertEqual(n, 0)  # לא מודגש: אין א. ואחריו ב.
        new, n = core.single_letter_headers(text, suffixes=".", bold_only=True)
        self.assertEqual(n, 4)
        self.assertIn("<h3>ד</h3>", new)
        text2 = "<h1>x</h1>\nא' מהם אמר\nעוד שורה"
        _, n2 = core.single_letter_headers(text2, suffixes="'", bold_only=False)
        self.assertEqual(n2, 0)

    def test_common_words_only_as_direct_continuation(self):
        # ה' אחרי ד' — כותרת; ה' / תו' / כו' / שם בלי רצף — לא, גם בלי sequential
        text = "<h1>x</h1>\nא' x\nב' x\nג' x\nד' x\nה' x\nתו' הקשו\nכו' וכו\nה' אמר"
        new, n = core.single_letter_headers(text, suffixes="'", bold_only=False)
        self.assertEqual(n, 5)
        self.assertIn("תו' הקשו", new)
        self.assertIn("ה' אמר", new)
        _, n2 = core.single_letter_headers("<h1>x</h1>\nר' יוחנן\nתו' כתבו\n<b>שם.</b> x",
                                           suffixes=["'", "."], bold_only=False, sequential=False)
        self.assertEqual(n2, 0)

    def test_continues_from_existing_same_level_heading(self):
        text = "<h1>x</h1>\n<h3>א</h3>\nx\n<h3>ב</h3>\ny\n<b>ג.</b> z"
        new, n = core.single_letter_headers(text, suffixes=".")
        self.assertEqual(n, 1)
        self.assertIn("<h3>ג</h3>", new)

    def test_sequence_restarts_after_other_heading(self):
        text = "<h1>x</h1>\n<h2>פרק א</h2>\n<b>א.</b> x\n<b>ב.</b> y\n<h2>פרק ב</h2>\n<b>א.</b> z\n<b>ב.</b> w\n<h2>פרק ג</h2>\n<b>א.</b> בודד"
        new, n = core.single_letter_headers(text, suffixes=".")
        self.assertEqual(n, 4)  # א בודד (בלי ב אחריו) אינו כותרת
        self.assertIn("<b>א.</b> בודד", new)


class Emphasize(unittest.TestCase):
    long = "מילה " * 11 + "סוף"

    def test_both_options_keep_ending(self):
        # באג: כשנבחרו שתי הפעולות — הסימן שנוסף אבד
        new, n = core.emphasize_and_punctuate(H + self.long, ending=":", emphasize=True)
        last = new.split("\n")[2]
        self.assertTrue(last.startswith("<b>מילה</b> "))
        self.assertTrue(last.endswith("סוף:"))

    def test_starts_after_header(self):
        # הגרסה הקודמת התחילה מהשורה הרביעית ודילגה על הפסקה הראשונה
        text = H + self.long + "\n" + self.long
        new, n = core.emphasize_and_punctuate(text, ending=None)
        self.assertEqual(n, 2)
        self.assertEqual(new.split("\n")[0], "<h1>ספר</h1>")

    def test_comma_replaced_and_headings_skipped(self):
        text = H + "<h2>" + self.long + "</h2>\n" + self.long + ","
        new, n = core.emphasize_and_punctuate(text, ending=".", emphasize=False)
        self.assertEqual(new.split("\n")[2], "<h2>" + self.long + "</h2>")
        self.assertTrue(new.split("\n")[3].endswith("סוף."))


class ReplacePageB(unittest.TestCase):
    def test_colon(self):
        text = H + "<h3>דף ב</h3>\nא\n<h3>עמוד ב</h3>\nב\n<h3>דף ג ע\"א</h3>\n<h3>עמוד ב</h3>"
        new, n = core.replace_page_b_headers(text)
        self.assertEqual(n, 2)
        self.assertIn("<h3>דף ב:</h3>", new)
        self.assertIn("<h3>דף ג:</h3>", new)
        new2, _ = core.replace_page_b_headers(text, style="ayin")
        self.assertIn('<h3>דף ג ע"ב</h3>', new2)


class Validate(unittest.TestCase):
    def test_sequence_step_one(self):
        # "בדיקת תגים גירסא 2" השוותה ל־index+2 גם בספר רגיל: פספוס של א→ג
        text = H + "<h2>סימן א</h2>\n<h2>סימן ג</h2>\n<h2>סימן ד</h2>"
        res = core.validate_headings(text)
        self.assertEqual(res["unmatched_tags"], ["סימן א || סימן ג"])

    def test_shas_mode(self):
        text = H + "<h3>דף ב.</h3>\n<h3>דף ב:</h3>\n<h3>דף ג.</h3>\n<h3>דף ד:</h3>"
        res = core.validate_headings(text, shas=True)
        self.assertEqual(res["unmatched_regex"], [])
        self.assertEqual(res["unmatched_tags"], ["דף ב: || דף ד:"])

    def test_gershayim_modes(self):
        text = H + "<h2>סימן א'</h2>\n<h2>סימן ב</h2>"
        self.assertIn("א'", core.validate_headings(text)["unmatched_tags"])
        self.assertIn("ב", core.validate_headings(text, gershayim=True)["unmatched_tags"])

    def test_validate_tags(self):
        res = core.validate_tags("<h2>כותרת</h2> טקסט\n<b>פתוח\nסגור</b>\n<big><b>x</b></big>")
        self.assertEqual([n for n, _ in res["heading_errors"]], [1])
        self.assertEqual([(n, t) for n, t, _ in res["opening_without_closing"]], [(2, "b")])
        self.assertEqual([(n, t) for n, t, _ in res["closing_without_opening"]], [(3, "b")])


class ColonNewline(unittest.TestCase):
    def test_body_only_not_short_quotes_not_inside_tags(self):
        # ציטוט קצר שנגמר (עכ"ל) והטקסט נמשך — באמצע משפט; לא בכותרת ולא בתוך <b>
        text = (H + "<h2>כותרת: משנה</h2>\nוהוא פשוט: ועוד קשה: וז\"ל: אסור. עכ\"ל ומה שכתב\n"
                "<b>מחצלת: עשויה</b> מחלף: סוף:")
        new, n = core.colon_newline(text)
        self.assertEqual(new.split("\n")[2:], [
            "<h2>כותרת: משנה</h2>", "והוא פשוט:", "ועוד קשה:", "וז\"ל: אסור. עכ\"ל ומה שכתב",
            "<b>מחצלת: עשויה</b> מחלף:", "סוף:"])
        self.assertEqual(n, 3)

    def test_dibbur_opening_is_new_paragraph(self):
        # ד"ה אחרי סוף עניין פותח פסקה; אחרי הפניה לדף או בסוגריים — המשך המשפט
        self.assertTrue(core.colon_ends_matter("וזה ברור", 'ד"ה ומה שכתב'))
        self.assertTrue(core.colon_ends_matter("ודו\"ק", '<b>בד"ה</b> אלא'))
        self.assertFalse(core.colon_ends_matter("תוס' שם פ\"ה", 'ד"ה בעי כתבו'))
        self.assertFalse(core.colon_ends_matter("מתוס' יומא (לב", 'ד"ה הוי) ועוד'))

    def test_quote_intro_opening_a_paragraph(self):
        # ז"ל לבדו אחרי שם הוא תואר כבוד; וז"ל: שאחריו ציטוט שלם — פסקה חדשה
        self.assertTrue(core.colon_ends_matter('כדברי הב"י ז"ל', "ולענין הלכה"))
        self.assertTrue(core.colon_ends_matter('וכתב וז"ל', "אסור להראות סכין לחכם ביום טוב"))
        self.assertTrue(core.colon_ends_matter('וכתב וז"ל', "<b>ולענין</b> הלכה"))
        self.assertFalse(core.colon_ends_matter('וכתב וז"ל', 'אסור. עכ"ל ומה שכתב'))

    def test_open_parenthesis_must_close_right_away(self):
        self.assertFalse(core.colon_ends_matter("כמו שכתבו התוס' (דף", 'פ"ו ע"א) בד"ה'))
        self.assertTrue(core.colon_ends_matter("ובפסחים (הגה\"ה", "ולכאורה יש להוכיח"))
        self.assertTrue(core.colon_ends_matter("(בס' אהל נפתלי דף מ\"א", "כג) בה' יתרת מעי"))
        self.assertTrue(core.colon_ends_matter("(בס' אהל נפתלי דף מ\"א", "(ג) ולכאורה"))

    def test_daf_reference_not_split(self):
        # QA 6: "שבת קיט: ובגמ'" — הנקודותיים הן עמוד ב
        new, n = core.colon_newline(H + "כדאיתא בשבת קיט: ובגמ' שם. ועיין דף ל\"ג: ובתוס' כתבו: ועוד")
        self.assertEqual(n, 1)
        self.assertEqual(new.split("\n")[2:], ["כדאיתא בשבת קיט: ובגמ' שם. ועיין דף ל\"ג: ובתוס' כתבו:", "ועוד"])

    def test_more_daf_reference_forms_not_split(self):
        cases = [
            "ועי' בב\"ק כ\"ה: ובתוס' שם",          # קיצור מסכת עם גרשיים + אות שימוש
            "ועיין בבא מציעא ל: והנה",             # מסכת בת שתי מילים
            "כדאיתא בדף ה': ומזה",                 # דף עם אות שימוש
            "כמ\"ש בד' כא: וא\"ת",                  # בד' = בדף
            "עיין שם כ\"ה ע\"ב: ומבואר",            # מספר + ע"ב
            "סיפא ודוק. ע\"ב: בגמ' שם",             # סמן עמוד לבדו
            "דף ה' עמוד ב: והנה",
            "תוס' שם פ\"ה: ד\"ה בעי כתבו",          # ד"ה אחרי הנקודותיים
            "ועי' תוס' שם י\"ח: דבגד",
            "מתוס' יומא (לב: ד\"ה הוי) ועוד",       # בתוך סוגריים קצרים
        ]
        for c in cases:
            new, n = core.colon_newline(H + c)
            self.assertEqual(n, 0, c)
            self.assertEqual(new, H + c)

    def test_sentence_end_still_split(self):
        # אחרי סוגר, ואחרי סוגר פתוח רחוק (OCR) — נקודותיים של סוף עניין נשברות
        new, n = core.colon_newline(H + "כדאיתא בשבת (דף קיט): ובזה יתיישב")
        self.assertEqual(n, 1)
        new, n = core.colon_newline(H + "(ובאמת " + "מילה " * 12 + "ועוד קשה: אך קצת יש")
        self.assertEqual(n, 1)
        new, n = core.colon_newline(H + "ומיושב היטב קמ\"ה פעמים: ועוד")
        self.assertEqual(n, 1)  # מספר שאינו אחרי מסכת/דף

    def test_no_empty_lines(self):
        new, _ = core.colon_newline(H + "סוף: \nהתחלה")
        self.assertNotIn("\n\n", new)


class CleanText(unittest.TestCase):
    def test_space_before_bracket_not_glued(self):
        # QA 7: "בהו ]היינו" → "בהו]היינו"
        self.assertEqual(core.clean_text("בהו ]היינו וכן ( שם ) כו' ."), "בהו ]היינו וכן (שם) כו'.")

    def test_space_before_only_real_closers(self):
        opt = ("remove_spaces_before",)
        # סוגר בלי פותח לפניו (הפוך) — הרווח נשאר גם כשאחריו רווח
        self.assertEqual(core.clean_text("בהו ] היינו [שם ]", opt), "בהו ] היינו [שם]")
        self.assertEqual(core.clean_text("ר\"ל ) וכן (כך )", opt), "ר\"ל ) וכן (כך)")
        # פסיק/נקודה/נקודותיים/נקודה־פסיק שאחריהם אות — לא מודבקים ("לא ,לא")
        self.assertEqual(core.clean_text("לא ,לא וכן :היינו", opt), "לא ,לא וכן :היינו")
        self.assertEqual(core.clean_text("כך ; ועוד , וגם .\nסוף :", opt), "כך; ועוד, וגם.\nסוף:")
        self.assertEqual(core.clean_text("שם <b>כך</b> .", opt), "שם <b>כך</b>.")

    def test_quotes(self):
        self.assertEqual(core.clean_text("א''ב ״ג״ ”ד“ ׳ה"), 'א"ב "ג" "ד" \'ה')


if __name__ == "__main__":
    unittest.main()
