"""
Build the manual-linking viewer dataset:

  otzaria_mb.txt   - Otzaria משנה ברורה (seforim.db bookId 5832), one DB line per
                     file line, in lineIndex order. file line N == DB lineIndex N
                     == link "line_index_1".
  תא שמע.txt        - Tashma משנה ברורה (book_12006), per ס"ק, שער-הציון markers kept
                     inline as {{ot}} tokens.
  שער הציון.txt     - Tashma שער הציון notes, one note per line (== "line_index_2").
  shaar_links.json - links in Otzaria format (line_index_1 / heRef_2 / path_2 /
                     line_index_2 / mb_char_index) + UI fields (class, siman...).
  viewer_index.json- navigation index (siman -> header line in each pane).

Char placement reuses the alignment from link_shaar (normalize + SequenceMatcher).
"""
import json
import re
import sys
import io
import sqlite3
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
RAW_JSON = Path("book_12006_1779653718165.json")
DB_PATH = Path(r"C:\ProgramData\otzaria\books\seforim.db")
MB_BOOK_ID = 5832

F_OTZ = "otzaria_mb.txt"
F_TASH = "תא שמע.txt"
F_SH = "שער הציון.txt"
# Otzaria book preamble: line 1 = <h1> title, line 2 = author. Every packaged book
# carries it, and metadata.json's author is scraped from line 2 — emitting the notes
# without it made "(א) מטור" the author of שער הציון. The notes therefore start at
# file line 3, which every "line_index_2" below accounts for automatically (they are
# derived from len(sh_lines), so seeding the list is the only change needed).
SH_PREAMBLE = ["<h1>שער הציון</h1>", "רבי ישראל מאיר הכהן"]
OUT_LINKS = HERE / "shaar_links.json"
OUT_INDEX = HERE / "viewer_index.json"

PRELUDE_SIMANIM = {"הקדמה", "הקדמה להלכות שבת"}
sh_pattern = re.compile(r"<@#שער הציון#([^#]+)#(.+?)[:.]?\s*@>", re.DOTALL)
HEB = re.compile(r"[א-ת]")

# Some simanim lump a whole "קונטרס" into a single ס"ק in the Tashma source while
# seforim.db splits the same material across many sub-section lines. e.g. סימן ל"ו:
# the entire קונטרס משנת סופרים (צורת כל אות, כללי שלא כסדרן וכו') sits inside ס"ק ט"ו
# in the source, but the DB holds it as separate ס"ק ט"ז ... פ"ב. Keying ט"ו->ט"ו alone
# dumps all ~148 tags onto one short DB line (everything falls to "שורה"). For these we
# align the source ס"ק against the *concatenated* DB span and map each tag back to its
# own DB sub-section line.
#   (siman_gem, seif_gem) -> first seif_gem of the DB span to concatenate
KUNTRES_SPLIT = {(36, 15): 15}   # סימן ל"ו ס"ק ט"ו -> span ס"ק ט"ו..סוף
_B_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_LEAD_ORD = re.compile(r"^\s*(?:\([^)]*\)\s*)+")


def build_kuntres_target(otz_line_of, otz_content, sg, from_seif):
    """Concatenate all DB sub-section lines (sg, s>=from_seif) in lineIndex order.
    HTML tags and the leading "(ord)" markers are dropped from the alignment text but
    every kept char maps back to (lineIndex, original-offset-in-that-line's-content).
    Returns (Bstr, Bmap, first_lineIndex)."""
    segs = sorted(((s2, li) for (s1, s2), li in otz_line_of.items()
                   if s1 == sg and s2 >= from_seif),
                  key=lambda x: x[1])
    B, Bmap = [], []
    for _s2, li in segs:
        content = otz_content[li]
        mask = [True] * len(content)
        for mt in _B_TAG.finditer(content):
            for j in range(mt.start(), mt.end()):
                mask[j] = False
        om = _LEAD_ORD.match(content)
        if om:
            for j in range(om.start(), om.end()):
                mask[j] = False
        for j, ch in enumerate(content):
            if mask[j]:
                B.append(ch); Bmap.append((li, j))
        B.append("\n"); Bmap.append((li, len(content)))   # separator between sections
    return "".join(B), Bmap, (segs[0][1] if segs else None)

GEM = {'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,
       'י':10,'כ':20,'ל':30,'מ':40,'נ':50,'ס':60,'ע':70,'פ':80,'צ':90,
       'ק':100,'ר':200,'ש':300,'ת':400,'ך':20,'ם':40,'ן':50,'ף':80,'ץ':90}
def gematria(s): return sum(GEM.get(c, 0) for c in s)

ABBREVIATIONS = {
    'הקב"ה':'הקדושברוךהוא','ממ"ה':'מלךמלכיהמלכים','ב"ו':'בשרודם',
    'כ"ש':'כלשכן','וכ"ש':'וכלשכן','מכ"ש':'מכלשכן','ומכ"ש':'ומכלשכן',
    'ק"ו':'קלוחומר','וק"ו':'וקלוחומר','ר"ל':'רוצהלומר','אעפ"כ':'אףעלפיכן',
    'אעפ"י':'אףעלפי','אע"ג':'אףעלגב','אע"פ':'אףעלפי','ע"י':'עלידי',
    'עפ"י':'עלפי','עי"ז':'עלידיזה','ע"ז':'עלזה','ע"ש':'עייןשם',
    'אח"כ':'אחרכך','ז"ל':'זכרונולברכה','מ"מ':'מכלמקום','ומ"מ':'ומכלמקום',
    'מ"ע':'מצותעשה','ת"ת':'תלמודתורה','ד"א':'ארבעאמות','כד\'':'כארבע',
    "ד'":'ארבע','ג"פ':'שלושפעמים','נט"י':'נטילתידיים','נ"י':'נטילתידיים',
    'מד"ת':'מדבריתורה','בעה"ב':'בעלהבית','עוה"ז':'העולםהזה','עוה"ב':'העולםהבא',
    'ק"ש':'קריאתשמע','בה"כ':'ביתהכנסת','בהכ"נ':'ביתהכנסת','ביהכ"נ':'ביתהכנסת',
    'ב"י':'ביתיוסף','ב"ח':'ביתחדש','ש"ץ':'שליחציבור','יו"ט':'יוםטוב',
    'יוה"כ':'יוםהכפורים','יו"כ':'יוםהכפורים','ר"ה':'ראשהשנה','ר"ח':'ראשחודש',
    'מג"א':'מגןאברהם','מ"א':'מגןאברהם','ט"ז':'טוריזהב','ש"ך':'שפתיכהן',
    'פמ"ג':'פרימגדים','א"ר':'אליהרבה','שו"ע':'שולחןערוך','דה"ח':'דרךהחיים',
    'ח"א':'חייאדם','זוה"ק':'זוהרהקדוש','ובזוה"ק':'ובזוהרהקדוש',
    'י"א':'ישאומרים','כ"א':'כיאם','וכו\'':'וכו','וגו\'':'וגו',
}
_ABBR_MAX = max(len(k) for k in ABBREVIATIONS)

def normalize(s):
    out, idx_map = [], []
    i, n = 0, len(s)
    while i < n:
        matched = False
        for L in range(min(_ABBR_MAX, n - i), 1, -1):
            exp = ABBREVIATIONS.get(s[i:i+L])
            if exp is not None:
                for ch in exp:
                    out.append(ch); idx_map.append(i)
                i += L; matched = True; break
        if matched:
            continue
        if HEB.match(s[i]):
            out.append(s[i]); idx_map.append(i)
        i += 1
    return "".join(out), idx_map

def build_aligned(normA, normB):
    sm = SequenceMatcher(a=normA, b=normB, autojunk=False)
    alignedB = [None] * len(normA)
    matched = 0
    for tag, a1, a2, b1, b2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(a2 - a1):
                alignedB[a1 + k] = b1 + k
            matched += a2 - a1
    return alignedB, matched

def classify(p, alignedB, nlen):
    i = p - 1
    while i >= 0 and alignedB[i] is None:
        i -= 1
    if i >= 0:
        skip = (p - 1) - i
        run, k = 1, i
        while k - 1 >= 0 and alignedB[k-1] is not None and alignedB[k-1] == alignedB[k] - 1:
            run += 1; k -= 1
        q = alignedB[i] + 1
        if skip == 0 and run >= 8: return "ודאי", q, run
        if skip == 0 and run >= 3: return "גבוה", q, run
        if skip <= 6 and run >= 2: return "נמוך", q, run
    j = p
    while j < nlen and alignedB[j] is None:
        j += 1
    if j < nlen:
        skip_r = j - p
        run_r, k = 1, j
        while k + 1 < nlen and alignedB[k+1] is not None and alignedB[k+1] == alignedB[k] + 1:
            run_r += 1; k += 1
        if skip_r <= 6 and run_r >= 2:
            return "נמוך", alignedB[j], run_r
    return None, None, 0


def main():
    print("loading book_12006 ...")
    data = json.loads(RAW_JSON.read_text(encoding="utf-8"))
    book = data["contain"]["אורח חיים"]

    # ---------- 1. export Otzaria MB text + index ----------
    print("exporting", F_OTZ, "...")
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    cur.execute("SELECT lineIndex, content, heRef FROM line WHERE bookId=? ORDER BY lineIndex",
                (MB_BOOK_ID,))
    otz_rows = cur.fetchall()
    con.close()
    otz_content = {}                 # lineIndex -> content
    otz_line_of = {}                 # (siman_gem, seif_gem) -> lineIndex
    otz_siman_hdr = {}               # siman_gem -> lineIndex of <h2>
    otz_sections = []                # [(label, lineIndex)] every <h2> incl preludes
    nlines = 0
    with (HERE / F_OTZ).open("w", encoding="utf-8", newline="\n") as f:
        for li, content, heref in otz_rows:
            content = content.replace("\n", " ").replace("\r", " ")
            f.write(content + "\n")
            otz_content[li] = content
            nlines += 1
            mh = re.match(r"^<h2>(.+)</h2>$", content)
            if mh:
                otz_sections.append((mh.group(1).strip(), li))
            m = re.match(r"^<h2>סימן (.+)</h2>$", content)
            if m:
                otz_siman_hdr[gematria(m.group(1).strip())] = li
            if heref:
                parts = heref.split(',')
                if len(parts) >= 3:
                    siman = parts[1].strip(); seif = parts[-1].strip()
                    if siman not in PRELUDE_SIMANIM:
                        otz_line_of.setdefault((gematria(siman), gematria(seif)), li)
    print(f"  {nlines} lines, {len(otz_line_of)} ס\"ק mapped, {len(otz_siman_hdr)} siman headers")

    # ---------- 2. export Tashma MB (markers inline) + שער הציון notes ----------
    print("exporting", F_TASH, "and", F_SH, "...")
    tash_lines = []
    sh_lines = list(SH_PREAMBLE)
    tash_hdr_gem = {}      # siman_gem -> file line (0-based)
    sh_hdr_gem = {}        # siman_gem -> file line
    note_lines = []        # k-th שער-הציון match -> its 1-based file line (document order)
    for siman, simanv in book.items():
        tash_hdr_gem[gematria(siman)] = len(tash_lines)
        sh_hdr_gem[gematria(siman)] = len(sh_lines)
        tash_lines.append(f"<h2>סימן {siman}</h2>")
        sh_lines.append(f"<h2>סימן {siman}</h2>")
        for seif, text in simanv.items():
            disp = sh_pattern.sub(lambda m: "{{" + m.group(1) + "}}", text)
            tash_lines.append(f"({seif}) {disp}")
            for m in sh_pattern.finditer(text):
                ot = m.group(1)
                note_lines.append(len(sh_lines) + 1)   # 1-based line of this note
                sh_lines.append(f"({ot}) {m.group(2).strip()}")
    (HERE / F_TASH).write_text("\n".join(tash_lines) + "\n", encoding="utf-8", newline="\n")
    (HERE / F_SH).write_text("\n".join(sh_lines) + "\n", encoding="utf-8", newline="\n")
    print(f"  תא שמע: {len(tash_lines)} lines | שער הציון: {len(sh_lines)} lines")

    # ---------- 3. compute links ----------
    print("aligning + classifying ...")
    links = []
    cls_count = Counter()
    lid = 0
    k = 0           # global match counter -> note_lines index (same document order)
    for siman, simanv in book.items():
        sg = gematria(siman)
        for seif, text in simanv.items():
            matches = list(sh_pattern.finditer(text))
            if not matches:
                continue
            clean_full = sh_pattern.sub("", text)
            okey = (sg, gematria(seif))

            if okey in KUNTRES_SPLIT:
                # kuntres lumped into one source ס"ק -> align vs concatenated DB span,
                # map each tag back to its own DB sub-section line.
                Bstr, Bmap, first_li = build_kuntres_target(
                    otz_line_of, otz_content, sg, KUNTRES_SPLIT[okey])
                normA, _ = normalize(clean_full)
                normB, mapB = normalize(Bstr)
                alignedB, matched = build_aligned(normA, normB)
                ratio = matched / max(len(normA), 1)
                for m in matches:
                    ot = m.group(1)
                    l2 = note_lines[k]; k += 1
                    rec = {
                        "id": lid,
                        "line_index_1": None,
                        "heRef_2": f"שער הציון, סימן {siman}, סעיף {seif} אות {ot}",
                        "path_2": F_SH,
                        "line_index_2": l2,
                        "mb_char_index": None,
                        "class": None,
                        "siman": siman, "seif": seif, "ot": ot,
                        "sh_text": m.group(2).strip(),
                        "lemma": sh_pattern.sub("", text[:m.start()])[-30:],
                    }
                    lid += 1
                    prefix_clean = sh_pattern.sub("", text[:m.start()])
                    p = min(len(normalize(prefix_clean)[0]), len(normA))
                    cls, qnorm, run = classify(p, alignedB, len(normA))
                    if cls is None or ratio < 0.25 or first_li is None:
                        rec["class"] = "שורה"
                        rec["line_index_1"] = (first_li + 1) if first_li is not None else None
                    else:
                        bpos = len(Bstr) if qnorm >= len(mapB) else mapB[qnorm]
                        seg_li, off = Bmap[bpos] if bpos < len(Bmap) else Bmap[-1]
                        rec["class"] = cls
                        rec["line_index_1"] = seg_li + 1
                        rec["mb_char_index"] = off
                        rec["left_run"] = run
                    links.append(rec)
                    cls_count[rec["class"]] += 1
                continue

            l1 = otz_line_of.get(okey)
            if l1 is None:
                normA = alignedB = None
            else:
                normA, _ = normalize(clean_full)
                normB, mapB = normalize(otz_content[l1])
                alignedB, matched = build_aligned(normA, normB)
                ratio = matched / max(len(normA), 1)
            for m in matches:
                ot = m.group(1)
                l2 = note_lines[k]          # 1-based, document-order aligned
                k += 1
                rec = {
                    "id": lid,
                    "line_index_1": (l1 + 1) if l1 is not None else None,  # 1-based
                    "heRef_2": f"שער הציון, סימן {siman}, סעיף {seif} אות {ot}",
                    "path_2": F_SH,
                    "line_index_2": l2,                                    # 1-based
                    "mb_char_index": None,
                    "class": None,
                    "siman": siman, "seif": seif, "ot": ot,
                    "sh_text": m.group(2).strip(),
                    "lemma": sh_pattern.sub("", text[:m.start()])[-30:],
                }
                lid += 1
                if l1 is None:
                    rec["class"] = "אחר"
                else:
                    prefix_clean = sh_pattern.sub("", text[:m.start()])
                    p = min(len(normalize(prefix_clean)[0]), len(normA))
                    cls, qnorm, run = classify(p, alignedB, len(normA))
                    if cls is None or ratio < 0.25:
                        rec["class"] = "שורה"
                    else:
                        rec["class"] = cls
                        rec["mb_char_index"] = (len(otz_content[l1]) if qnorm >= len(mapB)
                                                else mapB[qnorm])
                        rec["left_run"] = run
                links.append(rec)
                cls_count[rec["class"]] += 1

    OUT_LINKS.write_text(json.dumps(links, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT_LINKS} ({len(links)} links) classes={dict(cls_count)}")

    # ---------- 4. navigation index (every Otzaria <h2>, incl. preludes) ----------
    nav = []
    for label, otz_li in otz_sections:
        m = re.match(r"^סימן (.+)$", label)
        g = gematria(m.group(1).strip()) if m else None
        th = tash_hdr_gem.get(g) if g is not None else None
        shh = sh_hdr_gem.get(g) if g is not None else None
        nav.append({
            "s": label,                      # display label (סימן א / הקדמה / ...)
            "otz": otz_li + 1,               # 1-based
            "tash": (th + 1) if th is not None else None,
            "sh": (shh + 1) if shh is not None else None,
            "prelude": m is None,
        })
    index = {
        "files": {"otzaria": F_OTZ, "tashma": F_TASH, "shaar": F_SH},
        "line_index_base": "1-based: file line N == index N (line 1 = first line of file)",
        "simanim": nav,
    }
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT_INDEX} ({len(nav)} sections)")


if __name__ == "__main__":
    main()
