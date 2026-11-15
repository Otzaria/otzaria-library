"""Offline regression tests: invalid corrections must not alter converter outputs."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import post_convert_fixes as P

def converter(source, filename, name):
    directory = REPO / source / 'סקריפטים'
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location(name, directory / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
TE = converter('ToratEmetToOtzaria', 'te_convert.py', 'te_write_test')

class OutputSafetyTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.book = self.root / 'ספר.txt'
        self.notes = self.root / 'הערות על ספר.txt'
        self.links_dir = self.root / 'links'
        self.links_dir.mkdir()
        self.links = self.links_dir / 'ספר_links.json'
        for n, path in enumerate((self.book, self.notes, self.links)):
            path.write_text(f'EXISTING OUTPUT {n}\n', encoding='utf-8')
        self.before = {p: p.read_bytes() for p in (self.book, self.notes, self.links)}

    def rules(self, target, old='עוגן', new='מתוקן'):
        (self.source / P.FILE_NAME).write_text('book\told\tnew\tnote\n' + f'{target}\t{old}\t{new}\tregression\n', encoding='utf-8')
        P._cache.pop(str(self.source / P.FILE_NAME), None)

    def unchanged(self):
        self.assertEqual({p: p.read_bytes() for p in self.before}, self.before)

    def torat_emet(self, text):
        source = self.root / 'input.txt'
        source.write_text('&UniqueId=1&CosmeticsType=\n$ ספר\n' + text, encoding='cp1255')
        with patch.object(TE, 'SOURCE_DIR', str(self.source)), patch.object(sys, 'argv', ['te_convert.py', source.name, '--src', str(self.root), '-o', str(self.book)]):
            TE.main()

    def test_single_book_errors_preserve_existing_output(self):
        self.rules('ספר')
        for writer in (self.torat_emet,):
            for text in ('טקסט אחר', 'עוגן עוגן'):
                with self.subTest(writer=writer.__name__, text=text), self.assertRaises(P.PostConvertFixError):
                    writer(text)
                self.unchanged()

    def test_single_book_errors_do_not_create_output(self):
        self.book.unlink()
        self.rules('ספר')
        for writer in (self.torat_emet,):
            with self.subTest(writer=writer.__name__), self.assertRaises(P.PostConvertFixError):
                writer('טקסט אחר')
            self.assertFalse(self.book.exists())

    def test_single_book_success_writes_corrected_text(self):
        self.rules('ספר')
        for writer in (self.torat_emet,):
            with self.subTest(writer=writer.__name__):
                writer('עוגן')
                self.assertIn('מתוקן', self.book.read_text(encoding='utf-8'))
                self.assertNotIn('עוגן', self.book.read_text(encoding='utf-8'))
if __name__ == '__main__':
    unittest.main()
