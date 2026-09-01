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
This mirrors ``targetTitleOrNull`` + ``SefariaTitleAliases`` + ``primaryHeTitleCount``
in SeforimLibrary: the ``path_2`` basename (minus ``.txt``) is first translated
through the ``he_title_aliases`` map of ``manual_links_sync.json`` -- an explicit,
per-links-root Otzaria-title to Sefaria-heTitle bridge -- and only then looked up
against the Hebrew titles of the Sefaria corpus.  Both steps are exact: there is
no gershayim folding and no guessing anywhere, because that is what the tool does.
Otzaria file names are stripped of gershayim, so a target spelled ``רשי על יבמות``
under a root that declares the alias IS Sefaria's ``רש"י על יבמות`` and therefore
requires a stable ``ref_2``.  Under a root with no such alias the same spelling is
a local Otzaria copy that must not carry one.

The Sefaria title list is read from a checked-in snapshot
(``.github/data/sefaria_he_titles.txt``) because the multi-gigabyte export is
not available to a pull-request runner.  When the snapshot is missing the check
degrades to a no-op rather than guessing, so it can never invent a failure.
"""

from __future__ import annotations

import argparse
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


def load_config(workspace: Path) -> dict:
    """Parse ``manual_links_sync.json`` through the one committed config validator.

    Reusing ``manual_links_packaging.validate_config`` keeps this gate from
    drifting into a private idea of a valid config; an unreadable or invalid
    config raises instead of degrading to a guess.
    """
    path = Path(__file__).resolve().parents[2] / PACKAGING_NAME
    spec = importlib.util.spec_from_file_location("manual_links_packaging", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load the config validator from {path}")
    packaging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packaging)
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


def sefaria_he_title(aliases: dict, path: str, title: str) -> str:
    """Mirrors ``SefariaTitleAliases.sefariaHeTitle``: explicit per-root map only."""
    roots = [root for root in aliases if path.startswith(root + "/")]
    if len(roots) > 1:
        raise SystemExit(f"multiple he_title_aliases roots match {path}")
    if not roots:
        return title
    return aliases[roots[0]].get(title, title)


def alias_problems(aliases: dict, sefaria: set[str]) -> list[str]:
    """An alias that no longer names a Sefaria book fails the weekly sync outright."""
    return [
        f"manual_links_sync.json: he_title_aliases[{root}][{title}] maps to "
        f"{he_title!r}, which is not a Sefaria heTitle"
        for root, entries in aliases.items()
        for title, he_title in entries.items()
        if he_title not in sefaria
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


def check_file(workspace: Path, path: str, sefaria: set[str], aliases: dict) -> list[str]:
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

        owned = sefaria_he_title(aliases, path, target_title(target)) in sefaria
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
    config = load_config(workspace)
    aliases = config["he_title_aliases"]
    files = changed_link_files(workspace, args.base, synced_roots(config))
    sefaria = sefaria_he_titles(workspace)
    if sefaria is None:
        print(f"{TITLES_PATH} is missing; skipping (no guess is better than a wrong one).")
        return 0

    # The alias map is checked even for a config-only PR: a stale alias is fatal to the sync.
    problems: list[str] = alias_problems(aliases, sefaria)
    for path in files:
        problems.extend(check_file(workspace, path, sefaria, aliases))

    print(
        f"Validated {len(files)} manual-link file(s) and "
        f"{sum(len(entry) for entry in aliases.values())} title alias(es) "
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
