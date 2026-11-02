# -*- coding: utf-8 -*-
"""תיקון חד-פעמי: ציטוטי הרמב"ם בספרי יד הרמב"ם מודגשים ולא נטויים.

ההמרה הפכה את מחלקת Z של האתר (ציטוט מדברי הרמב"ם) ל-<i>; מעכשיו parser.py
כותב <b> (ראו span_styles.py). הסקריפט מחיל את אותו כלל על הספרים שכבר במאגר:

* <i> הופך ל-<b>, ו-<b> שנמצא בתוך <b> אחר נפתח (<b><i>X</i></b> → <b>X</b>).
* ב"שקל הקודש" קטע נטוי שנפתח בסימן הערה ("(א) רש"ס...") נשאר נטוי.
* רק תגים משתנים: הטקסט ומספר השורות נשארים כמו שהם, ולכן הקישורים לא זזים.
"""

import re
import sys
from pathlib import Path

from span_styles import NOTE_MARKER, NOTES_IN_Z

TAG = re.compile(r'<(/?)([a-z0-9]+)(?:\s[^>]*)?(/?)>')
VOID = {'br'}


def fix_text(text: str, notes_in_z: bool = False) -> tuple[str, int]:
    """מחזיר את השורה המתוקנת ואת מספר תגי <i> שהשתנו."""
    out = []
    stack = []  # (שם מקורי, שם בפלט או None אם התג הושמט)
    pos = count = 0
    for m in TAG.finditer(text):
        out.append(text[pos:m.start()])
        pos = m.end()
        closing, name, self_closing = m.group(1), m.group(2), m.group(3)
        if name in VOID or self_closing:
            out.append(m.group(0))
            continue
        if closing:
            if not stack or stack[-1][0] != name:
                raise ValueError(f'תג סוגר </{name}> לא תואם במיקום {m.start()}')
            _, emitted = stack.pop()
            if emitted:
                out.append(f'</{emitted}>')
            continue
        emitted, tag = name, m.group(0)
        if name == 'i':
            if notes_in_z and NOTE_MARKER.match(re.sub(r'^(?:<[^>]+>)+', '', text[m.end():])):
                stack.append((name, name))
                out.append(tag)
                continue
            count += 1
            emitted, tag = 'b', '<b>'
        if emitted == 'b' and any(e == 'b' for _, e in stack):
            emitted, tag = None, ''
        stack.append((name, emitted))
        out.append(tag)
    out.append(text[pos:])
    if stack:
        raise ValueError(f'תגים שלא נסגרו: {[n for n, _ in stack]}')
    return ''.join(out), count


def main() -> None:
    roots = [Path(p) for p in sys.argv[1:]]
    total = files_changed = 0
    for root in roots:
        for p in sorted(root.rglob('*.txt')):
            notes_in_z = p.stem in NOTES_IN_Z
            lines = p.read_text(encoding='utf-8').split('\n')
            n = 0
            for i, line in enumerate(lines):
                if '<i>' in line:
                    lines[i], c = fix_text(line, notes_in_z)
                    n += c
            if n:
                p.write_text('\n'.join(lines), encoding='utf-8')
                files_changed += 1
                total += n
                print(f'{n}\t{p}')
    print(f'--- files: {files_changed}, tags: {total}')


if __name__ == '__main__':
    main()
