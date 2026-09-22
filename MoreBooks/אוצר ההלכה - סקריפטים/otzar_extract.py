"""Otzar HaHalacha (Ish Matzliach) -- PDF to clean Unicode Hebrew text.

The book is a 2013 vector print PDF, not a scan: every glyph carries a real text
layer. The fonts, though, are pre-Unicode Hebrew DTP faces (FrankRuehl, Rashi,
Margaliot, Guttman...) whose ToUnicode tables map Hebrew glyphs onto Latin
codepoints, so a naive extraction yields gibberish for them.

Several distinct legacy encodings coexist in one file, so rather than hardcode a
table this learns the decoding per embedded font subset. Candidates are a
MacRoman-byte reading and every constant byte offset into cp1255; the winner is
scored against the Hebrew letter-frequency profile taken from the book's own
already-correct spans, which needs no external corpus.

Legacy runs are laid out in visual order, so both their characters and their
order within a line are reversed on output.
"""
import argparse
import collections
import json
import math
import os
import re

import pymupdf

LET_LO, LET_HI = 0x5D0, 0x5EA          # Hebrew letters
MARK = re.compile('[֑-ׇ]')   # nikud, te'amim, dagesh
SPACE_CODES = {0x03, 0x20, 0xA0}
SPACE_THRESHOLD = 0.25
CTRL = re.compile('[\\x00-\\x1f]')
MIN_SCORE = 0.55


def is_letter(c):
    return LET_LO <= ord(c) <= LET_HI


def heb_frac(s):
    """Share of Hebrew letters among letter-like chars; marks are neutral."""
    core = [c for c in s if not c.isspace() and not MARK.match(c)]
    if not core:
        return 0.0
    return sum(1 for c in core if is_letter(c)) / len(core)


# ------------------------------------------------------------------ decoders

def _byteval(c):
    n = ord(c)
    if n < 256:
        return n
    for enc in ('cp1252', 'mac_roman'):
        try:
            return c.encode(enc)[0]
        except Exception:
            continue
    return None


def _cp1255(n):
    if 0xB0 <= n <= 0xFA:
        try:
            return bytes([n]).decode('cp1255')
        except Exception:
            return None
    return None


def make_offset(delta):
    def dec(s):
        out = []
        for c in s:
            if ord(c) in SPACE_CODES:
                out.append(' ')
                continue
            b = _byteval(c)
            r = _cp1255((b + delta) & 0xFF) if b is not None else None
            out.append(r if r else c)
        return ''.join(out)
    return dec


def mac_decode(s):
    out = []
    for c in s:
        if ord(c) in SPACE_CODES:
            out.append(' ')
            continue
        try:
            b = c.encode('mac_roman')[0]
        except Exception:
            out.append(c)
            continue
        r = _cp1255(b)
        out.append(r if r else c)
    return ''.join(out)


CANDIDATES = [('macroman', mac_decode)] + \
             [('offset+0x%02X' % d, make_offset(d)) for d in range(256)]


# ------------------------------------------------------------------- scoring

def profile(text):
    c = collections.Counter(ch for ch in text if is_letter(ch))
    tot = sum(c.values())
    return {k: v / tot for k, v in c.items()} if tot else {}


def cosine(a, b):
    num = sum(a.get(k, 0) * b.get(k, 0) for k in set(a) | set(b))
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


def score(decoded, ref):
    f = heb_frac(decoded)
    if f < 0.70:
        return -1.0
    return f * cosine(profile(decoded), ref)


# --------------------------------------------------------------------- learn

def collect(doc, page_limit=None):
    """Undecoded spans keyed by font plus codepoint band, and the good corpus.

    PyMuPDF reports the family name without the subset prefix, and one family
    can appear in several subsets with different legacy encodings, so the
    codepoint band of the span is part of the key.
    """
    buckets = collections.defaultdict(list)
    good, full = [], []
    for i, page in enumerate(doc):
        if page_limit and i >= page_limit:
            break
        for blk in page.get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    t = _span_text(sp).strip()
                    if not t:
                        continue
                    if any(is_letter(c) for c in t):
                        full.append(t)
                        if len(good) < 6000:
                            good.append(t)
                        continue
                    k = bucket_key(sp["font"], t)
                    if k and len(buckets[k]) < 200:
                        buckets[k].append(t)
    return buckets, ' '.join(good), ' '.join(full)


def bucket_key(font, text):
    """Font family plus the 32-codepoint band its glyph codes fall in."""
    codes = [ord(c) for c in text if not c.isspace() and ord(c) > 0x20]
    if not codes:
        return None
    return (font.split('+')[-1], min(codes) // 32, max(codes) // 32)


def _best(blob, ref):
    best = (0.0, None, None)
    for name, fn in CANDIDATES:
        sc = score(fn(blob), ref)
        if sc > best[0]:
            best = (sc, name, fn)
    return best


def learn(buckets, ref, min_chars=6):
    """A decoder per (family, codepoint band) bucket."""
    table, report = {}, []
    for key, texts in buckets.items():
        blob = ' '.join(texts)
        alpha = len([c for c in blob if c.isalpha() or ord(c) > 127])
        if alpha < min_chars:
            continue
        sc, name, fn = _best(blob, ref)
        if fn is None or sc < MIN_SCORE:
            continue
        table[key] = (name, fn)
        report.append((key, name, sc, alpha, fn(' '.join(texts[:2]))[::-1][:46]))
    return table, report


# ---------------------------------------------------------- residual glyphs

def decoder_for(sp_font, raw, table, fallback):
    ent = table.get(bucket_key(sp_font, raw))
    if ent is None:
        ent = fallback.get(sp_font.split('+')[-1])
    return ent


def pick_line_decoders(line, by_family, fallback):
    """Choose one decoder per font family on this line.

    A span's own codepoints are too thin a signal -- a two-letter word cannot
    tell one legacy encoding from another -- so the longest legacy run of each
    family on the line decides for the rest of that family's spans.
    """
    best = {}
    for sp in line["spans"]:
        raw = _span_text(sp).strip()
        if not raw or any(is_letter(c) for c in raw):
            continue
        fam = sp["font"].split('+')[-1]
        opts = by_family.get(fam)
        if not opts:
            continue
        if len(opts) == 1:                     # the family is unambiguous
            best[fam] = (10 ** 6,) + opts[0]
            continue
        n = len([c for c in raw if ord(c) > 0x20])
        if n < 3 or n <= best.get(fam, (0,))[0]:
            continue
        cand = max(((heb_frac(fn(raw)), nm, fn) for nm, fn in opts),
                   key=lambda t: t[0])
        if cand[0] >= 0.6:
            best[fam] = (n, cand[1], cand[2])
    out = {fam: (nm, fn) for fam, (_, nm, fn) in best.items()}
    for fam, ent in fallback.items():
        out.setdefault(fam, ent)
    return out


def residuals(doc, table, fallback, by_family, lexicon, page_limit=None):
    """Resolve glyph codes the byte arithmetic cannot reach.

    MuPDF hands back a mangled codepoint for a few glyphs (the Hebrew nun of a
    MacRoman-mapped font arrives as U+001B, for instance), so no constant offset
    recovers them. Each such code stands for exactly one Hebrew letter, so the
    letter is inferred by pattern-matching the surrounding word against the
    book's own vocabulary -- "\u05de\u05ea\u05e7?\u05ea" only completes to
    "\u05de\u05ea\u05e7\u05e0\u05ea".
    """
    votes = collections.defaultdict(collections.Counter)
    for i, page in enumerate(doc):
        if page_limit and i >= page_limit:
            break
        for blk in page.get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                line_dec = pick_line_decoders(ln, by_family, fallback)
                for sp in ln["spans"]:
                    raw = _span_text(sp)
                    if not raw.strip() or any(is_letter(c) for c in raw):
                        continue
                    fam = sp["font"].split('+')[-1]
                    ent = line_dec.get(fam) or \
                        decoder_for(sp["font"], raw, table, fallback)
                    if not ent:
                        continue
                    name, fn = ent
                    key = (fam, name)
                    dec = fn(raw)
                    if heb_frac(dec) < 0.5:
                        continue
                    for word in dec.split():
                        holes = [j for j, c in enumerate(word)
                                 if not is_letter(c) and not MARK.match(c)
                                 and not c.isspace()]
                        if len(holes) != 1:
                            continue
                        j = holes[0]
                        code = ord(word[j])
                        if code > 0x20 and chr(code) in '.,:;()[]"\'*-\u05be':
                            continue
                        stem = MARK.sub('', word)
                        k = len(MARK.sub('', word[:j]))
                        if len(stem) < 3 or len(stem) > 12:
                            continue
                        for letter in HEB_LETTERS:
                            cand = (stem[:k] + letter + stem[k + 1:])[::-1]
                            if cand in lexicon:
                                votes[(key, code)][letter] += 1
    resid = {k: v.most_common(1)[0][0] for k, v in votes.items()
             if v and v.most_common(1)[0][1] >= 2}

    # MuPDF sanitises the single unmappable MacRoman code to a different control
    # value in each subset, so the control codes of one family all stand for the
    # same letter. Where the votes agree overwhelmingly, that letter becomes the
    # family default, covering codes too rare to vote on and outvoting noise.
    pooled = collections.defaultdict(collections.Counter)
    for (key, code), counter in votes.items():
        if code < 0x20:
            letter, n = counter.most_common(1)[0]
            pooled[key][letter] += n
    default = {}
    for key, counter in pooled.items():
        letter, n = counter.most_common(1)[0]
        if n >= 0.8 * sum(counter.values()):
            default[key] = letter
            for (k, code) in list(resid):
                if k == key and code < 0x20:
                    resid[(k, code)] = letter
    return resid, default


HEB_LETTERS = [chr(c) for c in range(LET_LO, LET_HI + 1)]


def build_lexicon(text, min_len=3):
    words = set()
    for w in MARK.sub('', text).split():
        w = w.strip('.,:;()[]"\'*\u05be-')
        if min_len <= len(w) <= 14 and all(is_letter(c) for c in w):
            words.add(w)
    return words


# ------------------------------------------------------------------- extract

LTR = re.compile(r'[0-9A-Za-z]')


def _order_chars(chars):
    """Put a line's characters into logical order.

    Character boxes are trustworthy even where MuPDF hands back a span whose
    own bbox is an aggregate, so reading right to left recovers the logical
    order for both the Unicode runs and the legacy ones it laid out as Latin.
    Digits and Latin words run the other way and are flipped back.
    """
    out = sorted(chars, key=lambda c: -c[0])
    i = 0
    while i < len(out):
        if LTR.match(out[i][2]):
            j = i
            while j < len(out) and LTR.match(out[j][2]):
                j += 1
            out[i:j] = reversed(out[i:j])
            i = j
        else:
            i += 1
    return out


def _join_chars(chars, size):
    parts, prev = [], None
    for c in chars:
        if prev is not None and prev - c[1] > SPACE_THRESHOLD * (c[5] or size):
            parts.append(' ')
        parts.append(c[2])
        prev = c[0]
    return ''.join(parts)


def calibrate_space(doc, pages=(30, 60)):
    """Find where a gap stops being letter spacing and starts being a space.

    These volumes justify by stretching the space between letters and some of
    them place the space glyphs themselves at nonsense coordinates, so spacing
    is read off the gaps alone. Those gaps are sharply bimodal -- tight inside
    a word, wide between words -- and the threshold is the middle of the empty
    band between the two modes.
    """
    hist = collections.Counter()
    for i in range(pages[0], min(pages[1], doc.page_count)):
        for blk in doc[i].get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    z = max(sp.get("size", 1.0), 1.0)
                    cs = [c for c in sp["chars"] if not c["c"].isspace()]
                    for a, b in zip(cs, cs[1:]):
                        g = (a["bbox"][0] - b["bbox"][2]) / z
                        if 0.0 <= g < 1.0:
                            hist[round(g, 2)] += 1
    if not hist:
        return 0.15
    floor = sum(hist.values()) * 0.0005
    lo = hi = None
    for step in range(2, 60):            # the first quiet band above the
        v = step / 100.0                 # intra-word mode is the word gap
        quiet = hist.get(v, 0) <= floor
        if quiet:
            lo = v if lo is None else lo
            hi = v
        elif lo is not None and hi - lo >= 0.04:
            break
        else:
            lo = hi = None
    if lo is None or hi is None:
        return 0.15
    return max(0.06, min(0.45, (lo + hi) / 2))


def _span_text(sp):
    t = sp.get("text")
    return t if t is not None else ''.join(c["c"] for c in sp["chars"])


def line_chars(line, table, fallback, by_family, unresolved,
               resid=None, default=None):
    """Decode one line into logically ordered characters with their fonts."""
    resid = resid or {}
    default = default or {}
    line_dec = pick_line_decoders(line, by_family, fallback)
    size, chars = 1.0, []
    for sp in line["spans"]:
        raw = _span_text(sp)
        if not raw.strip():
            continue
        size = max(size, sp.get("size", 1.0))
        fam = sp["font"].split('+')[-1]
        key, dec = None, raw
        if not any(is_letter(c) for c in raw):
            known = fam in line_dec
            ent = line_dec.get(fam) or \
                decoder_for(sp["font"], raw, table, fallback)
            if ent:
                name, fn = ent
                cand = fn(raw)
                allctrl = all(CTRL.match(c) or c.isspace() for c in cand)
                # a short run like "g'(" is mostly punctuation and would fail a
                # share test, but where the line has already identified the
                # face there is nothing to be cautious about
                ok = heb_frac(cand) >= 0.5 or allctrl
                if not ok and known:
                    ok = any(is_letter(c) for c in cand)
                if ok:
                    key, dec = (fam, name), cand
            if key is None and any(c.isalpha() or ord(c) > 127 for c in raw):
                unresolved[fam] += len(raw.strip())
        meta = (fam, sp.get("size", 1.0))
        boxes = sp.get("chars")
        if boxes and len(boxes) == len(dec):
            for cb, ch in zip(boxes, dec):
                # space glyphs are dropped: several of these files place them
                # at coordinates that do not match the gap they stand for
                if ch.isspace():
                    continue
                chars.append((cb["bbox"][0], cb["bbox"][2], ch, key) + meta)
        else:
            x0, x1 = sp["bbox"][0], sp["bbox"][2]
            w = (x1 - x0) / max(len(dec), 1)
            for k, ch in enumerate(dec):
                if ch.isspace():
                    continue
                chars.append((x1 - (k + 1) * w, x1 - k * w, ch, key) + meta)

    # the print file redraws some glyphs in place to fake bold
    seen, uniq = set(), []
    for c in chars:
        sig = (round(c[0], 1), c[2])
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(c)

    ordered = _order_chars(uniq)

    # MuPDF sanitises the one unmappable legacy glyph to a control code; it is
    # a letter when it sits tight against its neighbours, otherwise a space
    out = []
    for i, c in enumerate(ordered):
        ch = c[2]
        if c[3] and CTRL.match(ch):
            near = False
            if i and abs(ordered[i - 1][1] - c[1]) < size:
                near = ordered[i - 1][0] - c[1] < 0.25 * size
            if not near and i + 1 < len(ordered):
                near = c[0] - ordered[i + 1][1] < 0.25 * size
            ch = resid.get((c[3], ord(ch)),
                           default.get(c[3], ' ')) if near else ' '
        out.append((c[0], c[1], ch, c[3], c[4], c[5]))
    return out, size


def line_segments(*args, **kw):
    """Logical-order runs of one font and size, for markup decisions."""
    chars, size = line_chars(*args, **kw)
    segs = []
    prev = None
    for c in chars:
        ch = ' ' if CTRL.match(c[2]) else c[2]
        kind = (c[4], round(c[5], 1))
        if prev is not None and kind == segs[-1][1] and \
                prev - c[1] > SPACE_THRESHOLD * (c[5] or size) \
                and not ch.isspace() \
                and not segs[-1][0].endswith(' '):
            segs[-1][0] += ' '
        if not segs or kind != segs[-1][1]:
            segs.append([ch, kind])
        else:
            segs[-1][0] += ch
        prev = c[0]
    return [(re.sub(r'[ \t]+', ' ', t), f, z) for t, (f, z) in segs if t.strip()]


def line_text(*args, **kw):
    chars, size = line_chars(*args, **kw)
    text = CTRL.sub(' ', _join_chars(chars, size))
    return re.sub(r'[ \t]+', ' ', text).strip()


def build(doc, table, fallback, by_family, resid=None, default=None,
          strip_nikud=False, page_limit=None):
    pages, unresolved = [], collections.Counter()
    for i, page in enumerate(doc):
        if page_limit and i >= page_limit:
            break
        lines = []
        for blk in page.get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                s = line_text(ln, table, fallback, by_family, unresolved,
                              resid, default)
                if s:
                    lines.append(s)
        body = '\n'.join(lines)
        if strip_nikud:
            body = MARK.sub('', body)
        pages.append(body)
    return pages, unresolved


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('pdf')
    ap.add_argument('-o', '--out', default='otzar.txt')
    ap.add_argument('--json', help='also write per-page JSON')
    ap.add_argument('--pages', type=int, help='stop after N pages (for testing)')
    ap.add_argument('--strip-nikud', action='store_true')
    ap.add_argument('--no-page-marks', action='store_true')
    a = ap.parse_args()

    doc = pymupdf.open(a.pdf)
    print('pages: %d' % doc.page_count)
    buckets, ref_text, ref_text_full = collect(doc, a.pages)
    ref = profile(ref_text)
    print('reference: %d Hebrew chars | %d legacy buckets'
          % (len(ref_text), len(buckets)))

    table, report = learn(buckets, ref)
    by_family = collections.defaultdict(dict)
    for key, (nm, fn) in table.items():
        by_family[key[0]][nm] = fn
    by_family = {f: list(d.items()) for f, d in by_family.items()}
    fallback = {}
    for key, name, sc, n, _ in sorted(report, key=lambda r: r[3]):
        fallback[key[0]] = table[key]
    print('\n--- learned decoders ---')
    for key, name, sc, n, sample in sorted(report, key=lambda r: -r[3]):
        print('%-22s %-13s %.3f %-6d | %s'
              % ('%s[%02X-%02X]' % (key[0][:14], key[1] * 32, key[2] * 32),
                 name, sc, n, sample))

    lexicon = build_lexicon(ref_text_full)
    resid, resid_default = residuals(doc, table, fallback, by_family,
                                     lexicon, a.pages)
    for k, v in sorted(resid_default.items()):
        print('  %-16s %-13s any other control code -> %s' % (k[0], k[1], v))
    print('\n--- residual glyphs recovered from the book\'s own vocabulary ---')
    for (key, code), letter in sorted(resid.items()):
        print('  %-16s %-13s U+%04X -> %s' % (key[0], key[1], code, letter))

    pages, unresolved = build(doc, table, fallback, by_family, resid,
                              resid_default, a.strip_nikud, a.pages)
    text = '\n\n'.join(pages) if a.no_page_marks else '\n\n'.join(
        '--- עמוד %d ---\n%s' % (i + 1, p)
        for i, p in enumerate(pages))
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(text)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump([{'page': i + 1, 'text': p} for i, p in enumerate(pages)],
                      f, ensure_ascii=False)

    h = sum(1 for c in text if is_letter(c))
    al = sum(1 for c in text if c.isalpha())
    print('\nwrote %s (%.1f KB)' % (a.out, os.path.getsize(a.out) / 1024))
    print('Hebrew letters %d of %d alphabetic -> %.3f%%'
          % (h, al, 100.0 * h / max(al, 1)))
    print('unresolved:', unresolved.most_common(8) or 'none')


if __name__ == '__main__':
    main()
