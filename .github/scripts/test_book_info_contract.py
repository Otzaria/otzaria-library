"""book_info.csv: six- or eleven-column header, and the book-level extension fields."""
import csv
import io
from pathlib import Path
import tempfile
import unittest

from book_info_contract import EXTENDED_HEADER, EXTENSION, HEADER, split_topics, validate_book_info
from book_info_writer import encode_rows, plan_registration

DESCRIPTION = 'שורה ראשונה עם "מירכאות", ופסיק\nשורה שנייה\n\nאחרי שורה ריקה'
EXTENDED = ['הלכה; מנהג', 'תרפ"ה', 'וילנא', DESCRIPTION, '1']


def source(header, *rows):
    """Like the website: unquoted header, every record QUOTE_ALL, LF."""
    return (','.join(header) + '\n' + encode_rows(rows)).encode('utf-8')


class ContractTest(unittest.TestCase):
    def test_six_columns_pass(self):
        rows = validate_book_info(source(HEADER, ['ספר', 'מחבר', 'ראשונים', '', '100', '200']))
        self.assertEqual(rows[0], HEADER)

    def test_eleven_columns_pass_with_shared_values_across_coauthors(self):
        rows = validate_book_info(source(EXTENDED_HEADER,
                                         ['ספר', 'א', 'ראשונים', '', '', '', *EXTENDED],
                                         ['ספר', 'ב', 'ראשונים', '', '', '', *EXTENDED],
                                         ['אחר', '', '', '', '', '', '', '', '', '', '']))
        self.assertEqual(rows[1][len(HEADER):], EXTENDED)

    def test_any_other_header_fails(self):
        for header in (HEADER[:-1], HEADER + ['topics'], HEADER + ['topic', *EXTENSION[1:]],
                       HEADER + EXTENSION[::-1], EXTENDED_HEADER + ['extra'], [HEADER[1], HEADER[0], *HEADER[2:]]):
            with self.subTest(header=header), self.assertRaises(ValueError):
                validate_book_info(source(header))

    def test_record_width_must_match_the_header(self):
        for header, row in ((HEADER, ['ספר', '', '', '', '', '', '']),
                            (EXTENDED_HEADER, ['ספר', '', '', '', '', ''])):
            with self.subTest(width=len(header)), self.assertRaises(ValueError):
                validate_book_info(source(header, row))

    def test_conflicting_rows_of_one_book_fail(self):
        for index in range(len(EXTENSION)):
            other = list(EXTENDED)
            other[index] = ''
            with self.subTest(field=EXTENSION[index]), self.assertRaises(ValueError):
                validate_book_info(source(EXTENDED_HEADER, ['ספר', 'א', '', '', '', '', *EXTENDED],
                                          ['ספר', 'ב', '', '', '', '', *other]))

    def test_field_limits(self):
        valid = {'topics': ';'.join(f'נושא {i}' for i in range(10)) + '; נושא 0 ;;', 'pubDate': 'ת' * 100,
                 'pubPlace': 'ת' * 100, 'description': 'ת' * 4000, 'proofread': ''}
        invalid = {'topics': [';'.join(f'נושא {i}' for i in range(11)), 'ת' * 61, 'א\nב'],
                   'pubDate': ['ת' * 101, 'א\nב'], 'pubPlace': ['ת' * 101, 'א\nב'],
                   'description': ['ת' * 4001], 'proofread': ['0', '2', 'כן', ' 1']}
        row = ['ספר', '', '', '', '', '']
        validate_book_info(source(EXTENDED_HEADER, row + [valid[name] for name in EXTENSION]))
        for name, values in invalid.items():
            for value in values:
                fields = [value if n == name else valid[n] for n in EXTENSION]
                with self.subTest(field=name, value=value[:20]), self.assertRaises(ValueError):
                    validate_book_info(source(EXTENDED_HEADER, row + fields))

    def test_carriage_return_in_a_description_fails(self):
        with self.assertRaises(ValueError):
            validate_book_info(source(EXTENDED_HEADER, ['ספר', '', '', '', '', '', '', '', '', 'א\r\nב', '']))

    def test_topics_are_trimmed_deduplicated_and_empty_values_dropped(self):
        self.assertEqual(split_topics(' הלכה ;מנהג;; הלכה; '), ['הלכה', 'מנהג'])


class WriterFormatTest(unittest.TestCase):
    def plan(self, data, entries):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ForDB/book_info.csv'
            path.parent.mkdir()
            path.write_bytes(data)
            return plan_registration(tmp, entries).get('ForDB/book_info.csv', data)

    def test_a_six_column_file_stays_six_columns(self):
        data = source(HEADER, ['ספר', 'א', 'ראשונים', '', '', ''])
        written = self.plan(data, [['חדש', 'ב', 'אחרונים', '', '', '']])
        rows = validate_book_info(written)
        self.assertEqual(rows[0], HEADER)
        self.assertEqual(rows[1], ['חדש', 'ב', 'אחרונים', '', '', ''])

    def test_an_eleven_column_file_keeps_its_records_and_new_rows_copy_the_book_fields(self):
        existing = ['ספר', 'א', 'ראשונים', '', '', '', *EXTENDED]
        data = source(EXTENDED_HEADER, existing)
        written = self.plan(data, [['ספר', 'ב', 'ראשונים', '', '', ''], ['חדש', 'ג', 'אחרונים', '', '', '']])
        self.assertIn(encode_rows([existing]).encode('utf-8'), written)
        rows = validate_book_info(written)
        self.assertEqual(rows, [EXTENDED_HEADER, ['חדש', 'ג', 'אחרונים', '', '', '', '', '', '', '', ''],
                                existing, ['ספר', 'ב', 'ראשונים', '', '', '', *EXTENDED]])
        self.assertTrue(written.startswith((','.join(EXTENDED_HEADER) + '\n').encode('utf-8')))

    def test_a_multiline_description_round_trips(self):
        data = source(EXTENDED_HEADER, ['ספר', 'א', '', '', '', '', *EXTENDED])
        self.assertEqual(self.plan(data, [['ספר', 'א', 'אחרונים', '', '', '']]), data)
        reread = list(csv.reader(io.StringIO(data.decode('utf-8'), newline='')))
        self.assertEqual(reread[1][EXTENDED_HEADER.index('description')], DESCRIPTION)
        self.assertEqual(encode_rows(reread[1:]).encode('utf-8'), data.split(b'\n', 1)[1])


if __name__ == '__main__':
    unittest.main()
