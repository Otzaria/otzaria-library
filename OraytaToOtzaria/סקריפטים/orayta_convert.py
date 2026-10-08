"""המרת ספרי אורייתא (.obk) למבנה אוצריא.

מחליף את oryta.py. נאמן למנוע התצוגה של אורייתא
(https://github.com/MosheWagner/Orayta-QT, OraytaBase/htmlgen.cpp, book.cpp, bookiter.cpp):

* סימני רמה בעמודה 0: '#' (הגבוה) > '^' > '@' > '~' > '!' (הנמוך); '$' = שם הספר.
  הרמות שבפועל קיימות בספר ממופות לפי הסדר ל־h2, h3, ...
* כללי ההחלפה של CosmeticsType (#rep=from=to^^from=to) מוחלים על שורות הטקסט
  (לא על הכותרות), לפי הסדר, לפני פענוח ה־HTML — בדיוק כמו ב־renderChapterHtml.
* כל שורת מקור היא שורה (PutNewLinesAsIs=1, ברירת המחדל); ב־PutNewLinesAsIs=0
  שורות הטקסט שבין שתי כותרות מתאחדות לפסקה אחת.
* כל שורת פלט מאוזנת: תג שנפתח בשורה אחת ונסגר בשורה מאוחרת יותר (באותו פרק)
  נסגר בסוף השורה ונפתח מחדש בתחילת הבאה; תג שלעולם לא נסגר — נסגר בסוף שורתו.
  שום שורה לא מתאחדת עם שכנתה. גם <br> שובר שורה.
* כותרות: היררכיה רציפה לפי הקינון בפועל; שורת רמה ארוכה (פסקה) היא טקסט מודגש.
* זהר מתורגם: {…} (תרגום) → <small>, {{…}} → (…) קטן, [[…]] → […] קטן, <<…>> מודגש,
  כותרות דף → "דף קיז." / "דף קיז:".
* גמרא נוחה (HTML של Word): הערות Word של העורך (בלי השם וחותמת הזמן) → ספר נלווה
  "הערות על <ספר>" + links מסוג footnotes, וסמן <sup>(א)</sup> בגוף; חומר Kollel Iyun Hadaf
  באנגלית, פרטי קשר והקדשה — נמחקים; הערות הסיום → הערות שוליים פנימיות; כותרות "דף ב." / "דף ב:".
* טקסט: '' → ", … → ...,  <QM> → ?, תווי צורות מצגת (U+FB1D–FB4F) מפורקים, תווים בלתי נראים
  נמחקים, מילים מנוקדות שהודבקו מופרדות אחרי אות סופית.
* תמונות (<img src="../Pics/…">): מוטמעות כ־data: base64 מתוך books/Pics, בשורה משלהן.
  תמונה שאינה שם — נשמטת עם אזהרה (תמונות חק לישראל נלקחו מתורת אמת המקוון, p_hok1/2.PNG).

שימוש (גמרא נוחה: עם --gmara):
    python3 orayta_convert.py books/100_kblh/002_zohr_mtorgm/000023_ZOHAR-VETARGUM-3.obk out.txt
    python3 orayta_convert.py books/032_gmara_nocha/14_msct_ibmot.obk "<ספר>.txt" --gmara --links-dir ../links
"""

import base64
import html
import os
import re
import sys
import unicodedata
import zipfile

LEVEL_SIGNS = "#^@~!"  # מהגבוה לנמוך
LONG_HEADING = 150  # שורת רמה ארוכה מזה היא פסקה מודגשת, לא כותרת

# class של אורייתא → style (ערכי ה־CSS של htmlgen.cpp)
CLASS_STYLE = {
    "pirush": "color:#2828AC;",
    "editor": "color:#008A00;",
    "ref": "font-size:80%;",
    "pasuk": "",  # font-family: SBL Hebrew — הגופן לא קיים באוצריא
    "pasuk small": "font-size:70%;",
    "small": "font-size:70%;",
    "verysmall": "font-size:70%;",
    "aliyah": "font-size:80%; font-weight:bold;",
    "s0": "font-size:95%; font-weight:bold;",
    "copyright": "font-size:60%;",
}

# תיבת התרגום של הזהר המתורגם (`{…}` → div עם מסגרת באורייתא): באוצריא — אות קטנה
BOX_OPEN = "<small>"
BOX_CLOSE = "</small>"

INLINE_TAGS = {"b", "i", "u", "big", "small", "sup", "sub", "span", "a", "center"}
VOID_TAGS = {"br", "hr", "img"}
PICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "books", "Pics")
IMG_MIME = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".bmp": "bmp"}
TAG_ALIASES = {"strong": "b", "em": "i", "font": "span"}

INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮﻿­"))

TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)((?:\s+[^<>]*?)?)\s*(/?)>")
ATTR_RE = re.compile(r"""([A-Za-z_:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")


# ---------------------------------------------------------------- קריאה

def decode(data):
    for enc in ("utf-8-sig", "cp1255"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("orayta", data, 0, 1, "neither utf-8 nor cp1255")


def read_obk(path):
    with zipfile.ZipFile(path) as z:
        if "BookText" not in z.namelist():
            raise ValueError(f"{path}: אין BookText (ספר מוצפן/PDF?)")
        text = decode(z.read("BookText"))
        comment = decode(z.comment) if z.comment else ""
    return text, comment


CONF_KEY_RE = re.compile(r"^&?[A-Za-z][A-Za-z0-9]*=|^(Nikud|Teamim|NotInSearch|Kukayta)\s*$")


def parse_conf(comment):
    """הערת ה־zip: key=value בכל שורה; ערך ארוך (CosmeticsType) נשבר לפעמים לשורות המשך."""
    conf, last = {}, None
    for line in comment.splitlines():
        if not line.strip():
            continue
        if CONF_KEY_RE.match(line) and not line.startswith("&"):
            key, _, val = line.partition("=")
            conf[key.strip()] = val
            last = key.strip()
        elif line.startswith("&"):
            continue
        elif last:
            conf[last] += line  # המשך של הערך הקודם
    if "Kukayta" in conf:
        raise ValueError("ספר מוצפן (Kukayta)")
    return conf


def parse_reps(cosmetics):
    """CosmeticsType → רשימת (from, to) לפי הסדר, כמו Book::setCosmetics."""
    reps = []
    for entry in cosmetics.split("#"):
        key, _, val = entry.partition("=")
        if not key.startswith("rep"):
            continue
        for pair in val.split("^^"):
            frm, sep, to = pair.partition("=")
            if sep and frm:
                reps.append((frm, to))
    return reps


# ---------------------------------------------------------------- כללי החלפה

def adapt_reps(reps):
    """ממיר את יעדי ההחלפה של אורייתא ל־HTML שאוצריא מבינה."""
    out = []
    for frm, to in reps:
        if frm == to:
            continue  # FONT5=FONT5 וכדומה
        low = to.lower()
        if low.startswith("<div") and "border" in low:
            to = BOX_OPEN
        elif low == "</div>":
            to = BOX_CLOSE
        elif low.startswith("<!--") or low == "-->":
            continue  # rep4 של הזהר — כבר נבלע ב־rep3
        out.append((frm, to))
    # הזוג "(" / ")" — רק סוגריים מאוזנים, אחרת שארית השורה מוקטנת
    froms = [f for f, _ in out]
    if "(" in froms and ")" in froms:
        o = dict(out)
        paren = (o["("], o[")"])
        out = [(f, t) for f, t in out if f not in "()"]
        out.append(("__PAREN__", paren))
    return out


PAREN_RE = re.compile(r"\(([^()<>]*)\)")


def apply_reps(line, reps):
    for frm, to in reps:
        if frm == "__PAREN__":
            line = PAREN_RE.sub(lambda m: f"{to[0]}{m.group(1)}{to[1]}", line)
        else:
            line = line.replace(frm, to)
    return line


# ---------------------------------------------------------------- HTML

def parse_style(style):
    decls = []
    for d in style.split(";"):
        d = d.strip()
        if not d:
            continue
        if ":" not in d and "=" in d:  # color=#0055ff
            d = d.replace("=", ":", 1)
        prop, _, val = d.partition(":")
        prop, val = prop.strip().lower(), val.strip()
        if not val or re.search(r"\b(MIX\d+|FONT\d+)\b", val) or prop in ("ffont-size", "font-family"):
            continue
        if prop in ("padding", "margin") and re.fullmatch(r"\d+", val):
            val += "px"
        decls.append(f"{prop}:{val}")
    return decls


def norm_open_tag(name, attrs):
    """מחזיר (שם, טקסט־פתיחה) או None לתג שנזרק."""
    name = TAG_ALIASES.get(name, name)
    a = {m.group(1).lower(): next(g for g in m.groups()[1:] if g is not None)
         for m in ATTR_RE.finditer(attrs or "")}
    if name == "a":
        href = a.get("href", "")
        if href.startswith(("http://", "https://")):
            return name, f'<a href="{html.escape(href, quote=True)}">'
        return None
    if name not in INLINE_TAGS:
        return None
    decls = []
    cls = " ".join(a.get("class", "").lower().split())
    if cls in CLASS_STYLE:
        decls += parse_style(CLASS_STYLE[cls])
    if name == "span" and "color" in a:  # <font color=…>
        decls.append(f"color:{a['color']}")
    decls += parse_style(a.get("style", ""))
    if name == "span":
        decls = [d for d in decls if not d.startswith("text-align")]
        if not decls:
            return "span", None  # span ריק מסגנון — נשמר במחסנית אך לא נפלט
    style = f' style="{"; ".join(decls)};"' if decls else ""
    if name != "span" and name not in ("center",):
        style = ""
    return name, f"<{name}{style}>"


def tokenize(line):
    pos = 0
    for m in TAG_RE.finditer(line):
        if m.start() > pos:
            yield ("text", line[pos:m.start()])
        closing, name, attrs, selfclose = m.groups()
        name = name.lower()
        if name == "img":
            yield ("img", attrs)
        elif name in VOID_TAGS:
            yield ("void", name)
        elif closing:
            yield ("close", TAG_ALIASES.get(name, name))
        else:
            yield ("open", name, attrs)
        pos = m.end()
    if pos < len(line):
        yield ("text", line[pos:])


def text_escape(s):
    # במקורות אורייתא '' הוא קידוד ASCII של " (גרשיים וגם מירכאות)
    s = norm_chars(html.unescape(s.replace("&nbsp;", " "))).replace("''", '"').replace("…", "...")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def img_tag(attrs):
    """<img src="../Pics/x.PNG"> → <img src="data:image/png;base64,…"> מתוך books/Pics."""
    m = re.search(r"""src\s*=\s*["']?([^"'\s>]+)""", attrs or "", re.I)
    src = m.group(1).replace("\\", "/") if m else ""
    rel = re.split(r"(?i)pics/", src)[-1]
    path = next((os.path.join(PICS_DIR, f) for f in os.listdir(PICS_DIR) if f.lower() == rel.lower()), None) \
        if rel and os.path.isdir(PICS_DIR) else None
    mime = IMG_MIME.get(os.path.splitext(rel)[1].lower())
    if not path or not mime:
        print(f"אזהרה: תמונה חסרה {src!r} — נשמטה", file=sys.stderr)
        return " "
    with open(path, "rb") as f:
        return f'<img src="data:image/{mime};base64,{base64.b64encode(f.read()).decode()}">'


LOOKAHEAD = 400  # שורות; תג שלא נסגר בטווח הזה נחשב לא־סגור


def closers_ahead(lines_tokens, start, name):
    """האם יש סוגר בלתי מותאם ל־name בשורות שמתחילות ב־start."""
    depth = 0
    for toks in lines_tokens[start:start + LOOKAHEAD]:
        for t in toks:
            if t[0] == "open" and TAG_ALIASES.get(t[1], t[1]) == name:
                depth += 1
            elif t[0] == "close" and t[1] == name:
                if depth == 0:
                    return True
                depth -= 1
    return False


def render_section(lines):
    """שורות טקסט → שורות HTML מאוזנות (תג פתוח עובר לשורה הבאה רק אם ייסגר בהמשך)."""
    toks_per_line = [list(tokenize(l)) for l in lines]
    out = []
    carry = []  # [(name, opentext)] שעוברים מהשורה הקודמת
    for i, toks in enumerate(toks_per_line):
        stack = list(carry)
        buf = [o for _, o in stack if o]
        for t in toks:
            if t[0] == "text":
                buf.append(text_escape(t[1]))
            elif t[0] == "img":
                buf.append(img_tag(t[1]))
            elif t[0] == "void":
                buf.append("<br>" if t[1] == "br" else " ")
            elif t[0] == "open":
                r = norm_open_tag(t[1], t[2])
                if r is None:
                    stack.append((TAG_ALIASES.get(t[1], t[1]), None))
                    continue
                stack.append(r)
                if r[1]:
                    buf.append(r[1])
            else:  # close
                idx = next((k for k in range(len(stack) - 1, -1, -1) if stack[k][0] == t[1]), None)
                if idx is None:
                    continue  # סוגר יתום
                inner = stack[idx + 1:]
                for n, o in reversed(inner):
                    if o:
                        buf.append(f"</{n}>")
                if stack[idx][1]:
                    buf.append(f"</{stack[idx][0]}>")
                stack = stack[:idx] + inner
                for n, o in inner:
                    if o:
                        buf.append(o)
        # סוף השורה: סוגרים הכל; ממשיכים לשורה הבאה רק תג שייסגר בהמשך הפרק
        for n, o in reversed(stack):
            if o:
                buf.append(f"</{n}>")
        carry = [(n, o) for n, o in stack if closers_ahead(toks_per_line, i + 1, n)]
        out.append(clean_line("".join(buf)))
    return out


EMPTY_TAG_RE = re.compile(r"<(b|i|u|big|small|sup|sub|span|a|center)(?:\s[^<>]*)?>(\s*)</\1>")


def clean_line(s):
    prev = None
    while prev != s:
        prev = s
        s = EMPTY_TAG_RE.sub(r"\2", s)
    s = re.sub("( +)(\\d+)", r"\2\1", s)  # סמן הערת העורך צמוד למילה שלפניו
    # רווחים צמודים לתג → מחוצה לו
    while True:
        n = re.sub(r"(<(?!/|br)[^<>]+>)( +)", r"\2\1", s)
        n = re.sub(r"( +)(</[^<>]+>)", r"\2\1", n)
        if n == s:
            break
        s = n
    s = re.sub(r"^(\s*<br>)+|(<br>\s*)+$", "", s.strip())
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    return s


def norm_chars(s):
    s = s.translate(INVISIBLE).replace(" ", " ")
    return "".join(unicodedata.normalize("NFKD", c) if 0xFB1D <= ord(c) <= 0xFB4F else c for c in s)


# ---------------------------------------------------------------- תיקוני טקסט

NIKUD = "\u0591-\u05c7"
HEB = "א-ת"
# אות סופית באמצע מילה = שתי מילים שהודבקו ("קֳדָםיְיָ")
GLUED_FINAL_RE = re.compile(rf"([ךםןףץ][{NIKUD}]*)(?=[{HEB}])")
# אות סופית בודדת אחרי רווח = מילה שנחתכה ("יְרוּשָׁלַ ם", "אֱלֹהֵיהֶ ם") — רק כשהאות שלפני הרווח
# נושאת תנועה (צירה/סגול/פתח/קמץ); "אוֹת ם", "דָא ם", "כי ם" הם שם האות או "אם" שנחתכה ונשארים
SPLIT_FINAL_RE = re.compile(rf"([{HEB}][\u05b0-\u05c7]*[\u05b5-\u05b8][\u05b0-\u05c7]*) ([ךםןףץ][{NIKUD}]*)(?=[\s,.:;?!)\]<]|$)")
GERSHAYIM_RE = re.compile(rf"([{HEB}][{NIKUD}]*)''(?=[{HEB}])")
QM_RE = re.compile(rf"<QM>[{NIKUD}]*", re.I)
# ן בתחילת מילה לא מנוקדת = ו ("ןיקרא", "ןאכלו") — נמצא רק בגמרא נוחה
INITIAL_NUN_RE = re.compile(rf"(?<![{HEB}{NIKUD}'\"])ן(?=[{HEB}])")
# שגיאות מקור חד־משמעיות בגמרא נוחה: מילים שהודבקו או ו/ס שהוקלדו כאות סופית
TYPOS = {
    "העוףעולת": "העוף עולת", "ולקמןמפרש": "ולקמן מפרש", "בקידןושין": "בקידושין", "ואיןבו": "ואין בו",
    "בציםורי": "בציפורי", "ופטןר": "ופטור", "לננסיןשמונה": "לננסין שמונה", "עירןבין": "עירובין",
    "דבריםיב": "דברים יב", "קדושיםויקרא": "קדושים ויקרא", "פסוקיםיט": "פסוקים יט", "פסוקיםכז": "פסוקים כז",
    "דמתניתיןמשום": "דמתניתין משום", "בהמשךגירסת": "בהמשך גירסת", "דמיםובפרק": "דמים ובפרק",
    "וחןזר": "וחוזר", "מצןיה": "מצויה", "דףכז": "דף כז", "דףטז": "דף טז", "הנותריםעל": "הנותרים על",
    "ונסכיםלפרים": "ונסכים לפרים", "ועייןהיטב": "ועיין היטב", "תוספןת": "תוספות", "לאודןעיה": "לאודועיה",
    "הדרךמתי": "הדרך מתי", "קדשיםבטומאת": "קדשים בטומאת", "דהנךתכשיטין": "דהנך תכשיטין",
    "צפריםחטאת": "צפרים חטאת", "אומריםאין": "אומרים אין", "דבריםלג": "דברים לג", "נוןחלין": "נוחלין",
    "מםכת": "מסכת", "הדוגצאות": "הדוגמאות", "סםרא": "ספרא", "כתץוב": "כתוב", "ץיקון": "תיקון", "אםפשר": "אפשר",
}
QUOTES = "'\"״׳"

TANAKH = ("בראשית שמות ויקרא במדבר דברים יהושע שופטים שמואל מלכים ישעיה ישעיהו ירמיה ירמיהו "
          "יחזקאל הושע יואל עמוס עובדיה יונה מיכה נחום חבקוק צפניה חגי זכריה מלאכי תהלים תהילים "
          "משלי איוב רות איכה קהלת אסתר דניאל עזרא נחמיה").split()
GLUED_REF_RE = re.compile(r"\{\{(" + "|".join(sorted(set(TANAKH), key=len, reverse=True)) + r")([א-ת]{1,3})\}\}")


def fix_text(line):
    """תיקונים שחלים על טקסט השורה (לא על תגים — כל התבניות דורשות אותיות עבריות)."""
    line = QM_RE.sub("?", line)
    line = re.sub(r"<IRI>?", "", line, flags=re.I)
    line = GLUED_REF_RE.sub(r"{{\1 \2}}", line)
    # רק במילה מנוקדת: בטקסט לא מנוקד אות סופית באמצע מילה היא לרוב שגיאת הקלדה (ן במקום ו)
    line = re.sub(rf"[{HEB}{NIKUD}]+",
                  lambda m: GLUED_FINAL_RE.sub(r"\1 ", m.group()) if re.search(rf"[{NIKUD}]", m.group())
                  else m.group(), line)
    line = INITIAL_NUN_RE.sub("ו", line).replace("וחקרא", "ויקרא")
    for w, fix in TYPOS.items():
        line = line.replace(w, fix)
    line = SPLIT_FINAL_RE.sub(r"\1\2", line)
    return line


# ---------------------------------------------------------------- HTML של Word (גמרא נוחה)

WORD_COMMENT_RE = re.compile(
    r"\r(?:Yeshayahu Hollander|YH|הולנדר\s*)\r\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(.*?)(?=</span>)", re.S)
NOTE_BODY_RE = re.compile(
    r'<p><a href="#noteref-(\d+)" id="footnote-\1">\[\1\]</a>(.*?)(?=<p>|\n[~#^@!$]|\Z)', re.S)
NOTE_HEADER_RE = re.compile(r"<b>\s*הערות שוליים\s*</b>")
NOTE_MARK_RE = re.compile(r'(?:&nbsp;|\u00a0|[ \t])*<a href="#footnote-(\d+)"[^>]*?>\[\1\]</a>', re.S)
INNER_SPAN_RE = re.compile(r"<span[^<>]*>((?:[^<]|<(?!/?span\b))*)</span>")
FN_MARK = "\ue000{}\ue001"
CONTACT_RE = re.compile(r"כל המוצא שגיאה|על שם הורי נפתלי|ביאליק 27|[\w.]+@[\w.]+|geocities|כולל עיון הדף")
# הפניה להערה באנגלית שנמחקה
ENGLISH_NOTE_REF_RE = re.compile(r"\[\s*ראה הערה[^\[\]]*\[באנגלית\]\s*\]?")
JUNK_LINE_RE = re.compile(r"[_\s]{5,}|[=\s]{5,}|[{}\s]{3,}|[\W_]*FOOTNOTES[\W_]*", re.I)


def oc_text(t):
    return re.sub(r"<[^<>]*>", "", t)


def latin_count(t):
    return len(re.findall(r"[A-Za-z]", re.sub(r"<[^<>]*>", "", t)))


def hebrew_count(t):
    return len(re.findall(r"[א-ת]", re.sub(r"<[^<>]*>", "", t)))


def english_or_contact(t):
    return (is_english(t) and latin_count(t) >= 5) or bool(re.search(r"dafyomi|Kollel|@", t, re.I))


def is_english(t):
    return latin_count(t) > len(re.findall(r"[א-ת]", re.sub(r"<[^<>]*>", "", t)))


EDITOR_MARK = "{}"
EDITOR_MARK_RE = re.compile("(\\d+)")


SIGNATURE_RE = re.compile(r"^בברכה\b|הולנדר")
PUNCT_SEG_RE = re.compile(r"[\s).,;:!?\]'\"]+")


def unmatched_close_tail(t):
    """")" בסוף הטקסט שאין לו "(" פותח בתוכו."""
    depth = 0
    for ch in t:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0) if depth else -1
    return t.endswith(")") and depth == -1


def open_parens(t):
    """עומק הסוגריים הפתוחים בסוף [t]; ")" יתום לפני כן לא סוגר "(" שבא אחריו."""
    depth = 0
    for ch in t:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
    return depth


def editor_comment(m, editor_notes, before):
    """הערת Word של העורך: הכותרת (שם + חותמת זמן) נמחקת, הגוף נשמר להערה נלווית
    ובמקומו סמן; ")" שסוגר סוגריים פתוחים בפסקה שלפניה ([before]) נשאר בטקסט."""
    body = m.group(1)
    tail = re.search(r"[\s.;,?!:]*\)\s*$", body)
    keep = ""
    if tail and open_parens(before):
        keep, body = re.sub(r"\s+", "", tail.group()), body[:tail.start()]
    segs = []
    for s in body.split("\r"):
        s = s.strip()
        if not s or english_or_contact(s) or SIGNATURE_RE.search(s):
            continue
        if PUNCT_SEG_RE.fullmatch(s):
            if segs:
                segs[-1] += s  # ")" שסוגר קטע עברי שלפני האנגלית שנמחקה
            continue
        # שארית אנגלית מ־Kollel: "Yevamot 93b", "ANSWERS:", "6:19).", חותמת זמן של הערה מקוננת
        s = re.sub(r"^[^א-ת]*[A-Za-z0-9][^א-ת]*(?=[א-ת])", "", s)
        if hebrew_count(s):
            segs.append(s)
    if segs and unmatched_close_tail(" ".join(segs)):
        segs[-1] = segs[-1][:-1].rstrip()
    if hebrew_count(" ".join(segs)) < 2:
        return keep
    editor_notes.append(segs)
    return EDITOR_MARK.format(len(editor_notes) - 1) + keep


def replace_editor_comments(text, editor_notes):
    """פסקת ההקשר של כל הערה נמדדת על הטקסט אחרי החלפת ההערות שלפניה."""
    out, pos = [], 0
    for m in WORD_COMMENT_RE.finditer(text):
        out.append(text[pos:m.start()])
        done = "".join(out)
        start = max(done.rfind("\n\n"), done.rfind("<p"), len(done) - 3000, 0)
        # ")" שבא מיד אחרי ההערה כבר סוגר בעצמו את מה שנפתח לפניה
        closes = re.match(r"[\s)]*", re.sub(r"<[^<>]*>", "", text[m.end():m.end() + 200])).group()
        out.append(editor_comment(m, editor_notes, re.sub(r"<[^<>]*>", "", done[start:]) + closes))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def preprocess_word_html(text):
    """הערות Word של העורך עוברות לספר הערות נלווה, הערות הסיום הופכות להערות שוליים
    פנימיות, קטעי אנגלית שהועתקו (Kollel Iyun Hadaf) נמחקים, ו־\\r בודד הוא שבירת שורה."""
    editor_notes = []
    text = replace_editor_comments(text, editor_notes)

    titles = {m.group(1): m.group(2) for m in
              re.finditer(r'<a href="#footnote-(\d+)"[^>]*?title="([^"]*)', text)}
    bodies = {m.group(1): m.group(2) for m in NOTE_BODY_RE.finditer(text)}
    text = NOTE_BODY_RE.sub("", text)
    text = NOTE_HEADER_RE.sub("", text)
    text = re.sub(r"</?p\b[^>]*>", "", text)

    notes = []

    def mark(m):
        body = bodies.get(m.group(1)) or titles.get(m.group(1), "")
        # הערה מעורבת: הפסקאות העבריות נשארות, האנגלית/Kollel/מיילים נמחקים
        segs = [x for x in body.split("\r") if not english_or_contact(x)]
        body = re.sub(r"\s+", " ", re.sub(r"-{3,}", " ", " ".join(segs))).strip()
        if hebrew_count(body) < 2:
            return ""
        notes.append(body)
        return FN_MARK.format(len(notes) - 1)

    text = NOTE_MARK_RE.sub(mark, text)

    def english_span(m):
        """span פנימי עם חומר אנגלי ארוך: הפסקאות העבריות שבו נשארות."""
        inner = m.group(1)
        if latin_count(inner) <= 200 or not is_english(inner):
            return m.group(0)
        keep = []
        for x in re.split(r"[\r\n]", inner):
            if english_or_contact(x) or not x.strip() or re.fullmatch(r"[-_=|\s]*\)?\s*", x):
                continue  # אנגלית, או קווי הפרדה/טבלה שלה
            if keep and re.fullmatch(r"\s*[).,;:!?\]]+\s*", x):
                keep[-1] += x.strip()  # ")" שסוגר את הקטע העברי שלפני האנגלית
            else:
                keep.append(x)
        if hebrew_count("".join(keep)) < 2:
            return ""
        keep = [re.sub(r"([א-ת])\d+(?=\)|$)", r"\1", x.rstrip()) for x in keep]
        joined = "".join(keep)
        if inner.rstrip().endswith(")") and joined.count("(") > joined.count(")"):
            keep[-1] += ")"  # הסוגר נפל יחד עם האנגלית שלפניו
        return m.group(0)[:m.start(1) - m.start()] + "\n".join(keep) + "</span>"

    prev = None
    while prev != text:
        prev = text
        text = INNER_SPAN_RE.sub(english_span, text)
    text = ENGLISH_NOTE_REF_RE.sub("", text)
    text = text.replace("\r", "\n").replace("\t", " ")
    return text, notes, editor_notes


# ---------------------------------------------------------------- כותרות

BR_RE = re.compile(r"<br\s*/?>", re.I)
DAF_GMARA_RE = re.compile(r"^(?:דף\s*,?\s*)?([א-ת]{1,3})\s*[,\-]\s*([אב])$")
DAF_ZOHAR_RE = re.compile(r"^דף\s+([א-ת" + QUOTES + r"]+)\s+ע(?:''|\"|״)([אב])$")


def is_level_line(l):
    """סימן רמה + רווח; או סימן צמוד לכותרת קצרה עברית ("!א"). "## …" ו־"#4-9" הם טקסט."""
    if l[1:2] in (" ", "\t", ""):
        return True
    return len(l) <= 8 and bool(re.fullmatch(r"[א-ת'\" ]+", l[1:]))


# "(זבחים פט,א)", "[הוריות ו,ב]", "(דף ז,ב)", "דף כא,א", "טו,א"
PEREK_DAF_RE = re.compile(r"\s*[\[(](?:[א-ת]+\s+)?([א-ת]{1,3}),([אב])[\])]|\s*(?:דף\s+)?([א-ת]{1,3}),([אב])(?![א-ת])")


def rank_of(sign):
    return LEVEL_SIGNS.index(sign)


def daf(num, amud):
    return f"דף {num}{'.' if amud == 'א' else ':'}"


def heading_text(raw):
    t = re.sub(r"<[^<>]*>", "", raw)
    t = html.unescape(t.replace("&nbsp;", " "))
    t = re.sub(r"\s+", " ", t).strip().replace("''", '"')
    m = DAF_ZOHAR_RE.match(t)
    if m:
        t = daf(m.group(1).strip(QUOTES).translate(dict.fromkeys(map(ord, QUOTES))), m.group(2))
    return t


def convert(obk_path, gmara_daf_level=None):
    text, comment = read_obk(obk_path)
    conf = parse_conf(comment)
    reps = adapt_reps(parse_reps(conf.get("CosmeticsType", "")))
    new_lines_as_is = conf.get("PutNewLinesAsIs", "1").strip() != "0"

    text = text.replace("\r\n", "\n")
    notes, editor_notes = [], []
    notes_mode = "#noteref-" in text or bool(WORD_COMMENT_RE.search(text))
    if notes_mode:
        text, notes, editor_notes = preprocess_word_html(text)
    else:
        text = text.replace("\r", "\n")
    lines = [norm_chars(l) for l in text.split("\n")]
    # דילוג על שורות התצורה (& / //) עד שורת $
    start = next((i for i, l in enumerate(lines) if l.startswith("$")), None)
    if start is None:
        raise ValueError(f"{obk_path}: אין שורת $ (שם הספר)")
    title = conf.get("DisplayName", "").strip() or heading_text(lines[start][1:])
    body = [l for l in lines[start + 1:] if not l.startswith("**INDEX")]

    present = [s for s in LEVEL_SIGNS
               if any(l[:1] == s and is_level_line(l) and 0 < len(heading_text(l[1:])) <= LONG_HEADING
                      for l in body)]
    hlevel = {s: i + 2 for i, s in enumerate(present)}

    items = []  # ("h", html) | ("t", [שורות טקסט של פרק])
    hstack = []  # [(דרגת הסימן, רמת h בפועל)]
    perek_daf, inserted_daf, items_since_daf = None, None, False

    def perek_soon(i):
        return any(l[:1] and l[0] in LEVEL_SIGNS and rank_of(l[0]) < rank_of(gmara_daf_level) and is_level_line(l)
                   for l in body[i + 1:i + 7])
    section = []
    pending_marks = []  # סמני הערות עורך שנפלו בשורת כותרת עוברים לשורת הטקסט הבאה

    def flush():
        if section:
            items.append(("t", list(section) if new_lines_as_is else [" ".join(section)]))
            section.clear()

    for bi, l in enumerate(body):
        sign = l[:1]
        if sign and sign in LEVEL_SIGNS and is_level_line(l):
            pending_marks += [m.group() for m in EDITOR_MARK_RE.finditer(l)]
            l = EDITOR_MARK_RE.sub("", l)
            t = heading_text(l[1:])
            if not t:
                continue
            if sign not in hlevel or len(t) > LONG_HEADING:
                # באורייתא שורת רמה מוצגת כטקסט מודגש; פסקה שלמה אינה כותרת לתוכן העניינים
                section.append(f"<b>{fix_text(l[1:].strip())}</b>")
                continue
            flush()
            if gmara_daf_level and sign == gmara_daf_level:
                m = DAF_GMARA_RE.match(t)
                if m:
                    t = daf(m.group(1), m.group(2))
            elif gmara_daf_level and rank_of(sign) < rank_of(gmara_daf_level):
                # "פרק שני טו,א המביא גט בתרא" → "פרק שני המביא גט בתרא" + כותרת "דף טו." אחריו
                m = PEREK_DAF_RE.search(t)
                if m:
                    num, amud = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
                    perek_daf = daf(num, amud)
                t = re.sub(r"\s+", " ", PEREK_DAF_RE.sub("", t)).strip(" :")
            if gmara_daf_level and sign == gmara_daf_level:
                if not hstack and perek_soon(bi):
                    continue  # כותרת דף ממש לפני הפרק הראשון (שארית של עמוד השער)
                if inserted_daf == t and not items_since_daf:
                    continue  # הדף כבר נכתב אחרי כותרת הפרק
            # רמה = רמת הכותרת הגבוהה ממנה שקדמה לה + 1 (בלי דילוגים: "#" ישירות ל־"~" → h2, h3)
            rank = LEVEL_SIGNS.index(sign)
            while hstack and hstack[-1][0] >= rank:
                hstack.pop()
            lvl = hstack[-1][1] + 1 if hstack else 2
            hstack.append((rank, lvl))
            heading = ("h", f"<h{lvl}>{html.escape(t, quote=False)}</h{lvl}>")
            if items and items[-1] == heading:
                continue  # שורת רמה שהוכפלה במקור בלי טקסט ביניהן
            items.append(heading)
            items_since_daf = False
            if perek_daf:
                items.append(("h", f"<h{lvl + 1}>{perek_daf}</h{lvl + 1}>"))
                hstack.append((rank_of(gmara_daf_level), lvl + 1))
                inserted_daf, perek_daf = perek_daf, None
            else:
                inserted_daf = None
            continue
        l = re.sub(r"<!--ex[abc][A-P]*-->", "", l)       # קישור חיצוני: נשאר רק טקסט התצוגה
        l = re.sub(r"(\S?)<!--.*?-->(\S?)",
                   lambda m: m.group(1) + (" " if m.group(1) and m.group(2) else "") + m.group(2), l)
        l = apply_reps(fix_text(l), reps)
        # שבירת <br> היא שורה חדשה: באוצריא שורה היא יחידת התוכן (קישור, חיפוש, סימנייה)
        parts = [p for p in BR_RE.split(l) if p.strip()]
        if parts and pending_marks:
            parts[0] = "".join(pending_marks) + parts[0]
            pending_marks.clear()
        section.extend(parts)
        if parts and re.sub(r"<[^<>]*>", "", "".join(parts)).strip():
            items_since_daf = True
    flush()

    # כל שורות הטקסט מרונדרות יחד, כך שתג פתוח עובר גם מעל כותרת עד שנסגר
    flat = [l for kind, v in items if kind == "t" for l in v]
    rendered = iter(render_section(flat))
    rendered_notes = [render_section([n])[0] for n in notes]
    out = [f"<h1>{html.escape(title, quote=False)}</h1>"]
    fn_no = 0

    def fn(m):
        nonlocal fn_no
        fn_no += 1
        return (f'<sup class="footnote-marker">{fn_no}</sup>'
                f'<i class="footnote">{rendered_notes[int(m.group(1))]}</i>')

    word_html = notes_mode or bool(gmara_daf_level)
    marked = []  # (שורה, "keep" | "drop" | "cond")
    for kind, v in items:
        if kind == "h":
            marked.append((v, "keep"))
            continue
        for _ in v:
            full = re.sub("\ue000(\\d+)\ue001", fn, next(rendered))
            l = EDITOR_MARK_RE.sub("", full)
            text = html.unescape(oc_text(l))
            if not text.strip() and "<img" not in l:
                if full != l:
                    marked.append((full, "marks"))
                continue
            l = full
            status = "keep"
            if word_html:
                if ((is_english(l) and latin_count(l) >= 5) or (hebrew_count(l) == 0 and latin_count(l) >= 2)
                        or JUNK_LINE_RE.fullmatch(text) or ("|" in text and latin_count(l) >= 3)):
                    status = "drop"  # חומר Kollel Iyun Hadaf באנגלית (שאלות, טבלאות, זכויות יוצרים)
                elif CONTACT_RE.search(text):
                    status = "drop"  # הקדשה ופרטי קשר של העורך (מייל, טלפון, כתובת)
                elif gmara_daf_level and re.fullmatch(
                        r'\s*מתוך "גמרא נ[\u05b0-\u05c7]*ו[\u05b0-\u05c7]*ח[\u05b0-\u05c7]*ה"\s*', text):
                    status = "drop"  # כותרת־ראש של הקובץ המקורי
                elif hebrew_count(l) == 0:
                    status = "cond"  # קו מפריד / שלד טבלה / שארית מספרים — תלוי בשכנים
            marked.append((l, status))

    def neighbor(i, step):
        i += step
        while 0 <= i < len(marked) and marked[i][1] == "cond":
            i += step
        return marked[i][1] if 0 <= i < len(marked) else "keep"

    # שורה בלי עברית שצמודה לחומר אנגלי שנמחק היא חלק ממנו (קווי טבלה, "-----", "1:10:5)")
    orphan_marks = []  # סמני הערות עורך משורה שנמחקה — נצמדים לשורת הטקסט הקודמת
    for i, (l, st) in enumerate(marked):
        if st == "keep" or (st == "cond" and neighbor(i, -1) != "drop" and neighbor(i, 1) != "drop"):
            if orphan_marks and (len(out) == 1 or out[-1].startswith("<h")):
                l, orphan_marks = "".join(orphan_marks) + l, []
            if (re.fullmatch(r"\s*[).,;:!?\]'\"]+\s*", html.unescape(oc_text(EDITOR_MARK_RE.sub("", l))))
                    and len(out) > 1 and not out[-1].startswith("<h")):
                out[-1] += l  # ")." שנשאר לבד אחרי שהערת Word שלפניו נמחקה
            else:
                out.append(l)
        else:
            orphan_marks += [m.group() for m in EDITOR_MARK_RE.finditer(l)]
        if orphan_marks and len(out) > 1 and not out[-1].startswith("<h"):
            out[-1] += "".join(orphan_marks)
            orphan_marks = []

    # הערות העורך → ספר הערות נלווה: השורה N בו היא ההערה ה־N, והסמן בגוף מפנה אליה
    editor_lines, order = [], {}
    for n, line in enumerate(out, start=1):
        for m in EDITOR_MARK_RE.finditer(line):
            order[int(m.group(1))] = (len(order) + 1, n)
    if len(order) != len(editor_notes) or orphan_marks or pending_marks:
        raise ValueError(f"{obk_path}: {len(editor_notes) - len(order)} הערות עורך אבדו")

    def sup(m):
        return f"<sup>({gematria(order[int(m.group(1))][0])})</sup>"

    out = [EDITOR_MARK_RE.sub(sup, line) for line in out]
    for idx in sorted(order, key=lambda k: order[k][0]):
        k, n = order[idx]
        body = render_section(["<br>".join(fix_text(s) for s in editor_notes[idx])])[0]
        # אותו סמן כמו בגוף: בבניית המסד ההערה נשתלת במקום <sup>(א)</sup> שבשורה
        editor_lines.append((n, f"<sup>({gematria(k)})</sup> {body}"))
    return title, out, conf, editor_lines


GEMATRIA = [(400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"), (90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"),
            (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"), (10, "י"), (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"),
            (5, "ה"), (4, "ד"), (3, "ג"), (2, "ב"), (1, "א")]


def gematria(n):
    s = ""
    for v, ch in GEMATRIA:
        while n >= v:
            s, n = s + ch, n - v
    return s.replace("יה", "טו").replace("יו", "טז")


def write_editor_notes(out_path, editor_lines, links_dir):
    """'הערות על <ספר>.txt' ליד הספר + links/<ספר>_links.json מסוג footnotes."""
    import json
    stem = os.path.splitext(os.path.basename(out_path))[0]
    notes_title = f"הערות על {stem}"
    with open(os.path.join(os.path.dirname(out_path), notes_title + ".txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join([f"<h1>{html.escape(notes_title, quote=False)}</h1>"] + [b for _, b in editor_lines]))
    # בספר הסופי נוספת שורת מחבר אחרי ה־h1, ולכן כל שורה זזה באחת
    links = [{"line_index_1": n + 1, "line_index_2": k, "heRef_2": notes_title, "path_2": notes_title + ".txt",
              "Conection Type": "footnotes"} for k, (n, _) in enumerate(editor_lines, start=2)]
    os.makedirs(links_dir, exist_ok=True)
    with open(os.path.join(links_dir, stem + "_links.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(links, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    # python orayta_convert.py <obk> <out.txt> [--gmara] [--links-dir <links>]
    daf_level = "~" if "--gmara" in sys.argv[3:] else None
    title, out, _, editor_lines = convert(sys.argv[1], gmara_daf_level=daf_level)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    if editor_lines:
        links_dir = sys.argv[sys.argv.index("--links-dir") + 1] if "--links-dir" in sys.argv else \
            os.path.dirname(os.path.abspath(sys.argv[2]))
        write_editor_notes(sys.argv[2], editor_lines, links_dir)
