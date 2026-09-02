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
no gershayim folding and no guessing -- because that is what the tool does.  A
target that is Sefaria's own spelling, gershayim included, is Sefaria-owned and
needs a stable ``ref_2``; any other spelling is a local Otzaria copy that must
not carry one.

The Sefaria title list is read from a checked-in snapshot
(``.github/data/sefaria_he_titles.txt``) because the multi-gigabyte export is
not available to a pull-request runner.  When the snapshot is missing the check
degrades to a no-op rather than guessing, so it can never invent a failure.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

CONFIG_NAME = "manual_links_sync.json"
PACKAGING_NAME = "manual_links_packaging.py"


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


@functools.cache
def packaging_module():
    """The single committed implementation of the config and title contracts.

    Reusing it keeps this gate from drifting into a private idea of a valid
    config or of a target title -- that drift is where the ownership bug was born.
    """
    path = Path(__file__).resolve().parents[2] / PACKAGING_NAME
    spec = importlib.util.spec_from_file_location("manual_links_packaging", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load the config validator from {path}")
    packaging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packaging)
    return packaging


def load_config(workspace: Path) -> dict:
    """Parse ``manual_links_sync.json``; an invalid config raises instead of guessing."""
    packaging = packaging_module()
    return packaging.validate_config(packaging.load_json(workspace / CONFIG_NAME))


def synced_roots(config: dict) -> list[str]:
    """Return every root consumed by the recurring manual-link refresh.

    Bootstrap adapters may derive ``ref_2`` only during an explicit, lineage-free
    bootstrap. The weekly refresh is intentionally not allowed to bootstrap new
    records after lineage exists, so a newly added Sefaria target in an adapter
    root still needs a committed stable ``ref_2``.
    """
    return [
        entry["path"]
        for entry in config["links_roots"]
        if entry["expected_state"] == "present"
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

        # Extensionless path_2 values name no book at all, so the tool never owns them.
        title = packaging_module().target_title_or_none(target)
        owned = title is not None and title in sefaria
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
    files = changed_link_files(workspace, args.base, synced_roots(load_config(workspace)))
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

    print(f"Validated {len(files)} manual-link file(s) against {len(sefaria)} Sefaria titles.")
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
