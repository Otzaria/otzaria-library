#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת "ילקוט מעם לועז" (ארבעה כרכים) של ים החכמה משורות דפוס לפסקאות וכותרות.

בעיית המקור
-----------
הקבצים (`ילקוט מעם לועז <חומש>.txt`; נמשכו באוקטובר 2026 בשם `… - <חומש>_נקי.txt`, ובנובמבר 2026
הוחלפו בנוסח מתוקן שבו הוסרו רוב ההפניות `(א)` ורשימות המקורות, ובכרך שמות תוקן שוב ב־5.11.2026; 12–47 אלף שורות כל אחד) הם
טקסט גולמי בלי תגים: שורה לכל שורת דפוס (כ־65 תווים), ובתוכו:
  * כותרת עמוד רצה (`ילקוט מעם לועז - שמות`, גם בצורות משובשות: `לועו`, `מעם: לועז`) ומספר עמוד
    (אות־מספר לבדה) בכל מעבר עמוד, ושורות ריקות;
  * כותרות `פרשת …` ו־`פרק …` — אבל כותרת הפרשה חסרה לפעמים ונשאר רק `ביאור פרשת … והיא
    בספר תורה …` בשורה שלפני `פרק א`;
  * הפניות `(א)`, `(ב)`… באמצע הטקסט, ואחרי כל קטע רשימת `מקורות:` ובה הפריט לכל הפניה
    (כמה פריטים בשורה אחת, ופריט שנמשך על כמה שורות).

מה הסקריפט עושה
---------------
1. שורה 1 = `<h1>ילקוט מעם לועז - <חומש></h1>`, שורה 2 = המחבר, רבי יעקב כולי (המקור אינו מציין; נקבע על ידינו). שורת
   השער של המקור נמחקת (בכרכים ויקרא ושמות היא `ילקוט מעם לועז חומש שמות` — טעות במקור
   בכרך ויקרא, ולכן הכותרת נקבעת כאן ולא נלקחת ממנה).
2. מוחק שורות ריקות, כותרות עמוד רצות ומספרי עמוד (אות־מספר תקנית לבדה שליד שורה ריקה).
   כל שורה שנמחקה מודפסת בסיכום.
3. כותרות: `פרשת …` קצרה לבדה שבאה ממש לפני `פרק א` → `<h2>`; `פרק …` → `<h3>`. כשכותרת
   הפרשה חסרה, נוצרת `<h2>פרשת X</h2>` מתוך `ביאור פרשת X` שבשורות שלפני `פרק א` או אחריו (המקרים
   מודפסים, ו־`MISSING` שבקוד נותן שם לכותרת שאי אפשר להסיק). בכרך בראשית הכותרת `בראשית`
   הופכת ל־`פרשת בראשית`; בכרך במדבר `אל עין הקורא` (הקדמה) → `<h2>`.
4. פסקאות: שורה קצרה (<56 תווים) שנגמרת בסימן סוף משפט, שורת פסוק מצוטט שנגמרת בציון
   `(א, א)`, וכן `מקורות:` ו־פריט חדש ברשימת המקורות — כל אלה פותחים פסקה חדשה. ברשימת
   המקורות כל פריט `(א) …` הוא שורה נפרדת (גם כשהמקור מדפיס כמה פריטים בשורה אחת).
5. בדיקת שימור: הטקסט בלי רווחים זהה למקור בניכוי השורות שנמחקו והכותרות שנוצרו.

שימוש
-----
    python3 -X utf8 meam_loez_reflow.py בראשית SRC.txt OUT.txt
"""
import re, sys

VOL, SRC, OUT = sys.argv[1:4]
TITLE = f'ילקוט מעם לועז - {VOL}'
AUTHOR = 'רבי יעקב כולי'  # המקור אינו מציין מחבר; מחבר "מעם לועז"
SHORT = 56
SLACK = 64   # שורת דפוס מלאה היא ~65–70 תווים; מתחת לזה יש רווח בסוף השורה
LONG = 2000  # אורך פסקה שמעליו שוברים בסוף משפט
L = [l.strip() for l in open(SRC, encoding='utf-8').read().split('\n')]

# כותרות פרשה שאי אפשר להסיק מ־`ביאור פרשת …`: (כרך, תחילת השורה הראשונה אחרי `פרק א`) → שם הכותרת
MISSING = {('שמות', 'אלה פקודי המשכן'): 'פרשת פקודי'}

RUNNING = re.compile(r'^ילקוט מעם:? ?לוע[זו]\s*-\s*' + VOL + r'$')
NUMERAL_LETTERS = dict(zip('אבגדהוזחטיכלמנסעפצקרשת',
                           [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400]))


def is_numeral(s):
    if not 1 <= len(s) <= 3 or any(c not in NUMERAL_LETTERS for c in s):
        return False
    v = [NUMERAL_LETTERS[c] for c in s]
    return all(a >= b for a, b in zip(v, v[1:])) or s in ('טו', 'טז')


ITEM = re.compile(r'^\([א-ת]{1,3}\) ')
END = re.compile(r'[.:?!)]["\'״׳]?$')
VERSE_REF = re.compile(r'\([א-ת]{1,3}, [א-ת]{1,3}(?:[־-][א-ת]{1,3}(?:, [א-ת]{1,3})?)?\)[.:]?$')
PARASHA = re.compile(r'^פרשת [א-ת ]{2,16}$')
CHAPTER = re.compile(r'^פרק [א-ת]+$')
SYNTH = re.compile(r'(?:ביאור|באור|ביאיר) פרשת ([א-ת]+(?: (?!והיא|ובה|שהיא|בס|ובה)[א-ת]+)?)')

kept, dropped = [], []
for i, l in enumerate(L):
    if not l:
        continue
    if i == 0 and l.startswith('ילקוט מעם לועז'):
        dropped.append((i + 1, 'שער', l))
        continue
    if RUNNING.match(l):
        dropped.append((i + 1, 'כותרת עמוד', l))
        continue
    prev_blank = i > 0 and not L[i - 1]
    next_blank = i + 1 < len(L) and not L[i + 1]
    if is_numeral(l) and (prev_blank or next_blank):
        dropped.append((i + 1, 'מספר עמוד', l))
        continue
    # בנוסח המקור מנובמבר 2026 `פרק א` של משפטים נדבק לסוף שורת הביאור
    m = re.match(r'^(ביאור פרשת .+?[.:]) (פרק [א-ת]+)$', l)
    if m:
        kept.extend(m.groups())
        continue
    kept.append(l)

out =[f'<h1>{TITLE}</h1>', AUTHOR]
cur = []
synth = []
synth_lines = []
in_sources = False
prev = ''
since_h2 = 99
src_split = re.compile(r'(?<=[.:]) (?=\([א-ת]{1,3}\) )')


def flush():
    if cur:
        text = ' '.join(cur)
        out.extend(src_split.split(text) if in_sources else [text])
        cur.clear()


for n, line in enumerate(kept):
    since_h2 += 1
    if VOL == 'בראשית' and n == 0 and line == 'בראשית':
        out.append('<h2>פרשת בראשית</h2>')
        synth.append('פרשת בראשית')
        synth_lines.append(len(out) - 1)
        since_h2 = 0
        continue
    if VOL == 'במדבר' and line == 'אל עין הקורא':
        flush()
        out.append(f'<h2>{line}</h2>')
        continue
    if PARASHA.match(line) and any(x == 'פרק א' for x in kept[n + 1:n + 4]):
        flush()
        in_sources = False
        out.append(f'<h2>{line}</h2>')
        since_h2 = 0
        continue
    if CHAPTER.match(line):
        flush()
        in_sources = False
        if line == 'פרק א' and since_h2 > 6:
            name = next((v for (vol, pre), v in MISSING.items() if vol == VOL and kept[n + 1].startswith(pre)), None)
            near = kept[max(n - 2, 0):n][::-1] + kept[n + 1:n + 3]
            if not name:
                m = next((SYNTH.search(x) for x in near if SYNTH.search(x)), None)
                assert m, ('כותרת פרשה חסרה', n, kept[n + 1])
                name = 'פרשת ' + m.group(1)
            # שורת `ביאור פרשת X` שנדבקה לפני `פרק א` עוברת אחרי הכותרת
            lead = out.pop() if n and out[-1] == kept[n - 1] and SYNTH.search(kept[n - 1]) else None
            out.append(f'<h2>{name}</h2>')
            synth.append(name)
            synth_lines.append(len(out) - 1)
            if lead:
                out.append(lead)
            since_h2 = 0
        out.append(f'<h3>{line}</h3>')
        continue
    if line.startswith('מקורות:'):
        flush()
        out.append('מקורות:')
        in_sources = True
        line = line[len('מקורות:'):].strip()
        if not line:
            prev = 'מקורות:'
            continue
    elif in_sources:
        if ITEM.match(line):
            flush()
        elif END.search(prev) and len(line) >= SHORT:
            # הרשימה נגמרה: שורה ארוכה שאינה פריט אחרי פריט שלם היא גוף הספר
            flush()
            in_sources = False
    cur.append(line)
    prev = line
    if len(line) < SHORT and END.search(line) or VERSE_REF.search(line):
        flush()
    elif not in_sources and END.search(line) and len(line) < SLACK and sum(map(len, cur)) > LONG:
        # פסקה ארוכה במיוחד בלי שורת סיום קצרה (הנוסח המתוקן הסיר את מפרידי ההפניות): נשבר בסוף משפט עם רווח בסוף השורה
        flush()
flush()

open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')

strip = lambda s: re.sub(r'\s+', '', s)
want = strip(''.join(kept[1:] if VOL == 'בראשית' else kept))  # בבראשית שורה 1 הוחלפה בכותרת
got = strip(''.join(re.sub(r'</?h[23]>', '', l) for j, l in enumerate(out) if j >= 2 and j not in synth_lines))
assert want == got, 'הטקסט השתנה'
print(f'{len(L)} שורות → {len(out)}; h2: {sum(l.startswith("<h2>") for l in out)}, h3: {sum(l.startswith("<h3>") for l in out)};',
      f'נמחקו {len(dropped)}: ' + ', '.join(f'{k} {sum(1 for d in dropped if d[1] == k)}' for k in sorted({d[1] for d in dropped})))
print('כותרות שנוצרו:', synth)
print('שורות שנמחקו (לא מספרי עמוד):', [d for d in dropped if d[1] == 'שער'])
print('כותרות h2:', [l for l in out if l.startswith('<h2>')])
print('מספרי עמוד ייחודיים:', sorted({d[2] for d in dropped if d[1] == 'מספר עמוד'}, key=lambda x: (len(x), x))[:60])
