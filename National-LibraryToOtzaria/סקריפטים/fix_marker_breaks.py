# -*- coding: utf-8 -*-
"""תיקון חד-פעמי: הפרדה חסרה אחרי כותרת סימן בספרי ההמרה מהספרייה הלאומית.

מחלקת ה-H של הספרייה הלאומית הופכת ל-<span style="color:#1B1464"> — כותרת
הסימן. בחלק מהספרים ההמרה הדביקה את גוף הקטע ישירות לכותרת, בלי <br/> ובלי
רווח: <span ...>סימן א</span><b>וז"ל </b> מוצג כ"סימן אוז\"ל". דווח על ספר
'תבונה' ב-Otzaria/otzaria-library#38.

שזו תקלת המרה ולא בחירה סגנונית אפשר לראות מכך ש-17 ספרים מכילים את שתי
הצורות זו לצד זו, ושכאשר קיים מפריד הוא <br/> ב-93%-100% מהמקרים.

הכללים, מהמחמיר למקל:

* כותרת שכולה תווית סימן ("סימן א", "חלק שני סימן א", "רצב.") שצמוד אליה
  גוף הקטע — מקבלת <br/>, גם אם יש רווח בסוף התווית. זה הבאג שדווח: הסימן
  והטקסט על אותה שורה.
* כותרת שצמודה לכותרת נוספת מאותו סוג ("סימן רלג" + "בענין...") — מקבלת
  רווח בלבד. שתיהן חלק מאותה כותרת, וה-<br/> שכבר קיים אחריהן מפריד אותן
  מהגוף.
* כותרת תיאורית שצמודה לגוף בלי שום רווח — מקבלת רווח בלבד. <br/> עלול
  לשבור באמצע משפט, כי לעתים ההמרה גלשה עם תחילת הציטוט לתוך הכותרת
  (<span>שורש תקרובת ע"א ותקרובת </span><i>ע"א אינה בטלה לעולם.</i>).
* כותרת תיאורית שכבר יש בסופה רווח — לא נוגעים. היא אינה דבוקה בתצוגה.
"""

import re
import sys
from pathlib import Path

HEADER_STYLE = 'color:#1B1464'

# כותרת H, כולל תגי עיצוב פנימיים — בלי span מקונן
SPAN = re.compile(
    r'<span style="' + re.escape(HEADER_STYLE) + r'">'
    r'(?P<inner>(?:(?!</?span)[\s\S])*)'
    r'</span>'
)

TAG = re.compile(r'<[^>]+>')

# תוויות פתיחה של סימן, ומילות סדר שמופיעות בתוך תווית מורכבת
KEYWORDS = r'סימן|סי|שורש|פרט|חלק|קונטרס|ענף|כלל|הלכה|דרוש|מערכת|תשובה|פרק'
ORDINALS = (
    r'ראשון|שני|שלישי|רביעי|חמישי|חמשי|ששי|שישי|שביעי|שמיני|תשיעי|עשירי'
    r'|אחד|שנים|עשר|עשרה'
)
# אות/ות גימטריה קצרה, עם או בלי גרש/גרשיים
NUMERAL = r'[א-ת]{1,4}(?:[\'"\u05f3\u05f4][א-ת]{0,2})?'
TOKEN = re.compile(r'^(?:' + KEYWORDS + r'|' + ORDINALS + r'|' + NUMERAL + r')$')

MAX_LABEL_LEN = 24

NEXT_HEADER = '<span style="' + HEADER_STYLE + '">'
# חלון התצפית קדימה חייב להכיל תג כותרת שלם כדי לזהות כותרת עוקבת
LOOKAHEAD = len(NEXT_HEADER)

# פיסוק שצמוד לכותרת שייך לה ומפריד בעצמו ("סימן יב: מותר להרוג") — אין כאן
# דבקות בתצוגה, ושבירה לפניו הייתה מותירה את הפיסוק בראש שורה
PUNCT_AFTER = ':,;.)]}־–—'


def is_siman_label(plain: str) -> bool:
    """האם תוכן הכותרת הוא תווית סימן בלבד, בלי טקסט תיאורי."""
    text = plain.strip().rstrip('.:)')
    if not text or len(text) > MAX_LABEL_LEN:
        return False
    tokens = [t for t in re.split(r'[\s.:)\u05be-]+', text) if t]
    if not tokens:
        return False
    # תווית חייבת להתחיל במילת מפתח או להיות מספור טהור
    if not re.match(r'^(?:' + KEYWORDS + r')$', tokens[0]) and len(tokens) > 1:
        return False
    return all(TOKEN.match(t) for t in tokens)


def fix_text(text: str) -> tuple[str, dict]:
    stats = {'br': 0, 'space': 0}
    out = []
    pos = 0

    for m in SPAN.finditer(text):
        after = text[m.end():m.end() + LOOKAHEAD]
        # כבר מופרד — <br/>, רווח, פיסוק, סוף שורה או סוף קובץ
        if after.startswith('<br') or after[:1] in ('', ' ', '\t', '\n'):
            continue
        if after[:1] in PUNCT_AFTER:
            continue

        inner = m.group('inner')
        plain = TAG.sub('', inner)
        next_is_header = after.startswith(NEXT_HEADER)

        if next_is_header:
            sep, key = ' ', 'space'
        elif is_siman_label(plain):
            sep, key = '<br/>', 'br'
        elif plain == plain.rstrip():
            sep, key = ' ', 'space'
        else:
            continue

        # ל-<br/> אין טעם ברווח תלוי בסוף התווית
        if sep == '<br/>' and plain != plain.rstrip():
            trimmed = inner.rstrip()
            replacement = f'<span style="{HEADER_STYLE}">{trimmed}</span>{sep}'
        else:
            replacement = m.group(0) + sep

        out.append(text[pos:m.start()])
        out.append(replacement)
        pos = m.end()
        stats[key] += 1

    out.append(text[pos:])
    return ''.join(out), stats


def main() -> None:
    roots = [Path(p) for p in sys.argv[1:]]
    dry = '--dry-run' in sys.argv
    roots = [r for r in roots if r.name != '--dry-run']
    total = {'br': 0, 'space': 0}
    files_changed = 0
    for root in roots:
        for p in sorted(root.rglob('*.txt')):
            text = p.read_text(encoding='utf-8')
            fixed, n = fix_text(text)
            if not any(n.values()):
                continue
            if not dry:
                p.write_text(fixed, encoding='utf-8')
            files_changed += 1
            for k in total:
                total[k] += n[k]
            print(f'br={n["br"]:<5} space={n["space"]:<5} {p}')
    print(f'--- files: {files_changed}, <br/>: {total["br"]}, spaces: {total["space"]}')


if __name__ == '__main__':
    main()
