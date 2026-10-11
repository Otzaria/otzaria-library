"""Turn the block lines of a Ben-Yehuda book into Otzaria markup.

Every input line becomes exactly one output line, so line numbers (links, bookmarks)
stay where they were. Rules follow .claude/skills/otzaria-book-format:
  * block tags (p, blockquote, div...) are unwrapped; sibling blocks inside one line are
    joined with <br>;
  * inline tags are mapped to the tags the reader knows (strong->b, em->i...);
  * attributes (id, class, style) are dropped; a footnote reference becomes a bare
    <sup>N</sup>, which is not an RTL "box";
  * a line that held only <br> becomes an empty line;
  * tables and lists stay on their single line; heading levels become a gapless h2.. tree.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

DROPPED = {
    "applet", "area", "audio", "base", "button", "canvas", "datalist", "dialog",
    "embed", "frame", "frameset", "head", "iframe", "input", "link", "map", "meta",
    "meter", "noframes", "noscript", "object", "optgroup", "option", "param",
    "progress", "script", "select", "source", "style", "svg", "template",
    "textarea", "title", "track", "video", "col", "colgroup",
}
BLOCK = {
    "address", "article", "aside", "blockquote", "center", "details", "div", "dd",
    "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "header",
    "hgroup", "legend", "main", "menu", "nav", "p", "pre", "section", "summary",
}
INLINE = {
    "b": "b", "strong": "b",
    "i": "i", "em": "i", "cite": "i", "dfn": "i", "var": "i",
    "u": "u", "ins": "u",
    "s": "s", "del": "s", "strike": "s",
    "sub": "sub", "sup": "sup", "small": "small", "big": "big",
    "code": "code", "kbd": "code", "samp": "code", "tt": "code",
    "abbr": "abbr", "acronym": "abbr", "ruby": "ruby", "rt": "rt", "rp": "rp",
}
STRUCTURE = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "ol", "ul", "li"}
HEADING_RE = re.compile(r"h([1-6])$")
FN_REF_RE = re.compile(r"#fn:([^\"'\s]+)$")
IMAGE_NAME_RE = re.compile(r"^\S+\.(?:png|jpe?g|gif|svg|webp)$", re.I)
ENTITY_RE = re.compile(r"&(?=#?[A-Za-z0-9]+;)")


# '' between two Hebrew letters is gershayim (ע''ש -> ע"ש); after a word it closes a quote (וכו'')
GERSHAYIM_PAIR_RE = re.compile(r"(?<=[\u05d0-\u05ea\u0591-\u05c7])''(?=[\u05d0-\u05ea])")
# ...unless it opens a quote glued to a prefix letter (ש''אין אב'') that closes later in the line
QUOTE_PREFIX_RE = re.compile(r"(?<![א-ת֑-ׇ])(?:[בדהוכלמש][֑-ׇ]*){1,3}")
QUOTE_WORD_RE = re.compile(r"(?:[א-ת][֑-ׇ]*){2}")
QUOTE_CLOSE_RE = re.compile(r"(?<=[א-ת֑-ׇ.,;:!?])''(?![א-ת'])")


def opens_quote(s, start, end):
    if not QUOTE_WORD_RE.match(s, end):
        return False
    if not any(m.end() == start for m in QUOTE_PREFIX_RE.finditer(s, max(0, start - 16), start)):
        return False
    stop = s.find("\n", end)
    for m in re.finditer("''", s[end:] if stop < 0 else s[end:stop]):
        p = end + m.start()
        if GERSHAYIM_PAIR_RE.match(s, p):
            continue
        return bool(QUOTE_CLOSE_RE.match(s, p))
    return False


def gershayim(s):
    return GERSHAYIM_PAIR_RE.sub(lambda m: m.group() if opens_quote(s, m.start(), m.end()) else '"', s)
# junk invisibles: bidi marks, BOM, zero-width space, soft hyphen, controls.
# ZWJ/ZWNJ survive only before a point (vav+ZWJ+holam renders holam haser)
INVISIBLE_RE = re.compile("[\ufeff\u200b\u200e\u200f\u202a-\u202e\u2060\u2066-\u2069\u00ad\x00-\x08\x0b-\x1f\x7f-\x9f]"
                          "|[\u200c\u200d](?![\u05b0-\u05c7])")
ODD_SPACE = "\t\u00a0\u2000-\u200a\u202f\u205f\u3000"
SPACE_RUN_RE = re.compile(f"[ {ODD_SPACE}]*[{ODD_SPACE}][ {ODD_SPACE}]*")


def normalize_chars(text: str) -> str:
    text = SPACE_RUN_RE.sub(" ", INVISIBLE_RE.sub("", text))
    return gershayim(text)


def escape_text(text: str) -> str:
    return ENTITY_RE.sub("&amp;", text).replace("<", "&lt;").replace(">", "&gt;")


class _LineConverter(HTMLParser):
    def __init__(self, footnote_numbers: dict[str, int] | None):
        super().__init__(convert_charrefs=True)
        self.footnote_numbers = footnote_numbers
        self.out: list[str] = []
        self.stack: list[str] = []  # emitted closing tag per open source tag ("" = none)
        self.drop_depth = 0
        self.skip_depth = 0  # inside an <a> whose content is replaced or dropped
        self.need_break = False
        self.heading: int | None = None
        self.figcaption: list[str] | None = None
        self.markers: list[int] = []

    # -- output helpers ------------------------------------------------------------------
    def _has_text(self) -> bool:
        return bool(re.sub(r"<[^>]+>", "", "".join(self.out)).strip())

    def _emit(self, s: str, text: bool = False) -> None:
        if self.figcaption is not None:
            self.figcaption.append(s)
            return
        opening = s.startswith("<") and not s.startswith("</")
        if self.need_break and (opening or (text and s.strip())):
            if self._has_text():
                self.out.append("<br>")
            self.need_break = False
        self.out.append(s)

    def _block_edge(self) -> None:
        if self._has_text():
            self.need_break = True

    # -- parser callbacks ----------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrd = {k.lower(): (v or "") for k, v in attrs}
        if self.drop_depth:
            self.drop_depth += tag not in {"br", "img", "hr"}
            return
        if tag in DROPPED:
            self.drop_depth = 1
            return
        if self.skip_depth:
            if tag not in {"br", "img", "hr"}:
                self.skip_depth += 1
            return
        if tag == "br":
            if self._has_text():
                self.need_break = True
            return
        if tag == "hr" or tag == "img":
            # img: only data: URIs survive conversion; remote images never load in Otzaria.
            src = attrd.get("src", "")
            if tag == "img" and src.startswith("data:image/"):
                self._emit(f'<img src="{src}" style="max-width: 100%;"/>', text=True)
            return
        m = HEADING_RE.match(tag)
        if m:
            self._block_edge()
            if not self._has_text() and self.heading is None:
                self.heading = int(m.group(1))
            self.stack.append("")
            return
        if tag == "a":
            href = attrd.get("href", "").strip()
            fn = FN_REF_RE.search(href)
            if fn and self.footnote_numbers is not None and fn.group(1) in self.footnote_numbers:
                number = self.footnote_numbers[fn.group(1)]
                self.markers.append(number)
                self._emit(f"<sup>{number}</sup>", text=True)
                self.skip_depth = 1
                return
            if href.startswith("#fnref:"):
                self.skip_depth = 1
                return
            if re.match(r"(?:https?|mailto):", href, re.I) and '"' not in href:
                self._emit(f'<a href="{href}">')
                self.stack.append("</a>")
            else:
                self.stack.append("")
            return
        if tag == "figcaption":
            self._block_edge()
            self.figcaption = []
            self.stack.append("")
            return
        if tag in BLOCK:
            self._block_edge()
            self.stack.append("")
            return
        if tag in STRUCTURE:
            extra = ""
            for name in ("colspan", "rowspan"):
                if attrd.get(name, "").isdigit() and tag in {"td", "th"}:
                    extra += f' {name}="{attrd[name]}"'
            if tag == "ol" and attrd.get("start", "").isdigit():
                extra += f' start="{attrd["start"]}"'
            self.need_break = False
            self._emit(f"<{tag}{extra}>")
            self.stack.append(f"</{tag}>")
            return
        mapped = INLINE.get(tag)
        if mapped:
            self._emit(f"<{mapped}>")
            self.stack.append(f"</{mapped}>")
            return
        self.stack.append("")  # unknown tag: unwrap, keep the text

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"br", "img", "hr"} and tag.lower() not in DROPPED:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"br", "img", "hr"}:
            return
        if self.drop_depth:
            self.drop_depth -= 1
            return
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if not self.stack:
            return  # stray closing tag (a paragraph split across lines by hand)
        closing = self.stack.pop()
        if tag == "figcaption" and self.figcaption is not None:
            caption, self.figcaption = "".join(self.figcaption), None
            if not IMAGE_NAME_RE.match(re.sub(r"<[^>]+>", "", caption).strip()):
                self._emit(caption, text=True)
        if closing:
            self.out.append(closing)
            if closing in {"</td>", "</th>", "</li>", "</caption>"}:
                self.need_break = False
        elif tag in BLOCK or HEADING_RE.match(tag):
            self._block_edge()

    def handle_data(self, data):
        if self.drop_depth or self.skip_depth:
            return
        data = re.sub(r"\s+", " ", data)
        if data:
            self._emit(escape_text(data), text=True)

    def result(self) -> str:
        while self.stack:
            closing = self.stack.pop()
            if closing:
                self.out.append(closing)
        text = "".join(self.out)
        text = re.sub(r"<(b|i|u|s|small|big|sup|sub|code|abbr)>(\s*)</\1>", r"\2", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s*<br>\s*", "<br> ", text).replace("<br> <br>", "<br>")
        text = re.sub(r"^(?:<br>\s*)+|(?:\s*<br>)+\s*$", "", text).strip()
        if self.heading and text:
            inner = re.sub(r"</?(?:b|big)>", "", text)
            return f"<h{self.heading}>{inner}</h{self.heading}>"
        return text


def convert_line_markers(line: str, footnote_numbers: dict[str, int] | None = None) -> tuple[str, list[int]]:
    """One Ben-Yehuda block line -> (balanced Otzaria line, footnote numbers referenced in it)."""
    parser = _LineConverter(footnote_numbers)
    parser.feed(line)
    parser.close()
    return normalize_chars(parser.result()), parser.markers


def convert_line(line: str, footnote_numbers: dict[str, int] | None = None) -> str:
    """One Ben-Yehuda block line -> one balanced Otzaria line ("" when nothing is left)."""
    return convert_line_markers(line, footnote_numbers)[0]


# -- footnotes --------------------------------------------------------------------------
FN_ITEM_RE = re.compile(r'<li\s+id="fn:([^"]+)"\s*>(.*?)</li>', re.S)


def is_footnote_list(line: str) -> bool:
    return bool(re.search(r'<li\s+id="fn:', line))


def extract_footnotes(lines: list[str]) -> tuple[list[str], list[str], dict[str, int]]:
    """Return (lines without the footnote list, note bodies in order, fn id -> note number)."""
    notes: list[str] = []
    numbers: dict[str, int] = {}
    kept: list[str] = []
    for line in lines:
        if not is_footnote_list(line):
            kept.append(line)
            continue
        for fn_id, body in FN_ITEM_RE.findall(line):
            numbers[fn_id] = len(notes) + 1
            notes.append(body)
    notes = [convert_line(body) for body in notes]
    return kept, notes, numbers


# -- headings ---------------------------------------------------------------------------
HEADING_LINE_RE = re.compile(r"^<h([1-6])>(.*)</h\1>$")


def normalize_heading_levels(lines: list[str], first: int = 1) -> list[str]:
    """Map the heading levels after line 1 to a gapless tree starting at h2.

    A heading's level is its depth among the open source headings, so siblings keep
    one level and a skipped source level (h2 -> h4) does not leave a gap.
    """
    out = lines[:first]
    open_levels: list[int] = []  # source levels of the current heading's ancestors
    for line in lines[first:]:
        m = HEADING_LINE_RE.match(line)
        if m:
            source = int(m.group(1))
            while open_levels and open_levels[-1] >= source:
                open_levels.pop()
            level = min(2 + len(open_levels), 6)
            open_levels.append(source)
            line = f"<h{level}>{m.group(2)}</h{level}>"
        out.append(line)
    return out


def convert_block_lines(lines: list[str]) -> tuple[list[str], list[str], list[tuple[int, int]]]:
    """Old-format book lines (h1, author, block lines) -> (Otzaria lines, footnote bodies,
    (book line, note number) pairs, both 1-based).

    Line N of the input stays line N of the output, except the footnote list itself
    (always at the end of the book) and the empty lines it leaves behind at the end.
    """
    lines = [lines[0].lstrip("\ufeff")] + lines[1:] if lines else lines
    body, notes, numbers = extract_footnotes(lines)
    out: list[str] = []
    refs: list[tuple[int, int]] = []
    for line in body:
        text, markers = convert_line_markers(line, numbers)
        out.append(text)
        refs.extend((len(out), n) for n in markers)
    while len(out) > 2 and not out[-1]:
        out.pop()
    return normalize_heading_levels(out), notes, refs
