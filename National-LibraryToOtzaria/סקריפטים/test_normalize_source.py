# -*- coding: utf-8 -*-
"""בדיקות ל-normalize_source: שבירת שורה בטקסט = רווח, ליד תג = כמו בפרסר הישן."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from normalize_source import normalize_source_html


CASES = [
    ('\N{HEBREW LETTER SHIN}''\N{HEBREW LETTER RESH}\N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH} \N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH}''', '\N{HEBREW LETTER SHIN}''\N{HEBREW LETTER RESH}\N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH} \N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH}'''),
    # '' בין אותיות = גרשיים; אחרי מילה = סוגר ציטוט
    ('\N{HEBREW LETTER AYIN}\'\'\N{HEBREW LETTER SHIN} \N{HEBREW LETTER AYIN}\'\'', '\N{HEBREW LETTER AYIN}"\N{HEBREW LETTER SHIN} \N{HEBREW LETTER AYIN}\'\''),
    # שבירת שורה אמיתית בתוך טקסט
    ('אתכם\nשרבנו מביא', 'אתכם שרבנו מביא'),
    ('בשכר,\nנותן לו', 'בשכר, נותן לו'),
    ('מותר\r\nללמד', 'מותר ללמד'),
    ('מותר ללמד', 'מותר ללמד'),
    ('א\n\nב', 'א ב'),
    # כבר יש רווח לצד השבירה — נשאר רווח אחד לפחות (הכיווץ נעשה ב-clean_hidden_chars)
    ('מילה \nמילה', 'מילה  מילה'),
    ('מילה\n מילה', 'מילה  מילה'),
    # גבול בין תגים — הדפסה יפה, נמחק
    ('<b>א</b>\n<i>ב</i>', '<b>א</b><i>ב</i>'),
    ('</span>\n<span class="B">\nשידע </span>', '</span><span class="B">שידע </span>'),
    ('<br/>\n\n</span>', '<br/></span>'),
    ('<span class="">\nכמו', '<span class="">כמו'),
    # שבירה צמודה לתג מצד אחד בלבד — לא נוגעים ברווח של הטקסט
    ('מותר \n</span>', 'מותר </span>'),
    # קצוות
    ('\nטקסט', 'טקסט'),
    ('טקסט\n', 'טקסט'),
    ('', ''),
    (None, ''),
]


def main() -> None:
    failed = 0
    for raw, expected in CASES:
        got = normalize_source_html(raw)
        if got != expected:
            failed += 1
            print(f'FAIL: {raw!r}\n  expected {expected!r}\n  got      {got!r}')
    if failed:
        raise SystemExit(f'{failed} failed')
    print(f'OK: {len(CASES)} cases')


if __name__ == '__main__':
    main()
