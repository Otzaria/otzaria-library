#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""המרת HTML / Markdown / טקסט גולמי למבנה ספר של אוצריא.

מיישם את חוזה ה-markup של אוצריא כפי שהוא בקוד התוכנה
(`lib/utils/text/otzaria_markup.dart` + המפות ב-`lib/utils/file/html_to_otzaria.dart`):

  * הפלט נבנה מאפס — שום תגית מהמקור אינה מועתקת כמות שהיא.
  * תגיות ללא טקסט קריא נמחקות עם תוכנן; תגית לא מוכרת נפתחת (unwrap) והטקסט נשמר.
  * כל אלמנט בלוק פותח שורה חדשה; רשימה/טבלה נכתבות כשורה אחת.
  * ירידת שורה בתוך יחידת תוכן הופכת לרווח (שורה = יחידת תוכן).
  * href מוגבל ל-http/https/mailto/עוגן פנימי; src של תמונה ל-data URI.
  * הערות שוליים: inline (סמן+גוף צמודים) או פיצול לקובץ הערות + _links.json.

שימוש:
  python -X utf8 to_otzaria.py --in source.html --out "שם הספר.txt" --title "שם הספר" \
      [--author "מחבר"] [--format html|md|txt] [--split-footnotes --links-dir ../links]
      [--heading-pattern "^פרק .*$" --heading-level 2] [--keep-style]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DROPPED = {
    "applet", "area", "audio", "base", "button", "canvas", "datalist", "dialog",
    "embed", "frame", "frameset", "head", "iframe", "input", "link", "map", "meta",
    "meter", "noframes", "noscript", "object", "optgroup", "option", "param",
    "progress", "script", "select", "source", "style", "svg", "template",
    "textarea", "title", "track", "video",
}

BLOCK = {
    "address", "article", "aside", "blockquote", "caption", "center", "details",
    "div", "dd", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "legend", "li",
    "main", "menu", "nav", "ol", "p", "pre", "section", "summary", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}

INLINE_KEEP = {
    "b": "b", "strong": "b",
    "i": "i", "em": "i", "cite": "i", "dfn": "i", "var": "i",
    "u": "u", "ins": "u",
    "s": "s", "del": "s", "strike": "s",
    "sub": "sub", "sup": "sup",
    "small": "small", "big": "big",
    "code": "code", "kbd": "code", "samp": "code", "tt": "code",
    "abbr": "abbr", "acronym": "abbr",
    "ruby": "ruby", "rt": "rt", "rp": "rp",
}

# מבנה שנכתב כשורה אחת שלמה, על תתי-התגים שלו.
STRUCTURE_ROOTS = {"ol", "ul", "table", "details"}
STRUCTURE_KEEP = {"ol", "ul", "li", "table", "thead", "tbody", "tr", "td", "th",
                  "caption", "details", "summary"}

ALLOWED_SCHEMES = {"http", "https", "mailto"}
STYLE_PROPS = {
    "color", "background-color", "font-weight", "font-style", "font-size",
    "font-family", "line-height", "text-decoration", "text-align",
    "vertical-align", "list-style-type", "white-space",
}
BLOCK_ONLY_PROPS = {"text-align"}

SANITIZE_STRIP = re.compile(r"[֑-ׇ]")
SANITIZE_ILLEGAL = re.compile(r"[\\/:*\"״?<>|]")
WS_RUN = re.compile(r"[ \t\r\n\f ]+")


def sanitize_filename(name: str) -> str:
    s = SANITIZE_STRIP.sub("", name)
    s = SANITIZE_ILLEGAL.sub("", s)
    s = s.replace("_", " ").replace("''", "").replace("'", "")
    return s.strip()


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def safe_link(href: str, allow_book: bool = False) -> str | None:
    h = href.strip()
    if not h or '"' in h or "\n" in h:
        return None
    if h.startswith("#"):
        return h
    if h.startswith("//"):
        return None
    if ":" not in h:
        return h
    scheme = h.split(":", 1)[0].lower()
    if allow_book and scheme == "book":
        return h
    return h if scheme in ALLOWED_SCHEMES else None


def clean_style(value: str, block: bool) -> str | None:
    kept = []
    for decl in value.split(";"):
        if ":" not in decl:
            continue
        prop, val = decl.split(":", 1)
        prop = prop.strip().lower()
        val = " ".join(val.split())
        if prop not in STYLE_PROPS or not val:
            continue
        if prop in BLOCK_ONLY_PROPS and not block:
            continue
        if '"' in val or "<" in val or "url(" in val.lower():
            continue
        if re.search(r"\d(rem)\b", val, re.I):
            continue
        kept.append(f"{prop}: {val}")
    return "; ".join(kept) if kept else None


class OtzariaHtmlConverter(HTMLParser):
    """ממיר HTML לשורות אוצריא."""

    def __init__(self, keep_style: bool = False, allow_book_links: bool = False):
        super().__init__(convert_charrefs=True)
        self.keep_style = keep_style
        self.allow_book_links = allow_book_links
        self.lines: list[str] = []
        self._buf: list[str] = []
        self._drop_depth = 0
        self._dropping: str | None = None
        self._inline_stack: list[str] = []
        self._heading: int | None = None
        self._struct_depth = 0

    # ── ניהול שורות ──────────────────────────────────────────────────────
    def _flush(self) -> None:
        text = "".join(self._buf)
        text = WS_RUN.sub(" ", text).strip()
        self._buf = []
        if not text:
            return
        if self._heading:
            level = min(self._heading, 6)
            text = re.sub(r"</?(?:b|big)>", "", text)  # כותרת כבר מודגשת ומוגדלת
            self.lines.append(f"<h{level}>{text}</h{level}>")
        else:
            self.lines.append(text)

    def _emit(self, s: str) -> None:
        self._buf.append(s)

    # ── HTMLParser ───────────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrd = {k.lower(): (v or "") for k, v in attrs}
        if self._drop_depth:
            if tag == self._dropping:
                self._drop_depth += 1
            return
        if tag in DROPPED:
            self._dropping, self._drop_depth = tag, 1
            return

        if tag == "br":
            self._emit("<br>")
            return
        if tag == "img":
            src = attrd.get("src", "").strip()
            if src.startswith("data:image/"):
                self._emit(f'<img src="{src}" style="max-width: 100%;"/>')
            return
        if tag == "hr":
            self._flush()
            self.lines.append("<hr>")
            return

        if self._struct_depth and tag in STRUCTURE_KEEP:
            self._struct_depth += 1
            self._emit(self._open_tag(tag, attrd, block=True))
            return
        if not self._struct_depth and tag in STRUCTURE_ROOTS:
            self._flush()
            self._struct_depth = 1
            self._emit(self._open_tag(tag, attrd, block=True))
            return

        if tag in BLOCK and not self._struct_depth:
            self._flush()
            if re.fullmatch(r"h[1-6]", tag):
                self._heading = int(tag[1])
            return

        mapped = INLINE_KEEP.get(tag)
        if tag == "a":
            target = safe_link(attrd.get("href", ""), self.allow_book_links)
            if target:
                self._inline_stack.append("a")
                self._emit(f'<a href="{html.escape(target, quote=True)}">')
            else:
                self._inline_stack.append("")
            return
        if mapped:
            cls = attrd.get("class", "")
            style = attrd.get("style", "") if self.keep_style else ""
            attr = ""
            if "footnote-marker" in cls:
                attr = ' class="footnote-marker"'
            elif mapped == "i" and re.search(r"\bfootnote\b", cls):
                attr = ' class="footnote"'
            elif style:
                cleaned = clean_style(style, block=False)
                if cleaned:
                    attr = f' style="{cleaned}"'
            self._inline_stack.append(mapped)
            self._emit(f"<{mapped}{attr}>")
            return
        # תגית לא מוכרת — unwrap, הטקסט נשמר
        self._inline_stack.append("")

    def _open_tag(self, tag: str, attrd: dict, block: bool) -> str:
        attr = ""
        if self.keep_style:
            cleaned = clean_style(attrd.get("style", ""), block=block)
            if cleaned:
                attr = f' style="{cleaned}"'
        if tag in {"td", "th"}:
            for name in ("colspan", "rowspan"):
                val = attrd.get(name, "")
                if val.isdigit():
                    attr += f' {name}="{val}"'
        if tag == "ol" and attrd.get("start", "").isdigit():
            attr += f' start="{attrd["start"]}"'
        return f"<{tag}{attr}>"

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"br", "img", "hr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._drop_depth:
            if tag == self._dropping:
                self._drop_depth -= 1
                if self._drop_depth == 0:
                    self._dropping = None
            return
        if tag in {"br", "img", "hr"}:
            return

        if self._struct_depth and tag in STRUCTURE_KEEP:
            self._emit(f"</{tag}>")
            self._struct_depth -= 1
            if self._struct_depth == 0:
                self._flush()
            return

        if tag in BLOCK:
            self._flush()
            if re.fullmatch(r"h[1-6]", tag):
                self._heading = None
            return

        if self._inline_stack:
            mapped = self._inline_stack.pop()
            if mapped:
                self._emit(f"</{mapped}>")

    def handle_data(self, data):
        if self._drop_depth:
            return
        self._emit(esc(data))

    def close(self):
        super().close()
        while self._inline_stack:
            mapped = self._inline_stack.pop()
            if mapped:
                self._emit(f"</{mapped}>")
        self._flush()


# ── Markdown / טקסט גולמי ────────────────────────────────────────────────
MD_INLINE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"__(.+?)__"), r"<b>\1</b>"),
    (re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)"), r"<i>\1</i>"),
    (re.compile(r"~~(.+?)~~"), r"<s>\1</s>"),
    (re.compile(r"`([^`\n]+?)`"), r"<code>\1</code>"),
]
MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def md_to_lines(text: str) -> list[str]:
    out: list[str] = []
    pending: list[str] = []

    def flush_list() -> None:
        if pending:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in pending) + "</ul>")
            pending.clear()

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush_list()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_list()
            out.append(f"<h{len(m.group(1))}>{md_inline(m.group(2).strip())}</h{len(m.group(1))}>")
            continue
        m = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if m:
            pending.append(md_inline(m.group(1).strip()))
            continue
        flush_list()
        out.append(md_inline(line.strip()))
    flush_list()
    return out


def md_inline(text: str) -> str:
    text = esc(text)
    for rx, rep in MD_INLINE:
        text = rx.sub(rep, text)

    def link(m: re.Match) -> str:
        target = safe_link(m.group(2))
        return f'<a href="{html.escape(target, quote=True)}">{m.group(1)}</a>' if target else m.group(1)

    return MD_LINK.sub(link, text)


def txt_to_lines(text: str, heading_pattern: str | None, heading_level: int) -> list[str]:
    rx = re.compile(heading_pattern) if heading_pattern else None
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = " ".join(raw.split())
        if not line:
            continue
        if rx and rx.search(line):
            out.append(f"<h{heading_level}>{esc(line)}</h{heading_level}>")
        else:
            out.append(esc(line))
    return out


# ── הערות שוליים ─────────────────────────────────────────────────────────
FOOTNOTE_PAIR = re.compile(
    r'<sup class="footnote-marker">(.*?)</sup>\s*<i class="footnote">(.*?)</i>',
    re.S,
)


def split_footnotes(lines: list[str]) -> tuple[list[str], list[str], list[dict]]:
    """מפצל הערות inline לקובץ הערות נפרד + רשומות קישור (המנגנון של ספריא)."""
    notes: list[str] = []
    links: list[dict] = []
    out: list[str] = []
    for idx, line in enumerate(lines, start=1):
        def repl(m: re.Match) -> str:
            notes.append(" ".join(m.group(2).split()))
            n = len(notes)
            links.append({
                "line_index_1": idx,
                "heRef_2": "הערות",
                "path_2": None,  # מושלם אחר כך בשם הספר
                "line_index_2": n,
                "Conection Type": "commentary",
            })
            return f'<sup style="color: gray;">{n}</sup>'

        out.append(FOOTNOTE_PAIR.sub(repl, line))
    return out, notes, links


HEADING_LINE_RE = re.compile(r"^<h([2-6])>(.*)</h\1>$")


def normalize_heading_levels(lines: list[str]) -> tuple[list[str], dict[int, int]]:
    """ממפה את רמות הכותרות לרצף היררכי בלי דילוגים (h2, h3, h4…).

    התוכנה משייכת כותרת להורה שברמה level-1; דילוג (h2 ← h4) משאיר את הכותרת
    בלי הורה ושובר את עץ הניווט. המיפוי שומר על הסדר היחסי בין הרמות.
    """
    used = sorted({int(m.group(1)) for m in
                   (HEADING_LINE_RE.match(x) for x in lines) if m})
    if not used:
        return lines, {}
    mapping = {lvl: min(2 + i, 6) for i, lvl in enumerate(used)}
    if all(k == v for k, v in mapping.items()):
        return lines, {}
    out = []
    for line in lines:
        m = HEADING_LINE_RE.match(line)
        if m:
            new = mapping[int(m.group(1))]
            out.append(f"<h{new}>{m.group(2)}</h{new}>")
        else:
            out.append(line)
    return out, mapping


def main() -> int:
    ap = argparse.ArgumentParser(description="המרת מקור למבנה ספר של אוצריא")
    ap.add_argument("--in", dest="src", required=True, help="קובץ המקור")
    ap.add_argument("--out", required=True, help="קובץ הפלט (.txt)")
    ap.add_argument("--title", required=True, help="שם הספר ל-<h1>")
    ap.add_argument("--author", default="", help="שם המחבר (שורה 2). ריק = בלי שורה")
    ap.add_argument("--format", choices=["html", "md", "txt"], help="ברירת מחדל: לפי הסיומת")
    ap.add_argument("--encoding", default="utf-8", help="קידוד המקור")
    ap.add_argument("--keep-style", action="store_true", help="לשמר style מסונן מהמקור")
    ap.add_argument("--allow-book-links", action="store_true", help="לאפשר href של book://")
    ap.add_argument("--split-footnotes", action="store_true",
                    help="לפצל הערות inline לקובץ 'הערות על <ספר>.txt' + _links.json")
    ap.add_argument("--links-dir", help="תיקיית links/ לקובץ הקישורים (עם --split-footnotes)")
    ap.add_argument("--heading-pattern", help="regex לזיהוי כותרות בקלט txt")
    ap.add_argument("--heading-level", type=int, default=2, help="רמת הכותרת ל--heading-pattern")
    ap.add_argument("--keep-source-levels", action="store_true",
                    help="לא לנרמל את רמות הכותרות (ברירת מחדל: נרמול לרצף היררכי בלי דילוגים)")
    args = ap.parse_args()

    src = Path(args.src)
    fmt = args.format or {"html": "html", "htm": "html", "md": "md",
                          "markdown": "md"}.get(src.suffix.lstrip(".").lower(), "txt")
    text = src.read_text(encoding=args.encoding, errors="replace").lstrip("﻿")

    if fmt == "html":
        conv = OtzariaHtmlConverter(keep_style=args.keep_style,
                                    allow_book_links=args.allow_book_links)
        conv.feed(text)
        conv.close()
        body = conv.lines
    elif fmt == "md":
        body = md_to_lines(text)
    else:
        body = txt_to_lines(text, args.heading_pattern, args.heading_level)

    title = unicodedata.normalize("NFC", args.title.strip())
    # שורת ה-h1 של המקור, אם הייתה, לא נכפלת
    if body and re.match(r"^<h1>", body[0], re.I):
        body = body[1:]

    if not args.keep_source_levels:
        body, mapping = normalize_heading_levels(body)
        if mapping:
            moved = ", ".join(f"h{k}->h{v}" for k, v in mapping.items() if k != v)
            print(f"רמות כותרות נורמלו לרצף היררכי: {moved}")

    lines = [f"<h1>{esc(title)}</h1>"]
    if args.author.strip():
        lines.append(esc(args.author.strip()))
    lines.extend(body)

    out_path = Path(args.out)
    notes: list[str] = []
    links: list[dict] = []
    if args.split_footnotes:
        lines, notes, links = split_footnotes(lines)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"נכתב: {out_path}  ({len(lines)} שורות)")

    expected = sanitize_filename(title)
    if out_path.stem != expected:
        print(f"שימו לב: שם הקובץ {out_path.stem!r} אינו הצורה המנוקה של הכותרת ({expected!r})")

    if args.split_footnotes and notes:
        notes_path = out_path.with_name(f"הערות על {out_path.stem}.txt")
        notes_path.write_text("\n".join(notes) + "\n", encoding="utf-8", newline="\n")
        for entry in links:
            entry["path_2"] = notes_path.name
        links_dir = Path(args.links_dir) if args.links_dir else out_path.parent
        links_dir.mkdir(parents=True, exist_ok=True)
        links_path = links_dir / f"{out_path.stem}_links.json"
        links_path.write_text(json.dumps(links, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8", newline="\n")
        print(f"נכתב: {notes_path} ({len(notes)} הערות)\nנכתב: {links_path}")

    print("הריצו כעת: python -X utf8 validate_book.py \"%s\"" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
