#!/usr/bin/env python3
"""ייבוא רציף מספריית דיקטה — מקור האמת הוא קובץ המצב `dicta_state.json`.

    python3 dicta_sync.py detect  [--books-json F] [--no-head] [--max-books N] --out plan.json
    python3 dicta_sync.py import  --plan plan.json [--dry-run DIR] [--no-promote] [--claim-cmd CMD]
    python3 dicta_sync.py reconcile            # ספר שאדם העביר מ־"ערוך/ספרים/לא ממויין" אל "אוצריא/" → מרשמים
    python3 dicta_sync.py sort --accept FILENAME...|--all   # git mv למיקום המוצע + מרשמים
    python3 dicta_sync.py links-guard PATH...  # אילו מהקבצים משתתפים בקישורים ידניים
    python3 dicta_sync.py bootstrap --zip-cache DIR [--mapping book2files.json] [--seforim-db DB]
    python3 dicta_sync.py report

זהות ספר = `fileName` של דיקטה (לא displayName: רק 293 מ־737 ספרים ערוכים שמרו אותו).
שינוי מזוהה ב־HEAD בלבד: ה־ETag של השרת (S3) הוא ה־MD5 של ה־zip.

יעד לכל ספר (DESIGN §10):
| שער האיכות | מיקום | יעד |
| --- | --- | --- |
| עובר | בטוח (דרג A) | DictaToOtzaria/ערוך/ספרים/אוצריא/<נתיב> — נארז, + מרשמים |
| עובר | לא בטוח | DictaToOtzaria/ערוך/ספרים/לא ממויין/<קטגוריה של דיקטה>/ — לא נארז, בלי מרשמים |
| נכשל | בטוח | DictaToOtzaria/לא ערוך/ספרים/אוצריא/<נתיב> |
| נכשל | לא בטוח | DictaToOtzaria/לא ערוך/ספרים/אוצריא/לא ממויין/<קטגוריה>/ |
שם זהה לספר ספריא/נארז: חפיפה ≥50% → extraBooks/דיקטה (לא נארז); בלי חפיפה → לא ערוך + needs-human.
ספר ערוך קיים לעולם אינו נדרס (עמודים חדשים מדווחים בלבד). ספר גולמי שהשתנה — המרה מחדש
והעברת התיקונים שנעשו בו ב־git (dicta_replay).
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, ".github", "scripts"))
from book_info_writer import plan_registration, apply_registration
from validate_fordb_book_names import db_title as normalize_book_title

import dicta_convert as DC  # noqa: E402
import dicta_fp  # noqa: E402
import dicta_gate  # noqa: E402
import dicta_place  # noqa: E402
import dicta_replay  # noqa: E402

BOOKS_JSON_URL = ("https://raw.githubusercontent.com/Dicta-Israel-Center-for-Text-Analysis/"
                  "Dicta-Library-Download/refs/heads/main/books.json")
STATE_PATH = os.path.join(HERE, "dicta_state.json")
PAGES_PATH = os.path.join(HERE, "dicta_pages.json")
TABLE_PATH = os.path.join(HERE, "dicta_placement_table.json")
SEFARIA_FP_PATH = os.path.join(HERE, "sefaria_fp.dat")          # עותק מחויב: טביעות ספרי ספריא מ־seforim.db
# אינדקס הספרייה משתנה עם כל עדכון ספרים — לא מחויב; נשמר במטמון (ב־CI: actions/cache).
LIBRARY_FP_DEFAULT = os.path.join(os.environ.get("DICTA_FP_CACHE") or os.path.expanduser("~/.cache/otzaria-dicta"),
                                  "library_fp.dat")

ERUKH = "DictaToOtzaria/ערוך/ספרים/אוצריא"
ERUKH_UNSORTED = "DictaToOtzaria/ערוך/ספרים/לא ממויין"
RAW = "DictaToOtzaria/לא ערוך/ספרים/אוצריא"
RAW_UNSORTED = RAW + "/לא ממויין"
EXTRA = "extraBooks/דיקטה"
SEFARIA_COPIES = ("extraBooks/SefariaToOtzria/", "sefariaToOtzaria/")
SEFARIA_TITLES = ".github/data/sefaria_he_titles.txt"

# סטטוסים במצב
EDITED, EDITED_UNSORTED, RAW_S = "edited", "edited-unsorted", "raw"
DUP_SEF, DUP_PKG, EXTRA_ONLY = "dup-sefaria", "dup-packaged", "extra-only"
PARTIAL, ABSENT, EMPTY, NEEDS_HUMAN, REMOVED = "partial", "absent", "empty", "needs-human", "removed-upstream"
IMPORTABLE = {ABSENT, PARTIAL, EMPTY}

DUP_THRESHOLD = 0.5
HTTP_RETRIES = 4
HTTP_DELAY = 0.5


# ---------------------------------------------------------------------------
# כלים כלליים
# ---------------------------------------------------------------------------

def read_text(path: str, encoding: str = "utf-8") -> str:
    with open(path, encoding=encoding, errors="replace") as f:
        return f.read()


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_atomic(path: str, data, *, binary: bool = False) -> None:
    """כתיבה לקובץ זמני באותה תיקייה ואז os.replace — קובץ חצי־כתוב לעולם לא נשאר."""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8", "newline": ""})) as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def today() -> str:
    return _dt.date.today().isoformat()


def sanitize_filename(name: str) -> str:
    """שם הקובץ מתוך displayName (כמו שעשה all in one.py ההיסטורי)."""
    s = (name or "").replace("\u201c", '"').replace("\u201d", '"').replace("\u05f4", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")  # גרש מסולסל → ' (נשמר כמו ב־all in one ההיסטורי)
    s = re.sub('[\\\\/:*"?<>|\u200e\u200f\u202a-\u202e]', "", s).replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def title_key(name: str) -> str:
    """מפתח השוואת שמות: sanitize_title של הוולידטור (ניקוד, גרשיים, רווחים)."""
    s = re.sub("[֑-ׇ]", "", name or "")
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace("`", "׳")
    s = re.sub('[\\\\/:*"״?<>|]', "", s).replace("_", " ").replace("''", "").replace("'", "")
    s = s.replace("׳", "")
    return re.sub(r"[ \t\n\x0b\f\r]+", " ", s).strip()


def run_git(*args, check=True, binary=False):
    r = subprocess.run(["git", "-c", "core.quotepath=off", "-C", REPO, *args], capture_output=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace')[:300]}")
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def repo_files() -> list[str]:
    """הקבצים במאגר: ה־index (כולל sparse) + חדשים לא־עקובים, בלי מה שנמחק בעץ העבודה."""
    cached = set(run_git("ls-files", "-z").split("\0"))
    others = set(run_git("ls-files", "-z", "--others", "--exclude-standard").split("\0"))
    deleted = set(run_git("ls-files", "-z", "--deleted").split("\0"))
    return sorted(p for p in (cached | others) - deleted if p)


def packaged_roots() -> tuple[str, ...]:
    sys.path.insert(0, REPO)
    import manual_links_packaging as mlp  # noqa: E402
    return tuple(r.rstrip("/") + "/" for r in mlp.BOOK_ROOTS)


def is_packaged(path: str, roots=None) -> bool:
    return any(path.startswith(r) for r in (roots or packaged_roots()))


def http(url: str, *, head=False, retries=HTTP_RETRIES, delay=HTTP_DELAY) -> tuple[bytes, str]:
    """curl (עובד גם כשלפייתון אין תעודות שורש). מחזיר (גוף, כותרות)."""
    last = ""
    for attempt in range(retries):
        with tempfile.NamedTemporaryFile(delete=False) as hf:
            hpath = hf.name
        cmd = ["curl", "-sfL", "--max-time", "300", "-D", hpath]
        cmd += ["-I"] if head else []
        cmd += [url]
        r = subprocess.run(cmd, capture_output=True)
        headers = read_text(hpath, "latin-1")
        os.unlink(hpath)
        if r.returncode == 0:
            time.sleep(delay)
            return r.stdout, headers
        last = f"curl rc={r.returncode}"
        time.sleep(delay * (2 ** attempt) + 1)
    raise OSError(f"{url}: {last}")


def etag_of(headers: str) -> str | None:
    m = re.findall(r'(?im)^etag:\s*"?([0-9a-f]+)', headers)
    return m[-1] if m else None


def pages_json_url(ocr_url: str) -> str:
    return ocr_url.rsplit("/", 1)[0] + "/pages.json"


def page_no(name: str) -> int | None:
    m = re.search(r"-(\d+)(?:__ocr_data)?\.html?$", name)
    return int(m.group(1)) if m else None


def ranges(nums) -> list:
    out = []
    for n in sorted(nums):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [a if a == b else f"{a}-{b}" for a, b in out]


def expand(rs) -> set[int]:
    s = set()
    for r in rs:
        if isinstance(r, int):
            s.add(r)
        else:
            a, b = r.split("-")
            s.update(range(int(a), int(b) + 1))
    return s


def zip_signature(data: bytes) -> tuple[dict, dict]:
    """(remote-record, {page: letters-hash}) של zip של דיקטה."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    pages = {}
    for n in zf.namelist():
        if n.lower().endswith((".html", ".htm")):
            pn = page_no(n)
            if pn is not None:
                pages[pn] = dicta_fp.letters_hash(zf.read(n).decode("utf-8", "replace"))
    sig = hashlib.sha1("".join(pages[k] for k in sorted(pages)).encode()).hexdigest()[:16]
    return ({"zip_md5": hashlib.md5(data).hexdigest(), "zip_bytes": len(data), "n_pages": len(pages),
             "pages": ranges(pages), "text_sig": sig}, pages)


# ---------------------------------------------------------------------------
# zip קטוע: השלמת דפים חסרים מקובצי הדפים הבודדים
# ---------------------------------------------------------------------------
# ב־16 ספרים (QA, 2026-09-30) ה־zip המלא של דיקטה חסר דפים לעומת pages.json (למשל
# darkheteshuvah2: דף 1 מתוך 514; maharamlublin / chidusheiharadad: zip ריק של 22 בתים).
# כל דף זמין לחוד: files.dicta.org.il/library-1-0/<book>/<page>.zip (JSON).

import html as _html  # noqa: E402

def page_json_to_html(d):
    """דף JSON של דיקטה (files.dicta.org.il/library-1-0/<book>/<page>.zip) → HTML בפורמט ה־zip המלא.
    נבדק על 21 דפים שקיימים בשני המקורות: הטקסט זהה בכולם; ב־10 גבולות סימון (הדגשה/flagged בתוך
    מילה, רווח מודגש) שונים במעט — אינו משפיע על המילים."""
    toks = d.get("tokens", [])
    pending = ""  # פיסוק שנצמד למילה הבאה
    def bold(t): return any(x.get("bold") for x in (t.get("display") or []))
    def head(t): return any(x.get("heading") for x in (t.get("display") or []))
    items = []  # ("w", text, cls) / ("s", text, cls)
    for i, t in enumerate(toks):
        s = t.get("str", "")
        if t.get("sep") or not t.get("display"):
            m = re.match(r"^(\S*)(\s*)(.*?)(\S*)$", s, re.S)
            lead, sp, mid, tail = m.group(1), m.group(2), m.group(3), m.group(4)
            if not sp and not mid:  # אין רווח: כל הטקסט נצמד למילה הקודמת
                lead, tail = s, ""
            if lead:
                if items and items[-1][0] == "w": items[-1][1] += lead
                else: items.append(["s", lead, []])
            if sp or mid:
                p = next((toks[j] for j in range(i - 1, -1, -1) if not toks[j].get("sep")), None)
                n = next((toks[j] for j in range(i + 1, len(toks)) if not toks[j].get("sep")), None)
                cls = []
                if not mid and p and n and bold(p) and bold(n) and not n.get("markedParagraph"): cls.append("bold")
                if not mid and p and n and head(p) and head(n): cls.append("heading")
                items.append(["s", sp + mid, cls])
            pending += tail
            continue
        extra = []
        if t.get("markedParagraph"): extra.append("marked-paragraph")
        if t.get("flagged"): extra.append("flagged")
        if t.get("edited") or t.get("userTagged"): extra.append("edited")
        cls = (["bold"] if bold(t) else []) + (["heading"] if head(t) else []) + extra
        items.append(["w", pending + s, cls])
        pending = ""
    if pending: items.append(["s", pending, []])
    out = ["<html><head><meta charset='utf-8'></head><body dir='rtl'>"]
    for _k, text, cls in items:
        a = f' class="{" ".join(cls)}"' if cls else ""
        out.append(f"<span{a}>{_html.escape(text, quote=False)}</span>")
    out.append("</body></html>")
    return "".join(out)


def page_stem(name: str) -> str:
    return re.sub(r"(__ocr_data)?\.(zip|json|html?)$", "", name.rsplit("/", 1)[-1])


def complete_zip(data: bytes, order: list[str] | None, base_url: str, fetch=None) -> tuple[bytes, dict]:
    """מחזיר (zip שלם, info). info: expected, missing (שחסרו ב־zip), fetched, failed.
    אם אין pages.json — מחזיר את ה־zip כמו שהוא."""
    fetch = fetch or (lambda url: http(url)[0])
    zf = zipfile.ZipFile(io.BytesIO(data)) if data[:2] == b"PK" and len(data) > 22 else None
    have = {}
    if zf:
        for n in zf.namelist():
            if n.lower().endswith((".html", ".htm")):
                have[page_stem(n)] = zf.read(n)
    info = {"expected": len(order) if order else None, "missing": [], "fetched": [], "failed": []}
    if not order:
        return data, info
    want = [page_stem(p) for p in order]
    info["missing"] = [s for s in want if s not in have]
    for s in info["missing"]:
        try:
            raw = fetch(f"{base_url}/{s}.zip")
            pz = zipfile.ZipFile(io.BytesIO(raw))
            d = json.loads(pz.read(pz.namelist()[0]))
            have[s] = page_json_to_html(d).encode("utf-8")
            info["fetched"].append(s)
        except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as e:
            info["failed"].append(s)
            log(f"page {s}: {e}")
    if not info["fetched"]:
        return data, info
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for s, h in have.items():
            out.writestr(f"{s}__ocr_data.html", h)
    return buf.getvalue(), info


# ---------------------------------------------------------------------------
# קובץ המצב
# ---------------------------------------------------------------------------

DICTA_FIELDS = ("displayName", "author", "category", "subcategory", "printYear", "printLocation", "OCRDataURL")


def load_state(path=STATE_PATH) -> dict:
    if not os.path.exists(path):
        return {"schema": 1, "books_json": {}, "books": {}, "dicta_changes": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(st: dict, path=STATE_PATH) -> None:
    write_atomic(path, json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def load_pages(path=PAGES_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_pages(pages: dict, path=PAGES_PATH) -> None:
    """שורה לכל ספר — diff קריא, קובץ קטן (~3MB)."""
    items = sorted(pages.items())
    write_atomic(path, "{\n" + ",\n".join(json.dumps(k) + ":" + json.dumps({str(p): h for p, h in sorted(v.items(), key=lambda x: int(x[0]))},
                                                                         separators=(",", ":")) for k, v in items) + "\n}\n")


def dicta_record(book: dict) -> dict:
    return {k: book.get(k) for k in DICTA_FIELDS}


def repo_entry(status, **files) -> dict:
    e = {"status": status}
    for k in ("edited", "unsorted", "raw", "extra", "dup"):
        e[k] = sorted(set(files.get(k) or []))
    for k in ("reason", "suggested"):
        if files.get(k):
            e[k] = files[k]
    return e


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------

def diff_books(st: dict, books: list[dict]) -> dict:
    """מה השתנה ב־books.json מול המצב (לפי fileName). בלי רשת."""
    by = {}
    dups = []
    for b in books:
        fn = b.get("fileName")
        if not fn:
            continue
        if fn in by:
            dups.append(fn)
        by[fn] = b
    known = st["books"]
    new = sorted(fn for fn in by if fn not in known)
    removed = sorted(fn for fn, v in known.items() if fn not in by and v["repo"]["status"] != REMOVED
                     and not v["repo"].get("removed_upstream"))
    changes = []
    for fn in sorted(set(by) & set(known)):
        old = known[fn]["dicta"]
        cur = dicta_record(by[fn])
        for k in DICTA_FIELDS:
            if (old.get(k) or "") != (cur.get(k) or ""):
                changes.append({"fileName": fn, "field": k, "old": old.get(k), "new": cur.get(k)})
    return {"by": by, "new": new, "removed": removed, "changes": changes, "duplicates": dups}


MAX_REMOVED_SHARE = 0.05  # יותר מזה נעלמו ב־books.json → כנראה שינוי סכימה/קובץ שבור, לא הסרה אמיתית


def check_books_json(books, known: int) -> list[str]:
    """בעיות סכימה ב־books.json של דיקטה (רשימה ריקה = תקין)."""
    if not isinstance(books, list):
        return ["books.json is not a list"]
    probs = []
    if known and len(books) < 0.5 * known:
        probs.append(f"books.json has {len(books)} books, the state {known}")
    bad = [b for b in books if not (isinstance(b, dict) and b.get("fileName") and b.get("OCRDataURL"))]
    if bad:
        probs.append(f"{len(bad)} records without fileName/OCRDataURL")
    return probs


def cmd_detect(a) -> int:
    st = load_state()
    if a.books_json:
        raw = read_bytes(a.books_json)
    else:
        raw, _ = http(BOOKS_JSON_URL)
    books = json.loads(raw)
    probs = check_books_json(books, len(st["books"]))
    if probs:
        log("ABORT: " + "; ".join(probs))
        return 2
    d = diff_books(st, books)
    if len(d["removed"]) > max(5, MAX_REMOVED_SHARE * len(st["books"])):
        log(f"ABORT: {len(d['removed'])} books vanished from books.json — refusing to mark them removed")
        return 2
    items = []
    for fn in d["new"]:
        items.append({"fileName": fn, "action": "import", "why": "new in books.json"})
    for fn, v in sorted(st["books"].items()):
        if fn in d["by"] and v["repo"]["status"] in IMPORTABLE and not a.skip_missing:
            items.append({"fileName": fn, "action": "import", "why": f"status {v['repo']['status']}"})
    for fn in d["removed"]:
        items.append({"fileName": fn, "action": "mark-removed", "why": "not in books.json"})
    url_changed = {c["fileName"] for c in d["changes"] if c["field"] == "OCRDataURL"}
    for fn, v in sorted(st["books"].items()):
        if fn in d["by"] and v["repo"]["status"] == RAW_S and "import" in v["repo"] \
                and v["repo"]["import"].get("zip_md5") != v["remote"].get("zip_md5"):
            mp = v["repo"]["import"].get("missing_pages")
            items.append({"fileName": fn, "action": "reconvert",
                          "why": "raw file behind the zip" + (f" (pages {', '.join(map(str, mp))} never imported)" if mp else "")})
    if not a.no_head:
        import concurrent.futures as cf

        def head(fn):
            try:
                _, h = http(d["by"][fn]["OCRDataURL"], head=True, delay=0.1)
                return fn, etag_of(h)
            except OSError as e:
                return fn, "ERR " + str(e)
        todo = [fn for fn in sorted(set(d["by"]) & set(st["books"]))
                if st["books"][fn]["repo"]["status"] not in IMPORTABLE | {REMOVED}
                and not st["books"][fn]["repo"].get("pending_pr")]
        with cf.ThreadPoolExecutor(4) as ex:
            for fn, et in ex.map(head, todo):
                if et is None or et.startswith("ERR"):
                    log(f"HEAD {fn}: {et}")
                    continue
                if (et != st["books"][fn]["remote"].get("zip_md5") or fn in url_changed) \
                        and not any(i["fileName"] == fn for i in items):
                    status = st["books"][fn]["repo"]["status"]
                    act = "reconvert" if status == RAW_S else "report-changed"
                    items.append({"fileName": fn, "action": act, "why": f"zip changed ({status})"})
    if a.check_pages:
        import concurrent.futures as cf

        def pages_of(fn):
            try:
                pj, _ = http(pages_json_url(d["by"][fn]["OCRDataURL"]), delay=0.1)
                return fn, [page_stem(p["fileName"]) for p in json.loads(pj)]
            except (OSError, ValueError, KeyError, TypeError) as e:
                return fn, "ERR " + str(e)
        todo = [fn for fn in sorted(set(d["by"]) & set(st["books"])) if st["books"][fn]["repo"]["status"] != REMOVED]
        planned = {i["fileName"] for i in items}
        with cf.ThreadPoolExecutor(4) as ex:
            for fn, stems in ex.map(pages_of, todo):
                if isinstance(stems, str):
                    log(f"pages.json {fn}: {stems}")
                    continue
                want = {page_no(s + ".html") for s in stems} - {None}
                have = expand(st["books"][fn]["remote"].get("pages", []))
                if not want - have or fn in planned:
                    continue
                status = st["books"][fn]["repo"]["status"]
                if st["books"][fn]["repo"].get("pending_pr"):
                    continue
                if status in (EDITED, EDITED_UNSORTED) and \
                        st["books"][fn]["repo"].get("reported_missing_pages") == ranges(want - have):
                    continue  # כבר דווח, לא השתנה
                why = f"zip lacks {len(want - have)} of {len(want)} pages listed in pages.json"
                act = ("reconvert" if status == RAW_S else "import" if status in IMPORTABLE | {PARTIAL, NEEDS_HUMAN}
                       else "report-edited-missing-pages" if status in (EDITED, EDITED_UNSORTED) else "report-changed")
                if act == "import" and status == NEEDS_HUMAN:
                    act = "reconvert"
                items.append({"fileName": fn, "action": act, "why": f"{why} ({status})",
                              "missing_pages": ranges(want - have)})
    downloads = [i for i in items if i["action"] in ("import", "reconvert")]
    if a.max_books is not None and len(downloads) > a.max_books:
        keep = {id(i) for i in downloads[: a.max_books]}
        items = [i for i in items if i["action"] not in ("import", "reconvert") or id(i) in keep]
        log(f"capped to {a.max_books} downloads (of {len(downloads)})")
    plan = {"created": today(), "books_json_sha256": hashlib.sha256(raw).hexdigest(),
            "items": items, "changes": d["changes"], "duplicates": d["duplicates"],
            "books": {i["fileName"]: d["by"].get(i["fileName"]) for i in items}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    c = collections.Counter(i["action"] for i in items)
    log(f"plan: {dict(c)}; metadata changes: {len(d['changes'])}")
    return 0


# ---------------------------------------------------------------------------
# התנגשויות שם, כפילויות, קישורים
# ---------------------------------------------------------------------------

class RepoIndex:
    """שמות, נתיבים וקישורים — פעם אחת לריצה."""

    def __init__(self, files=None):
        self.files = files if files is not None else repo_files()
        self.file_set = set(self.files)
        self.roots = packaged_roots()
        self.packaged = [p for p in self.files if p.endswith(".txt") and is_packaged(p, self.roots)]
        self.by_key = collections.defaultdict(list)
        for p in self.files:
            if p.endswith(".txt"):
                self.by_key[title_key(os.path.basename(p)[:-4])].append(p)
        self.pkg_keys = {title_key(os.path.basename(p)[:-4]) for p in self.packaged}
        self.sefaria_keys: set[str] = set()
        tp = os.path.join(REPO, SEFARIA_TITLES)
        if os.path.exists(tp):
            for ln in read_text(tp).splitlines():
                if ln.strip() and not ln.startswith("#"):
                    self.sefaria_keys.add(title_key(ln.strip()))
        self.links_src, self.links_tgt = links_index()

    def collisions(self, title: str) -> dict:
        k = title_key(title)
        cands = [p for p in self.by_key.get(k, [])
                 if is_packaged(p, self.roots) or p.startswith(SEFARIA_COPIES)]
        return {"sefaria": k in self.sefaria_keys, "packaged": k in self.pkg_keys, "candidates": cands}


def read_repo_text(path: str) -> str | None:
    full = os.path.join(REPO, path)
    if os.path.exists(full):
        return read_text(full)
    try:  # sparse / blobless: git מושך את ה־blob לפי דרישה
        return run_git("show", f"HEAD:{path}")
    except RuntimeError:
        return None


def links_index() -> tuple[set, set]:
    """(שמות ספרים שהם מקור של קובץ קישורים, שמות ספרים שהם יעד path_2) בשורשי הקישורים הקיימים."""
    cfg = read_json(os.path.join(REPO, "manual_links_sync.json"))
    src, tgt = set(), set()
    for r in cfg["links_roots"]:
        d = os.path.join(REPO, r["path"])
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith("_links.json"):
                continue
            src.add(fn[: -len("_links.json")])
            try:
                for rec in read_json(os.path.join(d, fn)):
                    p = rec.get("path_2") or ""
                    if p:
                        tgt.add(p[:-4] if p.endswith(".txt") else p)
            except (ValueError, OSError):
                continue
    return src, tgt


def links_guard(paths: list[str], idx: RepoIndex | None = None) -> list[dict]:
    """לכל נתיב: האם שם הקובץ שלו משתתף בקישורים ידניים, ואם כן — אסור לשנות בו מספור שורות."""
    src, tgt = (idx.links_src, idx.links_tgt) if idx else links_index()
    out = []
    for p in paths:
        b = os.path.basename(p)[:-4] if p.endswith(".txt") else os.path.basename(p)
        out.append({"path": p, "links_source": b in src, "links_target": b in tgt,
                    "packaged": is_packaged(p)})
    return out


def dup_check(text: str, coll: dict) -> tuple[str | None, str, str | None]:
    """(סטטוס כפילות או None, הסבר, הנתיב החופף). חפיפה ≥50% מול מועמד באותו שם → כפילות;
    מועמד שהוא ספר דיקטה ערוך → EDITED (הספר כבר עובד, לא כותבים כלום)."""
    fp = dicta_fp.fingerprint(text)
    best = (0.0, None)
    for p in coll["candidates"]:
        t = read_repo_text(p)
        if t is None:
            continue
        cov = dicta_fp.coverage(fp, dicta_fp.fingerprint(t))
        best = max(best, (cov, p), key=lambda x: x[0])
    if best[1] and best[0] >= DUP_THRESHOLD:
        kind = (EDITED if best[1].startswith(ERUKH + "/") else
                DUP_SEF if best[1].startswith(SEFARIA_COPIES) else DUP_PKG)
        return kind, f"same title, {best[0]:.0%} of the text is in {best[1]}", best[1]
    if coll["sefaria"] or coll["packaged"]:
        where = "Sefaria" if coll["sefaria"] else "a packaged book"
        cov = f"{best[0]:.0%} overlap with {best[1]}" if best[1] else "no local copy to compare"
        return NEEDS_HUMAN, f"same title as {where}; {cov}", best[1]
    return None, "", None


# ---------------------------------------------------------------------------
# כפילות תוכן מול כל הספרייה (גם בשם אחר)
# ---------------------------------------------------------------------------

def packaged_blobs(roots=None) -> dict[str, str]:
    """{נתיב: blob sha} של כל קובצי ה־.txt הנארזים ב־HEAD (ls-tree — בלי להוריד תוכן)."""
    roots = roots or packaged_roots()
    out = {}
    raw = run_git("ls-tree", "-r", "-z", "HEAD", "--", *[r.rstrip("/") for r in roots])
    for rec in raw.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        if path.endswith(".txt"):
            out[path] = meta.split()[2]
    return out


def prefetch_blobs(shas: list[str]) -> None:
    """ב־partial clone (blob:none): משיכת ה־blobs החסרים במנות, במקום בקשה לכל blob. בלי partial clone — כלום."""
    if not shas or run_git("config", "--get", "remote.origin.promisor", check=False).strip() != "true":
        return
    for k in range(0, len(shas), 500):
        r = subprocess.run(["git", "-C", REPO, "-c", "fetch.negotiationAlgorithm=noop", "fetch", "-q", "--no-tags",
                            "--no-write-fetch-head", "--filter=blob:none", "origin", *shas[k:k + 500]],
                           capture_output=True)
        if r.returncode:
            log(f"batch prefetch failed ({r.stderr.decode('utf-8', 'replace')[:120]}); falling back to lazy fetch")
            return


def _cat_blobs(shas: list[str]) -> dict[str, str]:
    """תוכן blobs דרך תהליך git cat-file אחד (ב־partial clone ה־blob נמשך לפי דרישה)."""
    if not shas:
        return {}
    p = subprocess.Popen(["git", "-C", REPO, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out = {}
    for s in shas:
        p.stdin.write((s + "\n").encode())
        p.stdin.flush()
        head = p.stdout.readline().split()
        if len(head) < 3 or head[1] != b"blob":
            continue
        data = p.stdout.read(int(head[2]))
        p.stdout.read(1)
        out[s] = data.decode("utf-8", "replace")
    p.stdin.close()
    p.wait()
    return out


def build_library_index(out_path: str, previous: str | None = None) -> dicta_fp.FingerprintIndex:
    """אינדקס טביעות של כל הספרים הנארזים ב־HEAD. אינקרמנטלי: ספר שה־blob שלו לא השתנה
    מאז האינדקס הקודם נלקח ממנו; השאר נקראים (מעץ העבודה אם הקובץ שם וזהה, אחרת מ־git)."""
    blobs = packaged_blobs()
    old = {}
    if previous and os.path.exists(previous):
        try:
            pi = dicta_fp.FingerprintIndex.load(previous)
            if pi.mod == dicta_fp.INDEX_MOD:
                by = collections.defaultdict(set)
                for h, i in pi._pairs:
                    by[i].add(h)
                old = {b["key"]: (b.get("blob"), by[i]) for i, b in enumerate(pi.books)}
        except (OSError, ValueError) as e:
            log(f"previous index unusable: {e}")
    idx = dicta_fp.FingerprintIndex()
    todo = []
    for path, sha in sorted(blobs.items()):
        o = old.get(path)
        if o and o[0] == sha:
            idx.add(path, o[1], {"blob": sha})
        else:
            todo.append((path, sha))
    log(f"library index: {len(blobs)} packaged books, {len(todo)} to (re)fingerprint")
    prefetch_blobs([s for _, s in todo])
    for k in range(0, len(todo), 200):
        chunk = todo[k:k + 200]
        texts = _cat_blobs([s for _, s in chunk])
        for path, sha in chunk:
            t = texts.get(sha)
            if t is None and os.path.exists(os.path.join(REPO, path)):
                t = read_text(os.path.join(REPO, path))
            if t is None:
                log(f"  cannot read {path}")
                continue
            idx.add(path, dicta_fp.fingerprint(t, mod=dicta_fp.INDEX_MOD), {"blob": sha})
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    idx.save(out_path, {"built": today(), "head": run_git("rev-parse", "HEAD").strip()})
    return idx


def build_sefaria_index(db_path: str, out_path: str) -> dicta_fp.FingerprintIndex:
    import sqlite3
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    idx = dicta_fp.FingerprintIndex()
    books = c.execute("select b.id, b.title from book b join source s on s.id=b.sourceId "
                      "where s.name='Sefaria' order by b.title").fetchall()
    for n, (bid, title) in enumerate(books):
        ks = []
        for (content,) in c.execute("select content from line where bookId=? order by lineIndex", (bid,)):
            ks.extend(dicta_fp.keys(content or ""))
        idx.add(title, dicta_fp.fingerprint(ks, mod=dicta_fp.INDEX_MOD))
        if n % 500 == 0:
            log(f"sefaria {n}/{len(books)}")
    idx.save(out_path, {"built": today(), "source": os.path.basename(db_path)})
    return idx


class ContentDup:
    """כפילות תוכן של ספר חדש מול הספרייה הנארזת וספרי ספריא — אותם ספים כמו ב־bootstrap:
    ספר (קובץ) נחשב ל"מכיל" אם file_cov ≥ 0.3 (חלק ממנו) או book_cov ≥ 0.5 (רוב הספר החדש בו);
    לפי אזור: ערוך ≥50% → EDITED; נארז אחר ≥50% → DUP_PKG; ספריא ≥50% → DUP_SEF; סכום ≥20% → PARTIAL."""

    def __init__(self, library: dicta_fp.FingerprintIndex | None, sefaria: dicta_fp.FingerprintIndex | None):
        self.library, self.sefaria = library, sefaria

    def check(self, text: str) -> dict:
        exact = dicta_fp.fingerprint(text)            # MOD של bootstrap, לשלב 2
        summed = collections.defaultdict(float)
        mx = collections.defaultdict(float)
        best = {}
        for kind, ix in (("library", self.library), ("sefaria", self.sefaria)):
            if ix is None:
                continue
            for h in ix.query(text):
                bc, fc = h["book_cov"], h["file_cov"]
                if kind == "library" and bc >= 0.2:   # שלב 2: טקסט מלא, דגימת bootstrap
                    t = read_repo_text(h["key"])
                    if t is not None:
                        g = dicta_fp.fingerprint(t)
                        shared = len(exact & g)
                        bc, fc = shared / max(1, len(exact)), shared / max(1, len(g))
                area = "sefaria" if kind == "sefaria" else ("edited" if h["key"].startswith(ERUKH + "/") else "packaged")
                if fc >= 0.3:
                    summed[area] += bc
                if bc >= 0.5:
                    mx[area] = max(mx[area], bc)
                if (fc >= 0.3 or bc >= 0.5) and bc > best.get(area, (0, None))[0]:
                    best[area] = (bc, h["key"])
        cov = {k: max(summed[k], mx[k]) for k in set(summed) | set(mx)}
        cov = {k: min(1.0, v) for k, v in cov.items()}
        for area, status in (("edited", EDITED), ("packaged", DUP_PKG), ("sefaria", DUP_SEF)):
            if cov.get(area, 0) >= 0.5:
                bc, key = best[area]
                return {"status": status, "path": key, "coverage": cov,
                        "reason": f"{bc:.0%} of the text is in {'Sefaria ' if area == 'sefaria' else ''}{key}"}
        if sum(cov.values()) >= 0.2:
            return {"status": PARTIAL, "path": None, "coverage": cov,
                    "reason": "partial overlap: " + ", ".join(f"{k} {v:.0%}" for k, v in cov.items())}
        return {"status": None, "path": None, "coverage": cov, "reason": ""}


def load_indexes(library_path: str | None) -> ContentDup:
    lib = sef = None
    if library_path and os.path.exists(library_path):
        lib = dicta_fp.FingerprintIndex.load(library_path)
    if os.path.exists(SEFARIA_FP_PATH):
        sef = dicta_fp.FingerprintIndex.load(SEFARIA_FP_PATH)
    return ContentDup(lib, sef)


# ---------------------------------------------------------------------------
# מרשמים (רק לספר שנכנס ל־ERUKH)
# ---------------------------------------------------------------------------

_HONORIFIC = re.compile(r"^(רבי|רבינו|רבנו|ר'|הרב|הגאון|מרן)\s+")


def _metadata_authors(repo=REPO):
    """({title: author}, {כל המחברים}) מ־metadata.json שבשורש."""
    p = os.path.join(repo, "metadata.json")
    if not os.path.exists(p):
        return {}, set()
    meta = read_json(p)
    return ({m["title"]: m["author"] for m in meta if m.get("title") and m.get("author")},
            {m["author"] for m in meta if m.get("author")})


def canonical_author(author: str, known: set[str]) -> str:
    a = re.sub(r"\s+", " ", (author or "").strip())
    if a in known:
        return a
    base = _HONORIFIC.sub("", a)
    for cand in (base, "רבי " + base, "רבינו " + base, "ר' " + base):
        if cand in known:
            return cand
    return base  # אדם חדש: בלי תואר כבוד (תארים מפצלים את טבלת המחברים — CLAUDE.md)


def generation_of(sub: str) -> str | None:
    sub = sub or ""
    if "ראשונים" in sub or "גאונים" in sub:
        return "ראשונים"
    return "אחרונים"


def _write_compact_list(path, items):
    write_atomic(path, "[\n" + ",\n".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")) for m in items) + "\n]\n")


def _write_indent2(path, items):
    write_atomic(path, json.dumps(items, ensure_ascii=False, indent=2) + "\n")


def _roundtrip_ok(path, writer) -> bool:
    raw = read_text(path)
    buf = io.StringIO()
    items = json.loads(raw)
    if writer is _write_compact_list:
        buf.write("[\n" + ",\n".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")) for m in items) + "\n]\n")
    else:
        buf.write(json.dumps(items, ensure_ascii=False, indent=2) + "\n")
    return buf.getvalue() == raw


def register_packaged(book: dict, rel_path: str, repo=REPO) -> list[str]:
    """מוסיף שורות ל־metadata.json, ForDB/all_metadata.json, all_metadata_with_file_paths.json,
    ForDB/book_info.csv עבור ספר בנתיב rel_path (יחסי ל־אוצריא/). מחזיר את הקבצים ששונו.
    מסרב (ValueError) אם קובץ אינו חוזר בית־בבית בפורמט הצפוי — כדי לא לשכתב אותו כולו."""
    title = os.path.basename(rel_path)[:-4]
    md = DC.build_metadata(book)
    # Plan the canonical CSV and check all registries before any mutation.
    existing_meta = read_json(os.path.join(repo, "metadata.json"))
    known = {m.get("author") for m in existing_meta if m.get("author")}
    existing_author = next((m.get("author") for m in existing_meta if m.get("title") == title and m.get("author")), None)
    authors = [existing_author] if existing_author else [canonical_author(a, known) for a in md.get("heAuthors", []) if a]
    if not authors:
        authors = [canonical_author(md.get("author", ""), known)]
    csv_plan = plan_registration(repo, [[normalize_book_title(title), author, generation_of(book.get("subcategory")), "", "", ""] for author in authors])
    for rel, writer in (("metadata.json", _write_compact_list), ("ForDB/all_metadata.json", _write_indent2), ("all_metadata_with_file_paths.json", _write_indent2)):
        if not _roundtrip_ok(os.path.join(repo, rel), writer):
            raise ValueError(f"{rel} registry format would change")
    touched = []
    p = os.path.join(repo, "metadata.json")
    if not _roundtrip_ok(p, _write_compact_list):
        raise ValueError("metadata.json is not in the compact one-object-per-line format")
    meta = read_json(p)
    if not any(m.get("title") == title for m in meta):
        known = {m.get("author") for m in meta if m.get("author")}
        meta.append({"title": title, "author": canonical_author(md["author"], known), "pubDate": None, "pubPlace": None,
                     "compPlace": None, "compDate": None, "תיאור_חדש": None, "heShortDesc": None, "heDesc": None,
                     "Unnamed: 9": None, "order": None})
        _write_compact_list(p, meta)
        touched.append("metadata.json")
    rec = {"heAuthors": md["heAuthors"], "title": title, "enTitle": md["enTitle"], "authors": md["authors"],
           "pubDate": md["pubDate"], "pubDateHeb": [md["pubDateHeb"]] if md["pubDateHeb"] else [],
           "pubPlaceStringEn": md["pubPlaceStringEn"], "pubPlaceStringHe": md["pubPlaceStringHe"],
           "heCategories": md["heCategories"][:1], "categories": md["categories"][:1],
           "publisher": md["publisher"], "Sourcefolder": "Dicta"}
    for rel, extra in (("ForDB/all_metadata.json", {}),
                       ("all_metadata_with_file_paths.json", {"file_path": rel_path.replace("/", "\\")})):
        p = os.path.join(repo, rel)
        if not _roundtrip_ok(p, _write_indent2):
            raise ValueError(f"{rel} is not indent=2")
        items = read_json(p)
        if not any(m.get("title") == title and m.get("Sourcefolder") == "Dicta" for m in items):
            items.append({**rec, **extra})
            _write_indent2(p, items)
            touched.append(rel)
    touched.extend(apply_registration(repo, csv_plan))
    return touched


# ---------------------------------------------------------------------------
# מיקום
# ---------------------------------------------------------------------------

def placed_books(st: dict) -> list[dict]:
    out = []
    for fn, v in st["books"].items():
        dirs = []
        for p in v["repo"].get("edited", []) + v["repo"].get("raw", []):
            for root in (ERUKH + "/", RAW + "/"):
                if p.startswith(root) and not p.startswith(RAW_UNSORTED + "/"):
                    dirs.append(os.path.dirname(p[len(root):]))
        if dirs:
            d = v["dicta"]
            out.append({"fn": fn, "name": d.get("displayName") or "", "author": d.get("author") or "",
                        "cat": d.get("category") or "", "sub": d.get("subcategory") or "", "dirs": dirs})
    return out


def make_placer(st: dict) -> dicta_place.Placer:
    table = read_json(TABLE_PATH) if os.path.exists(TABLE_PATH) else {}
    return dicta_place.Placer(placed_books(st), table.get("sefaria_categories", []))


def destination(title: str, book: dict, gate_pass: bool, place, promote: bool) -> tuple[str, str]:
    """(נתיב יחסי למאגר, סטטוס)."""
    rel, _rule, tier = place
    cat = sanitize_filename(book.get("category") or "ללא קטגוריה")
    if gate_pass and promote:
        if tier == "A":
            return f"{ERUKH}/{rel}/{title}.txt", EDITED
        return f"{ERUKH_UNSORTED}/{cat}/{title}.txt", EDITED_UNSORTED
    if rel and tier in ("A", "B"):
        return f"{RAW}/{rel}/{title}.txt", RAW_S
    return f"{RAW_UNSORTED}/{cat}/{title}.txt", RAW_S


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def first_blob(path: str) -> str | None:
    """התוכן של הקובץ כפי שנוסף לראשונה (עוקב אחרי שינויי שם)."""
    out = run_git("log", "--follow", "--format=@%H", "--name-only", "--", path, check=False)
    last = None
    cur = None
    for ln in out.splitlines():
        if ln.startswith("@"):
            cur = ln[1:]
        elif ln.strip() and cur:
            last = (cur, ln.strip())
    if not last:
        return None
    try:
        return run_git("show", f"{last[0]}:{last[1]}")
    except RuntimeError:
        return None


def human_edit_reasons(head: str, fresh: str, fixes: list, fst: dict, ast: dict) -> list[str]:
    """למה אסור להחליף את הקובץ הגולמי בהמרה חדשה (רשימה ריקה = מותר):
    זוג היסטוריה שאינו זוג תיקונים, תיקון שלא הועבר, או מבנה (כותרות) שהממיר לא מייצר —
    כולל עריכה שכבר הייתה בגרסה הראשונה של הקובץ ב־git."""
    heads = lambda s: len(re.findall(r"^<h[2-6]>", s, re.M))  # noqa: E731
    applied = ast.get("applied", 0) + ast.get("already_fixed", 0)
    out = []
    if fst.get("pair_rejected"):
        out.append("history is not an OCR-fix pair (replay rejected)")
    if fixes and applied < len(fixes):
        out.append(f"{len(fixes) - applied} of {len(fixes)} history fixes could not be carried over")
    if heads(head) > heads(fresh):
        out.append(f"file has {heads(head)} headings, a fresh conversion {heads(fresh)} — hand-edited structure")
    return out


class Deferred(Exception):
    """הספר לא נכנס לתקציב הזמן של הריצה — יתוכנן שוב בריצה הבאה (המצב לא שונה)."""


PAGE_SECONDS = 1.0  # הורדת דף בודד (כולל ההשהיה), למדידת תקציב הזמן


class Importer:
    def __init__(self, a, st, pages, plan):
        self.deadline = time.time() + (getattr(a, "time_budget", None) or 10 ** 9)
        self.a, self.st, self.pages, self.plan = a, st, pages, plan
        self.idx = RepoIndex()
        self.content = load_indexes(getattr(a, "library_index", None))
        if self.content.library is None:
            log("WARNING: no library fingerprint index — content duplicates under another name are NOT detected")
        if self.content.sefaria is None:
            log("WARNING: no Sefaria fingerprint file — Sefaria duplicates are detected by title only")
        self.meta_authors = _metadata_authors()
        self.placer = make_placer(st)
        self.taken: set[str] = set()
        self.summary = collections.defaultdict(list)
        self.touched: set[str] = set()
        self.sandbox = a.dry_run

    # כתיבה: לעץ העבודה, או ל־sandbox ב־dry-run
    def write(self, rel: str, text: str) -> None:
        if self.a.claim_cmd and not self.sandbox:
            r = subprocess.run(shlex.split(self.a.claim_cmd) + [rel], cwd=REPO, capture_output=True, text=True)
            if r.returncode:
                raise PermissionError(f"claim refused for {rel}: {r.stdout.strip()} {r.stderr.strip()}")
        root = self.sandbox or REPO
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        write_atomic(full, text)
        self.touched.add(rel)

    def fetch(self, book):
        """(zip שלם, סדר הדפים, md5 של ה־zip של דיקטה, info). דפים שחסרים ב־zip לעומת pages.json
        מושלמים מקובצי הדפים הבודדים; info['failed'] לא ריק = ספר קטוע — אסור לכתוב אותו."""
        data, _ = http(book["OCRDataURL"])
        md5 = hashlib.md5(data).hexdigest()
        order = None
        try:
            pj, _ = http(pages_json_url(book["OCRDataURL"]))
            order = [p["fileName"] for p in json.loads(pj)]
        except (OSError, ValueError, KeyError, TypeError):
            order = None
        if order:
            have = set()
            if data[:2] == b"PK" and len(data) > 22:
                have = {page_stem(n) for n in zipfile.ZipFile(io.BytesIO(data)).namelist()}
            need = sum(1 for p in order if page_stem(p) not in have)
            if need * PAGE_SECONDS > self.remaining():
                raise Deferred(f"{need} pages to fetch one by one (~{need * PAGE_SECONDS:.0f}s) exceed the time budget")
        full, info = complete_zip(data, order, book["OCRDataURL"].rsplit("/", 1)[0])
        return full, order, md5, info

    def remaining(self) -> float:
        return self.deadline - time.time()

    def truncated(self, fn, book, info, remote, pagemap) -> bool:
        if not info["failed"]:
            return False
        ent = self.st["books"].get(fn, {})
        repo = dict(ent.get("repo") or repo_entry(PARTIAL))
        if repo.get("status") in IMPORTABLE | {None}:
            repo["status"] = PARTIAL
        repo["truncated"] = {"expected": info["expected"], "missing": len(info["missing"]),
                             "unavailable": ranges(page_no(s + ".html") or 0 for s in info["failed"])}
        self._record(fn, book, remote, pagemap, repo)
        self.summary["truncated — nothing written"].append((fn, f"{len(info['failed'])} of {info['expected']} pages unavailable"))
        return True

    def convert(self, data, book, order):
        res = DC.convert_zip_final(data, book, page_order=order)
        src = " ".join(h for _, h in DC.read_zip_pages(data, order))
        return res, src

    def author_line(self, text, title, dicta_author, head=None):
        """שורה 2 (המחבר) בכתיב הקנוני של metadata.json כשהאדם כבר קיים שם; אחרת — כתיב דיקטה, ודיווח.
        סדר: רשומת metadata.json של אותו ספר → אותו אדם בלי/עם תואר כבוד → שורת המחבר של הקובץ הקודם."""
        lines = text.split("\n")
        dicta_author = re.sub(r"\s+", " ", (dicta_author or "").strip())
        if len(lines) < 2 or not dicta_author or lines[1] != DC._escape_text(dicta_author):
            return text, None
        by_title, known = self.meta_authors
        canon = by_title.get(title) or canonical_author(dicta_author, known)
        if canon not in known and head:
            prev = head.split("\n")[1] if head.count("\n") >= 1 else ""
            if prev in known:
                canon = prev
        if canon in known:
            lines[1] = DC._escape_text(canon)
            return "\n".join(lines), None
        return text, f"'{dicta_author}' not in metadata.json — kept Dicta spelling"

    # ---- עזרים ----
    def path_taken(self, path: str) -> bool:
        """תפוס: נכתב בריצה הזו, קיים בעץ העבודה, או עקוב ב־git (גם מחוץ ל־sparse)."""
        return path in self.taken or path in self.idx.file_set or os.path.exists(os.path.join(REPO, path))

    def same_text_as(self, fn: str, sig: str) -> str | None:
        """ספר אחר במצב שה־text_sig שלו זהה (DESIGN §3) — אותו טקסט בשני fileName."""
        for other, v in self.st["books"].items():
            if other != fn and v.get("remote", {}).get("text_sig") == sig and \
                    v["repo"]["status"] not in IMPORTABLE | {REMOVED}:
                return other
        return None

    def _entry(self, status, files, ent, **kw):
        merged = {k: sorted(set(files.get(k, [])) | set((ent or {}).get("repo", {}).get(k, [])))
                  for k in ("edited", "unsorted", "raw", "extra", "dup")}
        return repo_entry(status, **merged, **kw)

    def _gate_record(self, why, remote, place, gate, res):
        return {"date": today(), "why": why, "zip_md5": remote["zip_md5"],
                "rule": place[1] if place else None, "tier": place[2] if place else None, "gate": gate["pass"],
                "gate_failed": sorted(k for k, v in gate["checks"].items() if not v),
                "lost_words": gate["metrics"].get("lost_words"), "flagged": len(res.flagged)}

    def fetch_checked(self, fn, book):
        """הורדה + השלמת דפים, או None אם הספר נדחה לריצה הבאה / קטוע (כבר נרשם)."""
        data, order, md5, info = self.fetch(book)
        remote, pagemap = zip_signature(data)
        remote["zip_md5"] = md5
        if info["fetched"]:
            remote["pages_from_page_files"] = ranges(page_no(s + ".html") or 0 for s in info["fetched"])
        if self.truncated(fn, book, info, remote, pagemap):
            return None
        return data, order, remote, pagemap

    # ---- ספר חדש / חסר ----
    def do_import(self, fn, why):
        book = self.plan["books"].get(fn) or {}
        ent = self.st["books"].get(fn)
        # תכנית ישנה או ריצה כפולה: בתוך נעילת הכתיבה המצב הוא הקובע
        if ent and ent["repo"]["status"] not in IMPORTABLE:
            self.summary["skipped (state changed since the plan)"].append((fn, ent["repo"]["status"]))
            return
        if not book.get("OCRDataURL"):
            self.summary["skipped"].append((fn, "no OCRDataURL"))
            return
        got = self.fetch_checked(fn, book)
        if got is None:
            return
        data, order, remote, pagemap = got
        if remote["n_pages"] == 0:
            self._record(fn, book, remote, pagemap, repo_entry(EMPTY, reason="zip has no pages"))
            self.summary["empty"].append((fn, book.get("displayName")))
            return
        twin = self.same_text_as(fn, remote["text_sig"])
        if twin:
            self._record(fn, book, remote, pagemap, self._entry(DUP_PKG, {}, ent, reason=f"same text as Dicta book {twin}"))
            self.summary["same text as another Dicta book (nothing written)"].append((fn, twin))
            return
        res, src = self.convert(data, book, order)
        title = sanitize_filename(book.get("displayName") or fn)
        gate = dicta_gate.evaluate(res.text, src, source_is_html=True)
        cd = self.content.check(res.text)
        coll = self.idx.collisions(title)
        dup, dup_reason, dup_path = dup_check(res.text, coll)
        for st_, reason_, path_ in ((cd["status"], cd["reason"], cd["path"]), (dup, dup_reason, dup_path)):
            if st_ == EDITED:  # כבר עובד ונארז — לא כותבים; עמודים חדשים הם עבודה ידנית (linkshift)
                self._record(fn, book, remote, pagemap, self._entry(EDITED, {"edited": [path_]}, ent, reason=reason_))
                self.summary["already-edited (nothing written)"].append((fn, path_))
                return
        text, author_note = self.author_line(res.text, title, book.get("author"))
        if author_note:
            self.summary["author (report only)"].append((fn, author_note))
        x = {"name": book.get("displayName") or "", "author": book.get("author") or "",
             "cat": book.get("category") or "", "sub": book.get("subcategory") or ""}
        place = self.placer.predict(x)
        if cd["status"] in (DUP_SEF, DUP_PKG) and dup not in (DUP_SEF, DUP_PKG):
            dup, dup_reason = cd["status"], "content: " + cd["reason"]
        if dup in (DUP_SEF, DUP_PKG):
            rel_dir = place[0] if place[0] else sanitize_filename(book.get("category") or "")
            path, status, reason = f"{EXTRA}/{rel_dir}/{title}.txt", dup, dup_reason
        else:
            path, status = destination(title, book, gate["pass"] and dup is None, place, not self.a.no_promote)
            reason = dup_reason if dup == NEEDS_HUMAN else (cd["reason"] if cd["status"] == PARTIAL else "")
            if dup == NEEDS_HUMAN:
                status = NEEDS_HUMAN
        # מגן קישורים: ספר חדש בעץ הנארז לא יכול לקבל שם שכבר משתתף בקישורים
        g = links_guard([path], self.idx)[0]
        if g["packaged"] and (g["links_source"] or g["links_target"]):
            path = f"{RAW}/{place[0] or 'לא ממויין'}/{title}.txt"
            status, reason = NEEDS_HUMAN, "basename already used by manual links"
        # שם קובץ תפוס (שני fileName עם אותו displayName, ספר קיים באותו שם, תכנית כפולה) — לא יוצרים "_2"
        clash = self.path_taken(path) or (is_packaged(path, self.idx.roots) and title_key(title) in self.idx.pkg_keys)
        if clash:
            self._record(fn, book, remote, pagemap, self._entry(NEEDS_HUMAN, {}, ent,
                         reason=f"file name taken: {path}", suggested=path))
            self.summary["needs-human (file name taken — nothing written)"].append((fn, path))
            return
        self.taken.add(path)
        self.write(path, text)
        key = {EDITED: "edited", EDITED_UNSORTED: "unsorted", RAW_S: "raw", NEEDS_HUMAN: "raw",
               DUP_SEF: "extra", DUP_PKG: "extra"}[status]
        files = {key: [path]}
        suggested = f"{ERUKH}/{place[0]}/{title}.txt" if place[0] else None
        if status == EDITED:
            raw_copy = f"{EXTRA}/{place[0]}/{title}.txt"
            if not self.path_taken(raw_copy):
                self.taken.add(raw_copy)
                self.write(raw_copy, DC.convert_zip(data, book, page_order=order).text)
                files["extra"] = [raw_copy]
            if not self.sandbox:
                self.touched.update(register_packaged(book, path[len(ERUKH) + 1:]))
        entry = self._entry(status, files, ent, reason=reason,
                            suggested=suggested if status in (EDITED_UNSORTED, RAW_S, NEEDS_HUMAN) else None)
        if status == EDITED:
            entry["pending_pr"] = today()  # detect לא יתכנן אותו שוב; reconcile מנקה אחרי המיזוג
        entry["import"] = self._gate_record(why, remote, place, gate, res)
        self._record(fn, book, remote, pagemap, entry)
        self.summary[status].append((fn, path, place[1], "gate pass" if gate["pass"] else "gate fail"))

    # ---- ספר גולמי שהשתנה ----
    def do_reconvert(self, fn, why):
        ent = self.st["books"][fn]
        book = self.plan["books"].get(fn) or {}
        if ent["repo"]["status"] not in (RAW_S, NEEDS_HUMAN, PARTIAL):
            self.summary["skipped (state changed since the plan)"].append((fn, ent["repo"]["status"]))
            return
        raws = [p for p in ent["repo"].get("raw", []) if os.path.exists(os.path.join(REPO, p))]
        if len(raws) != 1:
            self.summary["needs-human"].append((fn, f"reconvert: {len(raws)} raw files"))
            return
        path = raws[0]
        g = links_guard([path], self.idx)[0]
        if g["packaged"]:
            self.summary["refused"].append((fn, "packaged file — never rewritten"))
            return
        got = self.fetch_checked(fn, book)
        if got is None:
            return
        data, order, remote, pagemap = got
        old_pages = expand(ent["remote"].get("pages", []))
        new_pages = expand(remote["pages"])
        res, src = self.convert(data, book, order)
        gate = dicta_gate.evaluate(res.text, src, source_is_html=True)
        head = read_text(os.path.join(REPO, path))
        base = first_blob(path) or head
        fixes, fst = dicta_replay.extract(base, head)
        text, ast = dicta_replay.apply(fixes, res.text)
        # עבודה אנושית שאסור לאבד: זוג שאינו זוג תיקונים, תיקון שלא הוחל, או מבנה (כותרות) שהממיר לא מייצר —
        # כולל עריכה שכבר הייתה בגרסה הראשונה (first blob) של הקובץ.
        human = human_edit_reasons(head, res.text, fixes, fst, ast)
        if human:
            e = dict(ent["repo"])
            e.update(status=NEEDS_HUMAN, reason="; ".join(human),
                     pending_pages=ranges(set(expand(ent["repo"].get("import", {}).get("missing_pages", []))) | (new_pages - old_pages)))
            self._record(fn, book, ent["remote"], {str(k): v for k, v in (self.pages.get(fn) or {}).items()}, e)
            self.summary["needs-human (would lose hand edits — nothing written)"].append((fn, path, e["reason"]))
            return
        text, author_note = self.author_line(text, os.path.basename(path)[:-4], book.get("author"), head=head)
        if author_note:
            self.summary["author (report only)"].append((fn, author_note))
        self.write(path, text)
        imp = self._gate_record(why, remote, None, gate, res)
        imp.update(pages_added=ranges(set(expand(ent["repo"].get("import", {}).get("missing_pages", []))) | (new_pages - old_pages)),
                   pages_removed=ranges(old_pages - new_pages), replay={"fixes": len(fixes), **fst, **ast})
        self._record(fn, book, remote, pagemap, {**ent["repo"]}, extra=imp)
        self.summary["reconverted"].append((fn, path, f"pages added {imp['pages_added']}, history fixes {len(fixes)} "
                                            f"applied {ast.get('applied', 0)}, lost words {gate['metrics'].get('lost_words')}"))

    def _record(self, fn, book, remote, pagemap, repo, extra=None):
        remote = {**remote, "checked": today()}
        e = self.st["books"].get(fn, {})
        e = {**e, "dicta": dicta_record(book) if book else e.get("dicta", {}), "remote": remote, "repo": repo}
        if extra:
            e["repo"] = {**repo, "import": extra}
        self.st["books"][fn] = e
        self.pages[fn] = {str(k): v for k, v in pagemap.items()}

    def run(self):
        self.attempted = self.failed = 0
        for it in self.plan["items"]:
            fn, act = it["fileName"], it["action"]
            if act in ("import", "reconvert") and self.remaining() <= 0:
                self.summary["deferred (time budget) — next run"].append((fn, act))
                continue
            try:
                if act in ("import", "reconvert"):
                    self.attempted += 1
                if act == "import":
                    self.do_import(fn, it["why"])
                elif act == "reconvert":
                    self.do_reconvert(fn, it["why"])
                elif act == "mark-removed":  # דגל נפרד — הסטטוס והקבצים נשמרים
                    self.st["books"][fn]["repo"]["removed_upstream"] = today()
                    self.summary[REMOVED].append((fn, self.st["books"][fn]["dicta"].get("displayName")))
                elif act == "report-changed":
                    self.summary["changed-not-touched"].append((fn, it["why"]))
                elif act == "report-edited-missing-pages":
                    r = self.st["books"][fn]["repo"]
                    r["reported_missing_pages"] = it.get("missing_pages")
                    self.summary["EDITED book missing pages (report — never edited automatically)"].append(
                        (fn, r.get("edited"), it.get("missing_pages")))
                if fn in self.st["books"]:
                    self.st["books"][fn]["repo"].pop("last_error", None)
            except Deferred as e:
                self.summary["deferred (time budget) — next run"].append((fn, str(e)))
            except Exception as e:  # noqa: BLE001 — ספר אחד לא מפיל את הריצה
                self.failed += 1
                log(f"ERROR {fn}: {e}")
                self.summary["errors"].append((fn, str(e)[:200]))
                if fn in self.st["books"]:
                    self.st["books"][fn]["repo"]["last_error"] = {"date": today(), "error": str(e)[:300]}

    def systemic_failure(self) -> bool:
        """כשל מערכתי = רוב הספרים שנוסו נכשלו (רשת/שרת/באג), לא ספר בודד."""
        return self.attempted >= 2 and self.failed * 2 > self.attempted

    def finish(self):
        for c in self.plan.get("changes", []):
            self.summary["dicta-metadata-change (report only)"].append((c["fileName"], c["field"], c["old"], c["new"]))
        if not self.sandbox:
            known = {(c["fileName"], c["field"]) for c in self.st.get("dicta_changes", [])}
            for c in self.plan.get("changes", []):
                if (c["fileName"], c["field"]) not in known:
                    self.st.setdefault("dicta_changes", []).append({**c, "seen": today()})
            self.st["books_json"] = {"sha256": self.plan.get("books_json_sha256"), "checked": today()}


def summary_md(summary) -> str:
    out = [f"## ייבוא דיקטה — {today()}", ""]
    for k, rows in summary.items():
        out.append(f"### {k} ({len(rows)})")
        out += ["- " + " | ".join(str(x) for x in r) for r in rows[:200]]
        out.append("")
    return "\n".join(out)


def cmd_import(a) -> int:
    plan = read_json(a.plan)
    st = load_state()
    pages = load_pages()
    imp = Importer(a, st, pages, plan)
    imp.run()
    imp.finish()
    md = summary_md(imp.summary)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    print(md)
    if a.dry_run:
        save_state(st, os.path.join(a.dry_run, "dicta_state.json"))
        log(f"dry-run: outputs in {a.dry_run}")
    else:
        save_state(st)
        save_pages(pages)
    return 1 if imp.systemic_failure() else 0


# ---------------------------------------------------------------------------
# reconcile / sort
# ---------------------------------------------------------------------------

def same_book(a_text: str | None, b_text: str | None, threshold: float = DUP_THRESHOLD) -> bool:
    """אותו ספר לפי תוכן: ≥threshold מהטביעה של הקטן מהשניים נמצא בגדול."""
    if not a_text or not b_text:
        return False
    fa, fb = dicta_fp.fingerprint(a_text), dicta_fp.fingerprint(b_text)
    small, big = (fa, fb) if len(fa) <= len(fb) else (fb, fa)
    return dicta_fp.coverage(small, big) >= threshold


def best_match(old_text: str | None, candidates: list[str], old_path: str, prefer_edited: bool = False) -> str | None:
    """המועמד (באותו שם) שתוכנו הכי קרוב לגרסת HEAD של הקובץ שנעלם; שוויון — לפי סיומת נתיב משותפת
    ארוכה יותר (אותו תת־עץ). None אם אף מועמד אינו אותו ספר (same_book)."""
    if not old_text:
        return None
    fo = dicta_fp.fingerprint(old_text)
    scored = []
    for c in candidates:
        txt = read_repo_text(c)
        if not same_book(old_text, txt):
            continue
        cov = dicta_fp.coverage(fo, dicta_fp.fingerprint(txt))
        a, b = old_path.split("/")[::-1], c.split("/")[::-1]
        suffix = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        area = c.startswith(ERUKH + "/") == prefer_edited  # גולמי → עותק גולמי; ערוך → קובץ ערוך
        scored.append((area, round(cov, 3), suffix, c))
    return max(scored)[3] if scored else None


_SEF_TITLES: set[str] | None = None


def sefaria_titles() -> set[str]:
    global _SEF_TITLES
    if _SEF_TITLES is None:
        tp = os.path.join(REPO, SEFARIA_TITLES)
        _SEF_TITLES = {title_key(ln.strip()) for ln in read_text(tp).splitlines()
                       if ln.strip() and not ln.startswith("#")} if os.path.exists(tp) else set()
    return _SEF_TITLES


def _head_text(path: str) -> str | None:
    try:
        return run_git("show", f"HEAD:{path}")
    except RuntimeError:
        return None


def slot_of(path: str) -> str:
    """המקום במצב נקבע לפי מיקום הקובץ, לא לפי המקום שבו היה קודם."""
    if path.startswith(ERUKH + "/"):
        return "edited"
    if path.startswith(ERUKH_UNSORTED + "/"):
        return "unsorted"
    if path.startswith("DictaToOtzaria/לא ערוך/"):
        return "raw"
    return "extra"


def cmd_reconcile(a) -> int:
    """מיישר את המצב לשינויים ידניים במאגר. כל התאמה נבדקת לפי תוכן — לא לפי שם הקובץ בלבד:
    * קובץ שנעלם: מועמד באותו שם נקבל רק אם תוכנו הוא של הקובץ הישן (גרסת HEAD); לגולמי עדיף
      עותק גולמי (extraBooks/דיקטה), לערוך — קובץ בעץ הערוך.
    * כל נתיב נרשם במקום שמתאים למיקומו (ערוך → edited, extraBooks → extra ...).
    * ספר גולמי שעובד (הנוהג: ערוך חדש + הגולמי ל־extraBooks/דיקטה): הקובץ הערוך נמצא לפי שם, ואם
      שמו שונה — לפי טביעת התוכן מבין קובצי הערוך שאינם שייכים לשום ספר במצב; אז נכתבים המרשמים.
    * pending_pr: הקבצים הגיעו ל־main → הדגל יורד."""
    st = load_state(a.state) if getattr(a, "state", None) else load_state()
    files = repo_files()
    fset = set(files)
    by_base = collections.defaultdict(list)
    for p in files:
        if p.endswith(".txt"):
            by_base[os.path.basename(p)].append(p)
    referenced = {p for v in st["books"].values() for k in ("edited", "unsorted", "raw", "extra", "dup")
                  for p in v["repo"].get(k, [])}
    free_edited = [p for p in files if p.startswith(ERUKH + "/") and p.endswith(".txt") and p not in referenced]
    fp_cache: dict[str, set] = {}

    def fp_of(path):
        if path not in fp_cache:
            fp_cache[path] = dicta_fp.fingerprint(read_repo_text(path) or "")
        return fp_cache[path]

    changed = 0
    for fn, v in sorted(st["books"].items()):
        r = v["repo"]
        before = json.dumps(r, sort_keys=True, ensure_ascii=False)
        known_edited = set(r.get("edited", []))
        paths = []
        for k in ("edited", "unsorted", "raw", "extra"):
            for p in r.get(k, []):
                if p in fset or os.path.exists(os.path.join(REPO, p)):
                    paths.append(p)
                    continue
                cands = [c for c in by_base.get(os.path.basename(p), [])
                         if (c.startswith("DictaToOtzaria/") or c.startswith(EXTRA)) and c not in referenced]
                best = best_match(_head_text(p), cands, p, prefer_edited=k in ("edited", "unsorted"))
                if best:
                    paths.append(best)
                    log(f"{fn}: {p} → {best}")
                else:
                    paths.append(p)  # לא מוחקים מידע; מדווחים
                    log(f"{fn}: {p} is missing and no content-matching replacement ({len(cands)} same-name candidates)")
        slots = {k: set() for k in ("edited", "unsorted", "raw", "extra")}
        for p in paths:
            slots[slot_of(p)].add(p)
        for k, ps in slots.items():
            r[k] = sorted(ps)
        if r["status"] == EDITED and not r["edited"] and not r.get("pending_pr"):
            out = r["extra"][0] if r["extra"] else None
            title = os.path.basename(out)[:-4] if out else ""
            r["status"] = DUP_SEF if title_key(title) in sefaria_titles() else EXTRA_ONLY
            r["reason"] = f"edited copy moved out of the library to {out}"
            log(f"{fn}: edited copy moved out of the library → {r['status']}")
        if r.get("pending_pr") and r.get("edited") and all(p in fset for p in r["edited"]):
            r.pop("pending_pr")
        # קובץ ערוך *חדש* לספר גולמי (לא הפניות ישנות מ־bootstrap לחפיפה חלקית)
        promoted = [p for p in r.get("edited", []) if p not in known_edited
                    and r["status"] in (RAW_S, NEEDS_HUMAN, EDITED_UNSORTED)]
        if r["status"] in (RAW_S, NEEDS_HUMAN) and not r.get("raw") and r.get("extra") and not promoted:
            # הגולמי יצא מ"לא ערוך" אל extraBooks — חיפוש הערוך: לפי שם, ואז לפי תוכן
            raw_text = next((t_ for t_ in (read_repo_text(q) for q in r["extra"]) if t_), None)
            by_name = [c for q in r["extra"] for c in by_base.get(os.path.basename(q), []) if c.startswith(ERUKH + "/")]
            hits = [c for c in by_name if same_book(raw_text, read_repo_text(c))]
            if not hits and raw_text:
                g = dicta_fp.fingerprint(raw_text)
                scored = sorted(((dicta_fp.coverage(g, fp_of(c)), c) for c in free_edited), reverse=True)
                hits = [c for cov, c in scored[:1] if cov >= DUP_THRESHOLD]
            promoted = hits
        for p in sorted(set(promoted)):
            if not a.dry_run:
                register_packaged(v["dicta"] | {"fileName": fn}, p[len(ERUKH) + 1:])
            r["edited"] = sorted(set(r.get("edited", [])) | {p})
            r["status"] = EDITED
            referenced.add(p)
            log(f"{fn}: now packaged at {p} — registries written")
        if json.dumps(r, sort_keys=True, ensure_ascii=False) != before:
            changed += 1
    if changed and not a.dry_run:
        save_state(st)
    log(f"reconcile: {changed} updates")
    return 0


def cmd_sort(a) -> int:
    st = load_state()
    todo = [fn for fn, v in st["books"].items() if v["repo"]["status"] == EDITED_UNSORTED] if a.all else a.accept
    for fn in todo:
        v = st["books"][fn]
        src = (v["repo"].get("unsorted") or [None])[0]
        dst = v["repo"].get("suggested")
        if not src or not dst:
            log(f"{fn}: no unsorted file or no suggestion")
            continue
        if a.to:
            dst = f"{ERUKH}/{a.to.strip('/')}/{os.path.basename(src)}"
        os.makedirs(os.path.dirname(os.path.join(REPO, dst)), exist_ok=True)
        run_git("mv", src, dst)
        register_packaged(v["dicta"] | {"fileName": fn}, dst[len(ERUKH) + 1:])
        v["repo"]["unsorted"] = []
        v["repo"]["edited"] = sorted(set(v["repo"].get("edited", [])) | {dst})
        v["repo"]["status"] = EDITED
        log(f"{fn}: {src} → {dst}")
    save_state(st)
    return 0


def cmd_fp_index(a) -> int:
    if a.library:
        ix = build_library_index(a.library, a.previous or a.library)
        log(f"library index: {len(ix.books)} books, {len(set(ix._pairs))} pairs, {os.path.getsize(a.library) / 1e6:.1f} MB")
    if a.sefaria_db:
        ix = build_sefaria_index(a.sefaria_db, SEFARIA_FP_PATH)
        log(f"sefaria index: {len(ix.books)} books, {os.path.getsize(SEFARIA_FP_PATH) / 1e6:.1f} MB")
    return 0


def cmd_links_guard(a) -> int:
    rows = links_guard(a.paths)
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    return 1 if any(r["packaged"] and (r["links_source"] or r["links_target"]) for r in rows) else 0


def cmd_report(a) -> int:
    st = load_state()
    c = collections.Counter(v["repo"]["status"] for v in st["books"].values())
    print(json.dumps({"books": len(st["books"]), "status": dict(sorted(c.items())),
                      "dicta_changes": len(st.get("dicta_changes", []))}, ensure_ascii=False, indent=1))
    return 0


def missing_pages(data: bytes, text: str, n: int = 6, need: float = 0.5) -> list[int]:
    """דפי zip שרוב ה־n-grams (המלאים) שלהם אינם בטקסט — דפים שמעולם לא יובאו."""
    have = set()
    ks = dicta_fp.keys(text)
    for i in range(len(ks) - n + 1):
        have.add(" ".join(ks[i:i + n]))
    out = []
    zf = zipfile.ZipFile(io.BytesIO(data))
    for name in zf.namelist():
        pn = page_no(name)
        if pn is None:
            continue
        pk = dicta_fp.keys(zf.read(name).decode("utf-8", "replace"))
        grams = {" ".join(pk[i:i + n]) for i in range(len(pk) - n + 1)}
        if len(grams) >= 5 and len(grams & have) / len(grams) < need:
            out.append(pn)
    return sorted(out)


def cmd_verify_raw(a) -> int:
    """לכל ספר גולמי: האם הקובץ שבמאגר הומר מה־zip הנוכחי. אם חסרים בו דפים — import.zip_md5=None,
    ו־detect יתכנן המרה מחדש (עם העברת התיקונים מההיסטוריה)."""
    st = load_state()
    n = 0
    for fn, v in sorted(st["books"].items()):
        if v["repo"]["status"] != RAW_S:
            continue
        raws = [p for p in v["repo"].get("raw", []) if os.path.exists(os.path.join(REPO, p))]
        zp = os.path.join(a.zip_cache, fn + ".zip")
        if not raws or not os.path.exists(zp):
            continue
        text = "\n".join(read_text(os.path.join(REPO, p)) for p in raws)
        miss = missing_pages(read_bytes(zp), text)
        imp = v["repo"].setdefault("import", {})
        imp["zip_md5"] = None if miss else v["remote"]["zip_md5"]
        if miss:
            imp["missing_pages"] = ranges(miss)
            n += 1
            log(f"{fn}: pages never imported: {ranges(miss)}")
        else:
            imp.pop("missing_pages", None)
    save_state(st)
    log(f"verify-raw: {n} raw books are behind their Dicta zip")
    return 0


# ---------------------------------------------------------------------------
# bootstrap — פעם אחת, מקומית (דורש את כל ה־zips: ~560MB)
# ---------------------------------------------------------------------------

def _classify(cov: dict) -> str:
    order = [("edited", EDITED), ("packaged", DUP_PKG), ("sefaria", DUP_SEF), ("raw", RAW_S), ("extra", EXTRA_ONLY)]
    for k, s in order:
        if cov.get(k, 0) >= 0.5:
            return s
    return PARTIAL if sum(cov.values()) >= 0.2 else ABSENT


def area_of(p: str, roots) -> str:
    if p.startswith(ERUKH + "/"):
        return "edited"
    if p.startswith(ERUKH_UNSORTED + "/"):
        return "unsorted"
    if p.startswith("DictaToOtzaria/לא ערוך/"):
        return "raw"
    if p.startswith(SEFARIA_COPIES):
        return "sefaria"
    if p.startswith("extraBooks/"):
        return "extra"
    if is_packaged(p, roots):
        return "packaged"
    return "other"


def _fp_file(path):
    try:
        t = read_text(os.path.join(REPO, path))
    except OSError:
        return path, None, 0
    g = dicta_fp.fingerprint(t)
    return path, g, len(g)


def cmd_bootstrap(a) -> int:
    books = read_json(a.books_json) if a.books_json else json.loads(http(BOOKS_JSON_URL)[0])
    os.makedirs(a.zip_cache, exist_ok=True)
    fps, st_books, pages = {}, {}, {}
    for i, b in enumerate(books):
        fn = b["fileName"]
        zp = os.path.join(a.zip_cache, fn + ".zip")
        if not os.path.exists(zp):
            data, _ = http(b["OCRDataURL"])
            write_atomic(zp, data, binary=True)
        data = read_bytes(zp)
        remote, pm = zip_signature(data)
        remote["checked"] = today()
        pages[fn] = {str(k): v for k, v in pm.items()}
        fps[fn] = dicta_fp.fingerprint(" ".join(h for _, h in DC.read_zip_pages(data)))
        st_books[fn] = {"dicta": dicta_record(b), "remote": remote}
        if i % 100 == 0:
            log(f"zips {i}/{len(books)}")
    roots = packaged_roots()
    files = [p for p in repo_files() if p.endswith(".txt") and not p.startswith("Ben-Yehuda")]
    if a.mapping:  # מיפוי שחושב מראש (אותו אלגוריתם) — מסונן לקבצים שעדיין קיימים
        m = read_json(a.mapping)
        exist = set(files)
        hits = {fn: [(p, bc, fc) for p, _k, bc, fc in L if p in exist] for fn, L in m.items()}
    else:
        union = set().union(*fps.values())
        inv = collections.defaultdict(list)
        for fn, g in fps.items():
            for h in g:
                inv[h].append(fn)
        hits = collections.defaultdict(list)
        from multiprocessing import Pool
        with Pool(a.jobs) as pool:
            for n, (p, g, ng) in enumerate(pool.imap_unordered(_fp_file, files, chunksize=4)):
                if not g:
                    continue
                c = collections.Counter(fn for h in g & union for fn in inv[h])
                for fn, k in c.items():
                    bc, fc = k / max(1, len(fps[fn])), k / max(1, ng)
                    if k >= 5 and (bc >= 0.05 or fc >= 0.3):
                        hits[fn].append((p, round(bc, 3), round(fc, 3)))
                if n % 2000 == 0:
                    log(f"repo scan {n}/{len(files)}")
    for fn, e in st_books.items():
        cov = collections.defaultdict(float)
        mx = collections.defaultdict(float)
        fl = collections.defaultdict(set)
        for p, bc, fc in hits.get(fn, []):
            ar = area_of(p, roots)
            if fc >= 0.3:
                cov[ar] += bc
                fl[ar].add(p)
            if bc >= 0.5:
                mx[ar] = max(mx[ar], bc)
                fl[ar].add(p)
        c2 = {k: round(min(1.0, max(cov[k], mx[k])), 3) for k in set(cov) | set(mx)}
        status = EMPTY if e["remote"]["n_pages"] == 0 else _classify({k: v for k, v in c2.items() if k != "unsorted"})
        reason = ", ".join(f"{k} {v:.0%}" for k, v in sorted(c2.items(), key=lambda x: -x[1])) or "not found in repo"
        e["repo"] = repo_entry(status, edited=fl["edited"], unsorted=fl["unsorted"], raw=fl["raw"],
                               extra=fl["extra"], dup=sorted(fl["packaged"] | fl["sefaria"]), reason=reason)
    st = {"schema": 1, "books_json": {"sha256": None, "checked": today()}, "books": st_books, "dicta_changes": []}
    save_state(st)
    save_pages(pages)
    if a.seforim_db:
        import sqlite3
        c = sqlite3.connect(f"file:{a.seforim_db}?mode=ro", uri=True)
        cats = {r[0]: (r[1], r[2]) for r in c.execute("select id,parentId,title from category")}

        def cpath(cid):
            p = []
            while cid:
                par, t = cats[cid]
                p.append(t)
                cid = par
            return "/".join(reversed(p))
        sef = set()
        for (cid,) in c.execute("select b.categoryId from book b join source s on s.id=b.sourceId where s.name='Sefaria'"):
            parts = cpath(cid).split("/")
            for i in range(1, len(parts) + 1):
                sef.add(dicta_place.nq("/".join(parts[:i])))
        table = {"source": f"{os.path.basename(a.seforim_db)} category table, Sefaria-populated paths, quotes stripped",
                 "built": today(), "sefaria_categories": sorted(sef)}
        write_atomic(TABLE_PATH, json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    c = collections.Counter(v["repo"]["status"] for v in st_books.values())
    log(f"bootstrap: {dict(c)}")
    return 0


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("detect")
    p.add_argument("--books-json")
    p.add_argument("--no-head", action="store_true")
    p.add_argument("--skip-missing", action="store_true", help="לא לנסות שוב ספרים חסרים/ריקים")
    p.add_argument("--check-pages", action="store_true",
                   help="להשוות כל ספר ל־pages.json של דיקטה (zip קטוע) — כ־1,000 בקשות קטנות")
    p.add_argument("--max-books", type=int, default=None)
    p.add_argument("--out", required=True)
    p = sub.add_parser("import")
    p.add_argument("--plan", required=True)
    p.add_argument("--dry-run", metavar="DIR", help="לכתוב לתיקייה זו במקום למאגר; המצב נשמר שם")
    p.add_argument("--no-promote", action="store_true", help="גם ספר שעבר את השער נכנס ל'לא ערוך'")
    p.add_argument("--claim-cmd", help="פקודה שמקבלת נתיב ומחזירה 0 אם מותר לכתוב (עבודה מקבילה)")
    p.add_argument("--summary", help="קובץ markdown לצירוף הסיכום (GITHUB_STEP_SUMMARY)")
    p.add_argument("--time-budget", type=float, default=None, metavar="SECONDS",
                   help="אחרי הזמן הזה לא מתחילים ספר חדש; ספר שהשלמת דפיו לא תיכנס — נדחה לריצה הבאה")
    p.add_argument("--library-index", default=LIBRARY_FP_DEFAULT,
                   help="אינדקס טביעות של הספרייה הנארזת (fp-index --library)")
    p = sub.add_parser("reconcile")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state", help="קובץ מצב אחר (לבדיקה)")
    p = sub.add_parser("sort")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--accept", nargs="+", metavar="FILENAME")
    g.add_argument("--all", action="store_true")
    p.add_argument("--to", help="נתיב יחסי ל־אוצריא/ במקום המיקום המוצע")
    p = sub.add_parser("links-guard")
    p.add_argument("paths", nargs="+")
    sub.add_parser("report")
    p = sub.add_parser("fp-index", help="בניית/עדכון אינדקסי הטביעות לזיהוי כפילות תוכן")
    p.add_argument("--library", metavar="OUT", help="אינדקס הספרייה הנארזת (ב־CI: actions/cache)")
    p.add_argument("--previous", help="אינדקס קודם — עדכון אינקרמנטלי לפי blob sha")
    p.add_argument("--sefaria-db", help=f"seforim.db → {os.path.basename(SEFARIA_FP_PATH)} (מחויב במאגר)")
    p = sub.add_parser("verify-raw")
    p.add_argument("--zip-cache", required=True)
    p = sub.add_parser("bootstrap")
    p.add_argument("--zip-cache", required=True)
    p.add_argument("--books-json")
    p.add_argument("--mapping", help="book2files.json שחושב מראש (דילוג על סריקת המאגר)")
    p.add_argument("--seforim-db", help="seforim.db לבניית רשימת קטגוריות ספריא")
    p.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args(argv)
    return {"detect": cmd_detect, "import": cmd_import, "reconcile": cmd_reconcile, "sort": cmd_sort,
            "links-guard": cmd_links_guard, "report": cmd_report, "bootstrap": cmd_bootstrap,
            "verify-raw": cmd_verify_raw, "fp-index": cmd_fp_index}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
