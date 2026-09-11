#!/usr/bin/env python3
"""Regenerate the snapshot of legal English ref prefixes from a Sefaria export.

``validate_manual_links_refs.py`` needs to know, for a ref such as
``Zohar, Noach,  16:122``, what the generator would actually have emitted.  That
cannot be derived from the ref string alone: a comma inside a ref may be a node
separator (``Zohar Chadash`` + node ``Vaetchanan``) or simply part of a book's
own title (``Shulchan Arukh, Orach Chayim`` is one simple-schema book).  Only the
export's schemas can tell the two apart.

This script walks every schema exactly the way ``SefariaBookPayloadReader``
builds ``refPrefix``, and writes one line per addressable leaf node:

    <ref prefix><TAB><comma-separated index_offsets_by_depth, or empty>

The prefix is the literal text the generator puts in front of the numeric
address, trailing spaces included -- for a complex schema that is
``"Zohar, Noach,  "`` (comma, two spaces) and for a simple one ``"Genesis "``.
The double space is not a typo: the node loop appends ``", "`` and ``processNode``
then appends one more space before recursing.  Reproducing it here, rather than
normalising it away, is the whole point of the snapshot.

Offsets are recorded only for depth>=2 nodes that carry
``index_offsets_by_depth``; at depth 1 the generator never consults them.

Usage:  .github/scripts/refresh_sefaria_ref_prefixes.py <export-root> [-o <file>]

``<export-root>`` is the directory holding the export's ``schemas/`` folder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUT_DEFAULT = ".github/data/sefaria_ref_prefixes.tsv"

HEADER = [
    "# Legal English ref prefixes of the Sefaria corpus, one per addressable leaf node.",
    "# <ref prefix><TAB><index_offsets_by_depth for depth>=2, comma separated, else empty>",
    "# Trailing spaces in the prefix are significant -- see the generator's refPrefix.",
    "# Regenerate: .github/scripts/refresh_sefaria_ref_prefixes.py <export-root>",
]


def read_index_offsets(node: dict, depth: int) -> list[int] | None:
    """Mirror ``readIndexOffsets``: offsets live under the node's own depth key."""
    table = node.get("index_offsets_by_depth")
    if not isinstance(table, dict):
        return None
    values = table.get(str(depth))
    if not isinstance(values, list):
        return None
    offsets = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    return offsets or None


def walk(node: dict, ref_prefix: str, out: list[tuple[str, list[int] | None]]) -> None:
    """Mirror ``processNode``: recurse through named nodes, emit at leaves."""
    children = node.get("nodes")
    if isinstance(children, list) and children:
        for child in children:
            if not isinstance(child, dict):
                continue
            title = child.get("title") or ""
            key = child.get("key") or ""
            nxt = ref_prefix
            if str(key).lower() != "default" and title.strip():
                nxt = f"{ref_prefix}{title}, "
            walk(child, nxt, out)
        return

    section_names = node.get("sectionNames")
    depth = node.get("depth")
    if not isinstance(depth, int) or isinstance(depth, bool):
        depth = len(section_names) if isinstance(section_names, list) else 0
    if depth <= 0:
        return
    # processNode hands recursiveSections "$refPrefix " -- one extra space.
    out.append((ref_prefix + " ", read_index_offsets(node, depth) if depth >= 2 else None))


def prefixes_for_schema(index: dict) -> list[tuple[str, list[int] | None]]:
    en_title = index.get("title")
    schema = index.get("schema")
    if not isinstance(en_title, str) or not en_title or not isinstance(schema, dict):
        return []
    out: list[tuple[str, list[int] | None]] = []
    children = schema.get("nodes")
    if isinstance(children, list) and children:
        for node in children:
            if not isinstance(node, dict):
                continue
            title = node.get("title") or ""
            key = node.get("key") or ""
            prefix = f"{en_title}, "
            if str(key).lower() != "default" and title.strip():
                prefix = f"{prefix}{title}, "
            walk(node, prefix, out)
    else:
        # The simple-schema branch glues the title with a single space, no comma.
        section_names = schema.get("sectionNames")
        depth = schema.get("depth")
        if not isinstance(depth, int) or isinstance(depth, bool):
            depth = len(section_names) if isinstance(section_names, list) else 0
        if depth > 0:
            out.append((en_title + " ", read_index_offsets(schema, depth) if depth >= 2 else None))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_root", help="directory containing the export's schemas/")
    parser.add_argument("-o", "--output", default=OUT_DEFAULT)
    args = parser.parse_args(argv)

    schema_dir = Path(args.export_root) / "schemas"
    if not schema_dir.is_dir():
        print(f"no schemas/ under {args.export_root}", file=sys.stderr)
        return 2

    rows: dict[str, str] = {}
    files = 0
    for path in sorted(schema_dir.glob("*.json")):
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"skipping {path.name}: {exc}", file=sys.stderr)
            continue
        files += 1
        for prefix, offsets in prefixes_for_schema(index):
            if "\t" in prefix or "\n" in prefix:
                continue
            rows[prefix] = ",".join(str(v) for v in offsets) if offsets else ""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for line in HEADER:
            handle.write(line + "\n")
        for prefix in sorted(rows):
            handle.write(f"{prefix}\t{rows[prefix]}\n")
    print(f"{files} schemas -> {len(rows)} ref prefixes -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
