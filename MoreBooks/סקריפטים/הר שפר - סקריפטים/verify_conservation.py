import sys, re, collections, subprocess, html
import os
PDFPATH, OUTDIR = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = ["x", PDFPATH, os.path.join(OUTDIR, "events.json")]
import extract_pdf as X, pymupdf
from copyright_line import COPYRIGHT_LINE
doc = pymupdf.open(X.PDF)
inc = [p for p in range(1, len(doc)+1) if p not in X.SKIP]
out_base = open(os.path.join(OUTDIR, "הר שפר.txt"), encoding="utf-8").read()
assert out_base.count(COPYRIGHT_LINE) == 1, "שורת זכויות היוצרים חסרה"
out_base = out_base.replace(COPYRIGHT_LINE, "")  # לא קיימת ב־PDF
out_notes = open(os.path.join(OUTDIR, "הערות על הר שפר.txt"), encoding="utf-8").read()
def toks(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.findall(r"[א-ת]+|[0-9]+", s)
mine = collections.Counter(toks(out_base + "\n" + out_notes))
# מקור A: mupdf, מתחת לכותרת העליונה, ללא סמנים עיליים (נבדקים בנפרד) — אותיות בלבד
expA = collections.Counter()
for p in inc:
    pg = doc[p-1]
    d = pg.get_text("dict", clip=pymupdf.Rect(0, X.HDR_Y, 540, 739))
    for b in d["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["flags"] & 1: continue
                expA.update(toks(s["text"]))
# מקור B: poppler plain, לכל עמוד ללא כותרת עליונה (נגזר: מילים מ-bbox y>=HDR_Y)
pw = X.poppler_pages()
expB = collections.Counter()
for p in inc:
    for (x0, y0, x1, y1, t) in pw[p-1]:
        if y0 < X.HDR_Y: continue
        lt = X.logical_word(t)
        expB.update(toks(lt))
def canon(c):
    out = collections.Counter()
    for k, v in c.items():
        out[("".join(sorted(k)) if len(k) <= 3 else k)] += v
    return out
sup_mine = collections.Counter(m.group(1) for m in re.finditer(r"<sup>([^<]+)</sup>", out_base))
mine_nosup = mine.copy()
for k, v in sup_mine.items(): mine_nosup[k] -= v          # סמנים בבסיס (mupdf לא סופר sup)
mine_nosup = +mine_nosup
for name, exp, m in (("mupdf (ללא sup)", expA, mine_nosup), ("poppler-bbox (הכול)", expB, mine)):
    miss = canon(exp) - canon(m)
    extra = canon(m) - canon(exp)
    print(f"== {name}: expected {sum(exp.values())} mine {sum(m.values())}  missing {sum(miss.values())}  extra {sum(extra.values())}")
    print("  missing:", list(miss.items())[:40])
    print("  extra:", list(extra.items())[:40])
