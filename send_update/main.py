import codecs
import subprocess
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pyluach import dates

TZ = ZoneInfo("Asia/Jerusalem")
VERSION_FILE = "MoreBooks/ספרים/אוצריא/אודות התוכנה/גירסת ספריה.txt"
DEEPEN_STEP = 25
DEEPEN_MAX = 200
DEEPEN_RETRIES = 2          # extra attempts per step; 3 fetches in all before going red
DEEPEN_BACKOFF_SECONDS = 3  # multiplied by the attempt number: 3s, then 6s


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")


def is_shallow_repository() -> bool:
    return run_git("rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def commits_in_view() -> int:
    count = run_git("rev-list", "--count", "HEAD").stdout.strip()
    return int(count) if count.isdigit() else 0


def find_version_commit_sha() -> str:
    cmd = ["git", "log", "--grep=גרסת ספרייה", "-n", "1", "--pretty=%H"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip()


def deepen_history() -> subprocess.CompletedProcess:
    """One deepening step, retried before it is allowed to fail the prepare child.

    Failing here turns the whole cycle red (the weekly head watches this child), so a
    transient runner-side fetch failure must not be treated like the genuine "no version
    commit in range" answer below. `--no-tags` keeps every step from re-negotiating the
    ~87 saga handoff tags this repository carries; deepening only needs commits."""
    for attempt in range(1, DEEPEN_RETRIES + 2):
        result = run_git("fetch", "--no-tags", f"--deepen={DEEPEN_STEP}")
        if result.returncode == 0:
            return result
        if attempt <= DEEPEN_RETRIES:
            print(f"Warning: git fetch --no-tags --deepen={DEEPEN_STEP} failed (attempt {attempt}/{DEEPEN_RETRIES + 1}), retrying: {result.stderr.strip()}")
            time.sleep(DEEPEN_BACKOFF_SECONDS * attempt)
    return result


def get_last_version_commit_sha() -> str:
    sha = find_version_commit_sha()
    if sha:
        return sha

    # The checkout is a fixed shallow window (update-library.yml fetch-depth), and inside
    # one every path looks created by the boundary commit — so the VERSION_FILE fallback
    # would answer with the boundary instead of the real previous version. Deepen until
    # the commit is genuinely in view; a wrong BEFORE_SHA writes a wrong diff into
    # "עדכוני ספריה.md" on a green build.
    depth = DEEPEN_STEP
    while depth < DEEPEN_MAX and is_shallow_repository():
        deepen = deepen_history()
        if deepen.returncode != 0:
            print(f"::error::git fetch --no-tags --deepen={DEEPEN_STEP} failed {DEEPEN_RETRIES + 1} times while searching for the previous 'גרסת ספרייה' commit: {deepen.stderr.strip()}")
            raise SystemExit(1)
        depth += DEEPEN_STEP
        sha = find_version_commit_sha()
        if sha:
            print(f"Info: found the previous 'גרסת ספרייה' commit after deepening the history to {commits_in_view()} commits")
            return sha

    complete = not is_shallow_repository()
    if complete:
        cmd = ["git", "log", "-n", "1", "--pretty=%H", "--", VERSION_FILE]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        sha = result.stdout.strip()
        if sha:
            print(f"Warning: no 'גרסת ספרייה' commit found, using last commit that modified {VERSION_FILE}")
            return sha

    searched = "the full history" if complete else f"the newest {commits_in_view()} commits"
    print(f"::error::no 'גרסת ספרייה' commit and no usable {VERSION_FILE} fallback in {searched}; refusing to fall back to HEAD^ and publish a wrong update range")
    raise SystemExit(1)


BEFORE_SHA = get_last_version_commit_sha()
AFTER_SHA = "HEAD"

folders = [
    "Ben-YehudaToOtzaria/ספרים/אוצריא",
    "DictaToOtzaria/ערוך/ספרים/אוצריא",
    "OnYourWayToOtzaria/ספרים/אוצריא",
    "OraytaToOtzaria/ספרים/אוצריא",
    "tashmaToOtzaria/ספרים/אוצריא",
    # "sefariaToOtzaria/sefaria_export/ספרים/אוצריא",
    # "sefariaToOtzaria/sefaria_api/ספרים/אוצריא",
    "MoreBooks/ספרים/אוצריא",
    "KSK/ספרים/אוצריא",
    "wikiJewishBooksToOtzaria/ספרים/אוצריא",
    "ToratEmetToOtzaria/ספרים/אוצריא",
    "wikisourceToOtzaria/ספרים/אוצריא",
    "pninimToOtzaria/ספרים/אוצריא",
    "yam-HaHachmaToOtzaria/ספרים/אוצריא",
    "National-LibraryToOtzaria/ספרים/אוצריא",
]


def heb_date() -> str:
    return dates.HebrewDate.from_pydate(datetime.now(tz=TZ).date()).hebrew_date_string()


def decode_git_output_line(line: str) -> str:
    return codecs.escape_decode(line.strip())[0].decode("utf-8").strip('''"''')


def dedupe_preserving_order(paths: Sequence[str]) -> list[str]:
    """Keep the first occurrence of every path, in the order the diffs produced it.

    The announcement is read by people, so the order the two diffs below produce is
    part of the message; a set would scramble it and sorting would not match the
    other three sections."""
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def get_moves_from_outside(folders: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    cmd = ["git", "diff", "--name-status", "--diff-filter=R", BEFORE_SHA, AFTER_SHA]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    raw_output = result.stdout.strip()
    from_external_moves = []
    internal_moves = []
    to_external_moves = []
    for line in raw_output.split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            old_name = decode_git_output_line(parts[1])
            new_name = decode_git_output_line(parts[2])
            if not (new_name.lower().endswith(".txt") and not new_name.lower().endswith("גירסת ספריה.txt")):
                continue
            new_name_rel = new_name.split("אוצריא/")[-1]
            old_name_rel = old_name.split("אוצריא/")[-1]
            dest_is_watched = any(new_name.startswith(f) for f in folders)
            src_is_watched = any(old_name.startswith(f) for f in folders)
            if dest_is_watched and not src_is_watched:
                from_external_moves.append(new_name_rel)
            elif dest_is_watched and src_is_watched and new_name_rel != old_name_rel:
                internal_moves.append(f"{old_name_rel} -> {new_name_rel}")
            elif not dest_is_watched and src_is_watched:
                to_external_moves.append(old_name_rel)
    return from_external_moves, internal_moves, to_external_moves


def get_changed_files(status_filter: str, folders: Sequence[str]) -> list[str]:
    cmd = ["git", "diff", "--name-only", f"--diff-filter={status_filter}", BEFORE_SHA, AFTER_SHA, "--", *folders]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    raw_output = result.stdout.strip()
    decoded_files = []
    for line in raw_output.split("\n"):
        if not line:
            continue
        decoded_line = decode_git_output_line(line)
        if not decoded_line.lower().endswith(".txt") or decoded_line.lower().endswith("גירסת ספריה.txt"):
            continue
        book_rel_path = decoded_line.split("אוצריא/")[-1]
        decoded_files.append(book_rel_path)
    return decoded_files


added_files = get_changed_files("A", folders)
modified_files = get_changed_files("M", folders)
deleted_files = get_changed_files("D", folders)
from_external_moves, renamed_files, to_external_moves = get_moves_from_outside(folders)
# A rename that crosses the watched-folder boundary is reported TWICE.  get_changed_files
# runs its diff under a `-- folders` pathspec, and git cannot pair a rename whose other
# half the pathspec removed, so the half that is inside already appears there as a plain
# A or D; get_moves_from_outside then names that same path again from the unrestricted
# rename diff.  Union the two views instead of appending one to the other: version 168
# published 4 bullets for 2 deleted files, both of them
# DictaToOtzaria/…/שות אגודת אזוב… moved to extraBooks/….
deleted_files = dedupe_preserving_order(deleted_files + to_external_moves)
added_files = dedupe_preserving_order(added_files + from_external_moves)
modified_files = dedupe_preserving_order(modified_files)
renamed_files = dedupe_preserving_order(renamed_files)
date = heb_date()
# Four bare list reprs cannot be told apart in a log; the duplicate delete above was
# visible in one of them a full step before it was published.
print(f"added: {added_files}")
print(f"modified: {modified_files}")
print(f"deleted: {deleted_files}")
print(f"renamed: {renamed_files}")

info_folder_path = Path(__file__).parent.parent / "MoreBooks" / "ספרים" / "אוצריא" / "אודות התוכנה"
ver_file_path = info_folder_path / "גירסת ספריה.txt"
with ver_file_path.open("r", encoding="utf-8") as f:
    library_ver = int(f.read()) + 1

if any([added_files, modified_files, deleted_files, renamed_files]):
    content = ""
    if added_files:
        separator = "\n* "
        content += f"\n## התווספו הקבצים הבאים:\n* {separator.join(added_files)}\n"
    if modified_files:
        separator = "\n* "
        content += f"\n## השתנו הקבצים הבאים:\n* {separator.join(modified_files)}\n"
    if renamed_files:
        separator = "\n* "
        content += f"\n## שונה מיקום/שם של הקבצים הבאים:\n* {separator.join(renamed_files)}\n"
    if deleted_files:
        separator = "\n* "
        content += f"\n## נמחקו הקבצים הבאים:\n* {separator.join(deleted_files)}\n"
    print(content)
    content_text = f"# גירסת ספרייה {library_ver} \n" + f"\n**עדכון {date}**\n" + content
    md_file_path = info_folder_path / "עדכוני ספריה.md"
    existing_text = ""
    if md_file_path.exists():
        existing_text = md_file_path.read_text(encoding="utf-8").lstrip("\ufeff")
    md_file_path.write_text(f"{content_text}\n---\n" + existing_text, encoding="utf-8")
