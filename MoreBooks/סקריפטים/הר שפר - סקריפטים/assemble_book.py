#!/usr/bin/env python3
"""events.json -> הר שפר.txt + הערות על הר שפר.txt + הר שפר_links.json"""
import json, os, re, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from copyright_line import COPYRIGHT_LINE  # שורה 3 של הספר

EV = sys.argv[1]
OUTDIR = sys.argv[2]
FIXES = json.load(open(sys.argv[3], encoding="utf-8")) if len(sys.argv) > 3 else {}

TITLE = "הר שפר"
NOTES_TITLE = "הערות על הר שפר"
AUTHOR_LINE = "רבי שמואל פירר"

ev = json.load(open(EV, encoding="utf-8"))


def esc(t):
    assert "<" not in t and ">" not in t and "&" not in t, t
    return t


def norm_runs(runs, keep_small=True):
    """אחד ריצות, הוצא רווחים מחוץ לתגיות, שמור סמנים."""
    out = []
    for t, st in runs:
        if st == "br":
            out.append([t, "br"]); continue
        if st == "s" and not keep_small:
            st = ""
        if out and out[-1][1] == st and st not in ("sup", "br"):
            out[-1][0] += t
        else:
            out.append([t, st])
    # רווחים מחוץ לתגיות
    res = []
    for t, st in out:
        if st in ("b", "s"):
            m = re.match(r"^(\s*)(.*?)(\s*)$", t, re.S)
            lead, core, trail = m.groups()
            if lead:
                res.append([lead, ""])
            if core:
                res.append([core, st])
            if trail:
                res.append([trail, ""])
        else:
            res.append([t, st])
    out = []
    for t, st in res:
        if out and out[-1][1] == st and st not in ("sup", "br"):
            out[-1][0] += t
        else:
            out.append([t, st])
    return out


def render(runs, keep_small=True):
    runs = norm_runs(runs, keep_small)
    s = ""
    for t, st in runs:
        if st == "br":
            s += "<br>"
        elif st == "sup":
            s += f"<sup>{esc(t)}</sup>"
        elif st == "b":
            s += f"<b>{esc(t)}</b>"
        elif st == "s":
            s += f"<small>{esc(t)}</small>"
        else:
            s += esc(t)
    s = s.replace("\u201d", '"').replace("\u201c", '"').replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"[ \t]+", lambda m: m.group(0) if len(m.group(0)) >= 4 else " ", s)
    return s.strip()


def plain(runs):
    t = "".join(t for t, st in runs if st != "sup")
    t = t.replace("\u201d", '"').replace("\u201c", '"').replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", t).strip()


# ---------- הרכבת אירועים לבלוקים ----------
SECTION_TITLES = {  # טקסט כותרת 'chap' -> (רמה, סימון חלק)
}

base = []     # רשימת [kind, html, meta]
notes_raw = []  # הערות: dict(sec, label, runs)
sec = 0
pending_marks = []   # סמנים מכותרות שמחכים לפסקה הבאה
chap_has_daf = False
in_partB = False
in_horayot = False
emitted_part_a_h2 = False
emitted_part_b_h2 = False
section_of_marker = []

# הערות: איחוד המשכים
cur_note = None
prev_x0 = 0.0
note_list = []
for e in ev:
    if e["k"] == "note":
        newnote = e["new"]
        label = e["label"]
        if e["pg"] == 185:      # הערה ללא תווית ללא סמן (דברים אחדים)
            if cur_note is None or cur_note["pg"] != 185:
                newnote = True; label = "א"
            else:
                newnote = False
        if newnote:
            cur_note = dict(label=label, runs=[list(r) for r in e["runs"]], pg=e["pg"], sec=None)
            note_list.append(cur_note)
        else:
            assert cur_note is not None
            rr = [list(r) for r in e["runs"]]
            if prev_x0 > 92.0:
                cur_note["runs"].append(["<<BR>>", "br"])
            elif cur_note["runs"] and rr and not cur_note["runs"][-1][0].endswith(" "):
                if cur_note["runs"][-1][1] in ("sup", "br"):
                    cur_note["runs"].append([" ", ""])
                else:
                    cur_note["runs"][-1][0] += " "
            cur_note["runs"].extend(rr)
        prev_x0 = e["x0"]

lines = []   # (kind, html, markers_in_line:list[(label,sec)], level)


def add_line(kind, html, marks=None, level=None):
    global last_h
    if kind == "h" and level:
        last_h = level
    lines.append(dict(kind=kind, html=html, marks=marks or [], level=level))


def split_sig(text):
    return [x for x in re.split(r"\s{4,}", text) if x.strip()]


# שער והקדשה
add_line("h", f"<h1>{TITLE}</h1>")
add_line("t", AUTHOR_LINE)
add_line("t", COPYRIGHT_LINE)

SEC_BIO, SEC_C1, SEC_C2, SEC_C3, SEC_B = "bio", "c1", "c2", "c3", "B"
cur_sec = None
last_h = 1
topic_lvl = None

# מניעת כפילות: ספרור פרקים
for i, e in enumerate(ev):
    k = e["k"]
    if k == "h":
        txt = plain(e["runs"])
        marks = [t for t, st in e["runs"] if st == "sup"]
        title_runs = [r for r in e["runs"] if r[1] != "sup"]
        title = plain(title_runs)
        kind = e["kind"]
        if kind == "chap":
            if title == "פתח דבר":
                cur_sec = None
                add_line("h", "<h2>פתח דבר</h2>", level=2)
            elif title.startswith("פרק "):
                cur_sec = {"פרק ראשון": SEC_C1, "פרק שני": SEC_C2, "פרק שלישי": SEC_C3}[title]
                if title == "פרק ראשון":
                    add_line("h", "<h2>מסכת הוריות</h2>", level=2)
                add_line("h", f"<h3>{esc(title)}</h3>", level=3)
                chap_has_daf = False
                topic_lvl = None
            elif title == "דברים אחדים":
                cur_sec = SEC_B
                add_line("h", '<h2>חידושי תורה על סוגיות הש"ס ומדרשים</h2>', level=2)
                add_line("h", "<h3>דברים אחדים</h3>", level=3)
            elif title.startswith('הר שפר על סוגיות'):
                add_line("h", f"<h3>{esc(title)}</h3>", level=3)
                in_partB = True
            else:
                raise SystemExit("כותרת chap לא מוכרת: " + title)
        elif kind == "topic":
            if e["pg"] == 308:
                add_line("h", f"<h3>נספח - {esc(title)}</h3>", level=3)
            elif in_partB:
                add_line("h", f"<h4>{esc(title)}</h4>", level=4)
                topic_lvl = 4
            else:
                lvl = 5 if chap_has_daf else 4
                add_line("h", f"<h{lvl}>{esc(title)}</h{lvl}>", level=lvl)
                topic_lvl = lvl
        elif kind == "sub" and e["pg"] == 308:
            # מקור מבולבל (סוגריים/ספרות); תוקן ידנית מול התמונה
            add_line("t", '<small>(מתוך ספר אגרות ותולדות מהר"ם שפירא מלובלין, עמ\' 80)</small>')
        else:
            raise SystemExit("סוג כותרת לא צפוי: " + kind)
        for m in marks:
            pending_marks.append((m, cur_sec))
        continue
    if k == "daf":
        chap_has_daf = True
        topic_lvl = None
        t = e["text"].strip()
        add_line("h", f"<h4>{esc(t)}</h4>", level=4)
        continue
    if k == "p" and e.get("sub"):
        marks = [t for t, st in e["runs"] if st == "sup"]
        title = plain([r for r in e["runs"] if r[1] != "sup"])
        base_l = (topic_lvl if topic_lvl else last_h) + 1
        lvl = min(base_l, last_h + 1, 6)
        add_line("h", f"<h{lvl}>{esc(title)}</h{lvl}>", level=lvl)
        for m in marks:
            pending_marks.append((m, cur_sec))
        continue
    if k == "p":
        runs = [list(r) for r in e["runs"]]
        marks = [(t, cur_sec) for t, st in runs if st == "sup"]
        # פסקה מחולקת לפי רווחים ארוכים (שורות חתימה)
        s = render(runs)
        parts = split_sig(s) if re.search(r"\s{4,}", s) else [s]
        if pending_marks:
            pre = "".join(f"<sup>{esc(m)}</sup>" for m, _ in pending_marks)
            parts[0] = pre + parts[0]
            marks = pending_marks + marks
            pending_marks = []
        for j, part in enumerate(parts):
            add_line("p", part.strip(), marks=marks if j == 0 else [])
        continue

# מכתב הנספח: הנוסח המודפס שבתחתית עמ' 308 הוא תמונה — הוקלד ידנית
for t in [
    "שמואל פיהרער",
    'אב"ד דק"ק קראס יצ"ו',
    'ב"ה קראס צום גדליה תרפ"ח לפ"ק',
    '<b>התולה ארץ על בלימה, הוא ייטיב את החתימה, לכבוד ידידי ה"ה הרב המפורסם הגאון הגדול, מעוז ומגדול, רב פעלים, בכשרונותיו הנעלים, סיני ועוקר הרי הרים, בפלפולים יקרים, הוד שמו מפארים, מו"ה מאיר שפירא שליט"א האבד"ק פיעטרקוב יצ"ו.</b>',
    'אחדשכהד"ג. אביעה תודה ותש"ח לכת"ה עבור התשורה אשר כיבדני בספרו הבהיר וצהיר המשובח והמפואר <b>"אור המאיר"</b> אשר אור לו בציון המצינת בהלכה וכל הוגי תושי\' ומלומדי למד נהנים מאורו. וכבר נתתי מעות קדימה דמי מחירו עוד אשתקד לר\' אהרן וועבער מקארטשין.',
    'והנני שולח את ספרי הר שפר קרבן שלמים להשלמת מאת אלף ספרים לעקד הספרים של "ישיבת חכמי לובלין".',
    'ובזה הנני ידידו דושת"ה בלונ"ח ומברכו בגח"ט, מוקירו ומכבדו כערכו הרם והנשא.',
    '<b>שמואל פיהרער אבד"ק הנ"ל</b>',
]:
    add_line("p", t)

# ---------- הערה ללא סמן בגוף (דברים אחדים) ----------
# הערת "הקדמה זו נכתבה..." — ללא סמן בטקסט; מצורפת לכותרת "דברים אחדים"

# ---------- שיוך הערות לחלקים ----------
GV = {}
# קביעת החלק של כל הערה לפי עמוד
def sec_of_page(pg):
    if 21 <= pg <= 94: return SEC_C1
    if 97 <= pg <= 126: return SEC_C2
    if 129 <= pg <= 182: return SEC_C3
    if 185 <= pg <= 307: return SEC_B
    raise SystemExit(f"עמוד הערה לא צפוי: {pg}")


# הערות שמופיעות בעמוד הראשון של חלק הערות לפי עמוד תחילתן
for n in note_list:
    n["sec"] = sec_of_page(n["pg"])

# ---------- התאמה: סמן -> הערה ----------
avail = collections.defaultdict(list)   # (sec,label) -> [notes] לפי סדר
for n in note_list:
    avail[(n["sec"], n["label"])].append(n)
unmatched_marks = []
links = []   # (base_line_idx, note)
for idx, ln in enumerate(lines):
    for (m, s) in ln["marks"]:
        cands = avail.get((s, m), [])
        if not cands:
            unmatched_marks.append((idx, m, s))
            continue
        n = cands.pop(0)
        n["base_idx"] = idx
leftover = [n for n in note_list if "base_idx" not in n]
print("notes", len(note_list), "unmatched markers", unmatched_marks, "leftover notes", [(n["sec"], n["label"], n["pg"]) for n in leftover])

# הערה "א" של דברים אחדים — ללא סמן: שייך לכותרת "דברים אחדים"
for n in leftover:
    if n["sec"] == SEC_B and n["label"] == "א":
        # שורת הפסקה הראשונה אחרי הכותרת 'דברים אחדים'
        hi = next(i for i, l in enumerate(lines) if l["html"] == "<h3>דברים אחדים</h3>")
        pi = next(i for i in range(hi + 1, len(lines)) if lines[i]["kind"] == "p")
        lines[pi]["html"] = "<sup>א</sup>" + lines[pi]["html"]
        n["base_idx"] = pi
leftover = [n for n in note_list if "base_idx" not in n]
assert not leftover, leftover

# ---------- פלט ----------
for k, v in FIXES.get("line_replace", {}).items():
    pass

base_text = "\n".join(l["html"] for l in lines) + "\n"

# ספר ההערות: מסודר לפי שורת בסיס ואז מיקום הסמן בשורה
def marker_pos(n):
    h = lines[n["base_idx"]]["html"]
    m = re.search(r"<sup>" + re.escape(n["label"]) + r"</sup>", h)
    return m.start() if m else 10 ** 9


# לכל שורה: ההערות לפי סדר הופעת הסמנים (מימין לשמאל = לפי מיקום המחרוזת)
by_line = collections.defaultdict(list)
for n in note_list:
    by_line[n["base_idx"]].append(n)
note_lines = []
link_rows = []
for bi in sorted(by_line):
    html = lines[bi]["html"]
    # סדר ההערות בקובץ ההערות = סדר סמנים בשורה (לפי מיקום הסמן ה"שמאלי ביותר שלא נצרך")
    ordered = []
    used = []
    ns = by_line[bi]
    # הצבה: סמן i מתאים להערה עם אותה תווית; אם התווית חוזרת, לפי סדר
    positions = []
    for m in re.finditer(r"<sup>([^<]+)</sup>", html):
        positions.append(m.group(1))
    pool = list(ns)
    for lab in positions:
        for n in pool:
            if n["label"] == lab:
                ordered.append(n); pool.remove(n); break
    assert not pool, (bi, [p["label"] for p in pool], positions)
    for n in ordered:
        note_lines.append(n)
        link_rows.append((bi + 1, len(note_lines)))

note_txt = []
for n in note_lines:
    body = render(n["runs"], keep_small=False)
    note_txt.append(f"<sup>{esc(n['label'])}</sup> {body}")

open(f"{OUTDIR}/{TITLE}.txt", "w", encoding="utf-8").write(base_text)
open(f"{OUTDIR}/{NOTES_TITLE}.txt", "w", encoding="utf-8").write("\n".join(note_txt) + "\n")
links = [dict(line_index_1=a, heRef_2="הערות", path_2=f"{NOTES_TITLE}.txt", line_index_2=b, **{"Conection Type": "footnotes"}) for a, b in link_rows]
json.dump(links, open(f"{OUTDIR}/{TITLE}_links.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(f"{OUTDIR}/{TITLE}_links.json", "a").write("\n")
print("base lines", len(lines), "notes", len(note_txt), "links", len(links))
