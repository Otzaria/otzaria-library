#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared daf parsing. Handles every notation seen in this corpus."""
import re

_Q = '["״“”\'׳’]'
HEAD_RE = re.compile(r"^\s*<h([1-6])>(.*?)</h\1>\s*$")

def _clean(s):
    return re.sub(_Q, "", s or "").strip()

def parse_daf(text):
    """
    '<h2>דף ב.</h2>' body, or a heRef head, -> ('ב', '.') | ('ב', ':') | ('ב', None)
    Understands:  דף ב.   דף ב:   דף ב ע"א   דף ב ע"ב   דף ב עמוד א   דף ב
    """
    if not text: return None
    m = re.search(r"דף\s+(.+)$", text)
    rest = (m.group(1) if m else text).strip()
    rest = re.sub(r"</?[^>]+>", "", rest).strip()

    # ע"א / ע"ב / עמוד א / עמוד ב
    m2 = re.match(rf"^(.*?)\s*(?:ע{_Q}?\s*([אב])|עמוד\s+([אב])){_Q}?\s*$", rest)
    if m2:
        page = _clean(m2.group(1))
        a = m2.group(2) or m2.group(3)
        return (page, "." if a == "א" else ":") if page else None

    rest = _clean(rest)
    if rest.endswith("."): return (rest[:-1], ".")
    if rest.endswith(":"): return (rest[:-1], ":")
    return (rest, None) if rest else None

def daf_from_heref(heref):
    """'זבחים ב., ו' -> ('ב','.')   'רש\"י על בבא מציעא עו:, ג, ג' -> ('עו',':')"""
    if not heref: return None
    head = heref.split(",")[0].strip()
    tok = head.split()
    if not tok: return None
    return parse_daf(tok[-1]) or parse_daf(" ".join(tok[-2:]))

def same_daf(a, b, strict_amud=True):
    """None amud on either side = wildcard."""
    if not a or not b: return None
    if a[0] != b[0]: return False
    if a[1] is None or b[1] is None: return True
    return (a[1] == b[1]) if strict_amud else True

def heading_daf_map(lines):
    """1-based line -> (page, amud) of the daf heading above it."""
    out = [None] * (len(lines) + 1)
    curr = None
    for i, l in enumerate(lines, start=1):
        m = HEAD_RE.match(l)
        if m:
            # only daf headings reset the pointer; פרק/פתיחה headings do not
            if "דף" in m.group(2):
                d = parse_daf(m.group(2))
                if d and d[0]: curr = d
        out[i] = curr
    return out
