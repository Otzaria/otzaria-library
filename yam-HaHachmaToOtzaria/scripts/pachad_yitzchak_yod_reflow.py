#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "פחד יצחק חלק י" (אותיות ק–ר) של ים החכמה משורות דפוס לפסקאות.

בעיית המקור
-----------
הקובץ (נמשך בנובמבר 2026, 14,752 שורות; שורה 1 במקור `פחד יצחק אות ק`) הוא OCR בלי תגים:
שורה לכל שורת דפוס (60–70 תווים), בלי סימון סוף פסקה, ובו:
  * מספרי עמוד (אות־מספר לבדה: `ב`, `ג`, `ד` … `קלג`) כל ~100 שורות, ולפעמים משובשים;
  * שורות זבל של OCR בלי אות עברית (`AR A A RA A`, `..`, `6 1`);
  * תתי־ערכים `אות י״ג. …` (המספור הפנימי בתוך הערך), שכל אחד מהם פסקה.

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>פחד יצחק חלק י</h1>`, שורה 2 = המחבר. שורת המקור `פחד יצחק אות ק` נמחקת.
2. מוחק שורות בלי אות עברית, ומספרי עמוד: אות־מספר לבדה שערכה גדול מערך מספר העמוד האחרון
   שנמחק ב־6 לכל היותר (עמוד שנשמט מהסריקה לא מפיל את הרצף). כל שורה שנמחקה מודפסת.
3. מחבר שורות דפוס לפסקה. פסקה חדשה אחרי שורה שנגמרת ב־`.`/`:` כשהיא קצרה (<45 תווים)
   או כשהשורה הבאה פותחת ב־`אות <מספר>`, ובפסקה שעברה 2,500 תווים — גם אחרי שורה של פחות מ־62 תווים. כמו ב־`pachad_yitzchak_reflow.py`, טעות לכאן
   היא פיצול בסוף משפט, ולכאן — שני ערכים בפסקה אחת; בשני המקרים לא נמחקת מילה.
4. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי השורות שנמחקו.

אין כותרות לערכים: גבול המילה הראשית אינו מסומן בטקסט. שגיאות OCR לא תוקנו (להבדיל מחלק ט,
שתוקן מול הסריקה: אתר HebrewBooks חסום לגישה אוטומטית).

שימוש
-----
    python3 -X utf8 pachad_yitzchak_yod_reflow.py SRC.txt OUT.txt
"""
import re, sys

TITLE = 'פחד יצחק חלק י'
AUTHOR = 'רבי יצחק חזקיה למפרונטי'
WINDOW = 6
LONG = 2500  # בפסקה ארוכה במיוחד גם שורה עם רווח בסופה סוגרת משפט
SRC, OUT = sys.argv[1:3]
L = [l.strip() for l in open(SRC, encoding='utf-8').read().split('\n')]
assert L[0] == 'פחד יצחק אות ק', L[0]

V = dict(zip('אבגדהוזחטיכלמנסעפצקרשת', [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))


def numeral(s):
    if not 1 <= len(s) <= 3 or any(c not in V for c in s):
        return None
    v = [V[c] for c in s]
    if all(a >= b for a, b in zip(v, v[1:])) or s in ('טו', 'טז'):
        return sum(v)


dropped, body = [], []
last = 1
for i, l in enumerate(L[1:], 1):
    if not l:
        continue
    if not re.search(r'[א-ת]', l):
        dropped.append((i, 'זבל', l))
        continue
    n = numeral(l)
    if n and last < n <= last + WINDOW:
        dropped.append((i, 'עמוד', l))
        last = n
        continue
    body.append(l)

END = re.compile(r'[.:][)\]]?$')
paras, cur = [], []
for line in body:
    if cur and END.search(cur[-1]) and (len(cur[-1]) < 45 or re.match(r'^אות [א-ת״׳\']{1,5}[.\s]', line)
                                        or len(cur[-1]) < 62 and sum(map(len, cur)) > LONG):
        paras.append(' '.join(cur))
        cur = []
    cur.append(line)
paras.append(' '.join(cur))

out = [f'<h1>{TITLE}</h1>', AUTHOR] + paras
open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
if strip(''.join(body)) != strip(''.join(paras)):
    sys.exit('שימור טקסט נכשל')
print(f'{len(L)} שורות מקור → {len(out)} שורות; נמחקו {len(dropped)}: עמוד {sum(d[1] == "עמוד" for d in dropped)} (אחרון: {last}), זבל {sum(d[1] == "זבל" for d in dropped)}')
print('מספרי עמוד שנמחקו:', [d[2] for d in dropped if d[1] == 'עמוד'])
print('זבל:', [d[2] for d in dropped if d[1] == 'זבל'])
