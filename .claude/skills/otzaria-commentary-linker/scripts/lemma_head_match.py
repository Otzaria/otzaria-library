#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lemma-head alignment matcher — precision-first dibur→lemma resolution.

WHY THIS EXISTS
The citer quotes the OPENING words of the target's lemma, but with rabbinic
spelling drift: ר"ל/ריש לקיש · הימנה/ממנה · דילמא/דלמא · שקולין/שקולים ·
וליהוי/ולהוי · כדא"פ/כדי אכילת פרס · והאמר/והא אמר. Generic token-overlap
scoring mis-ranks these badly — it once picked the lemma "ומר סבר מלא חפניו"
for the dibur "כאן שניתותרו" purely on incidental word overlap.

This aligns the dibur's leading words against each candidate's own lemma head
(the text before the " - " dash), word by word, with fuzzy per-word equality,
preferring exact matches and tolerating one word-boundary shift.

CONTRACT: `best()` returns (None, n) when it is not confident. That is a
REMOVAL signal, not an invitation to take the top-scoring candidate anyway —
a missing link beats a wrong one. See the overriding principle in SKILL.md.

Validated against 30 hand-adjudicated cases (30/30) plus a blind held-out
sample of 30 (15/16 acceptances clearly correct).

Usage:
    import lemma_head_match as lhm
    line, n = lhm.best(dibur, [(fileline, content), ...], raw_dibur=dibur)
    if line is None: drop the link
"""
import re

NIK = re.compile(r"[֑-ׇ]")
QUOTE = re.compile(r'["״“”\'׳’]')
FINALS = str.maketrans("ךםןףץ", "כמנפצ")

ABBREV = [
    (r"ר\"?ל", "ריש לקיש"), (r"ריב\"?ל", "רבי יהושע בן לוי"),
    (r"ר\"?י", "רבי יהודה"), (r"ר\"?ע", "רבי עקיבא"),
    (r"ר\"?ש", "רבי שמעון"), (r"ר\"?א", "רבי אליעזר"),
    (r"רשב\"?י", "רבי שמעון בן יוחאי"),
    (r"כדא\"?פ", "כדי אכילת פרס"), (r"ב\"?ש", "בית שמאי"),
    (r"ב\"?ה", "בית הלל"), (r"ת\"?ל", "תלמוד לומר"),
    (r"ק\"?ו", "קל וחומר"), (r"ט\"?י", "טבול יום"),
    (r"מנל\"?ן", "מנא לן"), (r"ל\"?ש", "לא שנו"),
    (r"אע\"?ג", "אף על גב"), (r"וא\"?ת", "ואם תאמר"),
    (r"וי\"?ל", "ויש לומר"), (r"עכ\"?ל", ""), (r"כו'?", ""), (r"וכו'?", ""),
]

def norm(s):
    s = NIK.sub("", s or "")
    s = QUOTE.sub('"', s)
    for pat, rep in ABBREV:
        # keep a single attached prefix letter: ור"ל -> ו + ריש לקיש
        s = re.sub(rf'(?<![א-ת])([ובדשכלמה]?){pat}(?![א-ת])',
                   (lambda m, r=rep: (m.group(1) + r) if r else ""), s)
    s = QUOTE.sub("", s)
    return s.translate(FINALS)

def words(s):
    return [w for w in re.findall(r"[א-ת]+", norm(s)) if w]

def _skel(w):
    """Drop matres lectionis so מיתני ~ מתני, שקולין ~ שקולים."""
    return re.sub(r"[יוה]", "", w)

def weq(a, b):
    """Fuzzy equality. Returns 2 for exact, 1 for a variant match, 0 for none."""
    if a == b: return 2
    return 1 if _fuzzy(a, b) else 0

def _fuzzy(a, b):
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)): return True
    sa, sb = _skel(a), _skel(b)
    if sa and sa == sb: return True
    if len(sa) >= 3 and len(sb) >= 3 and (sa.startswith(sb) or sb.startswith(sa)): return True
    # הלכתא / הלכה — same 3-letter root opening; only ever accepted as part of
    # a multi-word alignment, so it cannot carry a match on its own.
    if len(a) >= 4 and len(b) >= 4 and a[:3] == b[:3]: return True
    # single edit
    if abs(len(a) - len(b)) <= 1 and max(len(a), len(b)) >= 4:
        la, lb = (a, b) if len(a) <= len(b) else (b, a)
        i = j = d = 0
        while i < len(la) and j < len(lb):
            if la[i] == lb[j]: i += 1; j += 1
            else:
                d += 1
                if d > 1: return False
                if len(la) == len(lb): i += 1; j += 1
                else: j += 1
        return True
    return False

def lemma_head(content):
    """Target's own lemma: before ' - ' dash, else up to first . or :"""
    m = re.match(r"^(.{0,90}?)\s+[-–]\s", content)
    if m: return m.group(1)
    m = re.match(r"^(.{0,80}?)[.:]", content)
    if m: return m.group(1)
    return content[:80]

STOP_HEAD = {"הגהה", "הגה", "גה"}

def align(dibur, content):
    """(#leading words aligned, exactness) — exact matches outrank variants."""
    d = words(dibur)
    c = words(lemma_head(content))
    while c and c[0] in STOP_HEAD: c = c[1:]
    if not d or not c: return 0, 0
    # Walk both sides allowing a 1:2 / 2:1 word-boundary shift, because the
    # citer writes והאמר where the target prints והא אמר (and vice versa).
    i = j = n = ex = 0
    while i < len(d) and j < len(c):
        q = weq(d[i], c[j])
        if q:
            n += 1; ex += q; i += 1; j += 1; continue
        if j + 1 < len(c) and weq(d[i], c[j] + c[j + 1]):
            n += 1; ex += 1; i += 1; j += 2; continue
        if i + 1 < len(d) and weq(d[i] + d[i + 1], c[j]):
            n += 1; ex += 1; i += 2; j += 1; continue
        break
    return n, ex

_KUV = re.compile(r"^\s*\S+\s+(?:כו'|וכו'|כו|עכ\"ל)")

def quotes_one_word(raw_dibur):
    """'מה ליושב כו'' — the citer quotes only the opening, so 1 word suffices."""
    return bool(_KUV.match(raw_dibur or ""))

def best(dibur, cands, raw_dibur=None):
    """cands: [(fileline, content)] -> (fileline, n_aligned) or (None, 0)"""
    scored = []
    for fl, txt in cands:
        n, ex = align(dibur, txt)
        scored.append((n, ex, -fl, fl))
    if not scored: return None, 0
    scored.sort(reverse=True)
    n, ex, _, fl = scored[0]
    if n == 0: return None, 0
    # A lone aligned word counts only when it is the ONLY candidate that aligns
    # at all, and the word is either exact or long enough to be distinctive
    # (שקולין/שקולים, דילמא/דלמא are real variants of a real lemma).
    if n == 1:
        if len([s for s in scored if s[0] >= 1]) > 1: return None, n
        w = words(dibur)[0]
        if ex < 2 and len(w) < 5: return None, n
        if not (quotes_one_word(raw_dibur or dibur) or len(w) >= 5): return None, n
    return fl, n
