# -*- coding: utf-8 -*-
"""בדיקות לכללי הרווחים של fix_missing_spaces."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fix_missing_spaces import fix_text


CASES_CHANGED = [
    ('<b>וראיתי</b>להרב', '<b>וראיתי</b> להרב'),
    ('<i>והנה</i>כתב', '<i>והנה</i> כתב'),
    ('<small>אמרתי</small>להוסיף', '<small>אמרתי</small> להוסיף'),
    ('<span>*)</span>וכן', '<span>*)</span> וכן'),
    ('<br/><b>ב</b>וכמה', '<br/><b>ב</b> וכמה'),
    ('<h4><b>א</b>כל', '<h4><b>א</b> כל'),
    ('<b>א</b>מצרים', '<b>א</b> מצרים'),
    ('<i>דשן</i><i>המזבח', '<i>דשן</i> <i>המזבח'),
    ("<b>וכו'.</b><i>ואשר", "<b>וכו'.</b> <i>ואשר"),
    ('<br/><b>[ו]</b><b>האוכל', '<br/><b>[ו]</b> <b>האוכל'),
    ('<span style="color:#999">*)</span><span style="color:#999">וכן', '<span style="color:#999">*)</span> <span style="color:#999">וכן'),
]

CASES_UNCHANGED = [
    'בתוך <b>מ</b>מצרים',
    'שצ"ל<b>וזהו</b>',
    '<b>שלום </b>וישע',
    '<b></b>מילה',
    '<b>text</b>מילה',
    '<small>עיין [</small><small>פרשה',
    'ו<i>אמר</i><i>ו',
]


def main() -> None:
    failures = []

    for src, want in CASES_CHANGED:
        got, count = fix_text(src)
        if got != want or count != 1:
            failures.append(
                f'  שינוי שגוי:\n    קלט : {src}\n    צפוי: {want}\n    בפועל: {got} (count={count})'
            )

    for src in CASES_UNCHANGED:
        got, count = fix_text(src)
        if got != src or count != 0:
            failures.append(
                f'  היה צריך להישאר ללא שינוי:\n    קלט : {src}\n    בפועל: {got} (count={count})'
            )

    for src, _ in CASES_CHANGED:
        once, _ = fix_text(src)
        twice, count = fix_text(once)
        if twice != once or count != 0:
            failures.append(f'  אינו אידמפוטנטי: {src}')

    total = len(CASES_CHANGED) + len(CASES_UNCHANGED) + len(CASES_CHANGED)
    if failures:
        print(f'נכשלו {len(failures)} בדיקות:')
        print('\n'.join(failures))
        sys.exit(1)
    print(f'כל {total} הבדיקות עברו')


if __name__ == '__main__':
    main()
