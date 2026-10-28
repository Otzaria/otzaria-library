#!/usr/bin/env python3
"""The ForDB archive: which files ship, and the deterministic zip of them.

validate-fordb-book-names.yml builds the candidate archive and update-fordb.yml the
published one; both call this file, so the two can no longer disagree about what is in
it (two inline copies of the exclusion list did, four runs in a row, on 2026-10-25).

    fordb_archive.py build OUT.zip          coverage check, then the archive
    fordb_archive.py same-content REV REV   exit 0 same ForDB files, 3 different, anything else = error

Coverage: every shipped file must be in SHIPPED, the files that a runtime consumer in
SeforimLibrary reads and validateForDbInputs checks.  A new file fails here until it is
added (with its consumer) or listed in NOT_SHIPPED.

The archive is a pure function of file names and bytes: stored entries, a fixed
timestamp and mode, bytewise path order.  Runner zlib upgrades and source mtimes cannot
mint a different digest, so the digest is the content address of the release.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = "ForDB"
DIFFERENT = 3  # same-content: a distinct code, so a crash (1) is never read as "main changed"
SHIPPED = frozenset({
    "ForDB/all_metadata.json",
    # טבלאות banner / book_banner / book_protection; קובץ חסר מפיל את הבנייה.
    "ForDB/book_banners.csv",
    # מידע על ספרים מהאתר; מקור הדור של seedGenerations (במקום generations.csv).
    "ForDB/book_info.csv",
    "ForDB/book_moves.csv",
    "ForDB/book_protection.csv",
    "ForDB/book_renames.csv",
    "ForDB/category_moves.csv",
    "ForDB/category_renames.csv",
    # שם המפרש כישות (book.collectiveTitleHe/En) לספרים שאינם מספריא; קובץ חסר = אין מילוי.
    "ForDB/commentator_collective_titles.csv",
    # קודש/חול בתנ"ך ל-line_divine_name; קובץ חסר מפיל את הבנייה.
    "ForDB/divine_name_overrides.csv",
    "ForDB/sefaria_author_changes.csv",
    "ForDB/sefaria_category_changes.csv",
    "ForDB/sefaria_metadata_changes.csv",
})
NOT_SHIPPED = frozenset({
    # יומן הזהות של האתר; נבדק במאמת ואינו נצרך בבנייה.
    "ForDB/book_info_identity.json",
    # כללי העריכה, לבני אדם.
    "ForDB/README.md",
})


def is_shipped_path(path: str) -> bool:
    """A repository path under ForDB/ that goes into the archive (before the coverage check)."""
    return path.startswith(ROOT + "/") and path.rsplit("/", 1)[-1] != ".DS_Store" and path not in NOT_SHIPPED


def archive_paths(repo: Path) -> list[str]:
    """The files of the working tree that go into the archive, in archive order."""
    root = repo / ROOT
    if not root.is_dir():
        raise SystemExit(f"Source directory '{ROOT}' not found.")
    found = [p for p in root.rglob("*") if is_shipped_path(p.relative_to(repo).as_posix())]
    if any(p.is_symlink() for p in found):
        raise SystemExit("ForDB archive refuses symlinks")
    return sorted((p.relative_to(repo).as_posix() for p in found if p.is_file()), key=str.encode)


def check_coverage(paths) -> None:
    actual = set(paths)
    if actual != SHIPPED:
        raise SystemExit(
            "ForDB consumer coverage is incomplete; "
            f"missing={sorted(SHIPPED - actual)}, files without a runtime validator={sorted(actual - SHIPPED)}"
        )


def build(repo: Path, out: Path) -> list[str]:
    paths = archive_paths(repo)
    check_coverage(paths)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in paths:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, (repo / path).read_bytes())
    return paths


def shipped_blobs(repo: Path, rev: str) -> dict[str, str]:
    """path -> blob id of the shipped ForDB files at a commit.  Reads trees only (no blobs)."""
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "-z", "--full-tree", rev, "--", ROOT + "/"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    blobs = {}
    for entry in filter(None, out.split("\0")):
        meta, _, path = entry.partition("\t")
        mode, kind, oid = meta.split()
        if kind != "blob":
            continue
        if mode == "120000" and is_shipped_path(path):
            raise SystemExit(f"ForDB archive refuses symlinks ({rev}:{path})")
        if is_shipped_path(path):
            blobs[path] = oid
    return blobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="command", required=True)
    build_cmd = sub.add_parser("build", help="check coverage and write the archive")
    build_cmd.add_argument("out", type=Path)
    same = sub.add_parser("same-content", help="exit 0 when two commits ship the same ForDB files")
    same.add_argument("rev", nargs=2)
    args = parser.parse_args(argv)
    if args.command == "build":
        paths = build(args.repo, args.out)
        print(f"{args.out}: {len(paths)} files")
        return 0
    left, right = (shipped_blobs(args.repo, rev) for rev in args.rev)
    if left == right:
        print(f"{args.rev[0]} and {args.rev[1]} ship the same ForDB files")
        return 0
    changed = sorted(p for p in left.keys() | right.keys() if left.get(p) != right.get(p))
    print(f"ForDB differs between {args.rev[0]} and {args.rev[1]}: {', '.join(changed)}")
    return DIFFERENT


if __name__ == "__main__":
    sys.exit(main())
