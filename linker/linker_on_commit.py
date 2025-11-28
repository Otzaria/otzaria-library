import codecs
import subprocess
from collections.abc import Sequence
from pathlib import Path

from linker import link_book


def decode_git_output_line(line: str) -> str:
    return codecs.escape_decode(line.strip())[0].decode("utf-8").strip('''"''')


def get_renamed_files(folders: Sequence[str]) -> list[tuple[str, str]]:
    cmd = ["git", "diff", "--name-status", "--diff-filter=R", "HEAD^", "HEAD", "--", *folders]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    raw_output = result.stdout.strip()
    rename_pairs = []
    for line in raw_output.split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            old_name = decode_git_output_line(parts[1])
            new_name = decode_git_output_line(parts[2])
            if old_name.lower().endswith(".txt") and new_name.lower().endswith(".txt") and not new_name.lower().endswith("גירסת ספריה.txt"):
                rename_pairs.append((old_name, new_name))
    return rename_pairs


def get_changed_files(status_filter: str, folders: Sequence[str]) -> list[str]:
    cmd = ["git", "diff", "--name-only", f"--diff-filter={status_filter}", "HEAD^", "HEAD", "--", *folders]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    raw_output = result.stdout.strip()
    decoded_files = []
    for line in raw_output.split("\n"):
        if not line:
            continue
        decoded_line = decode_git_output_line(line)
        if not decoded_line.lower().endswith(".txt") or decoded_line.lower().endswith("גירסת ספריה.txt"):
            continue
        decoded_files.append(decoded_line)
    return decoded_files


def main() -> None:
    folders = (
        "Ben-YehudaToOtzaria/ספרים/אוצריא",
        "DictaToOtzaria/ערוך/ספרים/אוצריא",
        "OnYourWayToOtzaria/ספרים/אוצריא",
        "OraytaToOtzaria/ספרים/אוצריא",
        "tashmaToOtzaria/ספרים/אוצריא",
        # "sefariaToOtzaria/sefaria_api/ספרים/אוצריא",
        "MoreBooks/ספרים/אוצריא",
        # "wikisourceToOtzaria/ספרים/אוצריא",
        # "wikiJewishBooksToOtzaria/ספרים/אוצריא",
        "ToratEmetToOtzaria/ספרים/אוצריא"
    )
    renamed_files = get_renamed_files(folders)
    for renamed_file in renamed_files:
        src, target = renamed_file
        src_path = Path(src)
        target_path = Path(target)
        src_link = Path(src_path.parts[0]) / "linker_links" / f"{src_path.stem}_links.json"
        target_link = Path(target_path.parts[0]) / "linker_links" / f"{target_path.stem}_links.json"
        if not src_link.exists():
            continue
        target_link.parent.mkdir(parents=True, exist_ok=True)
        src_path.rename(target_link)
    added_files = get_changed_files("A", folders)
    modified_files = get_changed_files("M", folders)
    all_new_links = added_files + modified_files
    for new_file in all_new_links:
        new_file_path = Path(new_file)
        title = " ".join(new_file_path.parts[new_file_path.parts.index("אוצריא") + 1:-1]) + " " + new_file_path.stem
        output_file = Path(new_file_path.parts[0]) / "linker_links" / f"{new_file_path.stem}_links.json"
        link_book(new_file_path, output_file, title)
    deleted_files = get_changed_files("D", folders)
    for deleted_file in deleted_files:
        deleted_file_path = Path(deleted_file)
        deleted_link = Path(deleted_file_path.parts[0]) / "linker_links" / f"{deleted_file_path.stem}_links.json"
        if deleted_link.exists():
            deleted_link.unlink()
