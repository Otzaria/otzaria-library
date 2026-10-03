# -*- coding: utf-8 -*-
"""מעקב אחרי שינויי-שם של קבצי ספרים נארזים, לתוך כל קובץ שמזהה ספר לפי שמו.

למה: שם ספר אוצריא ב-DB הוא שם הקובץ. מי שמשנה שם קובץ ולא מעדכן את ForDB משאיר
שורות שמצביעות על שם שכבר אינו קיים. validate_fordb_book_names.py --fix מסיר אז את
שורת generations.csv כ"יתומה" (כך נמחקה ב-bccfea27 השורה של 'אמת ואמונה - מנחם מנדל
מקוצק' אחרי ש-e6bb6a79 שינה את שם הקובץ ל'אמת ואמונה'), והמטא-דאטה (מחבר, תיאור,
שנת דפוס) והקישורים הידניים נשארים בשם הישן ונופלים בשקט.

המודול מזהה, מתוך ההיסטוריה שטרם אומתה, קובץ ספר נארז ששמו שונה, ומשכתב את השם הישן
לשם החדש בכל הקבצים שמזהים ספר לפי שם — במקום שהשורה תימחק.

כללי זהירות (כל אחד מהם נבדק ב-test_fordb_book_renames.py):
  * רק שינוי-שם שזוהה ב-git (R, דמיון >= RENAME_SIMILARITY) בין שני נתיבים *נארזים*.
    העברה ל-extraBooks, מחיקה או פיצול לכמה ספרים אינם שינוי-שם, והשורה מוסרת כמקודם.
  * השם הישן חייב להיות מת (אינו book.title של אף ספר ב-DB) והחדש חי ב-HEAD.
  * שם ישן שמוביל ליותר מיעד אחד, או שמעורב ב-book_renames.csv, או שהקישורים שלו
    מתנגשים בקובץ קיים — אינו מוחלף וגם *אינו נמחק*: הוא מדווח ומפיל את הריצה.
  * כל קובץ נערך בטוקן בלבד (שאר הבתים נשמרים כלשונם), ואחרי העריכה נקרא מחדש
    ומושווה למבנה הצפוי. סטייה כלשהי מפילה את הריצה לפני כתיבה.
"""

import csv
import io
import json
import os
import re
import subprocess
from dataclasses import dataclass, field

# דמיון מינימלי ל-rename. 50% של git מתיר לזווג ספר שהועבר עם מהדורה אחרת שנוספה
# באותו קומיט; שינוי-שם אמיתי כמעט תמיד מעל 90% (e6bb6a79 היה R099 — רק הכותרת שונתה).
RENAME_SIMILARITY = "70%"

# טווח שגדול מזה אינו "הדחיפה הנוכחית" אלא היסטוריה ישנה; עוברים למועמד הבא.
MAX_RANGE_COMMITS = 500

TXT_PATHSPEC = ":(glob)**/*.txt"
LINKS_SUFFIX = "_links.json"


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------
def _git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} נכשל ({result.returncode}): "
            + result.stderr.decode("utf-8", "replace").strip()
        )
    return result


def pick_rename_base(repo, candidates, head="HEAD", max_commits=MAX_RANGE_COMMITS):
    """המועמד הראשון שהוא קומיט קיים, אב של head, ובמרחק סביר ממנו. אחרת None."""
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if not candidate or set(candidate) == {"0"}:
            continue
        resolved = _git(repo, "rev-parse", "--verify", "--quiet", candidate + "^{commit}", check=False)
        if resolved.returncode != 0:
            print(f"[renames] בסיס {candidate[:12]} אינו קומיט זמין; מדלגים")
            continue
        sha = resolved.stdout.decode().strip()
        if _git(repo, "merge-base", "--is-ancestor", sha, head, check=False).returncode != 0:
            print(f"[renames] בסיס {sha[:12]} אינו אב של {head}; מדלגים")
            continue
        count = int(_git(repo, "rev-list", "--count", f"{sha}..{head}").stdout.decode().strip())
        if count > max_commits:
            print(f"[renames] בסיס {sha[:12]} רחוק מדי ({count} קומיטים); מדלגים")
            continue
        return sha
    return None


@dataclass(frozen=True)
class PathEvent:
    commit: str
    status: str  # R / D / A / M (בלי ציון הדמיון)
    path: str  # R: הנתיב הישן
    new_path: str = None  # R בלבד


def _parse_name_status_z(chunks, commit):
    events = []
    i = 0
    while i < len(chunks):
        status = chunks[i]
        if not status:
            i += 1
            continue
        kind = status[0]
        if kind in "RC":
            events.append(PathEvent(commit, kind, chunks[i + 1], chunks[i + 2]))
            i += 3
        else:
            events.append(PathEvent(commit, kind, chunks[i + 1]))
            i += 2
    return [e for e in events if e.status != "C"]


def read_path_events(repo, base, head="HEAD"):
    """אירועי קבצי .txt לכל קומיט בטווח, מהישן לחדש. עובד על partial-clone: git מושך
    רק את ה-blobs שזיהוי שינוי-שם לא-מדויק צריך (קומיט שיש בו גם מחיקה וגם הוספה)."""
    out = _git(
        repo, "log", "--topo-order", "--reverse", f"-M{RENAME_SIMILARITY}", "--name-status",
        "-z", "--format=%x01%H", f"{base}..{head}", "--", TXT_PATHSPEC,
    ).stdout.decode("utf-8")
    events = []
    for block in out.split("\x01"):
        if not block:
            continue
        sha, _, rest = block.partition("\0")
        events.extend(_parse_name_status_z(rest.lstrip("\n").split("\0"), sha.strip()))
    return events


def read_net_renames(repo, base, head="HEAD"):
    """שינויי-שם בין base ל-head כמכלול: תופס מחיקה והוספה שנעשו בקומיטים נפרדים."""
    out = _git(
        repo, "diff", f"-M{RENAME_SIMILARITY}", "--name-status", "-z", base, head, "--", TXT_PATHSPEC,
    ).stdout.decode("utf-8")
    return [e for e in _parse_name_status_z(out.split("\0"), f"{base[:7]}..{head}") if e.status == "R"]


# ---------------------------------------------------------------------------
# פענוח שינויי-השם
# ---------------------------------------------------------------------------
def stem(path):
    return os.path.splitext(path.replace("\\", "/").rsplit("/", 1)[-1])[0]


@dataclass(frozen=True)
class BookRename:
    old_title: str  # שם הקובץ (ללא סיומת) לפני השינוי
    new_title: str  # שם הקובץ ב-HEAD
    old_path: str
    new_path: str
    commit: str
    # אותו מפתח מנוקה, איות אחר (למשל 'הגהות הבח' -> 'הגהות הב”ח'). השורות אינן
    # יתומות, אך נופלות בשקט כי הצרכנים משווים איות מדויק. מותאם לפי איות, לא לפי מפתח.
    respell: bool = False


@dataclass
class RenameResolution:
    # מזהה -> BookRename. המזהה הוא המפתח הישן; ב-respell — האיות הישן כלשונו.
    renames: dict = field(default_factory=dict)
    ambiguous: dict = field(default_factory=dict)  # מפתח ישן -> [נתיבי יעד]
    blocked: dict = field(default_factory=dict)  # מפתח ישן -> סיבה

    @property
    def held_keys(self):
        """מפתחות שאסור למחוק כיתומים: היה להם שינוי-שם, אך לא ניתן להחילו בבטחה."""
        return set(self.ambiguous) | set(self.blocked)


def resolve_renames(
    events, read_net, head_paths, is_db_path, key, is_live_key, rename_keys,
    db_title=None, is_live_spelling=None,
):
    """
    events           - אירועי הקומיטים בסדר כרונולוגי (read_path_events).
    read_net         - מחזירה את שינויי-השם נטו base..head (read_net_renames). נקראת רק
                       כשנשארה שרשרת שנקטעה במחיקה, כי זיהוי לא-מדויק על כל הטווח מושך
                       את ה-blobs של כל הקבצים שנוספו ונמחקו בו.
    head_paths       - כל הנתיבים העקובים ב-HEAD.
    is_db_path       - האם נתיב הוא קובץ ספר שמגיע ל-DB.
    key              - מפתח ההתאמה (sanitize_title).
    is_live_key      - האם מפתח הוא book.title קיים ב-DB (כולל ספריא ו-book_renames).
    rename_keys      - מפתחות שמופיעים ב-book_renames.csv (מקור או יעד).
    db_title         - איות book.title; נדרש לזיהוי respell.
    is_live_spelling - האם איות (db_title) עדיין שייך לספר חי כלשהו, כולל ספריא. בלי
                       פונקציה זו (רשימת ספריא לא זמינה) respell אינו מופעל.
    """
    # origins[נתיב נוכחי] = כל הנתיבים ההיסטוריים שהגיעו אליו בשרשרת R.
    origins = {}
    # הקומיט שבו *שם* הקובץ השתנה (לא העברת תיקייה בהמשך השרשרת) — לדיווח בלבד.
    renamed_in = {}
    chains_gone = []  # שרשראות שהסתיימו במחיקה: [set(נתיבים)]
    for ev in events:
        if ev.status == "R":
            carried = origins.pop(ev.path, set()) | {ev.path}
            origins.setdefault(ev.new_path, set()).update(carried)
            if stem(ev.path) != stem(ev.new_path):
                renamed_in.setdefault(ev.path, ev.commit)
        elif ev.status == "D":
            chains_gone.append(origins.pop(ev.path, set()) | {ev.path})

    candidates = {}  # מפתח ישן -> {נתיב יעד: (נתיב ישן, קומיט)}
    respells = {}  # איות ישן -> {נתיב יעד: (נתיב ישן, קומיט)}

    def offer(old_path, new_path, commit):
        if not is_db_path(old_path) or not is_db_path(new_path) or new_path not in head_paths:
            return
        old_stem, new_stem = stem(old_path), stem(new_path)
        old_key, new_key = key(old_stem), key(new_stem)
        if not old_key or not new_key:
            return
        if old_key != new_key:
            candidates.setdefault(old_key, {}).setdefault(new_path, (old_path, commit))
        elif db_title and db_title(old_stem) != db_title(new_stem):
            respells.setdefault(old_stem, {}).setdefault(new_path, (old_path, commit))

    for current, olds in origins.items():
        for old in olds:
            offer(old, current, renamed_in.get(old, ""))

    # שרשרת שנקטעה במחיקה (מחיקה והוספה בקומיטים נפרדים): רק ה-diff הנטו רואה את הזיווג.
    leftover = {
        key(stem(p)) for chain in chains_gone for p in chain if is_db_path(p)
    } - set(candidates)
    leftover = {k for k in leftover if k and not is_live_key(k)}
    if leftover:
        for ev in read_net():
            if key(stem(ev.path)) not in leftover:
                continue
            chain = next((c for c in chains_gone if ev.path in c), {ev.path})
            for old in chain:
                offer(old, ev.new_path, ev.commit)

    resolution = RenameResolution()
    for old_key, targets in sorted(candidates.items()):
        if is_live_key(old_key):
            continue  # השם הישן עדיין שם של ספר חי: אין מה ליישר
        if len(targets) != 1:
            resolution.ambiguous[old_key] = sorted(targets)
            continue
        (new_path, (old_path, commit)), = targets.items()
        if old_key in rename_keys or key(stem(new_path)) in rename_keys:
            resolution.blocked[old_key] = "השם מופיע ב-ForDB/book_renames.csv"
            continue
        resolution.renames[old_key] = BookRename(stem(old_path), stem(new_path), old_path, new_path, commit)

    # respell הוא תיקון איות בלבד, ולכן לעולם אינו מפיל ואינו מגן על שורות: כשאי אפשר
    # להחילו בבטחה, בדיקת האיות (find_spelling_drift) ממשיכה לדווח עליו כמקודם.
    if is_live_spelling is not None:
        for old_stem, targets in sorted(respells.items()):
            if len(targets) != 1 or is_live_spelling(db_title(old_stem)):
                continue  # עמום, או שהאיות הישן הוא עדיין ספר (למשל כותרת ספריא)
            if key(old_stem) in rename_keys:
                continue
            (new_path, (old_path, commit)), = targets.items()
            resolution.renames[old_stem] = BookRename(
                old_stem, stem(new_path), old_path, new_path, commit, respell=True
            )
    return resolution


# ---------------------------------------------------------------------------
# עריכה בטוקן, עם אימות
# ---------------------------------------------------------------------------
class EditVerificationError(RuntimeError):
    """העריכה לא הניבה בדיוק את המבנה הצפוי; הקובץ לא נכתב."""


def _split_bom(data):
    text = data.decode("utf-8")
    if text.startswith("\ufeff"):
        return "\ufeff", text[1:]
    return "", text


def csv_records(text):
    """מפרק CSV לרשומות עם מיקומי השדות: [(start, end, [(fs, fe, quoted)])].
    end כולל את סוף השורה. שדות מרכאות יכולים להכיל שורות חדשות."""
    records = []
    i, n = 0, len(text)
    while i < n:
        rec_start = i
        fields = []
        while True:
            fs = i
            if i < n and text[i] == '"':
                i += 1
                while True:
                    j = text.find('"', i)
                    if j < 0:
                        raise EditVerificationError("מרכאה לא נסגרה ב-CSV")
                    if j + 1 < n and text[j + 1] == '"':
                        i = j + 2
                        continue
                    i = j + 1
                    break
                fields.append((fs, i, True))
            else:
                while i < n and text[i] not in ',\r\n':
                    i += 1
                fields.append((fs, i, False))
            if i < n and text[i] == ",":
                i += 1
                continue
            if i < n and text[i] not in "\r\n":
                raise EditVerificationError("Unexpected text after quoted CSV field")
            break
        if i < n and text[i] == "\r":
            i += 1
        if i < n and text[i] == "\n":
            i += 1
        records.append((rec_start, i, fields))
    return records


def _csv_value(text, span):
    fs, fe, quoted = span
    raw = text[fs:fe]
    return raw[1:-1].replace('""', '"') if quoted else raw


def _csv_token(value, quoted):
    if quoted or any(c in value for c in ',"\r\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


def _parse_csv(text):
    return [row for row in csv.reader(io.StringIO(text, newline=""), strict=True)]


def edit_csv(data, edits, drop_records=()):
    """edits: {(record_index, field_index): value}; drop_records: אינדקסי רשומות להסרה.
    רשומה 0 היא שורת הכותרת. מחזיר bytes."""
    bom, text = _split_bom(data)
    records = csv_records(text)
    pieces, cursor = [], 0
    drop = set(drop_records)
    for idx, (rs, re_, fields) in enumerate(records):
        if idx in drop:
            pieces.append(text[cursor:rs])
            cursor = re_
            continue
        for f_idx, span in enumerate(fields):
            if (idx, f_idx) in edits:
                pieces.append(text[cursor:span[0]])
                pieces.append(_csv_token(edits[(idx, f_idx)], span[2]))
                cursor = span[1]
    pieces.append(text[cursor:])
    new_text = "".join(pieces)

    # אימות: אותה טבלה בדיוק, עם השינויים המבוקשים בלבד.
    want = []
    for idx, (rs, re_, fields) in enumerate(records):
        if idx in drop:
            continue
        row = [edits.get((idx, f), _csv_value(text, span)) for f, span in enumerate(fields)]
        want.append(row)
    got = _parse_csv(new_text)
    if [r for r in got if r != []] != [r for r in want if r != [""]]:
        raise EditVerificationError("עריכת CSV שינתה יותר מהשדות המבוקשים")
    return (bom + new_text).encode("utf-8")


def sort_csv_records(data, columns):
    """Sort logical data records by exact identity without re-encoding fields."""
    bom, text = _split_bom(data)
    records = csv_records(text)
    if len(records) < 2:
        return data
    header = [_csv_value(text, field) for field in records[0][2]]
    indices = [header.index(column) for column in columns]
    populated = [record for record in records[1:] if len(record[2]) == len(header)]
    ordered = iter(sorted(populated, key=lambda record: tuple(_csv_value(text, record[2][col]) for col in indices)))
    pieces = [bom, text[records[0][0]:records[0][1]]]
    for record in records[1:]:
        current = next(ordered) if len(record[2]) == len(header) else record
        token = text[current[0]:current[1]]
        pieces.append(token if token.endswith(("\n", "\r")) else token + "\n")
    return ''.join(pieces).encode('utf-8')


def _json_string_tokens(text, name):
    pattern = re.compile(r'"' + re.escape(name) + r'"(\s*:\s*)("(?:[^"\\]|\\.)*")')
    return list(pattern.finditer(text))


def _json_token(value, original_token):
    ascii_only = "\\u" in original_token and all(ord(c) < 128 for c in original_token)
    return json.dumps(value, ensure_ascii=ascii_only)


def edit_json_records(data, edits):
    """edits: {(record_index, field_name): value} עבור רשימת רשומות ברמה העליונה.
    רק טוקן הערך מוחלף; שאר הבתים נשמרים. מחזיר bytes."""
    bom, text = _split_bom(data)
    records = json.loads(text)
    if not isinstance(records, list):
        raise EditVerificationError("הקובץ אינו רשימת רשומות")
    replacements = []
    for name in sorted({f for _i, f in edits}):
        owners = [i for i, r in enumerate(records) if isinstance(r, dict) and isinstance(r.get(name), str)]
        tokens = _json_string_tokens(text, name)
        if len(tokens) != len(owners):
            raise EditVerificationError(f"מספר הטוקנים של '{name}' אינו תואם את מספר הרשומות")
        for owner, token in zip(owners, tokens):
            if json.loads(token.group(2)) != records[owner][name]:
                raise EditVerificationError(f"טוקן '{name}' אינו תואם את רשומה {owner}")
            if (owner, name) in edits:
                new_token = _json_token(edits[(owner, name)], token.group(2))
                replacements.append((token.start(2), token.end(2), new_token))
    missing = {(i, f) for i, f in edits} - {
        (i, f) for i, f in edits if isinstance(records[i], dict) and isinstance(records[i].get(f), str)
    }
    if missing:
        raise EditVerificationError(f"שדות לעריכה שאינם מחרוזות: {sorted(missing)}")
    pieces, cursor = [], 0
    for start, end, token in sorted(replacements):
        pieces.append(text[cursor:start])
        pieces.append(token)
        cursor = end
    pieces.append(text[cursor:])
    new_text = "".join(pieces)

    expected = json.loads(text)
    for (i, name), value in edits.items():
        expected[i][name] = value
    if json.loads(new_text) != expected:
        raise EditVerificationError("עריכת JSON שינתה יותר מהשדות המבוקשים")
    return (bom + new_text).encode("utf-8")


# ---------------------------------------------------------------------------
# תכנון השינויים
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CsvTarget:
    path: str
    column: str
    spelling: str  # "db" = איות book.title (db_title); "raw" = שם הקובץ כלשונו
    drop_superseded: bool  # שורה לשם החדש כבר קיימת: למחוק את הישנה (כמו יתומה)


@dataclass(frozen=True)
class JsonTarget:
    path: str
    field: str
    spelling: str
    file_path_field: str = None  # שדה נתיב יחסי תחת אוצריא/ שמתעדכן יחד עם השם


# כל קובץ שמזהה ספר *לפי שם*. תיאור הצרכן של כל אחד:
#   generations / book_moves - SeedGenerations / RenameCategories, התאמה מדויקת ל-book.title.
#   book_info                - מידע על ספרים מהאתר (דור, שנים, מחבר), אותה התאמה. כמה שורות לאותו
#                              ספר (מחברים שונים) תקינות, וכולן עוברות יחד לשם החדש.
#   sefaria_metadata_changes - SeedAllMetadata (תיאור), לפי title.
#   ForDB/all_metadata.json  - SeedAllMetadata (שנת/מקום דפוס), לפי title.
#   metadata.json            - Generator.loadMetadata (מחבר, תיאור), לפי שם הקובץ הגולמי.
#   all_metadata_with_file_paths.json - הרשימה הקנונית של המאמת עצמו (לא מגיע ל-DB).
# קבצי *_links.json בשורשי ה-links הנארזים מטופלים בנפרד (plan_links).
CSV_TARGETS = (
    CsvTarget("ForDB/generations.csv", "שם ספר", "db", True),
    CsvTarget("ForDB/book_info.csv", "bookName", "db", True),
    CsvTarget("ForDB/book_moves.csv", "name", "db", True),
    CsvTarget("ForDB/sefaria_metadata_changes.csv", "title", "db", False),
)
JSON_TARGETS = (
    JsonTarget("ForDB/all_metadata.json", "title", "db"),
    JsonTarget("metadata.json", "title", "raw"),
    JsonTarget("all_metadata_with_file_paths.json", "title", "raw", "file_path"),
)


@dataclass
class Change:
    rename_key: str
    path: str
    kind: str  # renamed / dropped_superseded / kept_conflict / links_file_renamed / links_ref
    detail: str = ""


@dataclass
class RenamePlan:
    writes: dict = field(default_factory=dict)  # נתיב -> bytes
    moves: list = field(default_factory=list)  # [(ישן, חדש)]
    changes: list = field(default_factory=list)
    blocked: dict = field(default_factory=dict)  # מזהה -> סיבה (התגלה בתכנון)

    @property
    def touched(self):
        paths = list(self.writes)
        for old, new in self.moves:
            paths += [old, new]
        return sorted(set(paths))


class _Matcher:
    """איזה שינוי-שם (אם בכלל) חל על ערך נתון: לפי מפתח מנוקה, או ב-respell לפי איות."""

    def __init__(self, renames, key, db_title):
        self.key = key
        self.by_key = {rid: r for rid, r in renames.items() if not r.respell}
        self.by_spelling = {}
        for rid, r in renames.items():
            if r.respell:
                for spelling in {r.old_title, db_title(r.old_title)}:
                    self.by_spelling[spelling] = (rid, r)

    def find(self, value):
        if not isinstance(value, str) or not value:
            return None
        if value in self.by_spelling:
            return self.by_spelling[value]
        k = self.key(value)
        if k in self.by_key:
            return k, self.by_key[k]
        return None


def _title_for(rename, spelling, db_title):
    return db_title(rename.new_title) if spelling == "db" else rename.new_title


def _package_relative(path, prefixes):
    for prefix in prefixes:
        if path.startswith(prefix):
            return path[len(prefix):]
    return None


def _boundary_rewrite(value, old, new):
    """כמו ManualLinksRefresh.rewriteAtTitleBoundary, בלי כשל: מחזיר None כשאין גבול."""
    if value == old:
        return new
    for sep in (" ", ", "):
        if value.startswith(old + sep):
            return new + value[len(old):]
    return None


def _conflicts(rename, target_value, values, key, keyed_values=None):
    """כבר קיימת רשומה נפרדת בשם החדש? ב-respell (אותו מפתח) — רק באיות המדויק."""
    if rename.respell:
        return target_value in values
    return key(target_value) in (keyed_values if keyed_values is not None else {key(v) for v in values})


class _Collisions:
    """שתי רשומות באותו קובץ שהיו מקבלות אותו שם חדש: לא מנחשים איזו נכונה.

    רק כששני שינויי-שם *שונים* מתנקזים לאותו שם. כמה רשומות של אותו שם ישן (ב-book_info:
    שורה לכל מחבר של הספר) עוברות יחד לשם החדש, ואין כאן מה לנחש.
    """

    def __init__(self):
        self.by_target = {}

    def add(self, path, target_value, rid):
        self.by_target.setdefault((path, target_value), []).append(rid)

    def blocked(self):
        out = {}
        for (path, target_value), rids in self.by_target.items():
            if len(set(rids)) > 1:
                for rid in rids:
                    out[rid] = f"כמה רשומות ב-{path} היו מקבלות את השם '{target_value}'"
        return out


def plan_links(repo, roots, renames, key, db_title):
    """שמות קבצי *_links.json ו-path_2/heRef_2 ששייכים לשם הישן, בכל שורשי ה-links הנארזים."""
    matcher = _Matcher(renames, key, db_title)
    writes, moves, changes, blocked = {}, [], [], {}
    listing = {}
    for root in roots:
        folder = os.path.join(repo, root)
        if os.path.isdir(folder):
            listing[root] = sorted(n for n in os.listdir(folder) if n.endswith(LINKS_SUFFIX))
    # manual_links_packaging ממזג את כל השורשים ל-links/ אחד: שם תפוס בכל שורש הוא התנגשות.
    taken = {name for names in listing.values() for name in names}

    for root, names in listing.items():
        for name in names:
            rel = f"{root}/{name}"
            hit = matcher.find(name[: -len(LINKS_SUFFIX)])
            if hit:
                rid, rename = hit
                target = rename.new_title + LINKS_SUFFIX
                if target in taken:
                    blocked[rid] = f"קובץ הקישורים {target} כבר קיים"
                else:
                    moves.append((rel, f"{root}/{target}"))
                    taken.add(target)
                    changes.append(Change(rid, rel, "links_file_renamed", f"{root}/{target}"))
            with open(os.path.join(repo, rel), "rb") as handle:
                data = handle.read()
            records = json.loads(data.decode("utf-8-sig"))
            if not isinstance(records, list):
                continue
            edits = {}
            for idx, record in enumerate(records):
                if not isinstance(record, dict) or not isinstance(record.get("path_2"), str):
                    continue
                path2 = record["path_2"]
                cut = max(path2.rfind("/"), path2.rfind("\\")) + 1
                component = path2[cut:]
                if not component.lower().endswith(".txt"):
                    continue
                old_stem = component[:-4]
                hit = matcher.find(old_stem)
                if not hit:
                    continue
                rid, rename = hit
                if old_stem == rename.new_title:
                    continue
                edits[(idx, "path_2")] = path2[:cut] + rename.new_title + ".txt"
                heref = record.get("heRef_2")
                if isinstance(heref, str):
                    rewritten = _boundary_rewrite(heref, old_stem, rename.new_title)
                    if rewritten is not None:
                        edits[(idx, "heRef_2")] = rewritten
                changes.append(Change(rid, rel, "links_ref", f"רשומה {idx}"))
            if edits:
                writes[rel] = edit_json_records(data, edits)
    return writes, moves, changes, blocked


def _plan_once(repo, renames, db_title, key, db_prefixes, links_roots):
    plan = RenamePlan()
    matcher = _Matcher(renames, key, db_title)
    collisions = _Collisions()

    l_writes, l_moves, l_changes, l_blocked = plan_links(repo, links_roots, renames, key, db_title)
    plan.blocked.update(l_blocked)

    for target in CSV_TARGETS:
        full = os.path.join(repo, target.path)
        if not os.path.exists(full):
            continue
        with open(full, "rb") as handle:
            data = handle.read()
        _bom, text = _split_bom(data)
        records = csv_records(text)
        if not records:
            continue
        header = [_csv_value(text, s) for s in records[0][2]]
        if target.column not in header:
            raise EditVerificationError(f"{target.path}: אין עמודה '{target.column}'")
        col = header.index(target.column)
        values = [_csv_value(text, f[col]) for _s, _e, f in records[1:] if len(f) > col]
        values = set(values)
        keyed_values = {key(v) for v in values}
        author_col = header.index("authorName") if target.path == "ForDB/book_info.csv" else None
        identities = {
            (key(_csv_value(text, f[col])), _csv_value(text, f[author_col]))
            for _s, _e, f in records[1:] if author_col is not None and len(f) > author_col
        }
        exact_identities = {
            (_csv_value(text, f[col]), _csv_value(text, f[author_col]))
            for _s, _e, f in records[1:] if author_col is not None and len(f) > author_col
        }
        identity_rows = {}
        exact_identity_rows = {}
        if author_col is not None:
            for _start, _end, fields in records[1:]:
                if len(fields) != len(header):
                    continue
                row = [_csv_value(text, f) for f in fields]
                identity_rows.setdefault((key(row[col]), row[author_col]), []).append(row)
                exact_identity_rows.setdefault((row[col], row[author_col]), []).append(row)
        edits, drop = {}, []
        for idx, (_s, _e, fields) in enumerate(records[1:], start=1):
            if len(fields) <= col:
                continue
            old_value = _csv_value(text, fields[col])
            hit = matcher.find(old_value)
            if not hit:
                continue
            rid, rename = hit
            new_value = _title_for(rename, target.spelling, db_title)
            if old_value == new_value:
                continue
            conflict = _conflicts(rename, new_value, values, key, keyed_values)
            if author_col is not None:
                author = _csv_value(text, fields[author_col])
                conflict = ((new_value, author) in exact_identities if rename.respell
                            else (key(new_value), author) in identities)
                if conflict:
                    target_rows = (exact_identity_rows.get((new_value, author), []) if rename.respell
                                   else identity_rows.get((key(new_value), author), []))
                    source_row = [_csv_value(text, f) for f in fields]
                    if any(row[:col] + row[col + 1:] != source_row[:col] + source_row[col + 1:]
                           for row in target_rows):
                        plan.blocked[rid] = f"{target.path}: conflicting metadata for author {author!r} at {new_value!r}"
                        continue
            if conflict:
                if target.drop_superseded:
                    drop.append(idx)
                    plan.changes.append(Change(rid, target.path, "dropped_superseded", old_value))
                else:
                    plan.changes.append(Change(rid, target.path, "kept_conflict", old_value))
                continue
            edits[(idx, col)] = new_value
            collisions.add(target.path, new_value, rid)
            plan.changes.append(Change(rid, target.path, "renamed", f"{old_value} -> {new_value}"))
        if edits or drop:
            result = edit_csv(data, edits, drop)
            if author_col is not None:
                result = sort_csv_records(result, ("bookName", "authorName"))
            plan.writes[target.path] = result

    for target in JSON_TARGETS:
        full = os.path.join(repo, target.path)
        if not os.path.exists(full):
            continue
        with open(full, "rb") as handle:
            data = handle.read()
        records = json.loads(data.decode("utf-8-sig"))
        values = [r.get(target.field) for r in records if isinstance(r, dict)]
        values = [v for v in values if isinstance(v, str)]
        values = set(values)
        keyed_values = {key(v) for v in values}
        edits = {}
        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            old_value = record.get(target.field)
            hit = matcher.find(old_value)
            if not hit:
                continue
            rid, rename = hit
            new_value = _title_for(rename, target.spelling, db_title)
            if old_value == new_value:
                continue
            if _conflicts(rename, new_value, values, key, keyed_values):
                plan.changes.append(Change(rid, target.path, "kept_conflict", old_value))
                continue
            edits[(idx, target.field)] = new_value
            collisions.add(target.path, new_value, rid)
            plan.changes.append(Change(rid, target.path, "renamed", f"{old_value} -> {new_value}"))
            fp_field = target.file_path_field
            old_fp = record.get(fp_field) if fp_field else None
            new_rel = _package_relative(rename.new_path, db_prefixes)
            if isinstance(old_fp, str) and new_rel and matcher.find(stem(old_fp)):
                sep = "\\" if "\\" in old_fp or "/" not in old_fp else "/"
                edits[(idx, fp_field)] = new_rel.replace("/", sep)
        if edits:
            plan.writes[target.path] = edit_json_records(data, edits)

    plan.blocked.update(collisions.blocked())
    plan.writes.update(l_writes)
    plan.moves.extend(l_moves)
    plan.changes.extend(l_changes)
    return plan


def plan_renames(repo, renames, db_title, key, db_prefixes, links_roots):
    """מחשב את כל העריכות בזיכרון; דבר לא נכתב לדיסק. הכל-או-כלום לכל שם ישן: שם
    שנחסם (התנגשות קישורים או רשומות) מוצא מהתוכנית כולה, והתכנון חוזר בלעדיו."""
    active = dict(renames)
    blocked = {}
    while True:
        plan = _plan_once(repo, active, db_title, key, db_prefixes, links_roots)
        if not plan.blocked:
            plan.blocked = blocked
            return plan
        removed = [rid for rid in plan.blocked if rid in active]
        if not removed:
            raise EditVerificationError(f"חסימה של שמות שאינם בתוכנית: {sorted(plan.blocked)}")
        for rid in removed:
            blocked[rid] = plan.blocked[rid]
            active.pop(rid)


def find_references(repo, keys, key, links_roots):
    """אילו מהמפתחות מוזכרים בקובץ יעד כלשהו. שם שלא ניתן ליישר בבטחה מפיל את הריצה
    רק כשהוא באמת מוזכר; שינוי-שם עמום של ספר שאף קובץ אינו מזכיר אינו מזיק."""
    keys = set(keys)
    found = set()
    for target in CSV_TARGETS:
        full = os.path.join(repo, target.path)
        if os.path.exists(full):
            with open(full, "rb") as handle:
                _bom, text = _split_bom(handle.read())
            rows = _parse_csv(text)
            if rows and target.column in rows[0]:
                col = rows[0].index(target.column)
                found |= {key(r[col]) for r in rows[1:] if len(r) > col} & keys
    for target in JSON_TARGETS:
        full = os.path.join(repo, target.path)
        if os.path.exists(full):
            with open(full, "rb") as handle:
                records = json.loads(handle.read().decode("utf-8-sig"))
            found |= {key(r.get(target.field)) for r in records if isinstance(r, dict)} & keys
    for root in links_roots:
        folder = os.path.join(repo, root)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith(LINKS_SUFFIX):
                continue
            found |= {key(name[: -len(LINKS_SUFFIX)])} & keys
            with open(os.path.join(folder, name), "rb") as handle:
                records = json.loads(handle.read().decode("utf-8-sig"))
            if isinstance(records, list):
                found |= {
                    key(stem(r["path_2"])) for r in records
                    if isinstance(r, dict) and isinstance(r.get("path_2"), str)
                } & keys
    return found


def apply_plan(repo, plan):
    for rel, data in plan.writes.items():
        with open(os.path.join(repo, rel), "wb") as handle:
            handle.write(data)
    for old, new in plan.moves:
        os.rename(os.path.join(repo, old), os.path.join(repo, new))


# ---------------------------------------------------------------------------
# sparse checkout
# ---------------------------------------------------------------------------
def ensure_in_worktree(repo, paths):
    """ה-workflow עושה sparse-checkout של ForDB/ וה-scripts בלבד. כשיש שינוי-שם לעקוב
    אחריו, מוסיפים לעץ העבודה את metadata.json ואת שורשי ה-links (כ-100MB) — ורק אז.
    בעותק מלא (לא sparse) זו פעולה ריקה."""
    sparse = _git(repo, "config", "--bool", "core.sparseCheckout", check=False).stdout.decode().strip()
    if sparse != "true":
        return
    tracked = set(
        _git(repo, "ls-tree", "-r", "--name-only", "-z", "HEAD").stdout.decode("utf-8").split("\0")
    )
    missing = []
    for rel in paths:
        is_dir = any(p.startswith(rel.rstrip("/") + "/") for p in tracked)
        if (rel in tracked or is_dir) and not os.path.exists(os.path.join(repo, rel)):
            missing.append("/" + rel.rstrip("/") + ("/" if is_dir else ""))
    if missing:
        cone = _git(repo, "config", "--bool", "core.sparseCheckoutCone", check=False).stdout.decode().strip()
        if cone == "true":
            _git(repo, "sparse-checkout", "add", *[m.strip("/") for m in missing])
        else:
            _git(repo, "sparse-checkout", "add", "--skip-checks", *missing)
        print(f"[renames] נוספו ל-sparse-checkout: {', '.join(missing)}")
