#!/usr/bin/env python3
"""dbs_breaks.py - אבחון ותיקון שורות שבורות וכותרות קטועות בספרי DBS שנוספו ל-ערוך.

רקע: קבצי DBS שהועתקו כמו שהם ל-DictaToOtzaria/ערוך (קומיט "הוספת ספרים מדיקטה")
שומרים שבירת שורות של הדפוס: משפט נקטע באמצע ונמשך בשורה הבאה, וכותרות (h) נחתכות
באורך קבוע (~47 תווים) או שהמשכן נשאר בשורה נפרדת. הגרסה הגולמית של אותו ספר
(extraBooks/דיקטה או DictaToOtzaria/לא ערוך) משמשת כ"עד": אם בגולמי שני קצוות
שורה DBS עומדים באותה שורה - השבירה מלאכותית.

שימוש:
  dbs_breaks.py scan  [--commit b9ce756e 0e63b8bb] [--out report.json]
  dbs_breaks.py fix   [--commit b9ce756e 0e63b8bb] [--out report.json]    (כותב לקבצים!)
  dbs_breaks.py dbs-raw UNITS.jsonl OUT.txt    (גולמי מפענוח COR של DBS, לספרים בלי ייצוא)
  dbs_breaks.py fix --raw-map map.json         (רק הספרים שבמפה, כל אחד עם הגולמי שלו)
ברירת המחדל: שני קומיטי ההעתקה של DBS - b9ce756e ("הוספת ספרים מדיקטה") ו-0e63b8bb
("תיקון ספרים מ'דיקטה>לא ערוך'"). שניהם שומרים את שבירות הדפוס.

תיקונים אוטומטיים (בטוחים בלבד):
  1. איחוד שורות: שורה A שלא מסתיימת בפיסוק סוף + שורה B, כשבגולמי רצף המילים
     (3 אחרונות של A + 3 ראשונות של B) נמצא בתוך שורה אחת, וכל ההתאמות בגולמי מסכימות.
  2. כותרת ש"נחתכה": כשהגולמי מראה שהכותרת (עד מילה חלקית) היא תחילת רצף שורות
     הגולמי, וגוף ה-DBS שאחריה מתחיל בדיוק בתחילת שורה בגולמי - משלימים מהגולמי.
  3. סוגריים הפוכים בכותרת (`]אות א[`, `)נוסח(`): מחליפים כשההיפוך מאזן את הכותרת.
  איחוד שורות מזיז מספרי שורות: ב-fix מוזזים line_index_1 בקובץ ה-links של הספר ו-line_index_2
  בכל קובץ links ששדה path_2 שלו מצביע עליו (בשורשי ה-links שארוזים). שתי שורות שלכל אחת
  קישור תלוי-טקסט משלה (line_index_1) לא מאוחדות - אחרת ייווצר קישור כפול לאותה שורה.
  ספרים שכותרותיהם תוקנו ביד (HAND_HEADINGS) מקבלים איחוד שורות בלבד, בלי תיקוני כותרות.

מה לא מתוקן (רק מדווח): כותרות שהמשכן בגוף בלי עד בגולמי, כותרת שנוצרה מחתיכת שורת גוף,
שורות לא-מסתיימות שאין להן עד בגולמי, אובדן מילה ראשונה בכותרות, `&amp;`.
"""
import argparse, collections, html, json, os, re, subprocess, sys
from json.decoder import scanstring

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
DEFAULT_COMMITS = ['b9ce756e', '0e63b8bb']
# כותרות הספרים האלה תוקנו ביד ב-08f86912; תיקוני הכותרות האוטומטיים עלולים לדרוס אותן
HAND_HEADINGS = ['אורח משפט', 'עט סופר', 'משמרת אלעזר', 'אלפי מנשה', 'תבואות השדה', 'העיטור']
RAW_DIRS = ['extraBooks/דיקטה', 'DictaToOtzaria/לא ערוך']
EDITED_PREFIX = 'DictaToOtzaria/ערוך/ספרים/'
OWN_LINKS_ROOT = 'DictaToOtzaria/ערוך/links'
DEPENDENT_TYPES = {'source', 'commentary', 'super_commentary', 'supercommentary', 'targum',
                   'midrash', 'parshanut', 'dibur_hamatchil', 'elucidation', 'ellucidation',
                   'explication', 'footnotes', 'footnote'}

TAG = re.compile(r'<[^>]+>')
HRE = re.compile(r'^<h([1-6])>(.*)</h\1>$')
TOKCH = re.compile(r'[^א-ת0-9A-Za-z]')
TERM = re.compile(r'[.:?!;׃]["\'”’»)\]׳״]*$')


def plain(s):
    return html.unescape(TAG.sub('', s))


def toks(s):
    out = []
    for w in plain(s).split():
        w = TOKCH.sub('', w)
        if w:
            out.append(w)
    return out


def terminated(line):
    return bool(TERM.search(plain(line).rstrip()))


def is_body(line):
    return bool(line.strip()) and not line.startswith('<h')


# ------------------------------------------------------------- DBS as raw
BLOCK_MARK = '\x01'


def wrap_threshold(lines):
    """אורך שורה שמתחתיו שבירה ב-COR היא סוף פסקה ולא גלישה (אותו כלל כמו dbs_otzaria.py)."""
    lengths = sorted(len(l.replace(BLOCK_MARK, '').strip()) for l in lines if l.strip())
    if len(lengths) < 20:
        return 56
    return max(20, min(56, lengths[int(len(lengths) * 0.9)] - 6))


def dbs_paragraphs(units):
    """units: טקסטים של יחידות COR (שורות דפוס) -> שורה לכל פסקה, כמו ייצוא גולמי.
    פסקה נגמרת בסימן 0xFE (BLOCK_MARK), בשורה קצרה מרוחב הגלישה, או בסוף יחידה."""
    th = wrap_threshold([l for u in units for l in u.split('\n')])
    out = []
    for u in units:
        buf = []
        for raw in u.split('\n'):
            line = raw.replace(BLOCK_MARK, '').strip()
            if line:
                buf.append(line)
            if buf and (BLOCK_MARK in raw or not line or len(line) < th):
                out.append(' '.join(buf))
                buf = []
        if buf:
            out.append(' '.join(buf))
    return out


def dbs_raw(jsonl, out):
    """units.jsonl של dbs_text.py --source cor -> קובץ גולמי (שורה לכל פסקה)."""
    units = [json.loads(l)['text'] for l in open(jsonl, encoding='utf-8') if l.strip()]
    open(out, 'w', encoding='utf-8').write('\n'.join(dbs_paragraphs(units)) + '\n')


# ---------------------------------------------------------------- raw index
class RawIndex:
    def __init__(self, path):
        self.path = path
        self.lines = open(path, encoding='utf-8').read().split('\n')
        self.T, self.start, self.lineno = [], [], []
        for n, l in enumerate(self.lines):
            for k, w in enumerate(toks(l)):
                self.T.append(w)
                self.start.append(k == 0)
                self.lineno.append(n)
        self.bi = collections.defaultdict(list)
        for i in range(len(self.T) - 1):
            self.bi[(self.T[i], self.T[i + 1])].append(i)

    def joined(self, A, B):
        """A, B: token lists של שתי שורות גוף רצופות ב-DBS -> join / break / unknown / ambig"""
        if not A or not B:
            return 'unknown'
        t, h = A[-3:], B[:3]
        W = t + h
        if len(W) < 4:
            return 'unknown'
        res = set()
        for q in self.bi.get((t[-1], h[0]), []):
            i = q - (len(t) - 1)
            if i < 0 or self.T[i:i + len(W)] != W:
                continue
            res.add('break' if self.start[q + 1] else 'join')
        if len(res) == 1:
            return res.pop()
        if res:
            return 'ambig'
        # רמה שנייה: DBS לפעמים קוצץ/משבש מילה בקצה השורה, אז מסתפקים ב-2+2 מילים,
        # אבל רק אם ההתאמה יחידה בכל הגולמי (אין מקום לבלבול בין מופעים)
        if len(A) >= 2 and len(B) >= 2:
            t, h = A[-2:], B[:2]
            W = t + h
            hits = [q for q in self.bi.get((t[-1], h[0]), [])
                    if q - 1 >= 0 and self.T[q - 1:q - 1 + 4] == W]
            if len(hits) == 1 and not self.start[hits[0] + 1]:
                return 'join'
        return 'unknown'

    def heading_status(self, h, b):
        """h: טוקני כותרת (DBS), b: טוקני שורת הגוף שאחריה.
        -> ('ok'|'trunc'|'notfound'|'ambig'|'skip', info)"""
        n = len(h)
        if n < 2 or len(b) < 3:
            return 'skip', None
        b4 = b[:4]
        T = self.T
        found = [q for q in self.bi.get((h[0], h[1]), [])
                 if T[q:q + n - 1] == h[:-1] and q + n - 1 < len(T) and T[q + n - 1].startswith(h[-1])]
        if not found:
            return 'notfound', None
        outs, info = set(), None
        for q in found:
            end = q + n
            rem = T[q + n - 1][len(h[-1]):]
            if rem == '' and T[end:end + len(b4)] == b4:
                outs.add('ok')
                continue
            for j in range(40):
                k = end + j
                if k + len(b4) > len(T):
                    break
                if T[k:k + len(b4)] == b4 and self.start[k] and (j > 0 or rem != ''):
                    outs.add('trunc')
                    info = (q, k)
                    break
            else:
                outs.add('other')
        if outs == {'trunc'}:
            return 'trunc', info
        if outs == {'ok'}:
            return 'ok', None
        return 'ambig', sorted(outs)

    def heading_midline(self, h):
        """הכותרת מופיעה בגולמי באמצע שורה (לא בתחילתה) - סימן לכותרת שנוצרה מחתיכת גוף."""
        n = len(h)
        if n < 4:
            return False
        T = self.T
        occ = [q for q in self.bi.get((h[0], h[1]), [])
               if T[q:q + n - 1] == h[:-1] and q + n - 1 < len(T) and T[q + n - 1].startswith(h[-1])]
        return len(occ) == 1 and not self.start[occ[0]]


# ------------------------------------------------------------------ helpers
def git(*a):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=REPO,
                          capture_output=True, text=True, check=True).stdout


def books_of_commits(commits, exclude):
    """הקבצים שהקומיטים הוסיפו ל-ערוך, לפי הנתיב הנוכחי (ספר שהועבר מאז נמצא לפי git log --follow)."""
    current = {}
    for p in git('ls-files', '--', EDITED_PREFIX).split('\n'):
        if p.endswith('.txt'):
            current.setdefault(os.path.basename(p), []).append(p)
    res = []
    for commit in commits:
        for p in git('show', '--name-only', '--diff-filter=A', '--format=', commit).split('\n'):
            if not (p.startswith(EDITED_PREFIX) and p.endswith('.txt')):
                continue
            if not os.path.exists(os.path.join(REPO, p)):
                moved = current.get(os.path.basename(p), [])
                if len(moved) != 1:
                    continue
                p = moved[0]
            if p not in res and not any(e in p for e in exclude):
                res.append(p)
    return res


def raw_files():
    d = collections.defaultdict(list)
    for root in RAW_DIRS:
        for r, _, fs in os.walk(os.path.join(REPO, root)):
            for f in fs:
                if f.endswith('.txt'):
                    d[f].append(os.path.join(r, f))
    return d


def find_raw_by_content(path, allraw, cache):
    """גיבוי כשאין שם קובץ זהה: חיפוש 4 ביטויים אקראיים מהגוף בכל הגולמיים."""
    import random
    rnd = random.Random(7)
    L = [l for l in open(os.path.join(REPO, path), encoding='utf-8').read().split('\n')
         if is_body(l) and len(l) > 120]
    phr = []
    for l in rnd.sample(L, min(4, len(L))):
        w = plain(l).split()
        k = len(w) // 2
        phr.append(' '.join(w[k:k + 4]))
    best, bn = None, 0
    for f in allraw:
        if f not in cache:
            cache[f] = open(f, encoding='utf-8').read()
        n = sum(1 for s in phr if s in cache[f])
        if n > bn:
            best, bn = f, n
    return best if bn >= 3 else None


def links_index():
    """שם ספר -> קבצי links (שורשים שארוזים) שבהם הוא מצטט או מצוטט."""
    conf = json.load(open(os.path.join(REPO, 'manual_links_sync.json'), encoding='utf-8'))
    idx = collections.defaultdict(list)
    for r in conf['links_roots']:
        if r['expected_state'] != 'present':
            continue
        d = os.path.join(REPO, r['path'])
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith('_links.json'):
                continue
            fp = r['path'] + '/' + f
            idx[f[:-len('_links.json')]].append(fp)
            try:
                data = json.load(open(os.path.join(REPO, fp), encoding='utf-8-sig'))
            except Exception:
                continue
            for t in sorted({os.path.splitext(os.path.basename(x.get('path_2', '').replace('\\', '/')))[0]
                             for x in data}):
                if fp not in idx[t]:
                    idx[t].append(fp)
    return idx


def packaged_title_counts():
    """כמה ספרים ארוזים נושאים כל שם - path_2 מזהה ספר לפי שם בלבד."""
    sys.path.insert(0, REPO)
    from manual_links_packaging import BOOK_ROOTS
    n = collections.Counter()
    for p in git('ls-tree', '-r', '--name-only', 'HEAD', '--', *BOOK_ROOTS).split('\n'):
        if p.endswith('.txt'):
            n[os.path.basename(p)[:-4]] += 1
    return n


def ctype(rec):
    return str(rec.get('Conection Type', '')).strip().lower().replace(' ', '_')


def pinned_lines(title):
    """שורות (0-based) של הספר שיש להן קישור תלוי-טקסט משלהן בקובץ ה-links שלו."""
    fp = os.path.join(REPO, OWN_LINKS_ROOT, title + '_links.json')
    if not os.path.exists(fp):
        return set()
    return {r['line_index_1'] - 1 for r in json.load(open(fp, encoding='utf-8-sig'))
            if isinstance(r.get('line_index_1'), int) and ctype(r) in DEPENDENT_TYPES}


# ------------------------------------------------------------- links shift
_NUM = re.compile(r'-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?')
_WS = re.compile(r'[ \t\n\r]*')


def _parse(s, i):
    """(value, end, spans): spans = מפתח -> (start, end) של ערך מספרי שלם, לשינוי בלי לגעת בעיצוב."""
    i = _WS.match(s, i).end()
    c = s[i]
    if c == '{':
        obj, spans = {}, {}
        i = _WS.match(s, i + 1).end()
        if s[i] == '}':
            return obj, i + 1, spans
        while True:
            i = _WS.match(s, i).end()
            key, i = scanstring(s, i + 1)
            i = _WS.match(s, i).end()
            vstart = _WS.match(s, i + 1).end()
            val, i, _ = _parse(s, vstart)
            obj[key] = val
            if isinstance(val, int) and not isinstance(val, bool):
                spans[key] = (vstart, i)
            i = _WS.match(s, i).end()
            if s[i] == ',':
                i += 1
                continue
            return obj, i + 1, spans
    if c == '[':
        arr = []
        i = _WS.match(s, i + 1).end()
        if s[i] == ']':
            return arr, i + 1, {}
        while True:
            val, i, sp = _parse(s, i)
            arr.append((val, sp))
            i = _WS.match(s, i).end()
            if s[i] == ',':
                i += 1
                continue
            return arr, i + 1, {}
    if c == '"':
        v, end = scanstring(s, i + 1)
        return v, end, {}
    m = _NUM.match(s, i)
    if m:
        t = m.group(0)
        return (float(t) if any(ch in t for ch in '.eE') else int(t)), m.end(), {}
    for lit, v in (('true', True), ('false', False), ('null', None)):
        if s.startswith(lit, i):
            return v, i + len(lit), {}
    raise ValueError('bad json at %d' % i)


def shift_links_text(text, linemap, keys, stem=None):
    """ממפה מספרי שורה (1-based) לפי linemap (0-based ישן -> 0-based חדש).
    keys: line_index_1 בקובץ של הספר עצמו, או line_index_2 ברשומות שה-path_2 שלהן הוא stem."""
    head = 1 if text.startswith('﻿') else 0
    val, _, _ = _parse(text, head)
    edits = []
    for rec, sp in val:
        if not isinstance(rec, dict):
            continue
        if stem is not None:
            p2 = str(rec.get('path_2', '')).replace('\\', '/')
            if not p2.endswith('.txt') or p2.rsplit('/', 1)[-1][:-4] != stem:
                continue
        for k in keys:
            if k in sp and 1 <= rec[k] <= len(linemap):
                nv = linemap[rec[k] - 1] + 1
                if nv != rec[k]:
                    edits.append((sp[k], str(nv)))
    for (s, e), rep in sorted(edits, reverse=True):
        text = text[:s] + rep + text[e:]
    return text, len(edits)


def shift_links(title, files, linemap):
    """מזיז את כל קבצי ה-links של הספר לפי linemap. מחזיר {קובץ: מספר ערכים שהשתנו}."""
    changed = {}
    for fp in files:
        full = os.path.join(REPO, fp)
        raw = open(full, 'rb').read()
        text = raw.decode('utf-8')
        n = 0
        if fp == OWN_LINKS_ROOT + '/' + title + '_links.json':
            text, k = shift_links_text(text, linemap, ('line_index_1', 'line_index_1_end'))
            n += k
        text, k = shift_links_text(text, linemap, ('line_index_2', 'line_index_2_end'), title)
        n += k
        if n:
            open(full, 'wb').write(text.encode('utf-8'))
            changed[fp] = n
    return changed


def fix_brackets(t):
    """מחליף סוגריים הפוכים אם ההיפוך מאזן את הכותרת (או מבטל עומק שלילי)."""
    def depth_ok(s):
        d = 0
        for ch in s:
            if ch in '([':
                d += 1
            elif ch in ')]':
                d -= 1
                if d < 0:
                    return False
        return True
    if not re.search(r'[\)\]]', t):
        return t
    if depth_ok(t):
        return t
    sw = t.translate(str.maketrans('()[]', ')(]['))
    # החלפה מלאה הופכת גם סוגריים תקינים; מבצעים רק אם התוצאה מאוזנת
    if depth_ok(sw) and sw.count('(') == sw.count(')') and sw.count('[') == sw.count(']'):
        return sw
    return t


# --------------------------------------------------------------- main logic
def process(path, ri, apply, pinned=frozenset(), block_merge=False, fix_headings=True):
    """pinned: שורות (0-based) עם קישור תלוי-טקסט משלהן; block_merge: לא לאחד כלל (שם ספר לא חד-ערכי)."""
    full = os.path.join(REPO, path)
    src = open(full, encoding='utf-8', newline='').read()
    L = src.split('\n')
    st = collections.Counter()
    ex = collections.defaultdict(list)

    def note(kind, i, text):
        st[kind] += 1
        if len(ex[kind]) < 4:
            ex[kind].append([i + 1, text[:70]])

    h1 = None
    fixes_h = 0

    def lost_first(h1, t):
        hw, tw = h1.split(), t.split()
        return (len(hw) > 1 and bool(tw) and tw[0] == hw[1] and tw[0] != hw[0]
                and hw[0] != 'ספר' and not hw[0].startswith('('))
    # כותרות שאיבדו את המילה הראשונה של שם הספר: מתקנים רק כשהדפוס שיטתי (>=90% מכותרות הקובץ)
    pre_h1, n_sub, n_lost = None, 0, 0
    for l in L:
        m = HRE.match(l)
        if not m:
            continue
        if m.group(1) == '1':
            pre_h1 = m.group(2).strip()
        else:
            n_sub += 1
            if pre_h1 and lost_first(pre_h1, m.group(2).strip()):
                n_lost += 1
    lost_systematic = n_sub >= 5 and n_lost >= 0.9 * n_sub
    # ---- כותרות
    for i, l in enumerate(L):
        if not l.startswith('<h'):
            continue
        m = HRE.match(l)
        if not m:
            note('h_unclosed', i, l)
            continue
        lv, t = m.group(1), m.group(2).strip()
        if lv == '1':
            h1 = t
            continue
        if re.search(r'[-–,(\[]$', t):
            note('h_trailing_joiner', i, t)
        if t != fix_brackets(t):
            note('h_reversed_brackets', i, t)
            if apply and fix_headings:
                L[i] = '<h%s>%s</h%s>' % (lv, fix_brackets(t), lv)
                fixes_h += 1
                t = fix_brackets(t)
        elif t.count('(') != t.count(')') or t.count('[') != t.count(']'):
            note('h_unbalanced', i, t)
        if len(t) in (47, 48) or len(t) >= 44 and not re.search(r'[.:?!)\]]$', t):
            note('h_len_suspect', i, t)
        lost_here = bool(h1) and lost_first(h1, t)
        if lost_here:
            note('h_lost_first_word_fixable' if lost_systematic else 'h_lost_first_word', i, t)
        if ri and i + 1 < len(L) and is_body(L[i + 1]):
            s, info = ri.heading_status(toks(t), toks(L[i + 1]))
            if s == 'trunc':
                q, k = info
                span = range(ri.lineno[q], ri.lineno[k - 1] + 1)
                allbold = all(re.sub(r'<[^>]+>', '', re.sub(r'<(b|big)>.*?</\1>', '', ri.lines[n])).strip(' \t.,:;') == ''
                              for n in span)
                if len(t) >= 40 and ri.start[q] and len(span) <= 3 and k - q <= 25 and allbold:
                    new = ' '.join(plain(ri.lines[n]).strip() for n in range(ri.lineno[q], ri.lineno[k - 1] + 1))
                    new = re.sub(r'\s+', ' ', new).strip().rstrip(':').strip()
                    note('h_truncated_fixable', i, '%s => %s' % (t, new))
                    if apply and fix_headings:
                        L[i] = '<h%s>%s</h%s>' % (lv, new, lv)
                        fixes_h += 1
                else:
                    note('h_truncated_manual', i, t)
            elif ri.heading_midline(toks(t)) and len(t) >= 40:
                note('h_from_body_fragment', i, t)
    if apply and fix_headings and lost_systematic:
        h1 = None
        for i, l in enumerate(L):
            m = HRE.match(l)
            if not m:
                continue
            if m.group(1) == '1':
                h1 = m.group(2).strip()
            elif h1 and lost_first(h1, m.group(2).strip()):
                L[i] = '<h%s>%s %s</h%s>' % (m.group(1), h1.split()[0], m.group(2).strip(), m.group(1))
                fixes_h += 1
    # ---- שורות גוף
    merged = 0
    n_body_pairs = 0
    out = []
    linemap = []
    i = 0
    while i < len(L):
        cur = L[i]
        cur_pinned = i in pinned
        linemap.append(len(out))
        i += 1
        while is_body(cur) and i < len(L) and is_body(L[i]):
            nxt = L[i]
            n_body_pairs += 1
            if terminated(cur):
                break
            j = ri.joined(toks(cur), toks(nxt)) if ri else 'noraw'
            blocked = block_merge or (cur_pinned and i in pinned)
            if j == 'join' and not re.search(r'\S[-־]$', cur.rstrip()) and not blocked:
                note('b_broken_fixable', i - 1, plain(cur)[-25:] + ' || ' + plain(nxt)[:25])
                cur = cur.rstrip() + ' ' + nxt.lstrip()
                cur_pinned = cur_pinned or i in pinned
                linemap.append(len(out))
                i += 1
                merged += 1
                continue
            if j == 'join':
                note('b_broken_blocked_links' if blocked else 'b_broken_ends_hyphen',
                     i - 1, plain(cur)[-25:] + ' || ' + plain(nxt)[:25])
            elif j == 'break':
                st['b_unterminated_raw_also_breaks'] += 1
            else:
                note('b_unterminated_no_evidence', i - 1, plain(cur)[-25:] + ' || ' + plain(nxt)[:25])
            break
        out.append(cur)
    body = [l for l in L if is_body(l)]
    st['amp_leftover'] = sum(l.count('&amp;') for l in L)
    res = {'lines': len(L), 'body_lines': len(body), 'body_pairs': n_body_pairs,
           'merged': merged, 'heading_fixes': fixes_h,
           'stats': dict(st), 'examples': {k: v for k, v in ex.items()}, 'linemap': linemap}
    if apply and (merged or fixes_h):
        open(full, 'w', encoding='utf-8', newline='').write('\n'.join(out))
    return res


def main():
    if sys.argv[1:2] == ['dbs-raw']:
        if len(sys.argv) != 4:
            sys.exit('usage: dbs_breaks.py dbs-raw UNITS.jsonl OUT.txt')
        return dbs_raw(sys.argv[2], sys.argv[3])
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['scan', 'fix'])
    ap.add_argument('--commit', nargs='+', default=DEFAULT_COMMITS)
    ap.add_argument('--raw-map', help='JSON {נתיב ספר: קובץ גולמי}; מעבד רק את הספרים האלה, עם הגולמי הזה')
    ap.add_argument('--out', default='dbs_breaks_report.json')
    ap.add_argument('--exclude', nargs='*', default=[])
    ap.add_argument('--hand-headings', nargs='*', default=HAND_HEADINGS,
                    help='ספרים שמקבלים איחוד שורות בלבד, בלי תיקוני כותרות')
    a = ap.parse_args()
    apply = a.mode == 'fix'
    raw_map = json.load(open(a.raw_map, encoding='utf-8')) if a.raw_map else None
    books = list(raw_map) if raw_map else books_of_commits(a.commit, a.exclude)
    raws = {os.path.basename(p): [raw_map[p]] for p in raw_map} if raw_map else raw_files()
    allraw = [f for v in raws.values() for f in v]
    cache = {}
    lidx = links_index()
    titles = packaged_title_counts()
    report = {}
    for p in books:
        b = os.path.basename(p)
        title = b[:-4]
        cands = raws.get(b) or []
        rp = cands[0] if cands else find_raw_by_content(p, allraw, cache)
        ri = RawIndex(rp) if rp else None
        files = lidx.get(title, [])
        ambiguous = bool(files) and titles[title] > 1
        r = process(p, ri, apply, pinned_lines(title), block_merge=ambiguous,
                    fix_headings=not any(h in p for h in a.hand_headings))
        linemap = r.pop('linemap')
        r['raw'] = os.path.relpath(rp, REPO) if rp else None
        r['links_files'] = files
        r['links_shifted'] = shift_links(title, files, linemap) if apply and r['merged'] else {}
        report[p] = r
    json.dump(report, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tot = collections.Counter()
    for r in report.values():
        for k, v in r['stats'].items():
            tot[k] += v
        tot['merged'] += r['merged']
        tot['heading_fixes'] += r['heading_fixes']
        tot['links_values_shifted'] += sum(r['links_shifted'].values())
    print('books scanned: %d, without raw: %d' % (len(report), sum(1 for r in report.values() if not r['raw'])))
    for k, v in sorted(tot.items()):
        print('%-36s %d' % (k, v))


if __name__ == '__main__':
    main()
