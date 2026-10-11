"""מפריד מילים מחוברות בתרגום של "חק לישראל" (אוריתא) לפי מקור תורת אמת.

בתורת אמת מילים בתרגום מופרדות ב-<j> (בכותרת: רווח רחב) ולא ברווח, ואוריתא
השמיטה אותו - כך נוצרו מילים מחוברות כמו "שְׁמַיָּאוְיָת". הסקריפט אוסף מכל כרך
את רצפי המילים המופרדים ב-<j>, ומוסיף רווח בכל מילה בספר שאותיותיה שוות
לחיבור של רצף כזה. רק רווחים נוספים; שורות ושאר התווים לא משתנים.

חיבור שהוא בעצמו מילה אמיתית (למשל "יתברך") מפוצל רק במקום שבו האותיות שסביבו
נמצאות במקור תורת אמת מופרדות (ב-<j> או ברווח) במקום החיתוך (Splitter._separate_in_te), ואחרת מדולג.
JOINS מסיר רווחים שגויים שהגיעו מתורת אמת באמצע מילה.

הרצה (מתיקיית השורש של המאגר):
    python OraytaToOtzaria/סקריפטים/split_hok_targum.py          # מתקן
    python OraytaToOtzaria/סקריפטים/split_hok_targum.py --check  # רק מדווח
"""

from __future__ import annotations

import argparse
import bisect
import collections
import functools
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TE_DIR = ROOT / "ToratEmetToOtzaria/סקריפטים/books/תורה/חק לישראל"
BOOK_DIR = ROOT / "OraytaToOtzaria/ספרים/אוצריא/לימוד יומי/חק לישראל"
VOLUMES = ("בראשית", "שמות", "ויקרא", "במדבר", "דברים")

LETTERS = "א-ת"
# ניקוד וטעמים בלבד - בלי מקף (05BE), פסק (05C0) וסוף פסוק (05C3), שמפרידים מילים.
MARKS = "֑-ׇֽֿׁׂׅׄ"
PRESENTATION = "יִ-ﭏ"
WORD = re.compile(f"[{LETTERS}{MARKS}{PRESENTATION}]+")
J_CHAIN = re.compile(f"[{LETTERS}{MARKS}]+(?:<j>[{LETTERS}{MARKS}]+)+")
COMMENT = re.compile(r"<!--.*?-->", re.S)
LETTER = re.compile(f"[{LETTERS}{PRESENTATION}]")
TE_TOKEN = re.compile(f"(<j>)|([{LETTERS}])|([{MARKS}])|.", re.S)
CONTEXT = 12
MIN_CONTEXT = 6

# <j> שגוי בתורת אמת באמצע מילה אחת (מלכא, במדברא, ואסיקו, ואמרת, מנהון, תברכינון,
# בפריע דילמא, לביל) - לא מפצלים לפיו.
DENIED = {
    ("מ", "לכא"), ("במ", "דברא"), ("ואס", "יקו"), ("ואמ", "רת"),
    ("מ", "נה"), ("נו", "ן"), ("ע", "די"),
    ("ל", "ביל"),
}

# רווחים שגויים בתרגום (מתורת אמת), באותיות בלבד: "|" רווח שנשאר, " " רווח שנמחק.
JOINS = (
    "גבר|ל ביל",  # ישעיה נג, ו "איש לדרכו"
    "ליסודא|ד מ דבחא",  # ויקרא ד, ז "יסוד מזבח"
    "סיחון|מ לכא",  # "סיחן מלך חשבון"
    "למ מ ת",  # שמות יד, יא "למות"
    "לא|תב ר כ י נון",  # במדבר כג, כה "לא תברכנו"
    "משכן|ז מנא",
    "לבית|ש מעון",  # במדבר כה, יד
    "מ עברא|לירדנא",  # "מעבר לירדן"
    "בשמיא|מ לעלא",  # דברים ד, לט "בשמים ממעל"
    "במימ רא",  # דברים: "במימרא" שנשברה כבר באוריתא
    # שברים ישנים במקור (רווח ממש, לא <j>):
    "עמ לק",  # שמות יז, טז
    "דמ צרים",  # שמות כ, ב
    "תשבעו ן",  # ויקרא כו, כו
    "וס רכיכון",  # דברים לא, כח
    "ואמ לל",  # דברים לא, כח
    "בשמ יא",  # דברים לג, כו
)


def skel(word: str) -> str:
    """האותיות בלבד, בלי ניקוד וטעמים."""
    return re.sub(f"[^{LETTERS}]", "", unicodedata.normalize("NFKD", word))


def read_te(path: Path) -> str:
    return COMMENT.sub("", path.read_bytes().decode("cp1255"))


def te_sources(volume: str, te_dir: Path = TE_DIR) -> list[Path]:
    return sorted(p for p in (te_dir / volume).glob("y_hok??.txt"))


def joined_parts(te_texts: list[str]) -> dict[str, tuple[str, ...]]:
    """חיבור-אותיות -> המילים שמרכיבות אותו, לכל תת-רצף רציף של שרשרת <j>."""
    parts: dict[str, tuple[str, ...]] = {}
    for text in te_texts:
        for m in J_CHAIN.finditer(text):
            words = [skel(w) for w in m.group().split("<j>")]
            for i in range(len(words)):
                for k in range(i + 2, len(words) + 1):
                    parts.setdefault("".join(words[i:k]), tuple(words[i:k]))
    return parts


def real_words(te_texts: list[str]) -> set[str]:
    """המילים במקורות תורת אמת כשה-<j> מתפרש כרווח."""
    found: set[str] = set()
    for text in te_texts:
        found.update(skel(w) for w in WORD.findall(text.replace("<j>", " ")))
    return found


def split_word(word: str, lengths: tuple[int, ...]) -> str:
    """מכניס רווח אחרי כל קבוצת אותיות לפי lengths, כשהניקוד נשאר על האות שלו."""
    cuts = set()
    total = 0
    for n in lengths[:-1]:
        total += n
        cuts.add(total)
    out = []
    letters = 0
    for ch in word:
        if skel(ch):
            if letters in cuts:
                out.append(" ")
            letters += 1
        out.append(ch)
    return "".join(out)


class TeIndex:
    """אותיות מקור תורת אמת ברצף אחד, והמיקומים שבהם מתחילה מילה (אחרי <j>, רווח או סימן)."""

    def __init__(self, te_texts: list[str]):
        letters: list[str] = []
        self.breaks: set[int] = set()
        after_break = True
        for text in te_texts:
            for m in TE_TOKEN.finditer(text):
                if m.group(2):
                    if after_break:
                        self.breaks.add(len(letters))
                    after_break = False
                    letters.append(m.group(2))
                elif not m.group(3):
                    after_break = True
        self.letters = "".join(letters)

    def find_all(self, needle: str) -> list[int]:
        found, i = [], self.letters.find(needle)
        while i >= 0:
            found.append(i)
            i = self.letters.find(needle, i + 1)
        return found


def _join_pattern(spec: str) -> tuple[re.Pattern, list[bool]]:
    groups = [g.split(" ") for g in spec.split("|")]
    words = [w for g in groups for w in g]
    keep = [i == len(g) - 1 for g in groups for i in range(len(g))][:-1]
    word_re = ["".join(f"{re.escape(ch)}[{MARKS}]*" for ch in w) for w in words]
    body = "( +)".join(word_re)
    return re.compile(f"(?<![{LETTERS}{MARKS}]){body}(?![{LETTERS}{MARKS}])"), keep


def apply_joins(line: str, specs: tuple[str, ...] = JOINS) -> tuple[str, int]:
    """מסיר את הרווחים שמסומנים ב-specs; מחזיר את השורה ומספר הרווחים שנמחקו."""
    removed = 0
    for spec in specs:
        pattern, keep = _join_pattern(spec)

        def fix(m: re.Match) -> str:
            nonlocal removed
            out, pos = [], m.start()
            for g, kept in enumerate(keep, 1):
                out.append(m.string[pos:m.start(g)])
                if kept:
                    out.append(m.group(g))
                else:
                    removed += len(m.group(g))
                pos = m.end(g)
            out.append(m.string[pos:m.end()])
            return "".join(out)

        line = pattern.sub(fix, line)
    return line, removed


class Splitter:
    def __init__(self, parts: dict[str, tuple[str, ...]], real: set[str], te: TeIndex | None = None):
        self.parts = {k: v for k, v in parts.items() if k not in real and v not in DENIED}
        self.real = real
        self.ambiguous = {k: v for k, v in parts.items() if k in real}
        self.te = te
        self.added = 0
        self.removed = 0
        self.resolved: collections.Counter[tuple[str, ...]] = collections.Counter()
        self.skipped: collections.Counter[tuple[str, ...]] = collections.Counter()

    def _separate_in_te(self, flat: str, li: int, key: str, pieces: tuple[str, ...]) -> bool:
        """האם כל מופע של המילה עם האותיות שסביבה במקור תורת אמת מופרד (<j> או רווח) במקום החיתוך."""
        if self.te is None or pieces in DENIED:
            return False
        before = flat[max(0, li - CONTEXT):li]
        after = flat[li + len(key):li + len(key) + CONTEXT]
        found = set()
        if len(before) >= MIN_CONTEXT:
            found.update(p + len(before) for p in self.te.find_all(before + key))
        if len(after) >= MIN_CONTEXT:
            found.update(self.te.find_all(key + after))
        cuts = [sum(len(p) for p in pieces[:i]) for i in range(1, len(pieces))]
        return bool(found) and all(q + c in self.te.breaks for q in found for c in cuts)

    def _fragment(self, words: list[re.Match], i: int) -> bool:
        """האם המילה היא שבר של מילה שכבר שבורה (יחד עם שכנתה היא מילה בתורת אמת) - לא מפצלים אותה שוב."""
        key = skel(words[i].group())
        prev = words[i - 1] if i and words[i - 1].end() + 1 == words[i].start() else None
        nxt = words[i + 1] if i + 1 < len(words) and words[i].end() + 1 == words[i + 1].start() else None
        return bool(
            prev and prev.string[prev.end()] == " " and skel(prev.group()) + key in self.real
            or nxt and nxt.string[words[i].end()] == " " and key + skel(nxt.group()) in self.real)

    def line(self, line: str) -> str:
        line, removed = apply_joins(line)
        self.removed += removed
        starts = [m.start() for m in LETTER.finditer(line)]
        flat = "".join(line[i] for i in starts)

        words = list(WORD.finditer(line))
        index = {m.start(): i for i, m in enumerate(words)}

        def replace(m: re.Match) -> str:
            word = m.group()
            key = skel(word)
            if self._fragment(words, index[m.start()]):
                return word
            pieces = self.parts.get(key)
            if pieces is None and key in self.ambiguous:
                if self._separate_in_te(flat, bisect.bisect_left(starts, m.start()), key, self.ambiguous[key]):
                    pieces = self.ambiguous[key]
                    self.resolved[pieces] += 1
                else:
                    self.skipped[self.ambiguous[key]] += 1
            if pieces is None:
                return word
            self.added += len(pieces) - 1
            return split_word(word, tuple(len(p) for p in pieces))

        line = WORD.sub(replace, line)
        # שוב אחרי הפיצול: מילה מחוברת לשכנתה מתפצלת לפי <j> שגוי בתורת אמת ורק אז JOINS תופס.
        line, removed = apply_joins(line)
        self.removed += removed
        return line


@functools.lru_cache(maxsize=None)
def _volume_data(volume: str, te_dir: Path) -> tuple[dict, set, TeIndex]:
    texts = [read_te(p) for p in te_sources(volume, te_dir)]
    if not texts:
        raise FileNotFoundError(f"אין מקור תורת אמת עבור {volume} ב-{te_dir}")
    all_texts = [read_te(p) for v in VOLUMES for p in te_sources(v, te_dir)]
    return joined_parts(texts), real_words(all_texts), TeIndex(texts)


def splitter_for(volume: str, te_dir: Path = TE_DIR) -> Splitter:
    return Splitter(*_volume_data(volume, te_dir))


def same_but_spaces(old: str, new: str) -> bool:
    return old.count("\n") == new.count("\n") and old.replace(" ", "") == new.replace(" ", "")


def process(path: Path, splitter: Splitter, write: bool) -> None:
    old = path.read_text(encoding="utf-8")
    new = "\n".join(splitter.line(line) for line in old.split("\n"))
    if not same_but_spaces(old, new):
        raise AssertionError(f"{path}: שינוי שאינו הוספת רווחים")
    if write and new != old:
        path.write_text(new, encoding="utf-8", newline="")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="לא לכתוב, רק לדווח")
    ap.add_argument("--te-dir", type=Path, default=TE_DIR)
    ap.add_argument("files", nargs="*", type=Path,
                    help="קבצים לתיקון (ברירת מחדל: חמשת כרכי אוריתא); שם הכרך נלקח מסוף שם הקובץ")
    args = ap.parse_args(argv)
    files = args.files or [BOOK_DIR / f"חק לישראל - {v}.txt" for v in VOLUMES]
    for path in files:
        volume = next((v for v in VOLUMES if path.stem.endswith(v) or path.parent.name == v), None)
        if volume is None:
            raise SystemExit(f"{path}: לא זוהה כרך")
        sp = splitter_for(volume, args.te_dir)
        process(path, sp, write=not args.check)
        print(f"{path.name}: נוספו {sp.added} רווחים, נמחקו {sp.removed}, "
              f"דו-משמעיים: פוצלו {sum(sp.resolved.values())}, דולגו {sum(sp.skipped.values())}")
        for pieces, n in sorted(sp.resolved.items()):
            print(f"  פוצל: {' '.join(pieces)} ({n})")
        for pieces, n in sorted(sp.skipped.items()):
            print(f"  דולג: {' '.join(pieces)} ({n})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
