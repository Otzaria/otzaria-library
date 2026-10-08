"""בדיקות ל-colon_breaks: איחוד רק כשהנקודותיים באמצע משפט, גם כשהעד אומר "אותה פסקה".

  python -X utf8 -m pytest .claude/skills/dicta-book-pipeline/scripts/test_colon_breaks.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import colon_breaks as CB  # noqa: E402
import dbs_breaks as D  # noqa: E402


class SameParagraph:
    """עד שאומר "join" לכל זוג שורות (פסקאות דיקטה גדולות מכילות כמה ד"ה וציטוטים)."""

    def joined(self, A, B):
        return 'join'


class ProcessColon(unittest.TestCase):
    def run_process(self, body):
        lines = ['<h1>ס</h1>', 'מחבר'] + body
        with tempfile.TemporaryDirectory() as d:
            old = D.REPO
            D.REPO = d
            try:
                open(os.path.join(d, 'b.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
                r, _ = CB.process('b.txt', SameParagraph(), True)
                return open(os.path.join(d, 'b.txt'), encoding='utf-8').read().split('\n')[2:], r
            finally:
                D.REPO = old

    def test_dibbur_opening_not_joined(self):
        body = ['וזה ברור:', 'ד"ה ומה שכתב', 'ודו"ק:', '<b>בד"ה</b> אלא']
        out, r = self.run_process(body)
        self.assertEqual((out, r['merged']), (body, 0))

    def test_quote_paragraph_not_joined(self):
        body = ['כדברי הב"י ז"ל:', 'ולענין הלכה', 'וכתב וז"ל:', 'אסור להראות סכין לחכם']
        out, r = self.run_process(body)
        self.assertEqual((out, r['merged']), (body, 0))

    def test_open_parenthesis_joined_only_when_it_closes(self):
        body = ['ובפסחים (הגה"ה:', 'ולכאורה יש', 'כמו שכתבו התוס\' (דף:', 'פ"ו ע"א) בד"ה']
        out, r = self.run_process(body)
        self.assertEqual(out, body[:2] + ['כמו שכתבו התוס\' (דף: פ"ו ע"א) בד"ה'])
        self.assertEqual(r['merged'], 1)


if __name__ == '__main__':
    unittest.main()
