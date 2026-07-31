#!/usr/bin/env python3
"""Fail a PR that adds manual-link records the weekly sync cannot resolve.

The weekly saga refuses to guess a stable Sefaria identifier: a new record whose
target is a Sefaria-owned book but which carries no ``ref_2`` aborts
``refreshManualLinks`` with ``new_target_ref_required`` -- after the Sefaria
export has already been downloaded and long before the DB is built.  That is an
expensive, late, and confusing place to learn about a malformed record.

This check reproduces the *decidable* part of that contract locally, so the same
mistake fails in seconds on the pull request that introduces it.

Ownership rule
--------------
This mirrors ``targetTitleOrNull`` + ``primaryHeTitleCount`` in SeforimLibrary:
the ``path_2`` basename (minus ``.txt``) is looked up **verbatim** against the
Hebrew titles of the Sefaria corpus.  The comparison is deliberately exact --
no gershayim folding -- because that is what the tool does.  A target spelled
``רשי על יבמות`` is therefore NOT Sefaria's ``רש"י על יבמות``; it is the local
Otzaria copy, needs no ``ref_2``, and adding one would make the weekly sync fail
with ``ref_2 side classification changed``.

The Sefaria title list is read from a checked-in snapshot
(``.github/data/sefaria_he_titles.txt``) because the multi-gigabyte export is
not available to a pull-request runner.  When the snapshot is missing the check
degrades to a no-op rather than guessing, so it can never invent a failure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

CONFIG_NAME = "manual_links_sync.json"


TITLES_PATH = ".github/data/sefaria_he_titles.txt"


def sefaria_he_titles(workspace: Path) -> set[str] | None:
    """Hebrew titles owned by Sefaria, or None when the snapshot is absent."""
    path = workspace / TITLES_PATH
    if not path.is_file():
        return None
    titles = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            titles.add(line)
    return titles or None


def synced_roots(workspace: Path) -> list[str]:
    """Link roots the weekly sync validates, excluding adapter-backed ones.

    A root listed in ``bootstrap_adapters`` derives its refs from ``heRef_2``
    through a deterministic adapter instead of a literal ``ref_2``, so a missing
    ``ref_2`` there is not decidable from this repository alone.
    """
    config = json.loads((workspace / CONFIG_NAME).read_text(encoding="utf-8"))
    adapters = set(config.get("bootstrap_adapters", {}))
    return [
        entry["path"]
        for entry in config["links_roots"]
        if entry["expected_state"] == "present" and entry["path"] not in adapters
    ]


def changed_link_files(workspace: Path, base: str, roots: list[str]) -> list[str]:
    """Link files added or modified relative to ``base``.

    Only new/edited files are inspected: records already on main are the
    lineage's problem, not this pull request's.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", "-z", base, "--"],
        cwd=workspace,
        capture_output=True,
        check=True,
    )
    changed = [item for item in result.stdout.decode("utf-8").split("\0") if item]
    prefixes = tuple(root + "/" for root in roots)
    return [
        path
        for path in changed
        if path.startswith(prefixes) and path.endswith("_links.json")
    ]


def target_title(target: str) -> str:
    """Book title addressed by a ``path_2`` value.

    Mirrors ``targetTitleOrNull``: take the last path component and drop the
    ``.txt`` suffix.  Values appear both bare (``יבמות.txt``) and as relative
    paths; historical records use Windows separators
    (``אוצריא\\תנך\\תורה\\שמות.txt``), so both are handled.
    """
    name = target.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".txt") else name


def check_file(workspace: Path, path: str, sefaria: set[str]) -> list[str]:
    try:
        records = json.loads((workspace / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: cannot parse ({exc})"]
    if not isinstance(records, list):
        return [f"{path}: top level must be an array"]

    problems: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(f"{path}[{index}]: record must be an object")
            continue
        if "ref_1" in record and "ref_2" in record:
            problems.append(f"{path}[{index}]: has both ref_1 and ref_2")
        target = record.get("path_2")
        if not isinstance(target, str) or not target:
            problems.append(f"{path}[{index}]: missing path_2")
            continue

        owned = target_title(target) in sefaria
        if owned and "ref_2" not in record:
            problems.append(
                f"{path}[{index}]: new_target_ref_required -- target {target!r} is "
                f"Sefaria-owned, so the record must carry a stable ref_2"
            )
        elif not owned and "ref_2" in record:
            # The mirror image, and just as fatal: the tool rejects a ref_2 whose
            # target it does not consider Sefaria-owned.
            problems.append(
                f"{path}[{index}]: ref_2 side classification changed -- target "
                f"{target!r} is not a Sefaria book, so it must not carry ref_2"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    parser.add_argument(
        "--base",
        required=True,
        help="commit/ref to diff against (usually the PR base)",
    )
    parser.add_argument(
        "--max-report",
        type=int,
        default=25,
        help="maximum individual problems to print",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    roots = synced_roots(workspace)
    files = changed_link_files(workspace, args.base, roots)
    if not files:
        print("No added or modified manual-link files; nothing to validate.")
        return 0

    sefaria = sefaria_he_titles(workspace)
    if sefaria is None:
        print(f"{TITLES_PATH} is missing; skipping (no guess is better than a wrong one).")
        return 0

    problems: list[str] = []
    for path in files:
        problems.extend(check_file(workspace, path, sefaria))

    print(
        f"Validated {len(files)} manual-link file(s) "
        f"against {len(sefaria)} Sefaria titles."
    )
    if not problems:
        print("OK: ref_2 presence matches Sefaria ownership on every record.")
        return 0

    for problem in problems[: args.max_report]:
        print(f"::error::{problem}")
    if len(problems) > args.max_report:
        print(f"::error::... and {len(problems) - args.max_report} more problem(s).")
    print(
        "\nThe weekly sync refuses to guess stable Sefaria identifiers. "
        "See docs/קישורים-וכותרות.md chapter 9 for the required ref_2 format.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
