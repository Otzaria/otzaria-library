#!/usr/bin/env python3
"""פירוק הקובץ __משלי.docx למבנה ביניים: פרק → פסוק → שורות רבנו יונה / הגר"א.

מבנה הקלט: שורת פסוק "(א) ...", אחריה "רבנו יונה: ..." (לא תמיד), ואחריה
"בהגר"א: ...". פסקה בלי תווית היא המשך של הפירוש האחרון. סגנונות Word אינם
אמינים (חצי הספר ב-Normal) — הסיווג לפי תוכן בלבד.

פלט: JSON עם רשימת פרקים; כל שורת פירוש היא HTML (b/u) שבו הערות שוליים
מסומנות כ-\x00FN<id>\x00, ומילון footnotes {id: טקסט}.
"""
import json
import re
import sys

import docx
from lxml import etree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

HEB_NUM = re.compile(r'^[א-ת]{1,3}$')
PEREK = re.compile(r'^פרק ([א-ת]{1,3})$')
PASUK = re.compile(r'^\(([א-ת]{1,3})\)\s*')
RY = re.compile(r'^\s*רבי?נו יונה\s*:\s*')
GRA = re.compile(r'^\s*ב?הגר["״]א\s*:\s*')


def run_props(r):
    rpr = r.find(W + 'rPr')
    b = u = False
    if rpr is not None:
        e = rpr.find(W + 'b')
        b = e is not None and e.get(W + 'val') not in ('0', 'false')
        e = rpr.find(W + 'u')
        u = e is not None and e.get(W + 'val') not in (None, 'none', '0')
    return b, u


MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'


def in_textbox(el):
    return any(a.tag == W + 'txbxContent' for a in el.iterancestors())


def textboxes(p):
    """טבלאות/פסקאות שבתוך תיבות טקסט מעוגנות (שתיים בכל הספר: 2:5, 4:3).

    כל תיבה מופיעה פעמיים (mc:Choice + mc:Fallback), ולכן נלקח רק ענף Choice.
    הפלט: HTML שורה אחת, שורות הטבלה מופרדות ב-<br> ותאים ב-" | ".
    """
    out = []
    for ac in p._p.iter(MC + 'AlternateContent'):
        ch = ac.find(MC + 'Choice')
        if ch is None:
            continue
        for box in ch.iter(W + 'txbxContent'):
            rows = []
            for el in box:
                if el.tag == W + 'p':
                    t = re.sub(r'\s+', ' ', ''.join(x.text or '' for x in el.iter(W + 't'))).strip()
                    if t:
                        rows.append(esc(t))
                elif el.tag == W + 'tbl':
                    for tr in el.findall(W + 'tr'):
                        cells = [re.sub(r'\s+', ' ', ''.join(x.text or '' for x in tc.iter(W + 't'))).strip()
                                 for tc in tr.findall(W + 'tc')]
                        if not any(cells):
                            continue
                        # תא ריק בשורת נתונים נשמר כמקף, כדי שהעמודות לא יזוזו
                        cells = [esc(c) if c else '–' for c in cells]
                        while cells and cells[0] == '–':
                            cells.pop(0)
                        rows.append(' | '.join(cells))
            if rows:
                out.append('<br>'.join(rows))
    return out


def para_segments(p):
    """רשימת (טקסט, bold, underline) ו-('\x00FN', id) לפי סדר.

    runs שבתוך תיבת טקסט אינם חלק מזרם הפסקה (ר' textboxes): בלעדי הסינון הזה
    טקסט התיבה נכנס פעמיים לתחילת הפסקה ומסתיר את התווית "בהגר"א:" (פסוק ד ג).
    """
    segs = []
    for r in p._p.iter(W + 'r'):
        if in_textbox(r):
            continue
        b, u = run_props(r)
        for ch in r:
            if ch.tag == W + 't':
                segs.append((ch.text or '', b, u))
            elif ch.tag == W + 'tab':
                segs.append((' ', b, u))
            elif ch.tag in (W + 'br', W + 'cr'):
                segs.append((' ', b, u))
            elif ch.tag == W + 'footnoteReference':
                segs.append(('\x00FN', ch.get(W + 'id')))
    return segs


def plain(segs):
    return ''.join(s[0] if s[0] != '\x00FN' else '' for s in segs)


def strip_prefix(segs, rx):
    """מסיר את התווית (רבנו יונה: / בהגר"א:) מתחילת רצף הסגמנטים."""
    text = plain(segs)
    m = rx.match(text)
    if not m:
        return segs
    n = m.end()
    out = []
    for s in segs:
        if s[0] == '\x00FN':
            out.append(s)
            continue
        if n <= 0:
            out.append(s)
            continue
        if len(s[0]) <= n:
            n -= len(s[0])
            continue
        out.append((s[0][n:],) + s[1:])
        n = 0
    return out


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def to_html(segs):
    """סגמנטים → HTML עם <b>/<u>; רווחים בקצוות התג מוצאים החוצה."""
    # איחוד סגמנטים סמוכים עם אותו עיצוב
    merged = []
    for s in segs:
        if s[0] == '\x00FN':
            merged.append(s)
            continue
        t, b, u = s
        if t == '':
            continue
        if merged and merged[-1][0] != '\x00FN' and merged[-1][1:] == (b, u):
            merged[-1] = (merged[-1][0] + t, b, u)
        elif merged and merged[-1][0] != '\x00FN' and t.strip() == '' :
            # רווח בלבד — מצרפים לקודם בלי לשבור את התג
            merged[-1] = (merged[-1][0] + t,) + merged[-1][1:]
        else:
            merged.append((t, b, u))
    out = []
    for s in merged:
        if s[0] == '\x00FN':
            out.append('\x00FN%s\x00' % s[1])
            continue
        t, b, u = s
        if not (b or u) or not t.strip():
            out.append(esc(t))
            continue
        lead = t[:len(t) - len(t.lstrip())]
        trail = t[len(t.rstrip()):]
        core = esc(t.strip())
        if u:
            core = '<u>%s</u>' % core
        if b:
            core = '<b>%s</b>' % core
        out.append(lead + core + trail)
    html = ''.join(out)
    html = re.sub(r'</b>(\s*)<b>', r'\1', html)
    html = re.sub(r'</u>(\s*)<u>', r'\1', html)
    html = re.sub(r'[ \t ]+', ' ', html).strip()
    return html


def main(path, out):
    d = docx.Document(path)
    fx = etree.fromstring(d.part.package.part_related_by(
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes'
    ).blob) if False else None
    # footnotes.xml
    import zipfile
    z = zipfile.ZipFile(path)
    fx = etree.fromstring(z.read('word/footnotes.xml'))
    footnotes = {}
    for f in fx.iter(W + 'footnote'):
        fid = f.get(W + 'id')
        if int(fid) <= 0:
            continue
        paras = []
        for p in f.iter(W + 'p'):
            t = ''.join((x.text or '') if x.tag == W + 't' else ' '
                        for x in p.iter(W + 't', W + 'tab'))
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                paras.append(t)
        footnotes[fid] = paras

    chapters = []
    cur_ch = cur_ps = None
    cur_comm = None
    anomalies = []
    for i, p in enumerate(d.paragraphs):
        segs = para_segments(p)
        boxes = textboxes(p)
        text = re.sub(r'\s+', ' ', plain(segs)).strip()
        if not text and boxes:
            # פסקה שכולה תיבת טקסט (2:5): המשך של הפירוש האחרון
            if cur_comm is None or cur_ps is None:
                anomalies.append((i, 'textbox without commentator'))
                continue
            cur_ps[cur_comm].append({'html': '<br>'.join(boxes), 'para': i,
                                     'style': p.style.name, 'textbox': True})
            anomalies.append((i, 'textbox-only paragraph appended to %s' % cur_comm))
            continue
        if not text:
            if any(s[0] == '\x00FN' for s in segs):
                anomalies.append((i, 'footnote on empty paragraph'))
            continue
        m = PEREK.match(text)
        if m:
            cur_ch = {'perek': m.group(1), 'pesukim': []}
            chapters.append(cur_ch)
            cur_ps = None
            cur_comm = None
            continue
        m = PASUK.match(text)
        if m:
            cur_ps = {'pasuk': m.group(1), 'text': text, 'ry': [], 'gra': [], 'para': i}
            cur_ch['pesukim'].append(cur_ps)
            cur_comm = None
            continue
        if RY.match(text):
            cur_comm = 'ry'
            segs = strip_prefix(segs, RY)
        elif GRA.match(text):
            cur_comm = 'gra'
            segs = strip_prefix(segs, GRA)
        elif cur_comm is None:
            # פסקת מבוא של העורך שמזכירה את המפרש בשמו, בלי תווית:
            # "בביאור רבינו יונה זצוק"ל ..." / "הגר"א קושר את כל הפסוקים ..."
            head = text[:30]
            if re.search(r'רבי?נו יונה', head):
                cur_comm = 'ry'
            elif re.search(r'הגר["״]א', head):
                cur_comm = 'gra'
            else:
                anomalies.append((i, 'continuation without commentator', text[:60]))
                continue
            anomalies.append((i, 'unlabeled %s paragraph (kept whole)' % cur_comm, text[:60]))
        html = to_html(segs)
        if not re.sub(r'\x00FN\d+\x00', '', html).strip():
            anomalies.append((i, 'empty after prefix', text[:60]))
            continue
        entry = {'html': html, 'para': i, 'style': p.style.name}
        if boxes:
            entry['html'] = html + '<br>' + '<br>'.join(boxes)
            entry['textbox'] = True
            anomalies.append((i, 'textbox appended to %s line' % cur_comm))
        if cur_ps is None:
            # לפני הפסוק הראשון בפרק — מבוא לפרק
            cur_ch.setdefault('intro', {'ry': [], 'gra': []})[cur_comm].append(entry)
            cur_comm = None
            continue
        cur_ps[cur_comm].append(entry)

    json.dump({'chapters': chapters, 'footnotes': footnotes, 'anomalies': anomalies},
              open(out, 'w'), ensure_ascii=False, indent=1)
    print('chapters', len(chapters), 'pesukim', sum(len(c['pesukim']) for c in chapters))
    print('ry lines', sum(len(p['ry']) for c in chapters for p in c['pesukim']),
          'gra lines', sum(len(p['gra']) for c in chapters for p in c['pesukim']))
    print('anomalies', anomalies)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
