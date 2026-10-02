"""Offline tests of te_reapply.py (synthetic lines and sources, no Torat Emet files).

    cd ToratEmetToOtzaria/סקריפטים && python3 -m unittest -v test_te_reapply
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import te_convert as E  # noqa: E402
import te_reapply as R  # noqa: E402


def merge(new, cur):
    return R.merge_line(new, cur, R.new_report())


def source(body, rules='#rep=(=<small>(^^)=)</small>^^{=<b>^^}=</b>'):
    """A Torat Emet book: parameter line, then the body."""
    return '&UniqueId=1&CosmeticsType=' + rules + '\n' + body


def book(body, cur, spec=None, max_carry=10, rules=None):
    """convert + merge + checks of a synthetic book -> (out, problems). A title and an
    author line go first (merge_book leaves those two as they are): the body starts at
    source line 4 and at line 3 of the book."""
    body = '$ שם\nמחבר\n' + body
    cur = ['<h1>שם</h1>', 'מחבר'] + cur
    conv = {}
    text = source(body) if rules is None else source(body, rules)
    _, new = E.convert('x.txt', text=text, markers=True, report=conv)
    spec = spec or {}
    out, rep = R.merge_book(new, cur, keep=[l for l, _ in R.allowlist(spec, 'keep', 2)])
    return out, R.format_problems(conv, out, spec, max_carry, cur, new, rep['pairs'], rep['unstable'])


class OrphanCloser(unittest.TestCase):
    def test_stray_closer_formats_nothing(self):
        # source '{מאי טעמא}?}': the old file kept the stray '}' as '</b>'
        new = 'ומבארת הגמרא: <b>מאי טעמא דרבי עקיבא</b>?'
        cur = 'ומבארת הגמרא: <b>מאי טעמא דרבי עקיבא</b>?</b>'
        self.assertEqual(merge(new, cur), new)

    def test_stray_small_closers(self):
        new = 'דְקִדּוּשִׁין (ל, א): אָמַר'
        cur = 'דְקִדּוּשִׁין </small></small>(ל, א)</small></small>: אָמַר'
        self.assertEqual(merge(new, cur), new)

    def test_real_carry_comes_from_the_conversion(self):
        new = '<b>סוף הציטוט</b> והסבר'
        cur = 'סוף הציטוט</b> והסבר'
        self.assertEqual(merge(new, cur), new)


class FixedPoint(unittest.TestCase):
    CASES = [
        # two spaces of different formatting between two runs the source has as one
        ('<b>משביחו (וכו\')</b>:', 'שנינו: <b>משביחו </b> <b>(וכו\')</b>:'),
        ('<b>משביחו </b> <b>(וכו\')</b>:', 'שנינו: <b>משביחו </b> <b>(וכו\')</b>:'),
        ('<b>אחר שריבה ???</b> <b>הכתוב</b> שיש',
         '<b>אחר שריבה </b> <span style="color:Gray;"><small><small>(תחילת העמוד)</small></small></span> <b>הכתוב</b> שיש'),
        ('שם <small>ט"ו. </small>. המחמם', 'שם <small><small>ט"ו.</small></small>.  המחמם'),
        ('<b>32.</b> <b>רשב\'\'ם</b>, ומבואר', '(32)  <b>רשב\'\'ם</b>, ומבואר'),
        ('<b>"<b>המוציא מחבירו</b>"</b>', '<b>"<b>המוציא מחבירו</b>"</b>'),
    ]

    def test_second_run_changes_nothing(self):
        for new, cur in self.CASES:
            once = merge(new, cur)
            self.assertEqual(merge(new, once), once, (new, cur))

    def test_runs_the_source_joins_are_joined(self):
        out = merge('<b>משביחו (וכו\')</b>:', '<b>משביחו </b> <b>(וכו\')</b>:')
        self.assertEqual(out, '<b>משביחו (וכו\')</b>:')

    def test_no_bold_inside_bold(self):
        self.assertEqual(merge('<b>"המוציא"</b>', '<b>"<b>המוציא</b>"</b>'), '<b>"המוציא"</b>')


class CurrentOnlyText(unittest.TestCase):
    def test_page_mark_keeps_its_own_formatting(self):
        new = '<b>אחר שריבה ???</b> <b>הכתוב</b> שיש'
        cur = ('<b>אחר שריבה </b> <span style="color:Gray;"><small><small>(תחילת העמוד)</small></small></span>'
               ' <b>הכתוב</b> שיש')
        out = merge(new, cur)
        self.assertIn('<span style="color:Gray;"><small><small>(תחילת העמוד)</small></small></span>', out)

    def test_punctuation_at_the_edge_of_a_run_stays_out(self):
        out = merge('שם <small>ט"ו. </small>. המחמם', 'שם <small><small>ט"ו.</small></small>.  המחמם')
        self.assertTrue(out.endswith('</small></small>. המחמם'), out)

    def test_extra_space_does_not_join_runs(self):
        out = merge('<b>32.</b> <b>רשב\'\'ם</b>, ומבואר', '(32)  <b>רשב\'\'ם</b>, ומבואר')
        self.assertTrue(out.startswith('<b>(32)</b> <b>רשב'), out)

    def test_hand_fixed_letter_inside_a_run_is_formatted(self):
        # the current file fixed רבא -> רבה inside a quote the conversion bolds
        self.assertEqual(merge('<b>אמר רבא</b> בזה', 'אמר רבה בזה'), '<b>אמר רבה</b> בזה')

    def test_gershayim_do_not_misalign(self):
        new = '<b>96.</b> לשון <b>רש\'\'י</b>. וב<b>רא\'\'ש</b> כתב'
        cur = '(96) לשון <b>רש"י</b>. וב<b>רא"ש</b> כתב'
        self.assertTrue(merge(new, cur).startswith('<b>(96)</b> לשון <b>רש"י</b>.'))


class Checks(unittest.TestCase):
    def test_foreign_effects_catch_the_old_orphan_rule(self):
        new = 'ומבארת הגמרא: <b>מאי טעמא</b>?'
        cur = 'ומבארת הגמרא: <b>מאי טעמא</b>?</b>'
        bad = '<b>ומבארת הגמרא: <b>מאי טעמא</b>?</b>'      # what a1f39803 wrote
        self.assertTrue(R.foreign_effects(new, cur, bad))
        self.assertFalse(R.foreign_effects(new, cur, merge(new, cur)))
        menorat = '<small><small><small><small>הַמְלַמֵּד אֶת בְּנוֹ (ל, א)</small></small></small></small>'
        self.assertTrue(R.foreign_effects('הַמְלַמֵּד אֶת בְּנוֹ <small>(ל, א)</small>',
                                          'הַמְלַמֵּד אֶת בְּנוֹ </small></small>(ל, א)</small></small>', menorat))

    def test_nested_tags(self):
        self.assertEqual(R.nested_tags('<b>א <b>ב</b> ג</b>'), ['b'])
        self.assertEqual(R.nested_tags('<small><small>א</small></small>'), [])

    def test_clean_book_passes(self):
        out, probs = book('~ כותרת\n{א} ב (ג)\n', ['<h2>כותרת</h2>', 'א ב (ג)'])
        self.assertEqual(probs, [])
        self.assertEqual(out[3], '<b>א</b> ב <small>(ג)</small>')

    def test_unbalanced_must_be_listed_by_line_and_tag(self):
        body = '~ ראש\nא (ב {ג\n~ סוף\nד\n'
        cur = ['<h2>ראש</h2>', 'א (ב {ג', '<h2>סוף</h2>', 'ד']
        _, probs = book(body, cur)
        self.assertEqual(len(probs), 2)                      # '(' and '{', both unlisted
        _, probs = book(body, cur, {'unbalanced': [[5, 'small']]})
        self.assertEqual(len(probs), 1)                      # one entry hides one tag only
        self.assertIn('<b>', probs[0])
        _, probs = book(body, cur, {'unbalanced': [[5, 'small'], [5, 'b']]})
        self.assertEqual(probs, [])
        _, probs = book(body, cur, {'unbalanced': [[5, 'small'], [5, 'b'], [9, 'b']]})
        self.assertEqual(len(probs), 1)                      # a stale entry fails
        self.assertIn('no such unclosed tag', probs[0])

    def test_unbalanced_entries_must_be_pairs(self):
        with self.assertRaises(SystemExit):
            book('א\n', ['א'], {'unbalanced': [2]})

    def test_runaway_inside_one_section(self):
        # '(' is closed by a stray ')' 30 lines on, no heading in between
        rules = '#rep=(=<small>(^^)=)</small>^^{SE}=)'
        body = '~ ראש\nא (ב ג{SE} ד\n' + 'מילוי\n' * 30 + 'ה ) ו\n~ סוף\nז\n'
        cur = ['<h2>ראש</h2>', 'א (ב ג) ד'] + ['מילוי'] * 30 + ['ה ) ו', '<h2>סוף</h2>', 'ז']
        _, probs = book(body, cur, rules=rules)
        self.assertTrue(any('runs over 31 lines' in p for p in probs), probs)
        _, probs = book(body, cur, {'carried': [[5, 36, 'small']]}, rules=rules)
        self.assertEqual(probs, [])
        _, probs = book(body, cur, {'carried': [[5, 36, 'small'], [5, 50, 'i']]}, rules=rules)
        self.assertEqual(len(probs), 1)                      # a stale entry fails

    def test_keep_leaves_the_line_and_goes_stale(self):
        body = '~ ראש\nהרי הם פ{סולין, משום ששחטן} מהם.\n'
        cur = ['<h2>ראש</h2>', 'הרי הם <b>פסולין</b>, משום ששחטן מהם.']
        out, probs = book(body, cur)
        self.assertEqual(out[3], 'הרי הם <b>פסולין, משום ששחטן</b> מהם.')
        out, probs = book(body, cur, {'keep': [[4, 'הרי הם פסולין']]})
        self.assertEqual((out[3], probs), (cur[1], []))
        _, probs = book(body, cur, {'keep': [[4, 'טקסט אחר']]})
        self.assertEqual(len(probs), 1)

    def test_unstable_lines_are_reported(self):
        conv = {'unbalanced': [], 'carried': []}
        probs = R.format_problems(conv, ['א'], {}, 10, ['ב'], [], {}, [0])
        self.assertEqual(probs, ['line 1: a second run would change it again'])


if __name__ == '__main__':
    unittest.main()
