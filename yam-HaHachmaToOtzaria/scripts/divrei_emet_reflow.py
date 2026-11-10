#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "דברי אמת (דרשות)" של ים החכמה משורות דפוס לפסקאות וכותרות.

בעיית המקור
-----------
הקובץ (`דברי אמת (דרשות).txt`, נמשך בנובמבר 2026; 10,226 שורות, בתיקיית השורש של המקור בלי
קטגוריה) הוא OCR בלי תגים: שורה לכל שורת דפוס (כ־50 תווים), בלי סימון סוף פסקה, ובלי
שורת שער או מחבר. בתוכו חמש עשרה דרושים (`דרוש ראשון` … `דרוש חמשה עשר`), שחלקם בלי מספר
(הדרוש השישי) וחלקם עם כותרת בשתי שורות (`דרוש שנים עשר` / `דרוש שדרשתי …`), ובין העמודים
נשארו קווי הפרדה (`-----`) וסימני עמוד שבורים (`(ח )8`, `(יא )11`).

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>דברי אמת (דרשות)</h1>`, שורה 2 = ריקה במקור (המחבר אינו מצוין בו); בספר שבספרייה נוסף ידנית "רבי יצחק בן דוד מקושטנטינא" לפי דיווח משתמש.
2. כותרות: שורות הכותרת של כל דרוש מאוחדות ל־`<h2>` אחד (מיקומן קבוע ב־`HEADINGS`, כי
   ה־OCR שיבש חלק מהן: `רוש שדרשתי`).
3. מוחק שורות בלי אות עברית (קווי הפרדה, `-(59,(5-s`) וסימני עמוד שבורים (`MARK`).
4. מחבר שורות דפוס לפסקה. פסקה חדשה אחרי שורה קצרה (<45 תווים, שארית שורה בדפוס) שנגמרת
   ב־`.` / `:` / `?` / `!` (ובפסקה שעברה 2,500 תווים — גם אחרי שורה של פחות מ־50 תווים),
   וכל כותרת בפסקה משלה.
5. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי השורות שנמחקו.

שימוש
-----
    python3 -X utf8 divrei_emet_reflow.py SRC.txt OUT.txt
"""
import re, sys

TITLE = 'דברי אמת (דרשות)'
SRC, OUT = sys.argv[1:3]
L = [l.strip() for l in open(SRC, encoding='utf-8').read().split('\n')]

# שורות (מונה מ־0, בקובץ המקור) שמרכיבות כותרת דרוש: (ראשונה, אחרונה)
HEADINGS = [(0, 1), (743, 743), (1168, 1168), (1388, 1389), (1908, 1909), (2659, 2660), (3146, 3147),
            (3421, 3422), (4325, 4325), (5160, 5160), (6034, 6034), (6734, 6735), (7551, 7553),
            (7925, 7926), (9515, 9517)]
# סימני עמוד שה־OCR שיבש (בצורת `(ח )8`), בלי טקסט
MARK = re.compile(r'^\([א-ת]{1,3} ?\)? ?\d{0,3}\)?$|^[א-ת]{1,3} \d\)$')
END = re.compile(r'[.:?!]$')
SHORT = 45
SLACK = 50   # בפסקה ארוכה במיוחד גם שורה עם רווח קטן בסופה סוגרת משפט
LONG = 2500

head_at = {a: b for a, b in HEADINGS}
in_head = {i for a, b in HEADINGS for i in range(a, b + 1)}
assert all(L[a].startswith(('דרוש', 'שדרשתי', 'רוש שדרשתי', 'שלשה עשר')) for a, _ in HEADINGS), 'כותרת לא במקומה'

out = [f'<h1>{TITLE}</h1>', '']
cur, dropped = [], []


def flush():
    if cur:
        out.append(' '.join(cur))
        cur.clear()


i = 0
while i < len(L):
    l = L[i]
    if i in head_at:
        flush()
        out.append('<h2>' + ' '.join(L[i:head_at[i] + 1]) + '</h2>')
        i = head_at[i] + 1
        continue
    if not l:
        i += 1
        continue
    if not re.search(r'[א-ת]', l) or MARK.match(l):
        dropped.append((i, l))
        i += 1
        continue
    cur.append(l)
    if END.search(l) and (len(l) < SHORT or len(l) < SLACK and sum(map(len, cur)) > LONG):
        flush()
    i += 1
flush()

open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
want = strip(''.join(l for i, l in enumerate(L) if l and (i, l) not in dropped))
got = strip(''.join(re.sub(r'</?h2>', '', l) for l in out[2:]))
assert want == got, 'הטקסט השתנה'
print(f'{len(L)} שורות → {len(out)}; h2: {sum(l.startswith("<h2>") for l in out)}; נמחקו {len(dropped)}')
print('נמחקו:', dropped)
print('כותרות:', [l for l in out if l.startswith('<h2>')])
