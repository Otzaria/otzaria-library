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

Byte contract
-------------
``ManualLinksDocument.read`` rejects a UTF-8 BOM, any CR, and more than one
trailing LF before it even parses the JSON.  Those are reproduced verbatim here:
a file saved with Windows line endings aborts the weekly sync just as late as a
missing ref_2, and the diff that introduces it is invisible in review.

Ref shape
---------
``resolveRef`` looks a ref up in ``refsByRef``, whose keys the generator builds
as ``<prefix><numeric address>``.  The prefix is *not* derivable from the ref
text: a comma may separate a node (``Zohar Chadash`` + ``Vaetchanan`` ->
``"Zohar Chadash, Vaetchanan,  "``, comma and two spaces) or may belong to the
book's own title (``"Shulchan Arukh, Orach Chayim "`` is one simple-schema book,
single space).  ``.github/data/sefaria_ref_prefixes.tsv`` is a snapshot of every
legal prefix, produced from the export by ``refresh_sefaria_ref_prefixes.py``.

A ref that exactly matches a known prefix plus a numeric address is accepted.
One that matches no prefix even after collapsing separators is *skipped* -- it
names a book this snapshot does not know, and inventing a failure there would be
guessing.  Only the middle case fails: the ref names a prefix we do know but
spells its separators differently, which is precisely the Sefaria-canonical form
(``Zohar Chadash, Vaetchanan 1``) that resolves to zero rows.

Offsets
-------
For a node carrying ``index_offsets_by_depth`` the generator adds the offset to
the *English* paragraph number and not to the Hebrew heRef, so heRef
``ספר הזהר, נח,  טז, א`` is ref ``Zohar, Noach,  16:122`` and never ``16:1``.
A legal paragraph is therefore always greater than its section's offset; a
smaller one is impossible, so rejecting it cannot produce a false failure.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG_NAME = "manual_links_sync.json"
PACKAGING_NAME = "manual_links_packaging.py"


TITLES_PATH = ".github/data/sefaria_he_titles.txt"
PREFIXES_PATH = ".github/data/sefaria_ref_prefixes.tsv"

# The address the generator appends after a prefix: integers, or a Talmud daf
# such as "2a", joined by ":" (see toEnglishDaf / shiftedIdx).
ADDRESS_RE = re.compile(r"\d+[ab]?(?::\d+[ab]?)*$")
# Separator-insensitive view of a prefix: every run of commas and spaces becomes
# a single space. Two prefixes that differ only in punctuation collapse together,
# which is exactly the confusion this gate exists to catch.
SEPARATORS_RE = re.compile(r"[,\s]+")


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


def ref_prefixes(workspace: Path) -> dict[str, list[int]] | None:
    """Legal ref prefixes mapped to their offsets, or None when absent.

    Returning None (not an empty dict) keeps a missing snapshot a no-op, the same
    way the title list behaves: a gate that cannot see the corpus must stay quiet.
    """
    path = workspace / PREFIXES_PATH
    if not path.is_file():
        return None
    table: dict[str, list[int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        prefix, _, offsets = line.partition("\t")
        if not prefix:
            continue
        table[prefix] = [int(v) for v in offsets.split(",")] if offsets else []
    return table or None


@functools.cache
def collapsed(text: str) -> str:
    return SEPARATORS_RE.sub(" ", text).strip()


def check_ref_shape(
    where: str, ref: str, prefixes: dict[str, list[int]]
) -> list[str]:
    """Reject a ref the generator could never have emitted. Never guess."""
    problems: list[str] = []
    exact = [p for p in prefixes if ref.startswith(p) and ADDRESS_RE.fullmatch(ref[len(p):])]
    if not exact:
        stem = ref[: ref.rfind(" ") + 1] if " " in ref else ""
        # Find the prefix the author meant, ignoring how they punctuated it. A
        # hit here is proof of a wrong spelling, not a guess about a new book.
        near = sorted({p for p in prefixes if collapsed(p) == collapsed(stem)})
        if near:
            suggestion = near[0] if len(near) == 1 else " | ".join(near)
            problems.append(
                f"{where}: ref {ref!r} is not the form the generator emits; "
                f"resolveRef would find 0 rows. Expected prefix {suggestion!r} "
                f"(note the exact commas and spaces)"
            )
        # No near match at all: a book outside this snapshot. Stay silent.
        return problems

    prefix = max(exact, key=len)
    offsets = prefixes[prefix]
    address = ref[len(prefix):].split(":")
    if offsets and len(address) == 2 and address[0].isdigit() and address[1].isdigit():
        section, paragraph = int(address[0]), int(address[1])
        if section > len(offsets):
            problems.append(
                f"{where}: ref {ref!r} names section {section} but "
                f"{prefix!r} has only {len(offsets)}"
            )
        elif paragraph <= offsets[section - 1]:
            problems.append(
                f"{where}: ref {ref!r} ignores index_offsets_by_depth -- section "
                f"{section} starts after {offsets[section - 1]}, so the first "
                f"paragraph is {offsets[section - 1] + 1}, not {paragraph}. The "
                f"offset applies to the English ref only, never to heRef"
            )
    return problems


def check_bytes(workspace: Path, path: str) -> list[str]:
    """Mirror ``ManualLinksDocument.read``'s pre-parse gate, byte for byte."""
    try:
        raw = (workspace / path).read_bytes()
    except OSError as exc:
        return [f"{path}: cannot read ({exc})"]
    problems: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append(f"{path}: UTF-8 BOM is forbidden")
    if b"\r" in raw:
        lines = raw.count(b"\r")
        problems.append(
            f"{path}: CRLF/CR is forbidden ({lines} line(s)); save with LF endings"
        )
    trailing = len(raw) - len(raw.rstrip(b"\n"))
    if trailing > 1:
        problems.append(f"{path}: more than one trailing LF ({trailing})")
    return problems


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


def assert_roots_intact(workspace: Path, config: dict) -> None:
    """Reuse the packaging scan, which is the same structural contract the sync runs.

    Deletions carry no records to validate, but deleting a required root's last
    file (or renaming the root away) aborts ``refreshManualLinks`` just as late as
    a missing ref_2 does, and no per-file check can see it.
    """
    packaging_module().scan_roots(workspace, config)


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
    """Link files that exist at head and differ from ``base``.

    Only new/edited files are inspected: records already on main are the
    lineage's problem, not this pull request's.
    """
    # Lowercase ``d`` selects every change except a deletion. Enumerating A/M is
    # what let a renamed-and-rewritten file (git says R) through unvalidated;
    # ``--name-only`` reports the destination path, so the decoding is unchanged.
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=d", "-z", base, "--"],
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


def check_file(
    workspace: Path,
    path: str,
    sefaria: set[str],
    prefixes: dict[str, list[int]] | None = None,
) -> list[str]:
    # The byte gate runs before parsing, exactly as the tool does: a CR makes the
    # document illegal even though json.loads is perfectly happy with it.
    byte_problems = check_bytes(workspace, path)
    try:
        records = json.loads((workspace / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return byte_problems + [f"{path}: cannot parse ({exc})"]
    if not isinstance(records, list):
        return [f"{path}: top level must be an array"]

    problems: list[str] = list(byte_problems)
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(f"{path}[{index}]: record must be an object")
            continue
        if "ref_1" in record and "ref_2" in record:
            problems.append(f"{path}[{index}]: has both ref_1 and ref_2")
        if prefixes is not None:
            for field in ("ref_1", "ref_2"):
                value = record.get(field)
                if isinstance(value, str) and value:
                    problems.extend(
                        check_ref_shape(f"{path}[{index}].{field}", value, prefixes)
                    )
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
    config = load_config(workspace)
    assert_roots_intact(workspace, config)
    files = changed_link_files(workspace, args.base, synced_roots(config))
    if not files:
        print("No added or modified manual-link files; nothing to validate.")
        return 0

    sefaria = sefaria_he_titles(workspace)
    if sefaria is None:
        print(f"{TITLES_PATH} is missing; skipping (no guess is better than a wrong one).")
        return 0

    prefixes = ref_prefixes(workspace)
    if prefixes is None:
        print(f"{PREFIXES_PATH} is missing; ref shapes are not checked this run.")

    problems: list[str] = []
    for path in files:
        problems.extend(check_file(workspace, path, sefaria, prefixes))

    known = len(prefixes) if prefixes else 0
    print(
        f"Validated {len(files)} manual-link file(s) against {len(sefaria)} Sefaria "
        f"titles and {known} ref prefixes."
    )
    if not problems:
        print("OK: byte contract, ref shapes and ref_2 ownership all hold.")
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
