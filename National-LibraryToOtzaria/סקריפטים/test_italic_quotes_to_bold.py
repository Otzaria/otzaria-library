# -*- coding: utf-8 -*-
"""בדיקות להדגשת ציטוטי הרמב"ם: span_styles (המרה מהאתר) ו-italic_quotes_to_bold (הספרים במאגר)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from italic_quotes_to_bold import fix_text
from span_styles import apply_span_styles

H = '<span style="color:#1B1464">'

# (קלט מהאתר, notes_in_z, פלט צפוי)
SPAN_CASES = [
    ('<span class="Z">כל מי שנאמר בו</span> וכו', False, '<b>כל מי שנאמר בו</b> וכו'),
    ('<span class="B Z">וכן כל הפסול</span>', False, '<b>וכן כל הפסול</b>'),
    ('<span class="H Z">ע"א אינה בטלה</span>', False, f'{H}<b>ע"א אינה בטלה</b></span>'),
    ('<span class="Z S">ציור</span>', False, '<b><small>ציור</small></b>'),
    ('<span class="B">ומ"ש <span class="Z">וכל העושה</span></span>', False, '<b>ומ"ש וכל העושה</b>'),
    ('<span class="B">כתב</span>', False, '<b>כתב</b>'),
    ('<span class="Z">(א) רש"ס דף ז\' ב\':</span>', True, '<i>(א) רש"ס דף ז\' ב\':</i>'),
    ('<span class="Z">לה) שטמ"ק כתובות</span>', True, '<i>לה) שטמ"ק כתובות</i>'),
    ('<span class="Z">במראה הנבואה.</span> עי\'', True, '<b>במראה הנבואה.</b> עי\''),
    ('<span class="Z">(א) בדמות הצורה.</span>', False, '<b>(א) בדמות הצורה.</b>'),
]

# (שורה במאגר, notes_in_z, שורה צפויה, מספר תגי <i> שהשתנו)
LINE_CASES = [
    ('<i>כשיעמוד נכרי וכו\' עכ"ל. </i>והוא בסוגיא', False, '<b>כשיעמוד נכרי וכו\' עכ"ל. </b>והוא בסוגיא', 1),
    ('<b>כתב</b> הרמב"ם וז"ל: <i>כל מי</i> ע"כ.', False, '<b>כתב</b> הרמב"ם וז"ל: <b>כל מי</b> ע"כ.', 1),
    ('<b>באמצע ההלכה </b><b><i>וכן כל הפסול,</i></b><b> ע"כ:</b>', False,
     '<b>באמצע ההלכה </b><b>וכן כל הפסול,</b><b> ע"כ:</b>', 1),
    (f'{H}שורש תקרובת </span><i>ע"א אינה בטלה.</i>', False, f'{H}שורש תקרובת </span><b>ע"א אינה בטלה.</b>', 1),
    (f'{H}<i>שם</i></span>', False, f'{H}<b>שם</b></span>', 1),
    ('<b><i><small>ציור</small></i></b>', False, '<b><small>ציור</small></b>', 1),
    ('<i>היה </i><i>התלם הזה</i>', False, '<b>היה </b><b>התלם הזה</b>', 2),
    ('<i>(א) רש"ס דף ז\' ב\': </i><br/><i>(ב) הרמב"ן</i>', True, '<i>(א) רש"ס דף ז\' ב\': </i><br/><i>(ב) הרמב"ן</i>', 0),
    ('<br/> <i>*</i> <i>במראה הנבואה.</i> עי\'', True, '<br/> <b>*</b> <b>במראה הנבואה.</b> עי\'', 2),
    ('<i>(ס"ד) רש"ס</i><i>ח) שם</i>', True, '<i>(ס"ד) רש"ס</i><i>ח) שם</i>', 0),
    ('<i>(א) רש"ס</i>', False, '<b>(א) רש"ס</b>', 1),
    ('בלי תגים', False, 'בלי תגים', 0),
]

MALFORMED = ['<i>פתוח', '<i>א</b>', 'א</i>']


def main() -> None:
    failures = []

    for src, notes, want in SPAN_CASES:
        got = apply_span_styles(src, notes)
        if got != want:
            failures.append(f'  span_styles:\n    קלט : {src}\n    צפוי: {want}\n    בפועל: {got}')

    for src, notes, want, want_count in LINE_CASES:
        got, count = fix_text(src, notes)
        if got != want or count != want_count:
            failures.append(
                f'  italic_quotes_to_bold:\n    קלט : {src}\n    צפוי: {want} ({want_count})\n    בפועל: {got} ({count})'
            )

    for src in MALFORMED:
        try:
            fix_text(src)
        except ValueError:
            continue
        failures.append(f'  היה צריך להיכשל על תגים שבורים: {src}')

    total = len(SPAN_CASES) + len(LINE_CASES) + len(MALFORMED)
    if failures:
        print(f'נכשלו {len(failures)} מתוך {total}:')
        print('\n'.join(failures))
        sys.exit(1)
    print(f'כל {total} הבדיקות עברו')


if __name__ == '__main__':
    main()
