#!/usr/bin/env python3
"""Fetch and verify the immutable Sefaria release chain for the link updater."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TAG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class ChainError(ValueError):
    pass


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ChainError(f"duplicate key {key!r} in {path}")
            out[key] = value
        return out

    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise ChainError(f"cannot read {path}: {exc}") from exc


def require_sha(value, field):
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ChainError(f"{field} is not a lowercase SHA-256")


def validate_descriptor(value, field):
    if not isinstance(value, dict) or set(value) != {"name", "size", "sha256"}:
        raise ChainError(f"{field} is not an exact file descriptor")
    if not isinstance(value["name"], str) or Path(value["name"]).name != value["name"]:
        raise ChainError(f"{field}.name is not a basename")
    if isinstance(value["size"], bool) or not isinstance(value["size"], int) or value["size"] < 0:
        raise ChainError(f"{field}.size is invalid")
    require_sha(value["sha256"], f"{field}.sha256")


def validate_metadata(value, expected_tag):
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("tag") != expected_tag
    ):
        raise ChainError(f"invalid metadata identity for {expected_tag}")
    required = {
        "schema_version", "tag", "run_id", "run_attempt", "source_commit",
        "previous", "archive", "manifest", "titles", "changelog",
    }
    if set(value) != required:
        raise ChainError(f"metadata keys differ from schema for {expected_tag}")
    if not TAG_RE.fullmatch(expected_tag):
        raise ChainError(f"unsafe tag: {expected_tag}")
    previous = value.get("previous")
    if previous is not None:
        if not isinstance(previous, dict) or set(previous) != {"tag", "metadata_sha256"}:
            raise ChainError(f"invalid previous pointer for {expected_tag}")
        if not isinstance(previous["tag"], str) or not TAG_RE.fullmatch(previous["tag"]):
            raise ChainError(f"unsafe previous tag in {expected_tag}")
        require_sha(previous["metadata_sha256"], f"{expected_tag}.previous.metadata_sha256")
    if any(isinstance(value[field], bool) or not isinstance(value[field], int) or value[field] <= 0 for field in ("run_id", "run_attempt")):
        raise ChainError(f"invalid run identity for {expected_tag}")
    if not isinstance(value["source_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["source_commit"]):
        raise ChainError(f"invalid source_commit for {expected_tag}")
    for field in ("manifest", "titles"):
        validate_descriptor(value[field], field)
    changelog = value.get("changelog")
    if not isinstance(changelog, dict) or set(changelog) != {"name", "size", "sha256", "old_tag", "new_tag"}:
        raise ChainError(f"invalid changelog descriptor for {expected_tag}")
    validate_descriptor({key: changelog[key] for key in ("name", "size", "sha256")}, "changelog")
    if changelog["new_tag"] != expected_tag or changelog["old_tag"] != (previous["tag"] if previous else ""):
        raise ChainError(f"changelog pointer mismatch for {expected_tag}")
    archive = value.get("archive")
    if not isinstance(archive, dict) or set(archive) != {"sha256", "size", "parts"}:
        raise ChainError(f"invalid archive descriptor for {expected_tag}")
    require_sha(archive["sha256"], "archive.sha256")
    if isinstance(archive["size"], bool) or not isinstance(archive["size"], int) or archive["size"] < 0:
        raise ChainError("archive.size is invalid")
    parts = archive["parts"]
    if not isinstance(parts, list) or not parts:
        raise ChainError("archive.parts is empty")
    for index, descriptor in enumerate(parts):
        validate_descriptor(descriptor, f"archive.parts[{index}]")
    names = [part["name"] for part in parts]
    if names != sorted(names, key=os.fsencode) or len(names) != len(set(names)):
        raise ChainError("archive.parts are not uniquely bytewise-sorted")
    all_names = names + [value["manifest"]["name"], value["titles"]["name"], value["changelog"]["name"], "release_metadata.json"]
    if len(all_names) != len(set(all_names)):
        raise ChainError("release asset names are not unique")
    if sum(part["size"] for part in parts) != archive["size"]:
        raise ChainError("archive.size differs from part sizes")
    return value


def download(repo: str, tag: str, asset: str, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "release", "download", tag, "-R", repo, "--pattern", asset, "--dir", str(destination)],
        check=True,
    )
    path = destination / asset
    if not path.is_file():
        raise ChainError(f"GitHub did not return {asset} for {tag}")
    return path


def verify_file(path: Path, descriptor: dict) -> None:
    if path.stat().st_size != descriptor["size"] or sha256(path) != descriptor["sha256"]:
        raise ChainError(f"asset bytes differ from metadata: {path}")


def classify_non_descendant(target_identities, base_identities) -> str:
    """Separate a delayed valid dispatch from a conflicting immutable fork."""
    if target_identities and target_identities[0] in set(base_identities):
        return "stale_dispatch"
    return "fork"


def load_identity_chain(repo: str, start_tag: str, start_digest: str, raw: Path):
    identities = []
    seen_tags = set()
    tag = start_tag
    digest = start_digest
    while True:
        if tag in seen_tags:
            raise ChainError(f"release chain cycle at {tag}")
        seen_tags.add(tag)
        metadata_path = download(repo, tag, "release_metadata.json", raw / tag)
        if sha256(metadata_path) != digest:
            raise ChainError(f"metadata digest mismatch for {tag}")
        metadata = validate_metadata(load_json(metadata_path), tag)
        if metadata_path.read_bytes() != canonical_bytes(metadata):
            raise ChainError(f"metadata is not canonical: {tag}")
        identities.append((tag, digest))
        previous = metadata["previous"]
        if previous is None:
            return identities
        tag = previous["tag"]
        digest = previous["metadata_sha256"]


def fetch(args) -> int:
    output = Path(args.output).resolve()
    if output.exists():
        if any(output.iterdir()):
            raise ChainError("output directory must be absent or empty")
    else:
        output.mkdir(parents=True)
    raw = output / "raw"
    chain_dir = output / "changelogs"
    assets_dir = output / "target-assets"
    raw.mkdir()
    chain_dir.mkdir()
    assets_dir.mkdir()

    base_lineage = load_json(Path(args.lineage))
    try:
        base_tag = base_lineage["sefaria"]["tag"]
        base_digest = base_lineage["sefaria"]["release_metadata_sha256"]
    except (KeyError, TypeError) as exc:
        raise ChainError("lineage lacks the Sefaria base identity") from exc
    require_sha(base_digest, "lineage.sefaria.release_metadata_sha256")
    require_sha(args.target_metadata_sha256, "target metadata SHA")

    nodes = []
    seen = set()
    target_identities = []
    current_tag = args.target_tag
    expected_digest = args.target_metadata_sha256
    target_metadata = None
    while True:
        if current_tag in seen:
            raise ChainError(f"release chain cycle at {current_tag}")
        seen.add(current_tag)
        target_identities.append((current_tag, expected_digest))
        node_dir = raw / current_tag
        metadata_path = download(args.repo, current_tag, "release_metadata.json", node_dir)
        if sha256(metadata_path) != expected_digest:
            raise ChainError(f"metadata digest mismatch for {current_tag}")
        metadata = validate_metadata(load_json(metadata_path), current_tag)
        if metadata_path.read_bytes() != canonical_bytes(metadata):
            raise ChainError(f"metadata is not canonical: {current_tag}")
        if target_metadata is None:
            target_metadata = metadata
        if current_tag == base_tag:
            if expected_digest != base_digest:
                raise ChainError("lineage base tag has a different metadata digest")
            break
        previous = metadata["previous"]
        if previous is None:
            base_identities = load_identity_chain(
                args.repo, base_tag, base_digest, raw / "committed-lineage"
            )
            classification = classify_non_descendant(target_identities, base_identities)
            if classification == "stale_dispatch":
                raise ChainError(
                    "stale_dispatch: target release already precedes the committed lineage"
                )
            raise ChainError(
                "fork: target release and committed lineage have no common immutable ancestry"
            )
        changelog_descriptor = metadata["changelog"]
        changelog_path = download(args.repo, current_tag, changelog_descriptor["name"], node_dir)
        verify_file(changelog_path, {key: changelog_descriptor[key] for key in ("name", "size", "sha256")})
        changelog = load_json(changelog_path)
        if not isinstance(changelog, dict) or changelog.get("old_tag") != previous["tag"] or changelog.get("new_tag") != current_tag:
            raise ChainError(f"changelog body differs from metadata for {current_tag}")
        nodes.append((current_tag, expected_digest, metadata_path, changelog_path, metadata))
        current_tag = previous["tag"]
        expected_digest = previous["metadata_sha256"]

    nodes.reverse()
    chain_summary = []
    for index, (tag, digest, metadata_path, changelog_path, metadata) in enumerate(nodes, 1):
        prefix = f"{index:04d}-{tag}"
        shutil.copyfile(metadata_path, chain_dir / f"{prefix}-release_metadata.json")
        shutil.copyfile(changelog_path, chain_dir / f"{prefix}-changelog_diff.json")
        chain_summary.append({
            "tag": tag,
            "metadata_sha256": digest,
            "previous": metadata["previous"],
            "changelog_name": metadata["changelog"]["name"],
            "changelog_sha256": metadata["changelog"]["sha256"],
        })

    for descriptor in target_metadata["archive"]["parts"]:
        path = download(args.repo, args.target_tag, descriptor["name"], assets_dir)
        verify_file(path, descriptor)
    combined = hashlib.sha256()
    combined_size = 0
    for descriptor in target_metadata["archive"]["parts"]:
        with (assets_dir / descriptor["name"]).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                combined.update(chunk)
                combined_size += len(chunk)
    if combined.hexdigest() != target_metadata["archive"]["sha256"] or combined_size != target_metadata["archive"]["size"]:
        raise ChainError("combined archive stream differs from metadata")
    shutil.copyfile(raw / args.target_tag / "release_metadata.json", output / "release_metadata.json")
    result = {
        "schema_version": 1,
        "target_tag": args.target_tag,
        "target_metadata_sha256": args.target_metadata_sha256,
        "archive": target_metadata["archive"],
        "applied_changelog_chain": chain_summary,
    }
    (output / "chain-result.json").write_bytes(canonical_bytes(result))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--target-tag", required=True)
    parser.add_argument("--target-metadata-sha256", required=True)
    parser.add_argument("--lineage", required=True)
    parser.add_argument("--output", required=True)
    try:
        return fetch(parser.parse_args(argv))
    except (ChainError, subprocess.CalledProcessError) as exc:
        print(f"Sefaria release chain error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
