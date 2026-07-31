#!/usr/bin/env python3
"""Regenerate the Sefaria Hebrew-title snapshot used by the manual-link check.

``validate_manual_links_refs.py`` needs to know which book titles Sefaria owns,
but the multi-gigabyte export is not available to a pull-request runner, so the
title list is checked in.  Refresh it from a local export whenever new Sefaria
books start being referenced:

    .github/scripts/refresh_sefaria_he_titles.py /path/to/sefaria/export

The export root is the directory holding both ``json/`` and ``schemas/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUTPUT = Path(".github/data/sefaria_he_titles.txt")
HEADER = (
    "# Hebrew titles of the Sefaria corpus, one per line.\n"
    "# Regenerate: .github/scripts/refresh_sefaria_he_titles.py <export-root>\n"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_root", help="directory containing json/ and schemas/")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(argv)

    schemas = Path(args.export_root) / "schemas"
    if not schemas.is_dir():
        print(f"error: {schemas} is not a directory", file=sys.stderr)
        return 2

    titles: set[str] = set()
    for path in schemas.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        title = data.get("heTitle")
        if isinstance(title, str) and title.strip():
            titles.add(title.strip())

    if not titles:
        print("error: no Hebrew titles found; refusing to write an empty snapshot", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        handle.write(HEADER)
        for title in sorted(titles):
            handle.write(title + "\n")
    print(f"wrote {output} with {len(titles)} titles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
