"""Tests for te_convert.marks() / te_tidy.py (no Torat Emet files needed). Run: python3 -m unittest -v test_te_tidy"""
import unittest

import te_convert as E
import te_reapply as RA
import te_tidy as T


class Marks(unittest.TestCase):
    def test_two_apostrophes_are_a_quotation_mark(self):
        self.assertEqual(E.marks("מספר ''כל בו'' סי' ס\"ח, ב''אשרי העם''"), 'מספר "כל בו" סי\' ס"ח, ב"אשרי העם"')

    def test_three_apostrophes_are_a_geresh_and_a_quotation_mark(self):
        self.assertEqual(E.marks("''שאול בחיר ה'''."), '"שאול בחיר ה\'".')

    def test_apostrophes_in_a_tag_are_kept(self):
        self.assertEqual(E.marks("<td style=''>טקסט</td>"), "<td style=''>טקסט</td>")

    def test_apostrophes_split_by_a_bold_tag(self):
        self.assertEqual(RA.tidy("אמר ליה '<b>'על מנת</b>'<b>'</b>, אזי"), 'אמר ליה "<b>על מנת</b>", אזי')

    def test_space_before_punctuation(self):
        self.assertEqual(E.marks('כי שמא תלך ; ומה ששנינו. וכו\' :'), 'כי שמא תלך; ומה ששנינו. וכו\':')
        self.assertEqual(E.marks('המתנה ... ועוד'), 'המתנה ... ועוד')

    def test_space_on_the_wrong_side_of_a_comma(self):
        self.assertEqual(E.marks('מספר עשרה ,מכל מקום (שם שם ,יג)'), 'מספר עשרה, מכל מקום (שם שם, יג)')

    def test_bold_word_cut_by_its_gershayim(self):
        self.assertEqual(E.marks('כתב <b>הריטב</b>"<b>א</b> ו<b>רש</b>"י ו<b>תוס</b>\'<b>ות</b>'),
                         'כתב <b>הריטב"א</b> ו<b>רש"י</b> ו<b>תוס\'ות</b>')

    def test_quotation_mark_after_a_bold_word_is_not_a_tail(self):
        for s in ('"<b>תנו</b>" <b>נותנין</b>', '<b>ו</b>"פני הכרוב"', '<b>מאי</b>"אין לו אב"'):
            self.assertEqual(E.marks(s), s)

    def test_punctuation_bold_alone_loses_its_bold(self):
        self.assertEqual(E.marks('את הגט<b>;</b> ונתקשו, גורסים <b>"</b>כשחרש<b>"</b>, הוא<b>?!</b> הלא'),
                         'את הגט; ונתקשו, גורסים "כשחרש", הוא?! הלא')

    def test_punctuation_inside_a_bold_run_stays(self):
        for s in ('<b>הרמב"ם</b>', '<b>"ציון"</b>', 'ק<b>י"</b>ד', '<b>אמר.</b>'):
            self.assertEqual(E.marks(s), s)

    def test_bold_runs_split_by_a_space_are_joined(self):
        self.assertEqual(E.marks('שב<b>עין</b> <b>יעקב</b> ו<b>א</b> <b>ב</b> <b>ג</b>'), 'שב<b>עין יעקב</b> ו<b>א ב ג</b>')

    def test_note_labels_stay_runs_of_their_own(self):
        for s in ('<b>(12)</b> <b>עין</b> כתב', '<b>(3א)</b> <b>רש"י</b> כתב', '<b>(*216)</b> <b>צל"ח</b>',
                  'כתב <b>עין</b> <b>(12)</b> ועוד', '<b>(סימן בא"ש)</b> <b>מתניתין</b>'):
            self.assertEqual(E.marks(s), s)

    def test_mid_line_parentheses_are_joined(self):
        self.assertEqual(E.marks('ועוד <b>(אסורין)</b> <b>לעולם</b>'), 'ועוד <b>(אסורין) לעולם</b>')

    def test_heading_edges(self):
        self.assertEqual(E.marks('<h1>בלבבי משכן אבנה - ו  </h1>'), '<h1>בלבבי משכן אבנה - ו</h1>')


class Tidy(unittest.TestCase):
    def test_letters_never_change_and_a_second_run_changes_nothing(self):
        for s in ("<b>(1)</b> וב<b>רש''</b>י שב<b>עין</b> <b>יעקב</b> <b>''</b>כשחרש וכו'<b>''</b> ; ועוד",
                  "סומך<b>; ; ; ;</b> וראה, '<b>'שכיר</b>'<b>' שכיר</b>'<b>'</b>.",
                  '<b> משמיעין.</b> ו<b>מותר תרומה </b>הכסף, (65) <b></b> וכינה'):
            once = T.tidy(s)
            self.assertEqual(RA.key(once), RA.key(s))
            self.assertEqual(T.tidy(once), once)

    def test_conversion_and_tidy_agree(self):
        s = "<b>(4)</b> כתב <b>הריטב</b>''<b>א</b> ; ''ציון''"
        self.assertEqual(E.tidy(s), T.tidy(s))


if __name__ == '__main__':
    unittest.main()
