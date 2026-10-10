#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dicta_edit_core.py — הלוגיקה הטהורה של כלי "עריכת ספרים" (ללא tkinter).

כל כלי GUI בתיקייה זו קורא לפונקציה מכאן, וכך גם הבדיקות. כל פונקציה מקבלת
טקסט ומחזירה (טקסט_חדש, מספר_שינויים) — בלי קבצים ובלי חלונות.

הקוד מבוסס על הגרסה המתוחזקת ב־github.com/Otzaria/EditingDictaBooks
(`edit_dicta_cli.py`), עם התיקונים שם ותיקונים נוספים:
  * כותרות "עמוד ב": `ע` חייב גרש/גרשיים וגבול מילה — "עבודה זרה" אינה ע"ב.
  * לא נמחק פיסוק מהטקסט שאחרי הכותרת, ו"גמ'" לא משוכפל.
  * "דף ב." ו"דף ב:" נשארים שתי כותרות שונות (העמוד לא נמחק).
  * "פרק ב דברכות" (הפניה) אינה כותרת.
  * בדיקת רצף הכותרות משווה כל כותרת לבאה אחריה (במצב ש"ס — לשתיים אחריה).
  * הדגשת מילה ראשונה + פיסוק בסוף קטע: שתי הפעולות יחד לא מאבדות את הפיסוק.
  * נקודותיים ורווח: שבירה רק בשורות גוף, לא בתוך תג ולא אחרי "וז"ל:", ולא
    אחרי הפניה לדף ("שבת קיט: ובגמ'", "ב"ק כ"ה:", "ע"ב:", "(לב: ד"ה …)").
  * אותיות בודדות: רק מספר שממשיך רצף; "<b>שם.</b>", "ר'", "ה'", "תו'" אינם כותרות.
  * ניקוי טקסט: רווח לפני סימן סוגר נמחק רק כשהוא באמת סוגר ("בהו ]היינו" נשאר).

אין תלות חיצונית (גימטריה ממומשת כאן).
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# גימטריה
# ---------------------------------------------------------------------------

_ONES = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"]
_TENS = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"]
_HUNDREDS = ["", "ק", "ר", "ש", "ת", "תק", "תר", "תש", "תת", "תתק"]
_VAL = {"א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
        "י": 10, "כ": 20, "ך": 20, "ל": 30, "מ": 40, "ם": 40, "נ": 50, "ן": 50,
        "ס": 60, "ע": 70, "פ": 80, "ף": 80, "צ": 90, "ץ": 90,
        "ק": 100, "ר": 200, "ש": 300, "ת": 400}
_FINAL = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}


def num_to_heb(n: int, finals: bool = False) -> str:
    """1..999 → גימטריה בלי גרשיים (15→טו, 16→טז)."""
    if not 0 < n < 1000:
        raise ValueError(n)
    h, rest = divmod(n, 100)
    t, o = divmod(rest, 10)
    s = _HUNDREDS[h]
    if rest == 15:
        s += "טו"
    elif rest == 16:
        s += "טז"
    else:
        s += _TENS[t] + _ONES[o]
    if finals and s and s[-1] in _FINAL:
        s = s[:-1] + _FINAL[s[-1]]
    return s


def heb_to_num(s: str) -> int | None:
    """גימטריה → מספר (מתעלם מגרש/גרשיים). None אם יש תו שאינו אות."""
    s = re.sub(r"[\"'״׳”’`]", "", s or "")
    if not s:
        return None
    total = 0
    for ch in s:
        if ch not in _VAL:
            return None
        total += _VAL[ch]
    return total


# מספרים כתובים במילים / צורות נוספות שהכלים הישנים קיבלו
_WORD_NUMBERS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "ששי",
                 "שביעי", "שמיני", "תשיעי", "עשירי"]
_EXTRA_FORMS = ["יוד", "למד", "נון", "דש", "חי", "טל", "שדמ", "ער", "שדם",
                "תשדם", "תשדמ", "ערב", "ערה", "עדר", "רחצ"]

_TAGS_PUNCT_RE = re.compile(
    r"</?(?:b|big|small|i|span|p|br)\s*/?>|[:,;\[\](){}.‚\"'״”’׳‘„`´“❝❞ˮ″ʺˈʹ′ʾʽ]")


def strip_tags_punct(text: str) -> str:
    """ניקוי מחמיר: תגי עיצוב ופיסוק (כמו strip_html_tags של הכלים)."""
    return _TAGS_PUNCT_RE.sub("", text)


def is_number_word(text: str, max_num: int = 999) -> bool:
    """האם המילה (אחרי ניקוי) היא מספר גימטריה 1..max_num / מספר במילים."""
    c = strip_tags_punct(text)
    if not c:
        return False
    if c in _WORD_NUMBERS or c in _EXTRA_FORMS:
        return True
    return _NUMBER_FORMS.get(c, 10 ** 6) <= max_num


_NUMBER_FORMS: dict[str, int] = {}
for _n in range(999, 0, -1):
    _NUMBER_FORMS[num_to_heb(_n)] = _n
    _NUMBER_FORMS.setdefault(num_to_heb(_n, finals=True), _n)


# ---------------------------------------------------------------------------
# 1. יצירת כותרות לפי מילה ("הגדרת כותרות לאוצריא")
# ---------------------------------------------------------------------------

_TRACTATES = [
    "ברכות", "פאה", "דמאי", "כלאים", "שביעית", "תרומות", "מעשרות", "מעשר שני",
    "חלה", "ערלה", "בכורים", "שבת", "עירובין", "ערובין", "פסחים", "שקלים",
    "יומא", "סוכה", "ביצה", "ראש השנה", "תענית", "מגילה", "מגלה", "מועד קטן",
    "חגיגה", "יבמות", "כתובות", "נדרים", "נזיר", "סוטה", "גיטין", "קידושין",
    "קדושין", "בבא קמא", "בבא מציעא", "בבא בתרא", "ב\"ק", "ב\"מ", "ב\"ב",
    "סנהדרין", "מכות", "שבועות", "עדיות", "עבודה זרה", "ע\"ז", "אבות",
    "הוריות", "זבחים", "מנחות", "חולין", "בכורות", "ערכין", "תמורה", "כריתות",
    "מעילה", "תמיד", "מדות", "קנים", "כלים", "אהלות", "נגעים", "פרה",
    "טהרות", "מקואות", "נדה", "מכשירין", "זבים", "טבול יום", "ידים", "עוקצין",
]
_TRACTATE_FIRST = {t.split()[0] for t in _TRACTATES}


def _looks_like_reference(rest_words: list[str]) -> bool:
    """"פרק ב דברכות" / "סימן ג בשו"ע" — המשך שהוא הפניה, לא כותרת."""
    if not rest_words:
        return False
    w = strip_tags_punct(rest_words[0])
    if len(w) > 2 and w[0] in "דבלמו" and w[1:] in _TRACTATE_FIRST:
        return True
    if w in {"דף", "ע\"א", "ע\"ב"} or re.fullmatch(r"(?:ב|ד|ל)?(?:שו\"?ע|טור|רמב\"?ם)", w):
        return True
    return False


_AMUD_A_RE = re.compile(r'^(?:<[^>]+>)*ע["\'״׳]+א(?![א-ת])')
_AMUD_B_RE = re.compile(r'^(?:<[^>]+>)*ע["\'״׳]+ב(?![א-ת])')


def _daf_suffix(num_word: str, next_word: str | None) -> tuple[str, bool]:
    """לכותרת "דף": ('.'|':'|'', האם המילה הבאה נצרכה כסמן עמוד)."""
    raw = re.sub(r"<[^>]+>", "", num_word).rstrip()
    if raw.endswith(":"):
        return ":", False
    if raw.endswith("."):
        return ".", False
    if next_word is not None:
        if _AMUD_A_RE.match(next_word):
            return ".", True
        if _AMUD_B_RE.match(next_word):
            return ":", True
    return "", False


def create_headers(text: str, word: str, level: int = 2, max_num: int = 999,
                   skip_lines: int = 2) -> tuple[str, int]:
    """כותרת <hN>WORD NUM</hN> לכל שורה שמתחילה ב־WORD ואחריה מספר.

    גם: WORD לבדו בשורה והמספר בתחילת השורה הבאה. שאר השורה עובר לשורה
    נפרדת. לכותרת "דף" נשמר סימן העמוד (`דף ב.` / `דף ב:`), גם מ־ע"א/ע"ב
    שבא אחרי המספר. `skip_lines` שורות ראשונות (h1 + מחבר) לא נבדקות.
    """
    target = strip_tags_punct(word).strip()
    lines = text.split("\n")
    out = lines[:skip_lines]
    count = 0
    i = skip_lines
    is_daf = target == "דף"
    while i < len(lines):
        line = lines[i]
        words = line.split()
        if re.match(r"^\s*<h\d", line) or not words:
            out.append(line)
            i += 1
            continue
        first = strip_tags_punct(words[0])
        if first == target and len(words) >= 2 and is_number_word(words[1], max_num) \
                and not _looks_like_reference(words[2:]):
            rest = words[2:]
            suffix = ""
            if is_daf:
                suffix, used = _daf_suffix(words[1], rest[0] if rest else None)
                if used:
                    rest = rest[1:]
            out.append(f"<h{level}>{target} {strip_tags_punct(words[1])}{suffix}</h{level}>")
            if rest:
                out.append(_balance_tags(" ".join(rest)))
            count += 1
            i += 1
            continue
        if first == target and len(words) == 1 and i + 1 < len(lines):
            nxt = lines[i + 1].split()
            if nxt and is_number_word(nxt[0], max_num) and not _looks_like_reference(nxt[1:]):
                rest = nxt[1:]
                suffix = ""
                if is_daf:
                    suffix, used = _daf_suffix(nxt[0], rest[0] if rest else None)
                    if used:
                        rest = rest[1:]
                out.append(f"<h{level}>{target} {strip_tags_punct(nxt[0])}{suffix}</h{level}>")
                if rest:
                    out.append(_balance_tags(" ".join(rest)))
                count += 1
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out), count


def _balance_tags(s: str) -> str:
    """אחרי הוצאת המילים הראשונות לכותרת: תג סוגר יתום בתחילה / פותח בסוף."""
    s = s.strip()
    # </b> שנשאר מתג שנפתח במילים שהוצאו
    while True:
        m = re.match(r"^(</(?:b|big|small)>)\s*", s)
        if not m:
            break
        s = s[m.end():]
    opens = re.findall(r"<(b|big|small)>", s)
    closes = re.findall(r"</(b|big|small)>", s)
    for tag in ("b", "big", "small"):
        extra = closes.count(tag) - opens.count(tag)
        if extra > 0:
            s = f"<{tag}>" * extra + s
        elif extra < 0:
            s = s + f"</{tag}>" * (-extra)
    return s


# ---------------------------------------------------------------------------
# 2. כותרות לאותיות בודדות ("אותיות בודדות…")
# ---------------------------------------------------------------------------

# מילים נפוצות שהן גם צורת גימטריה תקינה — כותרת רק כהמשך ישיר של רצף
# (אף פעם לא כהתחלה מחדש, ואף פעם כשאין רצף). כל צורה באות סופית (שם, רם,
# תן…) נחשבת כזו גם בלי להופיע כאן.
_COMMON_NUMBER_WORDS = frozenset({
    "ר", "ה", "תו", "כו", "שם", "של", "לא", "לו", "לב", "מה", "כה", "עד", "פה",
    "רב", "קל", "שי", "רע", "שד", "שב", "שה", "שו", "תל", "רצ", "קח", "צו",
    "שע", "רש", "תר", "קו", "רי", "טל", "חי", "גד", "יד", "יה", "טו", "מי",
})


def _is_common_number_word(c: str) -> bool:
    return c in _COMMON_NUMBER_WORDS or (len(c) > 1 and c[-1] in "ךםןףץ")


def single_letter_headers(text: str, suffixes: list[str] | str = ".",
                          prefixes: list[str] | str = "", level: int = 3,
                          max_num: int = 999, bold_only: bool = True,
                          ignore: list[str] | None = None,
                          remove_chars: list[str] | None = None,
                          skip_lines: int = 1, sequential: bool = True) -> tuple[str, int]:
    """כותרת לשורה שמתחילה באות/מספר גימטריה + סיומת (א. / (ב) / ג' …).

    `suffixes` / `prefixes` — מחרוזת אחת או רשימה (הכלי "כמה סימונים בו
    זמנית"). `bold_only` — רק כשהמילה הראשונה כולה עטופה ב־<b>…</b>
    (ובלי — רק כשאין בה <b>). `remove_chars` — מה להסיר מטקסט הכותרת
    (ברירת מחדל: כל הפיסוק).

    `sequential` (ברירת מחדל): רק מספר שממשיך את הרצף — הקודם + 1, או א
    (התחלה מחדש) כשהמועמד הבא אחריו הוא ב (א בודד אינו כותרת). כותרת ברמה אחרת (פרק/סימן) מאפסת.
    בכל מצב, מילה נפוצה שהיא גם גימטריה (`_COMMON_NUMBER_WORDS`: שם, ר', ה',
    תו', כו', לא…) מתקבלת רק כהמשך ישיר של רצף. בלי זה `<b>שם.</b>` (=340),
    `ר' יוחנן`, `ה' אמר`, `תו'` הפכו לכותרות (מאות שורות בספרים ערוכים).
    """
    if isinstance(suffixes, str):
        suffixes = [suffixes]
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    ignore = list(ignore or ["<big>", "</big>", "<i>", "</i>", "<small>", "</small>"])
    lines = text.split("\n")
    body = lines[skip_lines:]

    # מעבר 1: מועמדים (אינדקס, מספר, מילה נקייה, core) ונקודות איפוס
    items: list = []  # ("reset",) | (idx, n, clean, core)
    for idx, line in enumerate(body):
        words = line.split()
        if not words or re.match(r"^\s*<h\d", line):
            if words:
                # כותרת קיימת באותה רמה שהיא מספר (הרצה קודמת) — הרצף ממשיך
                # ממנה; כל כותרת אחרת (פרק/סימן) — הרצף מתחיל מחדש
                hm = re.match(rf"^\s*<h{level}>(.*?)</h{level}>\s*$", line)
                hn = _NUMBER_FORMS.get(strip_tags_punct(hm.group(1)).strip()) if hm else None
                items.append(("reset", hn or 0))
            continue
        cleaned = words[0]
        for t in ignore:
            cleaned = cleaned.replace(t, "")
        is_bold = cleaned.startswith("<b>") and cleaned.endswith("</b>")
        core = cleaned[3:-4] if is_bold else cleaned
        if bold_only and not is_bold:
            continue
        if not bold_only and ("<b>" in cleaned or "</b>" in cleaned):
            continue
        if not any(core.endswith(s) for s in suffixes) or \
                not any(core.startswith(p) for p in prefixes):
            continue
        if not is_number_word(core, max_num):
            continue
        c = strip_tags_punct(core)
        items.append((idx, _NUMBER_FORMS.get(c), c, core))

    # מעבר 2: מי מהמועמדים נכנס לרצף
    accepted: dict[int, str] = {}
    last = 0
    for k, it in enumerate(items):
        if it[0] == "reset":
            last = it[1]
            continue
        idx, n, c, core = it
        cont = n is not None and n > 1 and n == last + 1  # א — רק כהתחלה מחדש
        if _is_common_number_word(c):
            ok = cont
        elif not sequential:
            ok = True
        elif cont:
            ok = True
        elif n == 1:
            # התחלה מחדש — רק אם המועמד הבא (לפני איפוס) הוא ב
            # (מילה נפוצה באמצע — "שם." — אינה נחשבת). א בודד לפני כותרת/סוף
            # אינו כותרת: בספרים הערוכים אלה בעיקר תאריכים ("א' תמוז") ופתיחות.
            nxt = next((x for x in items[k + 1:]
                        if x[0] == "reset" or not _is_common_number_word(x[2])), None)
            ok = nxt is not None and nxt[0] != "reset" and nxt[1] == 2
        else:
            ok = False
        if ok:
            accepted[idx] = core
            if n is not None:
                last = n

    out = lines[:skip_lines]
    count = 0
    for idx, line in enumerate(body):
        if idx not in accepted:
            out.append(line)
            continue
        core = accepted[idx]
        words = line.split()
        if remove_chars is None:
            h = strip_tags_punct(core)
        else:
            h = re.sub(r"<[^>]+>", "", core)
            for t in remove_chars:
                h = h.replace(t, "")
        out.append(f"<h{level}>{h}</h{level}>")
        if words[1:]:
            # תג (<big>/<small>) שנפתח במילה הראשונה ונשאר פתוח — מאוזן בשורה שנשארה
            out.append(_balance_tags(" ".join(words[1:])))
        count += 1
    return "\n".join(out), count


# ---------------------------------------------------------------------------
# 3. הוספת מספר עמוד בכותרת הדף
# ---------------------------------------------------------------------------

_AMUD_MARK_RE = re.compile(
    r'^(?P<open>(?:<[a-z]+>)*)(?P<m>ע["\'״׳]+[אב](?![א-ת])|עמוד [אב](?![א-ת]))'
    r'[.,:()\[\]\'"״׳”’‘„`´“]?(?P<close>(?:</[a-z]+>)*)\s?')


def add_page_number(text: str, style: str = "dot-colon") -> tuple[str, int]:
    """`<hN>דף X</hN>` ואחריה שורה שמתחילה ב־ע"א/ע"ב/עמוד א|ב.

    style="dot-colon" → `דף X.` / `דף X:`; style="ayin" → `דף X ע"א` / `ע"ב`.
    הסמן נמחק משורת הטקסט; שאר הפיסוק בשורה נשמר.
    """
    lines = text.split("\n")
    out = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^<h([2-9])>(דף [^<]+?)</h\1>\s*$", line)
        if m and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            m2 = _AMUD_MARK_RE.match(nxt)
            if m2:
                lvl, title = m.group(1), m.group(2).rstrip(".:").rstrip()
                is_a = m2.group("m").endswith("א")
                if style == "ayin":
                    mark = 'ע"א' if is_a else 'ע"ב'
                    out.append(f"<h{lvl}>{title} {mark}</h{lvl}>")
                else:
                    out.append(f"<h{lvl}>{title}{'.' if is_a else ':'}</h{lvl}>")
                rest = nxt[m2.end():].strip()
                if rest:
                    # תג שנפתח לפני הסמן ולא נסגר מיד אחריו עוטף גם את ההמשך
                    keep_open = "" if m2.group("close") else m2.group("open")
                    out.append(_balance_tags(keep_open + rest))
                changes += 1
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out), changes


# ---------------------------------------------------------------------------
# 4. שינוי רמת כותרת
# ---------------------------------------------------------------------------

def change_heading_level(text: str, from_level: int, to_level: int) -> tuple[str, int]:
    pat = re.compile(rf"<h{from_level}>(.*?)</h{from_level}>", re.DOTALL)
    n = len(pat.findall(text))
    return pat.sub(rf"<h{to_level}>\1</h{to_level}>", text), n


# ---------------------------------------------------------------------------
# 5. הדגשת מילה ראשונה וניקוד בסוף קטע
# ---------------------------------------------------------------------------

def emphasize_and_punctuate(text: str, ending: str | None = ":",
                            emphasize: bool = True, min_words: int = 10,
                            skip_lines: int = 2) -> tuple[str, int]:
    """לכל שורת גוף ארוכה (> min_words מילים, לא כותרת):

    * ending ('.' / ':' / None): מוסיף סימן סוף כשאין; פסיק בסוף מוחלף.
    * emphasize: עוטף את המילה הראשונה ב־<b> אם אינה כבר בתוך תג.
    שתי הפעולות יחד — הסימן נשמר (באג בגרסה הישנה ובזו של EditingDictaBooks).
    """
    lines = text.split("\n")
    changes = 0
    for i in range(skip_lines, len(lines)):
        line = lines[i].rstrip()
        words = line.split()
        if len(words) <= min_words or re.match(r"^\s*<h\d", line):
            continue
        new = line
        if ending:
            if new.endswith(","):
                new = new[:-1] + ending
            elif not new.endswith((".", ":", "!", "?")) and \
                    not new.endswith(("</small>", "</big>", "</b>")):
                new = new + ending
        if emphasize:
            ws = new.split(" ")
            first = ws[0]
            if first and "<" not in first and ">" not in first:
                ws[0] = f"<b>{first}</b>"
                new = " ".join(ws)
        if new != lines[i]:
            lines[i] = new
            changes += 1
    return "\n".join(lines), changes


# ---------------------------------------------------------------------------
# 6. יצירת כותרות "עמוד ב"
# ---------------------------------------------------------------------------

_ANY_TAGS = r"(?:<[^>]+>\s*)*"


def _tag_agnostic(word: str) -> str:
    return "".join(_ANY_TAGS + re.escape(ch) for ch in word) + _ANY_TAGS


_PAGE_B_RE = re.compile(
    r"^\s*" + _ANY_TAGS
    + r"(?P<shem>" + _tag_agnostic("שם") + r"\s*(?=[עב]|<))?"
    + r"(?P<gmara>(?:" + "|".join(_tag_agnostic(w) for w in ["בגמרא", "גמרא", "בגמ'", "גמ'"])
    + r")\s*)?"
    + r"(?P<ab>(?<![א-ת])(?:" + "|".join([
        _tag_agnostic("עמוד") + r"\s*" + _tag_agnostic("ב"),
        r"ע" + _ANY_TAGS + r"(?:[\"'״׳’]|'')" + _ANY_TAGS + r"ב",
    ]) + r"))(?![א-ת])"
    + r"(?P<punct>" + _ANY_TAGS + r"[.,:]?" + _ANY_TAGS + r")"
    + r"(?P<rest>.*)$")


def create_page_b_headers(text: str, level: int = 3) -> tuple[str, int]:
    """כותרת `<hN>עמוד ב</hN>` לשורה שמתחילה ב"עמוד ב" / ע"ב (אפשר "שם"/"גמ'" לפני).

    "גמרא"/"גמ'" עוברים לתחילת השורה שאחרי הכותרת (פעם אחת). "שם" נמחק.
    מלבד סימן פיסוק אחד שצמוד ל־ע"ב, שום פיסוק בשורה לא נמחק. "עבודה" /
    "עב" / "עמודים" אינם מזוהים (דרוש גרש/גרשיים או מילה שלמה).
    """
    out = []
    count = 0
    for line in text.split("\n"):
        if re.search(r"<h\d>", line):
            out.append(line)
            continue
        m = _PAGE_B_RE.match(line)
        if not m:
            out.append(line)
            continue
        header = f"<h{level}>עמוד ב</h{level}>"
        gm = m.group("gmara")
        gm = re.sub(r"<[^>]+>", "", gm).strip() if gm else ""
        rest = m.group("rest").strip()
        rest = _balance_tags(rest) if rest else ""
        body = " ".join(x for x in (gm, rest) if x)
        out.append(header)
        if body:
            out.append(body)
        count += 1
    return "\n".join(out), count


# ---------------------------------------------------------------------------
# 7. החלפת כותרות "עמוד ב" לשם הדף
# ---------------------------------------------------------------------------

def replace_page_b_headers(text: str, style: str = "colon") -> tuple[str, int]:
    """`<hN>עמוד ב</hN>` → `<hN>דף X:</hN>` (או `דף X ע"ב`), לפי כותרת הדף הקודמת."""
    state = {"title": "", "level": "", "count": 0}

    def repl(m):
        level, title = m.group(1), m.group(2)
        if re.match(r"דף \S+", title):
            state["title"], state["level"] = title.strip(), level
            return m.group(0)
        if title.strip() == "עמוד ב" and state["title"]:
            state["count"] += 1
            base = re.sub(r'( ע"א| עמוד א)$', "", state["title"]).rstrip(".:")
            lv = state["level"]
            if style == "colon":
                return f"<h{lv}>{base}:</h{lv}>"
            return f'<h{lv}>{base} ע"ב</h{lv}>'
        return m.group(0)

    new = re.sub(r"<h([1-9])>(.*?)</h\1>", repl, text)
    return new, state["count"]


# ---------------------------------------------------------------------------
# 8. בדיקת תגים וכותרות
# ---------------------------------------------------------------------------

def validate_tags(text: str) -> dict:
    """תגים פותחים/סוגרים לא מאוזנים, וכותרת עם טקסט באותה שורה."""
    opening, closing, heading_errors = [], [], []
    for no, line in enumerate(text.split("\n"), start=1):
        stack = []
        for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*>", line):
            close, name = m.group(1), m.group(2).lower()
            if name in ("br", "img", "hr"):
                continue
            if not close:
                stack.append(name)
            else:
                for j in range(len(stack) - 1, -1, -1):
                    if stack[j] == name:
                        stack.pop(j)
                        break
                else:
                    closing.append((no, name, line.strip()))
        for name in stack:
            opening.append((no, name, line.strip()))
        hm = re.search(r"<h([1-6])>.*?</h\1>", line)
        if hm and (line[:hm.start()].strip() or line[hm.end():].strip()):
            heading_errors.append((no, line.strip()))
    return {"opening_without_closing": opening,
            "closing_without_opening": closing,
            "heading_errors": heading_errors}


def validate_headings(text: str, start_chars: str = "", end_chars: str = "",
                      gershayim: bool = False, shas: bool = False) -> dict:
    """רצף מספרי הכותרות בכל רמה (h2–h6).

    כל כותרת מושווית לבאה אחריה (`index+1`); במצב ש"ס (`דף ב.` / `דף ב:`
    כשתי כותרות) — לשתיים אחריה (`index+2`). "בדיקת תגים גירסא 2" השוותה
    תמיד ל־index+2, גם בספר שאינו ש"ס.
    `gershayim=True`: המספר בכותרת צריך גרש/גרשיים (ט' / י"א) — מדווח כשחסר.
    `gershayim=False`: המספר צריך להיות בלי — מדווח כשיש (מוסכמת הספרייה).
    """
    if shas:
        end_chars = end_chars + ".:"
    s_cls = f"[{re.escape(start_chars)}]*" if start_chars else ""
    e_cls = f"[{re.escape(end_chars)}]*" if end_chars else ""
    pat = re.compile(rf"^{s_cls}[א-ת]([א-ת \-]*[א-ת])?{e_cls}$")
    unmatched_regex, unmatched_seq, missing = [], [], []
    for lvl in range(2, 7):
        heads = [re.sub(r"<[^>]+>", "", h).strip()
                 for h in re.findall(rf"<h{lvl}>(.*?)</h{lvl}>", text)]
        if not heads:
            missing.append(lvl)
            continue
        # מצב ש"ס חל רק על רמה שרוב כותרותיה "דף …"
        daf = sum(1 for h in heads if h.startswith("דף ")) * 2 > len(heads)
        step = 2 if (shas and daf) else 1
        for h in heads:
            has_q = bool(re.search(r"[\"'״׳]", h))
            if not pat.match(h) and not (gershayim and has_q):
                unmatched_regex.append(h)
            num = _heading_number(h)
            n = heb_to_num(num)
            if gershayim and n is not None:
                need = "'" if n <= 9 else '"'
                if need not in num.replace("׳", "'").replace("״", '"'):
                    unmatched_seq.append(num)
            elif not gershayim and re.search(r"[\"'״׳]", num):
                unmatched_seq.append(num)
        for a, b in zip(heads, heads[step:]):
            na = heb_to_num(_heading_number(a))
            nb = heb_to_num(_heading_number(b))
            if na is None or nb is None or na + 1 != nb:
                unmatched_seq.append(f"{a} || {b}")
    return {"unmatched_regex": unmatched_regex, "unmatched_tags": unmatched_seq,
            "missing_levels": missing}


def _heading_number(h: str) -> str:
    parts = h.split()
    w = parts[1] if len(parts) > 1 else h
    return re.sub(r"[.:]+$", "", w)


# ---------------------------------------------------------------------------
# 9. נקודותיים ורווח → ירידת שורה
# ---------------------------------------------------------------------------

# בלי ז"ל לבדו: אחרי שם ("הרמב"ם ז"ל:") הוא תואר כבוד, לא מבוא לציטוט
_QUOTE_INTRO = {'וז"ל', "וזל\"ה", "וזה לשונו", "וזו לשונו", "ולשונו", "וזלה\"ק"}
# סוף ציטוט קצר שנמשך באותה פסקה ("וז"ל: אסור. עכ"ל ומה ש...")
_QUOTE_END = re.compile(r'עכ"ל|עכ"ד|עד כאן לשונו')  # לא ע"כ: גם "על כרחך"


_HEB_ONLY = re.compile(r"[^א-ת]")
# מפתחות מסכת בלי פיסוק: מילה ראשונה ("בבא"), שם מלא בן שתי מילים ("בבא קמא"),
# וקיצורים (ב"ק → בק, ע"ז → עז, מו"ק, ר"ה)
_TRACTATE_KEYS = {_HEB_ONLY.sub("", t.split()[0]) for t in _TRACTATES} | \
    {_HEB_ONLY.sub("", t) for t in _TRACTATES if '"' in t} | {"מוק", "רה"}
_TRACTATE_PAIRS = {" ".join(_HEB_ONLY.sub("", w) for w in t.split()) for t in _TRACTATES if " " in t}
_DAF_KEYS = {"דף", "ד", "דפ", "דפים"}
_GEMARA_REFS = {"תוס", "תוספות", "רשי", "גמ", "גמרא", "סוגיא", "משנה", "מתני"}
_DH_KEYS = {"דה", "בדה", "ודה", "בתודה", "תודה", "ובתודה", "דהמ"}


def _unprefixed(w: str) -> list[str]:
    """המילה, ובלי אות/שתי אותיות שימוש בתחילתה (בשבת, ובב"ק, דבדף)."""
    out = [w]
    for k in (1, 2):
        if len(w) > k + 1 and all(ch in "ובדלמשהכ" for ch in w[:k]):
            out.append(w[k:])
    return out


def _is_daf_number(w: str) -> bool:
    c = _HEB_ONLY.sub("", w)
    return bool(c) and len(c) <= 4 and 0 < _NUMBER_FORMS.get(c, 0) <= 200


def _is_daf_reference(prev_words: list[str]) -> bool:
    """הנקודותיים שאחרי המילים האלה הן סימן עמוד ב של הפניה, לא סוף עניין.

    "שבת קיט:" / "בב"ק כ"ה:" / "בבא מציעא ל:" / "דף ל"ג:" / "בדף ה':" / "בד' כא:" /
    "כ"ה ע"ב:" / "ע"ב:" / "דף ה' עמוד ב:".
    אחרי סוגר ("(שבת קיט):") הנקודותיים הן סוף משפט — נשבר.
    """
    if not prev_words:
        return False
    last = prev_words[-1]
    if last.endswith((")", "]")):
        return False  # "(שבת קיט):" — ההפניה נסגרה, הנקודותיים הן סוף משפט
    lc = _HEB_ONLY.sub("", last)
    # "כ"ה ע"ב:" / "ע"ב: בגמ'" (סמן עמוד שעומד לבדו) / "דף ה' עמוד ב:"
    if lc in ("עא", "עב") and re.search(r"[\"'״׳]", last):
        return True
    if lc in ("א", "ב") and len(prev_words) >= 3 and \
            _HEB_ONLY.sub("", prev_words[-2]) == "עמוד" and _is_daf_number(prev_words[-3]):
        return True
    if len(prev_words) < 2 or not _is_daf_number(last):
        return False
    before = _HEB_ONLY.sub("", prev_words[-2])
    for w in _unprefixed(before):
        if w in _DAF_KEYS or w in _TRACTATE_KEYS:
            return True
    if before in ("בד", "וד", "לד", "מד", "דד") and re.search(r"[\"'״׳]", prev_words[-2]):
        return True  # "בד' כא:" = בדף כא
    if before == "שם" and len(prev_words) >= 3 and any(
            w in _GEMARA_REFS for w in _unprefixed(_HEB_ONLY.sub("", prev_words[-3]))):
        return True  # "תוס' שם י"ח:" / "בגמ' שם כ:"
    if len(prev_words) >= 3:
        first = _HEB_ONLY.sub("", prev_words[-3])
        for w in _unprefixed(first):
            if f"{w} {before}" in _TRACTATE_PAIRS:
                return True
    return False


# סמן סעיף בתחילת פסקה: "(ג)", "ג)", "[ג]"
_ITEM_START = re.compile(r"^(?:\([א-ת]{1,3}['\"׳״]?\)|[א-ת]{1,3}\)|\[[א-ת]{1,3}['\"׳״]?\])(?:\s|$)")


def colon_ends_matter(before: str, after: str) -> bool:
    """האם `:` שבין before (עד הנקודותיים, בלעדיהן) ל־after היא סוף עניין שמותר לשבור אחריה.

    לא שוברים (באמצע משפט) רק בתוך תג פתוח, בסוגריים קצרים שנסגרים מיד ב־after,
    אחרי וז"ל: כשהציטוט נגמר מיד (עכ"ל) והטקסט נמשך, ובהפניה לעמוד ב ("שבת קיט: ובגמ'").
    after שפותח במודגש, בסמן סעיף או בד"ה (שלא אחרי הפניה) — פסקה חדשה.
    משמש את colon_newline, את dicta_convert ואת איחוד השורות (בספק — שוברים).
    """
    depth = len(re.findall(r"<(?:b|big|small|i)>", before)) -         len(re.findall(r"</(?:b|big|small|i)>", before))
    if depth > 0:
        return False
    if after.lstrip().startswith("<b>"):
        return True
    plain = re.sub(r"<[^>]+>", "", before)
    prev_words = plain.split()
    rest = re.sub(r"<[^>]+>", "", after).lstrip()
    if _ITEM_START.match(rest):
        return True
    op = plain.rfind("(")
    if op > max(plain.rfind(")"), plain.rfind("]")) and len(plain) - op <= 40:
        close, reopen = rest.find(")"), rest.find("(")
        if 0 <= close <= 40 and (reopen < 0 or close < reopen):
            return False  # "(שבת קיט: ד"ה ומה)" — הפניה בתוך סוגריים
    if _is_daf_reference(prev_words):
        return False  # "שבת קיט: ובגמ'" / "תוס' שם פ"ה: ד"ה" — עמוד ב, לא סוף עניין
    if prev_words and (prev_words[-1] in _QUOTE_INTRO or
                       " ".join(prev_words[-2:]) in _QUOTE_INTRO):
        m = _QUOTE_END.search(rest[:80])
        return not (m and rest[m.end():].strip(" .:"))
    return True


def colon_newline(text: str, skip_lines: int = 2) -> tuple[str, int]:
    """`: ` בתוך שורת גוף → `:` + ירידת שורה (סוף עניין בספרים הישנים), לפי colon_ends_matter."""
    lines = text.split("\n")
    out = lines[:skip_lines]
    count = 0
    for line in lines[skip_lines:]:
        line = re.sub(r" {1,5}$", "", line)
        if re.match(r"^\s*<h\d", line) or ": " not in line:
            out.append(line)
            continue
        pieces = []
        start = 0
        for m in re.finditer(r": +", line):
            if not line[m.end():].strip():
                continue
            if not colon_ends_matter(line[:m.start()], line[m.end():]):
                continue
            pieces.append(line[start:m.start()] + ":")
            start = m.end()
            count += 1
        pieces.append(line[start:])
        out.extend(pieces)
    return "\n".join(out), count


# ---------------------------------------------------------------------------
# 10. ניקוי טקסט (TextCleaner)
# ---------------------------------------------------------------------------

CLEAN_OPTIONS = ("remove_empty_lines", "remove_double_spaces", "remove_spaces_before",
                 "remove_spaces_after", "remove_spaces_around_newlines",
                 "replace_double_quotes", "normalize_quotes")


_SPACE_BEFORE_RE = re.compile(r"[ \t]+([)\],.:;])(?=\s|$|<)")


def _remove_spaces_before(line: str) -> str:
    """"כו' ." → "כו'." ; "( שם )" → "( שם)". רק לפני סימן שבאמת סוגר:
    אחריו רווח/סוף שורה/תג (לא אות — "בהו ]היינו" הוא סוגר הפוך של OCR ולא
    מודבק), ול־`)`/`]` — רק כשיש לפניו בשורה פותח תואם שלא נסגר."""
    def repl(m):
        ch = m.group(1)
        if ch in ")]":
            opener = "(" if ch == ")" else "["
            depth = 0  # סוגר יתום (בלי פותח) אינו מוריד מתחת ל־0
            for c in line[:m.start()]:
                if c == opener:
                    depth += 1
                elif c == ch and depth:
                    depth -= 1
            if not depth:
                return m.group(0)
        return ch
    return _SPACE_BEFORE_RE.sub(repl, line)


def clean_text(text: str, options=CLEAN_OPTIONS, normalize_unicode: bool = False) -> str:
    o = set(options)
    if "remove_empty_lines" in o:
        text = re.sub(r"\n\s*\n", "\n", text)
    if "remove_double_spaces" in o:
        text = re.sub(r" +", " ", text)
    if "remove_spaces_before" in o:
        # רק לפני סימן סוגר שאחריו רווח/סוף שורה/תג — "בהו ]היינו" (סוגר הפוך
        # של OCR) אינו מודבק למילה הבאה
        text = "\n".join(_remove_spaces_before(ln) for ln in text.split("\n"))
    if "remove_spaces_after" in o:
        text = re.sub(r"(\s|^)([\[(])(\s+)", r"\1\2", text, flags=re.MULTILINE)
    if "remove_spaces_around_newlines" in o:
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    if "replace_double_quotes" in o:
        for a in ("''", "``", "´´", "׳׳", "’’", "‘‘"):
            text = text.replace(a, '"')
    if "normalize_quotes" in o:
        for a, b in (("“", '"'), ("”", '"'), ("„", '"'), ("״", '"'),
                     ("‘", "'"), ("’", "'"), ("׳", "'"), ("`", "'"), ("´", "'")):
            text = text.replace(a, b)
    if normalize_unicode:
        text = unicodedata.normalize("NFC", text)
    return text.rstrip()


# ---------------------------------------------------------------------------
# עזר לקבצים (לשימוש ה־GUI)
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
