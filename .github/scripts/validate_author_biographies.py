"""Validate reviewed author links against the catalog inputs and a released bundle."""

import csv
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def catalog_name(name):
    # Match SeforimLibrary's normalizeAuthorName. Punctuation is significant.
    name = re.sub(r"[\u0591-\u05BD\u05BF-\u05C7\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]", "", name)
    return re.sub(r"[ \t\n\v\f\r\u00A0\u2000-\u200B\u202F\u205F\u3000]+", " ", name).strip()


def read_catalog_names(root):
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    names = {
        catalog_name(name)
        for book in metadata
        for name in [book.get("author"), *(book.get("authors") or [])]
        if isinstance(name, str) and name
    }
    with (root / "ForDB/sefaria_author_changes.csv").open(encoding="utf-8-sig", newline="") as stream:
        names.update(catalog_name(row["שם קנוני"]) for row in csv.DictReader(stream))
    return names


def validate(root, bundle_path):
    path = root / "author_biographies.json"
    mapping = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if type(mapping.get("version")) is not int or mapping["version"] != 1 or not isinstance(mapping.get("authors"), dict):
        raise ValueError(f"Unsupported mapping format: {path}")
    with gzip.open(bundle_path, "rt", encoding="utf-8") as stream:
        bundle = json.load(stream)
    if bundle.get("format") != "biographies-app" or bundle.get("version") != 1:
        raise ValueError("Expected a version 1 biographies-app bundle")
    ids = [entry["id"] for entry in bundle["entries"]]
    valid_ids = set(ids)
    if len(ids) != len(valid_ids):
        raise ValueError("Duplicate IDs in the biographies bundle")
    valid_names = read_catalog_names(root)
    errors = []
    for name, entry_id in mapping["authors"].items():
        if not name or name not in valid_names:
            errors.append(f"Unknown catalog author: {name!r}")
        if not isinstance(entry_id, str) or entry_id not in valid_ids:
            errors.append(f"Unknown biography ID for {name!r}: {entry_id!r}")
    if errors:
        raise ValueError("\n".join(errors))
    return len(mapping["authors"]), len(set(mapping["authors"].values())), bundle["release"]


if __name__ == "__main__":
    try:
        authors, entries, release = validate(ROOT, Path(sys.argv[1]))
    except (OSError, ValueError) as error:
        sys.exit(str(error))
    print(f"Validated {authors} names linked to {entries} entries in {release}")
