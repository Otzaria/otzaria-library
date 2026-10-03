"""Exercise actual importer/installer entrypoints against complete offline registries."""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from book_info_writer import HEADER, encode_rows, plan_registration, apply_registration

ROOT = Path(__file__).resolve().parents[2]
INSTALLERS = ['MoreBooks/אוצר ההלכה - סקריפטים/install.py',
              'MoreBooks/משנה הלכות - סקריפטים/install.py',
              'MoreBooks/משלי עם הגרא ורבינו יונה - סקריפטים/install.py']


def load_script(relative):
    spec = importlib.util.spec_from_file_location('writer_integration', ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WriterTest(unittest.TestCase):
    def test_additive_registration_blank_fallback_coauthors_sort_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ForDB/book_info.csv'
            path.parent.mkdir()
            existing = [['קיים', 'אחד', 'ראשונים', 'ערך', '100', '200'],
                        ['קיים', 'שני', 'מחברי זמננו', '', '', '']]
            path.write_text(encode_rows([HEADER, *existing]), encoding='utf-8')
            entries = [['קיים', '', 'אחרונים', '', '', ''], ['קיים', 'אחד', 'אחרונים', '', '', ''],
                       ['חדש', 'שלישי', 'אחרונים', '', '', '']]
            apply_registration(tmp, plan_registration(tmp, entries))
            rows = list(csv.reader(io.StringIO(path.read_text(), newline='')))
            self.assertEqual(rows, [HEADER, entries[2], *existing])
            self.assertEqual(plan_registration(tmp, entries), {})

    def test_missing_new_source_is_not_created_from_empty_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'ForDB').mkdir()
            (Path(tmp) / 'ForDB/generations.csv').write_text('שם ספר,קבוצת דור\nישן,ראשונים\n')
            with self.assertRaises(FileNotFoundError):
                plan_registration(tmp, [['חדש', '', 'ראשונים', '', '', '']])
            self.assertFalse((Path(tmp) / 'ForDB/book_info.csv').exists())

    def test_production_installers_with_and_without_legacy_source(self):
        for relative in INSTALLERS:
            for legacy in (False, True):
                with self.subTest(script=relative, legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                    module = load_script(relative)
                    repo = Path(tmp) / 'repo'
                    source = Path(tmp) / 'src'
                    source.mkdir()
                    (repo / 'ForDB').mkdir(parents=True)
                    module.REPO = str(repo)
                    module.BOOK_DIR = str(repo / 'packaged')
                    module.TANAKH = str(repo / 'packaged')
                    module.LINKS_DIR = str(repo / 'links')
                    (repo / 'links').mkdir()
                    if hasattr(module, 'BOOKS'):
                        books = list(module.BOOKS)
                        author = module.BOOKS[books[0]]['author']
                        for b in module.BOOKS.values():
                            (repo / 'packaged' / b['dir']).mkdir(parents=True, exist_ok=True)
                        for title in books:
                            (source / (title + '_links.json')).write_text('[]\n')
                    else:
                        books = [f'כרך {i:02}' for i in range(17)]
                        author = module.AUTHOR
                    for title in books:
                        (source / (title + '.txt')).write_text('<h1>' + title + '</h1>\nתוכן\n')
                    (repo / 'metadata.json').write_text('[\n\n]\n')
                    (repo / 'ForDB/all_metadata.json').write_text('[]\n')
                    (repo / 'ForDB/sefaria_metadata_changes.csv').write_text(encode_rows([['categoryPath', 'title', 'author', 'heShortDesc', 'heDesc', 'heDescNew']]))
                    existing = [[books[0], author, 'ראשונים', 'ישן', '100', '200'],
                                [books[0], 'עורך נוסף', 'אחרונים', '', '300', '400']]
                    existing.sort(key=lambda r: tuple(r[:2]))
                    info = repo / 'ForDB/book_info.csv'
                    info.write_text(encode_rows([HEADER, *existing]))
                    if legacy:
                        (repo / 'ForDB/generations.csv').write_text('שם ספר,קבוצת דור\n')
                    with patch.object(sys, 'argv', ['install.py', '--src', str(source), '--apply']), contextlib.redirect_stdout(io.StringIO()):
                        module.main()
                    rows = list(csv.reader(io.StringIO(info.read_text(), newline='')))
                    self.assertEqual(rows[0], HEADER)
                    self.assertEqual(rows[1:], sorted(rows[1:], key=lambda r: tuple(r[:2])))
                    for record in existing:
                        self.assertIn(record, rows)
                    self.assertEqual({r[0] for r in rows[1:]}, set(books))
                    self.assertTrue(all(len(r) == 6 for r in rows))
                    before = info.read_bytes()
                    with patch.object(sys, 'argv', ['install.py', '--src', str(source), '--apply']), contextlib.redirect_stdout(io.StringIO()):
                        module.main()
                    self.assertEqual(info.read_bytes(), before)
                    self.assertEqual((repo / 'ForDB/generations.csv').exists(), legacy)

    def test_production_make_metadata_prints_and_registers_six_fields_per_author(self):
        module = load_script('.claude/skills/otzaria-book-format/scripts/make_metadata.py')
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / 'ForDB/book_info.csv'
            info.parent.mkdir()
            info.write_text(encode_rows([HEADER]))
            output = io.StringIO()
            argv = ['make_metadata.py', '--title', 'ספר', '--author', 'מחבר א', '--author', 'מחבר ב',
                    '--generation', 'ראשונים', '--book-info-csv', str(info), '--print-fordb']
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                self.assertEqual(module.main(), 0)
            rows = list(csv.reader(io.StringIO(info.read_text(), newline='')))
            self.assertEqual(rows[1:], [['ספר', 'מחבר א', 'ראשונים', '', '', ''], ['ספר', 'מחבר ב', 'ראשונים', '', '', '']])
            for row in rows[1:]:
                self.assertIn(encode_rows([row]).strip(), output.getvalue())


if __name__ == '__main__':
    unittest.main()
