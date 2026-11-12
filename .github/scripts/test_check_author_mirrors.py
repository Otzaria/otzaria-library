"""check_author_mirrors: heAuthors / authorName מול metadata.json, לספרים הנארזים בלבד, ואזהרה בלבד."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from book_info_contract import EXTENDED_HEADER
from book_info_writer import HEADER, encode_rows
import check_author_mirrors as mirrors

DICTA = 'DictaToOtzaria/ערוך/ספרים/אוצריא/הלכה/'
MORE = 'MoreBooks/ספרים/אוצריא/הלכה/'


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True).stdout.decode()


class Repo:
    def __init__(self, tmp):
        self.root = Path(tmp)
        git(self.root, 'init', '-q', '-b', 'main')
        git(self.root, 'config', 'user.email', 'm@example.invalid')
        git(self.root, 'config', 'user.name', 'm')
        git(self.root, 'config', 'commit.gpgsign', 'false')

    def write(self, rel, text):
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def state(self, metadata, fordb, book_info, books, canonical=(), header=HEADER):
        self.write('metadata.json', '[\n' + ',\n'.join(
            json.dumps(m, ensure_ascii=False, separators=(',', ':')) for m in metadata) + '\n]\n')
        self.write('ForDB/all_metadata.json', json.dumps(fordb, ensure_ascii=False, indent=2) + '\n')
        self.write('ForDB/book_info.csv', encode_rows([header, *book_info]))
        self.write('all_metadata_with_file_paths.json', json.dumps(list(canonical), ensure_ascii=False) + '\n')
        for path in books:
            self.write(path, 'כותרת\nמחבר\n')
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '-m', 'state')
        return git(self.root, 'rev-parse', 'HEAD').strip()

    def find(self, rev='HEAD'):
        return mirrors.find_mismatches(mirrors.Snapshot(str(self.root), rev))

    def run(self, *args):
        out = io.StringIO()
        code = mirrors.main(list(args), str(self.root), out)
        return code, out.getvalue()


class AuthorMirrorsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = Repo(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_reports_stale_copies_of_packaged_books_only(self):
        metadata = [{'title': 'א', 'author': 'רבי משה סופר'},
                    {'title': 'ב', 'author': 'רבי יעקב'},
                    {'title': 'ג', 'author': 'רבי שלמה'},
                    {'title': 'ספריא', 'author': 'צורה ישנה שאינה נצרכת'},
                    {'title': 'שניים', 'authors': ['ראשון', 'שני']},
                    {'title': 'לא נארז', 'author': 'רבי'}]
        fordb = [{'title': 'א', 'heAuthors': ['רבי משה ב"ר שמואל סופר'], 'Sourcefolder': 'Dicta'},
                 {'title': 'ב', 'heAuthors': ['רבי יַעֲקב‏'], 'Sourcefolder': 'Dicta'},
                 {'title': 'ג', 'heAuthors': None, 'Sourcefolder': 'MoreBooks'},
                 {'title': 'שניים', 'heAuthors': ['ראשון', 'שני'], 'Sourcefolder': 'Dicta'},
                 {'title': 'לא נארז', 'heAuthors': ['אחר'], 'Sourcefolder': 'Dicta'}]
        book_info = [['א', 'רבי משה סופר', 'אחרונים', '', '', ''],
                     ['ב', 'יעקב', 'אחרונים', '', '', ''],
                     ['ג', '', 'אחרונים', '', '', ''],
                     ['ספריא', 'שם אחר', 'אחרונים', '', '', '']]
        books = [DICTA + 'א.txt', DICTA + 'ב.txt', MORE + 'ג.txt', DICTA + 'שניים.txt', DICTA + 'ספריא.txt',
                 'extraBooks/ספרים/אוצריא/לא נארז.txt']
        canonical = [{'title': 'ספריא', 'Sourcefolder': 'sefaria'}]
        self.repo.state(metadata, fordb, book_info, books, canonical)
        self.assertEqual(self.repo.find(), [
            ('ForDB/all_metadata.json', 'א', 'רבי משה ב"ר שמואל סופר', 'רבי משה סופר'),
            ('ForDB/all_metadata.json', 'ג', '', 'רבי שלמה'),
            ('ForDB/book_info.csv', 'ב', 'יעקב', 'רבי יעקב'),
        ])
        code, out = self.repo.run()
        self.assertEqual(code, 0)
        self.assertEqual(out.count('::warning file='), 3)
        self.assertIn('ForDB/all_metadata.json: 2, ForDB/book_info.csv: 1', out)

    def test_an_eleven_column_book_info_is_read_by_its_base_columns(self):
        metadata = [{'title': 'א', 'author': 'רבי משה סופר'}]
        book_info = [['א', 'משה סופר', 'אחרונים', '', '', '', 'הלכה', '', '', 'תיאור\nבשתי שורות', '1']]
        self.repo.state(metadata, [], book_info, [DICTA + 'א.txt'], header=EXTENDED_HEADER)
        self.assertEqual(self.repo.find(), [('ForDB/book_info.csv', 'א', 'משה סופר', 'רבי משה סופר')])

    def test_a_record_of_another_source_is_another_book(self):
        # רשומת דיקטה ישנה בשם שהספר הנארז שלו הוא עכשיו של מקור אחר
        metadata = [{'title': 'אגרת', 'author': 'רבי שניאור זלמן'}]
        fordb = [{'title': 'אגרת', 'heAuthors': ['רבי יונה'], 'Sourcefolder': 'Dicta'},
                 {'title': 'אגרת', 'heAuthors': ['רבי שניאור זלמן'], 'Sourcefolder': 'OnYourWay'}]
        self.repo.state(metadata, fordb, [], ['OnYourWayToOtzaria/ספרים/אוצריא/חסידות/אגרת.txt'])
        self.assertEqual(self.repo.find(), [])

    def test_last_metadata_entry_wins_and_titles_match_exactly(self):
        metadata = [{'title': 'א', 'author': 'ראשון'}, {'title': 'א', 'author': 'אחרון'}, {'title': ' ב', 'author': 'x'}]
        fordb = [{'title': 'א', 'heAuthors': ['אחרון'], 'Sourcefolder': 'Dicta'},
                 {'title': 'ב', 'heAuthors': ['y'], 'Sourcefolder': 'Dicta'}]
        self.repo.state(metadata, fordb, [], [DICTA + 'א.txt', DICTA + 'ב.txt'])
        self.assertEqual(self.repo.find(), [])

    def test_db_spelled_copies_are_compared(self):
        metadata = [{'title': "שות מהרי''ק", 'author': 'רבי יוסף'}]
        fordb = [{'title': 'שות מהרי״ק', 'heAuthors': ['יוסף'], 'Sourcefolder': 'Dicta'}]
        self.repo.state(metadata, fordb, [], [DICTA + "שות מהרי''ק.txt"])
        self.assertEqual(self.repo.find(), [('ForDB/all_metadata.json', 'שות מהרי״ק', 'יוסף', 'רבי יוסף')])

    def test_gershayim_are_not_folded(self):
        metadata = [{'title': 'א', 'author': 'רמב"ן'}]
        fordb = [{'title': 'א', 'heAuthors': ['רמב״ן'], 'Sourcefolder': 'Dicta'}]
        self.repo.state(metadata, fordb, [], [DICTA + 'א.txt'])
        self.assertEqual(len(self.repo.find()), 1)

    def test_only_differences_new_since_the_base_are_annotated(self):
        metadata = [{'title': 'א', 'author': 'רבי א'}, {'title': 'ב', 'author': 'רבי ב'}]
        books = [DICTA + 'א.txt', DICTA + 'ב.txt']
        base = self.repo.state(metadata, [{'title': 'א', 'heAuthors': ['ישן'], 'Sourcefolder': 'Dicta'},
                                          {'title': 'ב', 'heAuthors': ['רבי ב'], 'Sourcefolder': 'Dicta'}], [], books)
        self.repo.state(metadata, [{'title': 'א', 'heAuthors': ['ישן'], 'Sourcefolder': 'Dicta'},
                                   {'title': 'ב', 'heAuthors': ['חדש%\nשורה'], 'Sourcefolder': 'Dicta'}], [], books)
        code, out = self.repo.run('--base', '0' * 40, '--base', base)
        self.assertEqual(code, 0)
        self.assertEqual(out.count('::warning file='), 1)
        self.assertIn("ב: 'חדש%25%0Aשורה' != 'רבי ב'", out)
        self.assertIn('1 new since', out)

    def test_a_crash_of_the_check_fails(self):
        code, out = self.repo.run()  # an empty repository: no HEAD
        self.assertEqual(code, 2)
        self.assertIn('::error title=Author mirrors::', out)


if __name__ == '__main__':
    unittest.main()
