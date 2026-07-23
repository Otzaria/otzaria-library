#!/usr/bin/env python3
"""Strict, canonical contract for an event-driven weekly saga state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


SHA40 = re.compile(r"[0-9a-f]{40}")
SHA64 = re.compile(r"[0-9a-f]{64}")
TAG = re.compile(r"[A-Za-z0-9._-]{1,100}")
STATE_KEYS = {
    "schema_version", "correlation_id", "correlation_sha256", "saga_run_id",
    "saga_run_attempt", "expected_links_commit", "seforim_tool_commit",
    "sefaria_tag", "sefaria_release_metadata_sha256", "sefaria_archive_sha256",
    "fordb_tag", "fordb_archive_sha256", "fordb_provenance_sha256",
}


def strict_json(path: Path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise SystemExit(f"duplicate JSON key {key!r} in {path}")
            out[key] = value
        return out
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def validate(
    directory: Path,
    expected_run: int,
    expected_run_attempt: int,
    expected_correlation: str,
) -> dict:
    path = directory / "saga-state.json"
    sidecar = directory / "saga-state.sha256"
    raw = path.read_bytes()
    value = strict_json(path)
    if set(value) != STATE_KEYS or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise SystemExit("unknown saga-state schema/key set")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if raw != canonical:
        raise SystemExit("saga-state is not canonical JSON")
    digest = hashlib.sha256(raw).hexdigest()
    if sidecar.read_bytes() != (digest + "\n").encode("ascii"):
        raise SystemExit("saga-state SHA sidecar mismatch")
    if type(value["saga_run_id"]) is not int or value["saga_run_id"] != expected_run:
        raise SystemExit("saga_run_id mismatch")
    if (
        type(value["saga_run_attempt"]) is not int
        or value["saga_run_attempt"] != expected_run_attempt
    ):
        raise SystemExit("saga_run_attempt mismatch")
    if value["correlation_id"] != expected_correlation:
        raise SystemExit("correlation_id mismatch")
    if not isinstance(expected_correlation, str):
        raise SystemExit("correlation_id must be a string")
    correlation_match = re.fullmatch(
        r"sefaria:([1-9][0-9]*):([1-9][0-9]*):([A-Za-z0-9._-]{1,100}):([0-9a-f]{64})",
        expected_correlation,
    )
    if not correlation_match:
        raise SystemExit("invalid correlation_id shape")
    corr_digest = hashlib.sha256(expected_correlation.encode()).hexdigest()
    if value["correlation_sha256"] != corr_digest:
        raise SystemExit("correlation_sha256 mismatch")
    for field in ("expected_links_commit", "seforim_tool_commit"):
        if not isinstance(value[field], str) or not SHA40.fullmatch(value[field]):
            raise SystemExit(f"invalid {field}")
    for field in (
        "sefaria_release_metadata_sha256", "sefaria_archive_sha256",
        "fordb_archive_sha256", "fordb_provenance_sha256",
    ):
        if not isinstance(value[field], str) or not SHA64.fullmatch(value[field]):
            raise SystemExit(f"invalid {field}")
    if not isinstance(value["sefaria_tag"], str) or not TAG.fullmatch(value["sefaria_tag"]):
        raise SystemExit("invalid sefaria_tag")
    if value["sefaria_tag"] != correlation_match.group(3) or value["sefaria_release_metadata_sha256"] != correlation_match.group(4):
        raise SystemExit("correlation_id disagrees with pinned Sefaria fields")
    if value["fordb_tag"] != "fordb-sha256-" + value["fordb_archive_sha256"]:
        raise SystemExit("ForDB tag does not match its archive digest")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--expected-run-id", required=True, type=int)
    parser.add_argument("--expected-run-attempt", required=True, type=int)
    parser.add_argument("--expected-correlation", required=True)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    value = validate(
        Path(args.directory),
        args.expected_run_id,
        args.expected_run_attempt,
        args.expected_correlation,
    )
    if args.github_output:
        keys = (
            "correlation_id", "correlation_sha256", "saga_run_id", "saga_run_attempt",
            "expected_links_commit", "seforim_tool_commit", "sefaria_tag",
            "sefaria_release_metadata_sha256", "sefaria_archive_sha256",
            "fordb_tag", "fordb_archive_sha256", "fordb_provenance_sha256",
        )
        with Path(args.github_output).open("a", encoding="utf-8") as out:
            for key in keys:
                out.write(f"{key}={value[key]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
