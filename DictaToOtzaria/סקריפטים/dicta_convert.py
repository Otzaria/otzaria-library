#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dicta_convert.py — המרת קובצי ה־OCR של ספריית דיקטה לפורמט ספר של אוצריא.

מודול טהור (בלי רשת ובלי כתיבה לדיסק): מקבל את תוכן דפי ה־HTML של ספר
(`<fileName>__ocr_data_html_files.zip` שב־`OCRDataURL`) ומחזיר טקסט אוצריא.

API
===
    convert_pages(pages, meta=None, *, options=None) -> str
    convert_book(pages, meta=None, *, options=None) -> ConvertResult
    convert_zip(zip_path_or_bytes, meta=None, *, options=None,
                page_order=None) -> ConvertResult
    convert_zip_final(...)  -> ConvertResult   # + dicta_clean + איחוד <b> (לשימוש ה־workflow)
    finalize_text(text) -> str                 # ניקוי + איחוד <b> לטקסט קיים
    read_zip_pages(zip_path_or_bytes, page_order=None) -> list[tuple[name, html]]
    page_sort_key(name) -> tuple
    build_metadata(book_info) -> dict
    header_lines(meta) -> list[str]

`pages` הוא רשימת מחרוזות HTML (או זוגות `(name, html)`) **בסדר הדפים**.
`meta` הוא רשומת הספר מ־`books.json` של דיקטה (נדרשים רק `displayName`
ו־`author`; בלעדיהם לא נכתבות שורות הכותרת והמחבר).

סמנטיקת התגים של דיקטה (נבדק מול קוד האתר library.dicta.org.il ומול
קובצי ה־JSON של כל דף — ראו README.md):

* `marked-paragraph` — תחילת פסקה. האתר מצייר `<br><br>` לפני הטוקן,
  וייצוא הטקסט שלהם כותב `\\r\\r` לפניו. זה הסימן היחיד לפסקה.
  - פורמט חדש (`library-1-0`, מאז 2026): רק על המילה הראשונה של הפסקה.
  - פורמט ישן: על כל המילים של **השורה המודפסת הראשונה** של הפסקה, ו־`\\n`
    בסוף אותה שורה. פסקה חדשה = תחילת רצף מסומן, או `\\n` שאחריו הרצף
    ממשיך (פסקה של שורה אחת שאחריה פסקה נוספת).
* `bold` — הדגשה (font-bold). **אינה** תחילת פסקה. בפורמט החדש גם הרווח
  שבין שתי מילים מודגשות של אותו רצף מסומן `bold`.
* `heading` — אות גדולה (text-5xl font-bold) — סגנון, לא בלוק. בפועל אלה
  כותרות מודפסות (שם סימן/פרק/שער), ולכן כל רצף `heading` נכתב בשורה משלו.
* `flagged` — מילה ש־OCR לא בטוח בה (האתר צובע אותה אפור). לא נכנס לספר;
  מוחזר ב־`ConvertResult.flagged` לקובץ לוואי להגהה.
* `edited` — מילה שתויגה/תוקנה ידנית אצל דיקטה. מידע בלבד.
"""

from __future__ import annotations

import html as _html
import io
import json
import os
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable, Sequence

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "עריכת ספרים"))
from dicta_edit_core import colon_ends_matter  # noqa: E402

__all__ = [
    "ConvertOptions", "ConvertResult", "Token",
    "parse_page", "detect_format", "convert_pages", "convert_book",
    "convert_zip", "read_zip_pages", "page_sort_key", "build_metadata",
    "header_lines", "print_year_to_int", "finalize_text", "convert_zip_final",
]

# ---------------------------------------------------------------------------
# אפשרויות
# ---------------------------------------------------------------------------


@dataclass
class ConvertOptions:
    # תג הכותרת שבו נכתב רצף `heading` של דיקטה. None = להשאיר כשורת טקסט
    # רגילה (בלי תג). הרמה נקבעת אחר כך בעריכה (אדם/AI) — כאן רק מבנה.
    heading_tag: str | None = "h2"
    # פיצול בתוך פסקה שדיקטה לא פיצלה (ר' README למדדים מול ספרים ערוכים):
    # אחרי מילה שמסתיימת בנקודותיים — "סוף עניין" בספרים הישנים — אבל לא אחרי מילה
    # מודגשת, ולא באמצע משפט: סוגריים שנסגרים, ציטוט קצר, הפניה לעמוד ב (colon_ends_matter).
    split_colon: bool = True
    # לפני רצף מודגש שבא אחרי מילה לא־מודגשת המסתיימת בנקודה ("...ר"ת. <b>דין</b>").
    split_period_before_bold: bool = True
    # פורמט הדפים: "auto" / "word" (חדש) / "line" (ישן).
    fmt: str = "auto"
    # רצף heading באמצע משפט (לא בתחילת פסקה, המילה שלפניו אינה מסיימת
    # משפט, והטקסט ממשיך אחריו באותה פסקה) — שם/מילה באות גדולה בתוך
    # הטקסט, לא כותרת: נכתב כ־<b> בתוך השורה.
    inline_headings: bool = True
    # מיזוג <b> סמוכים שביניהם רק רווח. "auto" = לפי הרווח המודגש בפורמט
    # החדש, תמיד בפורמט הישן (שם הרווח לעולם אינו מסומן).
    merge_bold: str = "auto"


@dataclass
class Token:
    text: str
    bold: bool = False
    heading: bool = False
    para: bool = False
    flagged: bool = False
    edited: bool = False
    page: int = 0

    @property
    def is_space(self) -> bool:
        return not self.text.strip()


@dataclass
class ConvertResult:
    text: str
    fmt: str
    flagged: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ניקוי תווים
# ---------------------------------------------------------------------------

# תווים בלתי־נראים שנזרקים (BOM, רוחב־אפס, סימוני כיווניות, מקף רך)
_INVISIBLE_RE = re.compile(
    "[﻿​‌‍‎‏‪-‮⁦-⁩­]")
# רווחים מיוחדים → רווח רגיל (לא \n: הוא נושא מידע בפורמט הישן)
_SPACE_LIKE_RE = re.compile("[\t  -   　]")


def _clean_chars(s: str) -> str:
    s = _INVISIBLE_RE.sub("", s)
    s = _SPACE_LIKE_RE.sub(" ", s)
    return s


def _escape_text(s: str) -> str:
    """הטקסט נכתב לקובץ שאוצריא מפרשת כ־HTML: רק < ו־> מסוכנים.

    & נשאר כתו רגיל (כמו בשאר ספרי הספרייה); `&amp;` בקובץ הוא שארית באג.
    """
    return s.replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# פענוח דף
# ---------------------------------------------------------------------------

_KNOWN_CLASSES = {"bold", "heading", "marked-paragraph", "flagged", "edited"}


class _PageParser(HTMLParser):
    """אוסף (טקסט, מחלקות) מתוך דף OCR של דיקטה.

    טקסט מחוץ ל־<span> (לא קיים בקבצים שנבדקו) נשמר כטוקן בלי מחלקות —
    כדי שאף מילה לא תאבד. <br> הופך ל־\\n.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens: list[tuple[str, frozenset]] = []
        self._stack: list[frozenset] = []
        self._in_body = False
        self._in_head = 0
        self.unknown_classes: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self._in_head += 1
        elif tag == "body":
            self._in_body = True
        elif tag == "span":
            cls = ""
            for k, v in attrs:
                if k == "class" and v:
                    cls = v
            classes = frozenset(cls.split())
            self.unknown_classes |= classes - _KNOWN_CLASSES
            outer = self._stack[-1] if self._stack else frozenset()
            self._stack.append(outer | classes)
        elif tag == "br":
            self.tokens.append(("\n", frozenset()))

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.tokens.append(("\n", frozenset()))
        # <span/> ריק — אין טקסט

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = max(0, self._in_head - 1)
        elif tag == "span" and self._stack:
            self._stack.pop()

    def handle_data(self, data):
        if self._in_head:
            return
        if not self._stack and not data.strip():
            return  # רווחים בין תגים / אחרי </body>
        classes = self._stack[-1] if self._stack else frozenset()
        self.tokens.append((data, classes))


def parse_page(html: str, page: int = 0) -> list[Token]:
    """מפענח דף OCR אחד לרשימת Token (טקסט אחרי פענוח ישויות HTML)."""
    p = _PageParser()
    p.feed(html)
    p.close()
    out = []
    for text, cls in p.tokens:
        text = _clean_chars(text)
        if text == "":
            continue
        out.append(Token(
            text=text,
            bold="bold" in cls,
            heading="heading" in cls,
            para="marked-paragraph" in cls,
            flagged="flagged" in cls,
            edited="edited" in cls,
            page=page,
        ))
    return out


# ---------------------------------------------------------------------------
# זיהוי פורמט
# ---------------------------------------------------------------------------

def detect_format(pages_tokens: Sequence[Sequence[Token]]) -> str:
    """"word" = פורמט library-1-0 (סימון על המילה הראשונה בלבד),
    "line" = פורמט ישן (סימון על כל השורה הראשונה של הפסקה).

    ההבחנה: ממוצע המילים ברצף `marked-paragraph`. בחדש ≈1, בישן ≈5–12.
    `\\n` בתוך טקסט קיים רק בישן.
    """
    runs = 0
    words = 0
    newline = False
    for toks in pages_tokens:
        prev = False
        for t in toks:
            if "\n" in t.text:
                newline = True
            if t.is_space:
                continue
            if t.para:
                words += 1
                if not prev:
                    runs += 1
            prev = t.para
    if newline:
        return "line"
    if runs == 0:
        return "word"
    return "line" if words / runs >= 1.8 else "word"


# ---------------------------------------------------------------------------
# פילוח לפסקאות
# ---------------------------------------------------------------------------

# סימני סיום שאחריהם נקודותיים הן "סוף עניין"
_BOLD_START_AFTER_COLON = True


def _word_groups(toks: list[Token]) -> list[int]:
    """לכל טוקן: אינדקס הטוקן הראשון של "המילה" שלו (-1 לרווח).

    מילה = רצף טוקנים לא־ריקים בלי רווח ביניהם — כך דיקטה מציגה אותם (האתר
    מדביק span־ים זה לזה; הטוקן ב־JSON הוא המחרוזת המחוברת: "ביןמטה", "שבה\"א").
    """
    grp = [-1] * len(toks)
    start = -1
    for i, t in enumerate(toks):
        if t.is_space:
            start = -1
            continue
        if start < 0 or t.text[:1].isspace():
            start = i
        grp[i] = start
        if t.text[-1:].isspace():
            start = -1
    return grp


def _paragraph_starts(toks: list[Token], fmt: str,
                      grp: list[int] | None = None) -> list[bool]:
    """לכל טוקן: האם מתחילה לפניו פסקה חדשה. נקבע למילה כולה (על הטוקן
    הראשון שלה), גם כשהסימון יושב על span מודבק באמצע המילה ("(" + "א)")."""
    n = len(toks)
    grp = grp if grp is not None else _word_groups(toks)
    starts = [False] * n
    # סימון/מחלקה ברמת המילה
    para_of = {}
    for i, t in enumerate(toks):
        g = grp[i]
        if g >= 0 and t.para:
            para_of[g] = True
    if fmt == "word":
        for g in para_of:
            starts[g] = True
        return starts

    # fmt == "line": רצף מסומן = השורה המודפסת הראשונה של הפסקה
    prev_para = False
    nl_since_word = False
    for i, t in enumerate(toks):
        if t.is_space:
            if "\n" in t.text:
                nl_since_word = True
            continue
        if grp[i] != i:
            continue  # המשך של אותה מילה
        p = para_of.get(i, False)
        if p and (not prev_para or nl_since_word):
            starts[i] = True
        prev_para = p
        nl_since_word = False
    return starts


# ---------------------------------------------------------------------------
# רינדור
# ---------------------------------------------------------------------------

@dataclass
class _Line:
    heading: bool = False
    toks: list = field(default_factory=list)


_END_COLON_RE = re.compile(r":\s*$")
# טוקן שכולו פיסוק סוגר (ורווחים) — נצמד למילה הקודמת
_TRAILING_PUNCT_RE = re.compile(r"^[\s.,:;!?)\]}'\"\u05f3\u05f4]*[.,:;!?)\]}][\s.,:;!?)\]}'\"\u05f3\u05f4]*$")
_END_PERIOD_RE = re.compile(r"\.\s*$")


def _soft_break(prev: Token, cur: Token, opt: ConvertOptions, line_toks: Sequence[Token] = (),
                ahead: Sequence[Token] = ()) -> bool:
    """שבירת שורה בתוך פסקה של דיקטה, לפי סימני פיסוק (לא לפי הדגשה לבדה).

    line_toks: טוקני השורה הנוכחית עד prev (כולל); ahead: הטוקנים מ־cur והלאה
    (סוגריים שנסגרים, סוף ציטוט) — לפי colon_ends_matter.
    """
    if prev.heading:
        return False
    if opt.split_colon and _END_COLON_RE.search(prev.text):
        if prev.bold:
            return False  # למה מודגשת ("<b>מחצלת:</b>") או באמצע רצף מודגש
        before = _END_COLON_RE.sub("", "".join(t.text for t in line_toks))
        after = "".join(t.text for t in ahead) if ahead else cur.text
        return colon_ends_matter(before, ("<b>" if cur.bold else "") + after)
    if (opt.split_period_before_bold and cur.bold and not prev.bold
            and _END_PERIOD_RE.search(prev.text)):
        return True
    return False


# רצף כותרת שמתחיל באחת המילים האלה הוא כותרת מבנית גם באמצע משפט
# ("…פרק עשירי פרק אחד עשר הזורק…") — לא מורידים אותו לטקסט.
_STRUCT_WORDS = {
    "פרק", "סימן", "סי'", "שער", "הלכות", "הלכה", "מסכת", "דף", "חלק", "קונטרס",
    "ספר", "מאמר", "שאלה", "תשובה", "פרשת", "פרשה", "הקדמה", "הקדמת", "פתיחה",
    "כלל", "ענף", "אות", "סעיף", "משנה", "דרוש", "דרשה", "שורש", "מצוה", "פלג",
    "מערכת", "ערך", "חידושי", "בעזה\"י", "בס\"ד",
}


def _demote_inline_headings(toks: list[Token], starts: list[bool],
                            grp: list[int] | None = None) -> int:
    """רצף heading בתוך משפט → מודגש רגיל (in place). מחזיר כמה רצפים.

    רצף בתוך משפט: לא בתחילת פסקה, המילה שלפניו אינה מסיימת משפט, הטקסט
    ממשיך אחריו באותה פסקה, והוא אינו מתחיל במילה מבנית (פרק/סימן/שער…).
    """
    grp = grp if grp is not None else _word_groups(toks)
    words = [i for i, t in enumerate(toks)
             if grp[i] == i and not _TRAILING_PUNCT_RE.match(t.text)]
    n = 0
    k = 0
    while k < len(words):
        i = words[k]
        if not toks[i].heading:
            k += 1
            continue
        a = k
        while k + 1 < len(words) and toks[words[k + 1]].heading and not starts[words[k + 1]]:
            k += 1
        b = k
        k += 1
        first, last = words[a], words[b]
        if starts[first] or a == 0 or b + 1 >= len(words):
            continue
        first_word = toks[first].text.strip().split(" ")[0] if toks[first].text.strip() else ""
        if first_word.strip(".,:;()[]") in _STRUCT_WORDS:
            continue
        prev_i, next_i = words[a - 1], words[b + 1]
        prev_text = "".join(t.text for t in toks[prev_i:first]).strip()
        if toks[prev_i].heading or _SENT_END_RE.search(prev_text):
            continue
        if starts[next_i] or toks[next_i].heading:
            continue
        tail = "".join(t.text for t in toks[last:next_i]).strip()
        if _SENT_END_RE.search(tail):
            continue
        for j in range(first, next_i):
            if toks[j].heading:
                toks[j] = Token(text=toks[j].text, bold=True, heading=False,
                                para=toks[j].para, flagged=toks[j].flagged,
                                edited=toks[j].edited, page=toks[j].page)
        n += 1
    return n


_SENT_END_RE = re.compile(r"[.:!?]['\"\u05f3\u05f4)\]]*$")


def _segment(toks: list[Token], fmt: str, opt: ConvertOptions) -> list[_Line]:
    grp = _word_groups(toks)
    starts = _paragraph_starts(toks, fmt, grp)
    if opt.inline_headings and opt.heading_tag is not None:
        toks = list(toks)
        _demote_inline_headings(toks, starts, grp)
    lines: list[_Line] = []
    cur: _Line | None = None

    def new_line(heading: bool) -> _Line:
        nonlocal cur
        cur = _Line(heading=heading)
        lines.append(cur)
        return cur

    last_word: Token | None = None
    for i, t in enumerate(toks):
        if t.is_space:
            if cur is not None:
                cur.toks.append(t)
            continue
        if cur is not None and grp[i] != i:
            # המשך מודבק של אותה מילה ("אול"+"[א]ם", "י"+"סודי") — אף פעם לא שוברים
            # שורה באמצע מילה; ההחלטה נעשתה על הטוקן הראשון שלה.
            cur.toks.append(t)
            if last_word is not None:
                last_word = Token(text=last_word.text + t.text, bold=t.bold,
                                  heading=last_word.heading, page=t.page)
            continue
        if cur is not None and last_word is not None and _TRAILING_PUNCT_RE.match(t.text):
            # פיסוק בטוקן נפרד אחרי רווח — שייך למילה שלפניו; לא פותח שורה.
            cur.toks.append(t)
            last_word = Token(text=last_word.text + t.text, bold=last_word.bold,
                              heading=last_word.heading, page=t.page)
            continue
        is_head = t.heading and opt.heading_tag is not None
        if cur is None:
            new_line(is_head)
        elif starts[i]:
            new_line(is_head)
        elif is_head != cur.heading:
            # מעבר בין רצף כותרת לטקסט (בכל כיוון) = שורה חדשה
            new_line(is_head)
        elif not is_head and last_word is not None and _soft_break(last_word, t, opt, cur.toks, toks[i:i + 40]):
            new_line(False)
        cur.toks.append(t)
        last_word = t
    return lines


def _render_body(toks: list[Token], fmt: str, opt: ConvertOptions) -> str:
    """טקסט של שורת גוף עם <b>…</b> סביב רצפים מודגשים."""
    merge = opt.merge_bold
    if merge == "auto":
        merge = "space" if fmt == "word" else "always"
    out: list[str] = []
    in_b = False
    pending_space = ""
    for idx, t in enumerate(toks):
        text = t.text.replace("\n", " ")
        if t.is_space:
            if in_b:
                # רווח בתוך רצף מודגש: נשאר מודגש אם הוא עצמו מודגש (פורמט
                # חדש), או תמיד (merge="always"), אחרת סוגר את הרצף.
                keep = (merge == "always") or (merge == "space" and t.bold)
                if keep:
                    pending_space += text
                    continue
                out.append("</b>")
                in_b = False
            pending_space += text
            continue
        # מילה
        if t.bold and not in_b:
            out.append(pending_space)
            pending_space = ""
            out.append("<b>")
            in_b = True
        elif not t.bold and in_b:
            out.append("</b>")
            in_b = False
            out.append(pending_space)
            pending_space = ""
        else:
            out.append(pending_space)
            pending_space = ""
        out.append(_escape_text(text))
    if in_b:
        out.append("</b>")
    s = "".join(out)
    # רווחים שנכנסו לתוך התג (מילה מודגשת שנגמרת ברווח) — מחוץ לתג
    s = re.sub(r"(\s+)</b>", r"</b>\1", s)
    s = re.sub(r"<b>(\s+)", r"\1<b>", s)
    s = s.replace("<b></b>", "")
    s = re.sub(r"[ ]{2,}", " ", s)
    return s.strip()


def _render_heading(toks: list[Token], tag: str) -> str:
    text = "".join(t.text for t in toks).replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return f"<{tag}>{_escape_text(text)}</{tag}>"


# ---------------------------------------------------------------------------
# מטא־דאטה
# ---------------------------------------------------------------------------

def header_lines(meta: dict | None) -> list[str]:
    """שורת <h1> ושורת המחבר, בפורמט המקובל בספרי דיקטה במאגר."""
    if not meta:
        return []
    out = []
    name = (meta.get("displayName") or "").strip()
    name = re.sub(r"\s+", " ", name)
    if name:
        out.append(f"<h1>{_escape_text(name)}</h1>")
    author = re.sub(r"\s+", " ", (meta.get("author") or "").strip())
    if author:
        out.append(_escape_text(author))
    return out


def print_year_to_int(value) -> int | None:
    """printYear של דיקטה: מספר, מחרוזת מספר, טווח ('1925-1931') או ריק.

    מחזיר את השנה הראשונה, או None כשאין שנה.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 else None
    m = re.search(r"\d{3,4}", str(value))
    return int(m.group()) if m else None


def _hebrew_year(year: int) -> str | None:
    """שנה לועזית → שנה עברית בגימטריה (לפי 1 בינואר של אותה שנה)."""
    try:
        from pyluach import dates
    except ImportError:  # pragma: no cover
        return None
    try:
        from datetime import date
        return dates.HebrewDate.from_pydate(date(year, 1, 1)).hebrew_year(
            thousands=True, withgershayim=True)
    except (ValueError, OverflowError):
        return None


def build_metadata(book_info: dict) -> dict:
    """רשומת מטא־דאטה לספר (פורמט `DictaToOtzaria/.../metadata.json` הישן).

    לא קורס על printYear חסר או טווח. `heAuthors` נשמר לתאימות; טבלת
    המחברים של אוצריא נקראת מ־`author` ב־metadata.json שבשורש המאגר, ו־A2
    כותב אותו. כל ערכי המחרוזות עוברים strip.
    """
    def s(key):
        v = book_info.get(key)
        # כמו header_lines: strip וכיווץ רווחים פנימיים (כדי שהשם יתאים ל־<h1>)
        return re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else (v or "")

    year = print_year_to_int(book_info.get("printYear"))
    md = {
        "title": s("displayName"),
        "author": s("author"),
        "heAuthors": [s("author")] if s("author") else [],
        "enTitle": s("displayNameEnglish"),
        "authors": [s("authorEnglish")] if s("authorEnglish") else [],
        "pubDate": [year] if year else [],
        "pubDateHeb": _hebrew_year(year) if year else "",
        "printYearRaw": str(book_info.get("printYear") or "").strip(),
        "pubPlaceStringEn": s("printLocationEnglish"),
        "pubPlaceStringHe": s("printLocation"),
        "heCategories": [c for c in (s("category"), s("subcategory")) if c],
        "categories": [c for c in (s("categoryEnglish"), s("subcategoryEnglish")) if c],
        "publisher": s("source"),
        "dictaFileName": s("fileName"),
        "Sourcefolder": "Dicta",
    }
    return md


# ---------------------------------------------------------------------------
# סדר דפים וקריאת zip
# ---------------------------------------------------------------------------

_PAGE_NUM_RE = re.compile(r"-(\d+)(?:__ocr_data)?\.html?$", re.IGNORECASE)


def page_sort_key(name: str) -> tuple:
    """מפתח מיון לשם קובץ דף (`book-012__ocr_data.html`).

    המספר הוא הרצף האחרון של ספרות לפני `__ocr_data.html` (לא `split('-')`,
    שנשבר כששם הספר עצמו מכיל מקף). קבצים בלי מספר — בסוף, לפי שם.
    """
    base = name.rsplit("/", 1)[-1]
    m = _PAGE_NUM_RE.search(base)
    if m:
        return (0, int(m.group(1)), base)
    m = re.findall(r"\d+", base)
    if m:
        return (1, int(m[-1]), base)
    return (2, 0, base)


def read_zip_pages(src, page_order: Iterable[str] | None = None
                   ) -> list[tuple[str, str]]:
    """קורא zip של דיקטה ומחזיר [(שם, html)] ממוינים.

    `page_order` — רשימת שמות דפים בסדר הנכון (למשל מ־pages.json של
    האתר: `fileName` בלי `.zip`); דפים שאינם ברשימה — בסוף, לפי page_sort_key.
    """
    if isinstance(src, (bytes, bytearray)):
        zf = zipfile.ZipFile(io.BytesIO(src))
    else:
        zf = zipfile.ZipFile(src)
    with zf:
        names = [n for n in zf.namelist()
                 if n.lower().endswith((".html", ".htm")) and not n.endswith("/")]
        pages = {n: zf.read(n).decode("utf-8", errors="replace") for n in names}
    order_index = {}
    if page_order:
        for i, p in enumerate(page_order):
            stem = re.sub(r"\.(zip|json|html?)$", "", p.rsplit("/", 1)[-1])
            order_index[stem] = i

    def key(n):
        stem = re.sub(r"(__ocr_data)?\.html?$", "", n.rsplit("/", 1)[-1])
        if stem in order_index:
            return (0, order_index[stem], "")
        return (1,) + page_sort_key(n)

    return [(n, pages[n]) for n in sorted(names, key=key)]


# ---------------------------------------------------------------------------
# נקודת הכניסה
# ---------------------------------------------------------------------------

def _flatten(pages) -> list[tuple[str, str]]:
    out = []
    for i, p in enumerate(pages):
        if isinstance(p, tuple):
            out.append((p[0], p[1]))
        else:
            out.append((f"page-{i:04d}", p))
    return out


def convert_book(pages, meta: dict | None = None, *,
                 options: ConvertOptions | None = None) -> ConvertResult:
    """ממיר ספר שלם. `pages` בסדר הדפים (מחרוזות או (name, html))."""
    opt = options or ConvertOptions()
    named = _flatten(pages)
    pages_tokens = [parse_page(h, page=i) for i, (_, h) in enumerate(named)]
    fmt = opt.fmt if opt.fmt in ("word", "line") else detect_format(pages_tokens)

    # רצף אחד לכל הספר: פסקה ממשיכה מעבר לדף אלא אם הדף הבא מתחיל בסימון.
    toks: list[Token] = []
    for pt in pages_tokens:
        if toks and pt and not toks[-1].is_space:
            toks.append(Token(" ", page=pt[0].page))
        toks.extend(pt)

    lines = _segment(toks, fmt, opt)
    out_lines = header_lines(meta)
    flagged = []
    heads = 0
    for ln in lines:
        if ln.heading:
            text = _render_heading(ln.toks, opt.heading_tag)
            heads += 1
        else:
            text = _render_body(ln.toks, fmt, opt)
        if not re.sub(r"<[^>]+>", "", text).strip():
            continue
        out_lines.append(text)
        lineno = len(out_lines)  # 1-based
        wi = 0
        for t in ln.toks:
            if t.is_space:
                continue
            for w in t.text.split():
                if t.flagged:
                    flagged.append({"line": lineno, "word": wi, "text": w,
                                    "page": named[t.page][0],
                                    "edited": t.edited})
                wi += 1
    text = "\n".join(out_lines) + "\n"
    stats = {
        "pages": len(named),
        "format": fmt,
        "lines": len(out_lines),
        "headings": heads,
        "words": sum(len(t.text.split()) for t in toks),
        "flagged": len(flagged),
    }
    return ConvertResult(text=text, fmt=fmt, flagged=flagged, stats=stats)


def convert_pages(pages, meta: dict | None = None, *,
                  options: ConvertOptions | None = None) -> str:
    """כמו convert_book, מחזיר רק את הטקסט."""
    return convert_book(pages, meta, options=options).text


def convert_zip(src, meta: dict | None = None, *,
                options: ConvertOptions | None = None,
                page_order: Iterable[str] | None = None) -> ConvertResult:
    """ממיר zip של דיקטה (נתיב / bytes) — קיצור ל־read_zip_pages+convert_book."""
    return convert_book(read_zip_pages(src, page_order), meta, options=options)


def finalize_text(text: str, clean: bool = True) -> str:
    """השלב האחרון בשרשרת: ניקוי דטרמיניסטי (dicta_clean: G,E,F) ואיחוד
    רצפי <b> סמוכים (M) — תמיד אחרון. מחזיר טקסט שמסתיים ב־\n אחד."""
    if clean:
        import dicta_clean  # מודול אח באותה תיקייה
        text, _ = dicta_clean.clean_text(text)
    return text.rstrip("\n") + "\n"


def convert_zip_final(src, meta: dict | None = None, *,
                      options: ConvertOptions | None = None,
                      page_order: Iterable[str] | None = None) -> ConvertResult:
    """השרשרת המלאה שמיועדת ל־workflow: convert_zip → finalize_text.

    `flagged` מתייחס למספרי השורות של פלט ההמרה; הניקוי אינו מוסיף או מוחק
    שורות (G/E/F/M — F ממזג רק שורת ע"א/ע"ב יתומה, נדיר מאוד בפלט הזה).
    """
    res = convert_zip(src, meta, options=options, page_order=page_order)
    res.text = finalize_text(res.text)
    return res


def _main(argv=None) -> int:
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="המרת zip OCR של דיקטה לטקסט אוצריא")
    ap.add_argument("zip")
    ap.add_argument("-o", "--out", help="קובץ פלט (ברירת מחדל: stdout)")
    ap.add_argument("--meta", help="קובץ JSON עם רשומת הספר מ־books.json")
    ap.add_argument("--flagged", help="כתיבת קובץ לוואי עם המילים המסומנות flagged")
    ap.add_argument("--fmt", default="auto", choices=["auto", "word", "line"])
    ap.add_argument("--no-heading-tag", action="store_true",
                    help="לא לעטוף כותרות דיקטה ב־<h2>")
    ap.add_argument("--no-colon-split", action="store_true",
                    help="לא לפצל שורות אחרי נקודותיים")
    ap.add_argument("--raw", action="store_true",
                    help="פלט ההמרה בלבד, בלי dicta_clean (ובלי איחוד רצפי <b>)")
    a = ap.parse_args(argv)
    meta = json.load(open(a.meta, encoding="utf-8")) if a.meta else None
    opt = ConvertOptions(fmt=a.fmt,
                         heading_tag=None if a.no_heading_tag else "h2",
                         split_colon=not a.no_colon_split)
    res = convert_zip(a.zip, meta, options=opt) if a.raw else \
        convert_zip_final(a.zip, meta, options=opt)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(res.text)
    else:
        sys.stdout.write(res.text)
    if a.flagged:
        with open(a.flagged, "w", encoding="utf-8") as f:
            json.dump(res.flagged, f, ensure_ascii=False, indent=0)
    sys.stderr.write(json.dumps(res.stats, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
