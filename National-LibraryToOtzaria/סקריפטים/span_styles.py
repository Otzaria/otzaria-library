# -*- coding: utf-8 -*-
"""מחלקות ה-span של אתר יד הרמב"ם → תגי העיצוב של אוצריא.

Z הוא ציטוט מדברי הרמב"ם — הדיבור המתחיל, וגם ציטוט באמצע הקטע. הוא מודגש
כמו הדיבור המתחיל בשאר מפרשי הרמב"ם באוצריא, ולא נטוי. B ו-Z באותו קטע
נותנים <b> אחד, ו-<b> בתוך <b> נפתח.

חריג: ב"שקל הקודש" האתר מסמן ב-Z גם את שכבת הערות המקורות
("(א) רש"ס דף ז' ב':"), ולא רק את הציטוט. שם קטע Z שנפתח בסימן הערה נשאר נטוי.
"""

import re

from bs4 import BeautifulSoup, Tag

import fix_marker_breaks
import fix_missing_spaces

# כל מחלקות ה-span שנראו בפועל (לדיווח בסוף הריצה); apply_span_styles ממלא אותה
all_span_classes = set()


CLASS_STYLE = {
    "B": {"tag": "b"},
    "Z": {"tag": "b"},
    "S": {"tag": "small"},
    "H": {"tag": "span", "style": "color:#1B1464"},
    "N": {"tag": "span", "style": "color:#999"},
    "R": {"tag": "span", "style": "color:#999"},
}


COLOR_PRIORITY = ("H", "N", "R")
TAG_PRIORITY = ("B", "Z", "S")

# ספרים שבהם Z מסמן גם הערות מקורות (שם הספר אחרי rename_books)
NOTES_IN_Z = {"שקל הקודש"}
# "(א)", "(ס"ד)", "לה)" בתחילת הקטע
NOTE_MARKER = re.compile(r'\s*\(?[א-ת"]{1,4}\)')


def _wrappers_for(seen: set, z_tag: str = "b") -> list:
    wrappers = []
    for c in COLOR_PRIORITY:
        if c in seen:
            wrappers.append(("span", CLASS_STYLE[c]["style"]))
            break
    for c in TAG_PRIORITY:
        if c in seen:
            tag = z_tag if c == "Z" else CLASS_STYLE[c]["tag"]
            if (tag, None) not in wrappers:
                wrappers.append((tag, None))
    return wrappers


def _set_outer(span: Tag, name: str, style: str | None) -> None:
    span.name = name
    del span["class"]
    if style:
        span["style"] = style
    elif "style" in span.attrs:
        del span["style"]


def apply_span_styles(html: str, notes_in_z: bool = False) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for span in soup.find_all("span"):
        classes = span.get("class") or []
        all_span_classes.update(classes)
        seen = {c for c in classes if c in CLASS_STYLE}
        if not seen:
            span.unwrap()
            continue
        z_tag = "i" if notes_in_z and NOTE_MARKER.match(span.get_text()) else "b"
        wrappers = _wrappers_for(seen, z_tag)
        _set_outer(span, *wrappers[0])
        current = span
        for name, style in wrappers[1:]:
            new_tag = soup.new_tag(name)
            if style:
                new_tag["style"] = style
            new_tag.extend([child.extract() for child in list(current.contents)])
            current.append(new_tag)
            current = new_tag
    for b in soup.find_all("b"):
        if b.find_parent("b") is not None:
            b.unwrap()
    result = str(soup).replace("\n", " ")
    result = re.sub(r'(\s*<br\s*/?>)+\s*$', '', result).strip()
    # בנתוני המקור כותרת הסימן דבוקה לגוף הקטע (otzaria-library#38)
    result = fix_marker_breaks.fix_text(result)[0]
    # בנתוני המקור המילה שאחרי קטע מעוצב דבוקה לתג הסוגר (otzaria/otzaria#1068)
    return fix_missing_spaces.fix_text(result)[0]
