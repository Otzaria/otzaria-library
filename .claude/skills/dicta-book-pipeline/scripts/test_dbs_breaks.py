"""בדיקות ל-dbs_breaks: מיפוי שורות אחרי איחוד והזזת קבצי links בלי לשנות עיצוב.

  python -X utf8 -m pytest .claude/skills/dicta-book-pipeline/scripts/test_dbs_breaks.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbs_breaks as D  # noqa: E402


class FakeRaw:
    """עד שאומר "join" לכל זוג שורות."""

    def joined(self, A, B):
        return 'join'

    def heading_status(self, h, b):
        return 'skip', None

    def heading_midline(self, h):
        return False


class ShiftLinksText(unittest.TestCase):
    def test_maps_own_and_target_keeping_format(self):
        text = ('[\n  {\n    "line_index_1": 4,\n    "line_index_2": 9,\n'
                '    "path_2": "x/ספר.txt",\n    "Conection Type": "commentary"\n  }\n]\n')
        linemap = [0, 1, 2, 2, 3, 4, 5, 6, 7]   # שורה 4 אוחדה לתוך 3
        own, n = D.shift_links_text(text, linemap, ('line_index_1',))
        self.assertEqual(n, 1)
        self.assertEqual(own, text.replace('"line_index_1": 4', '"line_index_1": 3'))
        tgt, n = D.shift_links_text(text, linemap, ('line_index_2',), 'ספר')
        self.assertEqual(tgt, text.replace('"line_index_2": 9', '"line_index_2": 8'))
        other, n = D.shift_links_text(text, linemap, ('line_index_2',), 'אחר')
        self.assertEqual((other, n), (text, 0))


class ProcessMerge(unittest.TestCase):
    def run_process(self, lines, pinned=frozenset()):
        with tempfile.TemporaryDirectory() as d:
            old = D.REPO
            D.REPO = d
            try:
                open(os.path.join(d, 'b.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
                r = D.process('b.txt', FakeRaw(), True, pinned)
                return open(os.path.join(d, 'b.txt'), encoding='utf-8').read().split('\n'), r
            finally:
                D.REPO = old

    def test_merges_and_maps(self):
        out, r = self.run_process(['<h1>ס</h1>', '<h2>א</h2>', 'אחת', 'שתיים', 'שלוש ארבע.', 'חמש'])
        self.assertEqual(out, ['<h1>ס</h1>', '<h2>א</h2>', 'אחת שתיים שלוש ארבע.', 'חמש'])
        self.assertEqual(r['linemap'], [0, 1, 2, 2, 2, 3])

    def test_two_linked_lines_are_not_merged(self):
        out, r = self.run_process(['<h1>ס</h1>', 'אחת שתיים', 'שלוש ארבע.'], pinned={1, 2})
        self.assertEqual(out, ['<h1>ס</h1>', 'אחת שתיים', 'שלוש ארבע.'])
        self.assertEqual(r['merged'], 0)


class DbsParagraphs(unittest.TestCase):
    """שורות COR הן שורות דפוס; פסקה נגמרת בשורה קצרה, בסימן 0xFE או בסוף יחידה."""

    def test_wrap_lines_join_short_line_ends(self):
        wide = 'א' * 60
        unit = '\n'.join([wide, wide, 'סוף', wide, 'קצר'])
        self.assertEqual(D.dbs_paragraphs([unit, 'יחידה']),
                         [' '.join([wide, wide, 'סוף']), wide + ' קצר', 'יחידה'])

    def test_block_mark_ends_wide_line(self):
        wide = 'ב' * 60
        unit = '\n'.join([wide + D.BLOCK_MARK, wide, 'ג'])
        self.assertEqual(D.dbs_paragraphs([unit]), [wide, wide + ' ג'])

    def test_witness_joins_across_wrap_only(self):
        wide = ' '.join(['מילה%d' % i for i in range(12)])
        unit = '\n'.join([wide + ' אחת שתיים שלוש', 'ארבע חמש שש ' + wide, 'קצר כאן',
                          'שבע שמונה תשע'])
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, 'raw.txt')
            open(rp, 'w', encoding='utf-8').write('\n'.join(D.dbs_paragraphs([unit])))
            ri = D.RawIndex(rp)
        self.assertEqual(ri.joined(['אחת', 'שתיים', 'שלוש'], ['ארבע', 'חמש', 'שש']), 'join')
        self.assertEqual(ri.joined(['מילה11', 'קצר', 'כאן'], ['שבע', 'שמונה', 'תשע']), 'break')


if __name__ == '__main__':
    unittest.main()
