# -*- coding: utf-8 -*-
"""תיקון חד-פעמי: רווח חסר אחרי תגי עיצוב סוגרים בספרי ההמרה מהספרייה הלאומית.

ההמרה הדביקה את המילה שאחרי קטע מודגש/נטוי ישירות לתג הסוגר
(<b>וראיתי</b>להרב), ראו otzaria/otzaria#1068. הכללים:

* תג סוגר (b/i/small/span) שצמודה אליו אות עברית, כשאין רווח לפני התג —
  מקבל רווח אחריו, בתנאי שתוכן התג מכיל לפחות שתי אותיות עבריות.
* תוכן של אות עברית אחת מקבל רווח רק כשהתג נפתח אחרי <br/>, תג סוגר אחר
  או תחילת שורה (סימון הלכה) — אות בודדת באמצע משפט היא אקרוסטיכון
  (<b>מ</b>מצרים) ואסור לפצל אותו.
* גם כשמיד אחרי התג הסוגר נפתח תג נוסף (<i>דשן</i><i>המזבח): במקור יש שבירת שורה
  בין שני הקטעים, ו-normalize_source מוחק שבירה שצמודה לתג.
* תגים שנפתחים באמצע מילה (אות עברית צמודה לפני התג הפותח) לא נוגעים בהם.
"""

import re
import sys
from pathlib import Path

HEB = r'א-ת'
TAGS = ['b', 'i', 'small', 'span']

OPEN_TAGS = r'(?:<(?:' + '|'.join(TAGS) + r')(?:\s[^>]*)?>)*'

# <tag ...>inner</tag>[<tag2 ...>]letter — ללא רווח לפני התג הסוגר. הבדיקה שהתג לא נפתח באמצע מילה
# היא lookbehind ולא תו נצרך, כדי ששרשרת <i>א</i><i>ב</i><i>ג תיתפס כולה.
PAT = re.compile(
    r'(?<![' + HEB + r'])(?P<open><(?P<tag>' + '|'.join(TAGS) + r')(?:\s[^>]*)?>)'
    r'(?P<inner>[^<]*[^<\s(\[{])(?P<close></(?P=tag)>)(?=' + OPEN_TAGS + r'[' + HEB + r'])',
    re.MULTILINE,
)

MARKER_PREFIX = re.compile(r'(?:<br\s*/?>|</[a-z]+>|<h[1-6]>)\s*$', re.IGNORECASE)


def fix_text(text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        inner = m.group('inner')
        if inner[-1] in '([':
            return m.group(0)
        letters = re.sub(r'[^' + HEB + r']', '', inner)
        if len(letters) >= 2:
            ok = True
        elif '*' in inner or ')' in inner:
            # סימון הפניה להערה ("*)", "א)") — תמיד מילה נפרדת
            ok = True
        elif len(letters) == 1:
            # אות בודדת: רק סימון הלכה (אחרי <br/>/תג סוגר/תחילת שורה)
            start = m.start('open')
            line_start = m.string.rfind('\n', 0, start) + 1
            before = m.string[line_start:start]
            ok = before == '' or MARKER_PREFIX.search(before) is not None
        else:
            ok = False
        if not ok:
            return m.group(0)
        count += 1
        return f"{m.group('open')}{inner}{m.group('close')} "

    return PAT.sub(repl, text), count


def main() -> None:
    roots = [Path(p) for p in sys.argv[1:]]
    total = files_changed = 0
    for root in roots:
        for p in sorted(root.rglob('*.txt')):
            text = p.read_text(encoding='utf-8')
            fixed, n = fix_text(text)
            if n:
                p.write_text(fixed, encoding='utf-8')
                files_changed += 1
                total += n
                print(f'{n}\t{p}')
    print(f'--- files: {files_changed}, insertions: {total}')


if __name__ == '__main__':
    main()
