"""Solve a legacy font whose mapping is an arbitrary permutation.

A few of these fonts are neither a codepage nor a constant offset: the glyph
codes are simply shuffled. There is nothing to derive them from inside the
file, but the book supplies its own crib -- two million characters of correctly
encoded Hebrew from its other fonts. Matching decoded words against that
vocabulary scores a candidate mapping, and hill-climbing on the score recovers
the permutation.
"""
import collections
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
import otzar_extract as ox
from otzar_extract import collect, profile, learn, line_chars, is_letter, MARK

LETTERS = [chr(c) for c in range(0x5D0, 0x5EB)]
MISS = chr(1)


def sample(doc, family, limit=20000):
    """Collect the family's own runs, each read right to left with its gaps."""
    out = []
    for i in range(doc.page_count):
        for blk in doc[i].get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    if sp["font"].split('+')[-1] != family:
                        continue
                    z = max(sp.get("size", 1.0), 1.0)
                    cs = [(c["bbox"][0], c["bbox"][2], c["c"], None, family, z)
                          for c in sp["chars"] if not c["c"].isspace()]
                    if not cs:
                        continue
                    cs = ox._order_chars(cs)
                    txt = ox._join_chars(cs, z)
                    if txt.strip():
                        out.append(txt)
                    if len(out) >= limit:
                        return out
    return out


def lexicon(doc, limit=400000):
    words = set()
    for i in range(doc.page_count):
        for blk in doc[i].get_text("rawdict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    t = ''.join(c["c"] for c in sp["chars"])
                    if not any(is_letter(c) for c in t):
                        continue
                    for w in MARK.sub('', t).split():
                        w = w.strip('.,:;()[]"\'*-־')
                        if 2 <= len(w) <= 12 and all(is_letter(c) for c in w):
                            words.add(w)
                if len(words) >= limit:
                    return words
    return words


def tokens(lines):
    out = []
    for ln in lines:
        for w in ln.split():
            w = w.strip('.,:;()[]"\'*-־׳״')
            if 2 <= len(w) <= 12:
                out.append(w)
    return out


def score(toks, mapping, lex):
    hit = 0
    for w in toks:
        d = ''.join(mapping.get(c, MISS) for c in w)
        if MISS not in d and d in lex:
            hit += 1
    return hit


def solve(lines, lex, rounds=6, seed=0):
    toks = tokens(lines)
    freq = collections.Counter(c for w in toks for c in w)
    codes = [c for c, _ in freq.most_common(len(LETTERS))]
    ref = collections.Counter()
    for w in lex:
        ref.update(w)
    targets = [c for c, _ in ref.most_common(len(LETTERS))]
    best = dict(zip(codes, targets))
    best_s = score(toks, best, lex)
    rng = random.Random(seed)
    for _ in range(rounds):
        improved = True
        while improved:
            improved = False
            for i in range(len(codes)):
                for j in range(i + 1, len(codes)):
                    cand = dict(best)
                    a, b = codes[i], codes[j]
                    cand[a], cand[b] = best[b], best[a]
                    s = score(toks, cand, lex)
                    if s > best_s:
                        best, best_s = cand, s
                        improved = True
        if best_s >= 0.8 * len(toks):
            break
        i, j = rng.randrange(len(codes)), rng.randrange(len(codes))
        best[codes[i]], best[codes[j]] = best[codes[j]], best[codes[i]]
        best_s = score(toks, best, lex)
    return best, best_s, len(toks)


def learn_family(doc, family, lex, min_tokens=120, min_rate=0.55):
    """Return a decoder for a family whose mapping is a plain permutation."""
    lines = sample(doc, family)
    if not lines:
        return None, 0.0
    mapping, hits, n = solve(lines, lex)
    if n < min_tokens or hits < min_rate * n:
        return None, (hits / n if n else 0.0)
    table = dict(mapping)

    def dec(text):
        return ''.join(table.get(c, c) for c in text)

    return dec, hits / n


def main():
    path = sys.argv[1]
    family = sys.argv[2]
    doc = pymupdf.open(path)
    ox.SPACE_THRESHOLD = ox.calibrate_space(doc)
    lines = sample(doc, family)
    lex = lexicon(doc)
    print('%s: %d lines sampled, lexicon %d words' % (family, len(lines), len(lex)))
    mapping, s, n = solve(lines, lex)
    print('score %d of %d tokens (%.1f%%)' % (s, n, 100.0 * s / max(n, 1)))
    print('mapping: %s' % ''.join(
        '%s->%s ' % (k, v) for k, v in sorted(mapping.items())[:20]))
    for ln in lines[:6]:
        print('   %s' % ''.join(mapping.get(c, c) for c in ln)[:70])


if __name__ == '__main__':
    main()
