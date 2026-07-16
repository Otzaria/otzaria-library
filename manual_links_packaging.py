#!/usr/bin/env python3
"""Strict, deterministic packaging support for manually maintained links.

This is intentionally independent from the link updater.  It validates the
committed contract and lineage, rejects flattening collisions, and constructs a
reproducible archive from an exact checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import struct
import sys
import tempfile
import zipfile
import re
import zlib
from pathlib import Path, PurePosixPath


MAGIC = b"manual-links-tree-v1\0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CONFIG_NAME = "manual_links_sync.json"
LINEAGE_NAME = "manual_links_lineage.json"
TOOLCHAIN_NAME = "packaging_toolchain.json"
BOOK_ROOTS = (
    "Ben-YehudaToOtzaria/ספרים/אוצריא",
    "DictaToOtzaria/ערוך/ספרים/אוצריא",
    "OnYourWayToOtzaria/ספרים/אוצריא",
    "OraytaToOtzaria/ספרים/אוצריא",
    "tashmaToOtzaria/ספרים/אוצריא",
    "sefariaToOtzaria/sefaria_export/ספרים/אוצריא",
    "sefariaToOtzaria/sefaria_api/ספרים/אוצריא",
    "MoreBooks/ספרים/אוצריא",
    "wikiJewishBooksToOtzaria/ספרים/אוצריא",
    "wikisourceToOtzaria/ספרים/אוצריא",
    "ToratEmetToOtzaria/ספרים/אוצריא",
    "pninimToOtzaria/ספרים/אוצריא",
    "National-LibraryToOtzaria/ספרים/אוצריא",
)


class PackagingError(ValueError):
    pass


def load_json(path: Path) -> object:
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise PackagingError(f"duplicate JSON key {key!r} in {path}")
            value[key] = item
        return value

    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=reject_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagingError(f"cannot read {path}: {exc}") from exc


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(value: object, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise PackagingError(f"{field} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or str(path) != value:
        raise PackagingError(f"{field} is not a canonical repository-relative POSIX path: {value!r}")
    return path


def validate_config(config: object) -> dict:
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise PackagingError("manual_links_sync.json schema_version must be 1")
    if not isinstance(config.get("seforim_tool_ref"), str) or not config["seforim_tool_ref"].startswith("refs/"):
        raise PackagingError("seforim_tool_ref must be an explicit refs/... value")
    roots = config.get("links_roots")
    if not isinstance(roots, list) or not roots:
        raise PackagingError("links_roots must be a non-empty array")
    seen = set()
    for index, entry in enumerate(roots):
        if not isinstance(entry, dict) or set(entry) != {"path", "expected_state"}:
            raise PackagingError(f"links_roots[{index}] must contain only path and expected_state")
        path = str(safe_relative_path(entry["path"], f"links_roots[{index}].path"))
        if path in seen:
            raise PackagingError(f"duplicate links root: {path}")
        seen.add(path)
        if entry["expected_state"] not in {"present", "absent"}:
            raise PackagingError(f"invalid expected_state for {path}")
    return config


def assert_regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise PackagingError(f"non-regular entry is forbidden: {path}")


def scan_roots(workspace: Path, config: dict) -> tuple[list[tuple[str, str]], list[tuple[str, Path]]]:
    states = []
    files = []
    for entry in sorted(config["links_roots"], key=lambda item: os.fsencode(item["path"])):
        root_rel = entry["path"]
        root = workspace / root_rel
        expected = entry["expected_state"]
        if root.is_symlink():
            raise PackagingError(f"links root must never be a symlink: {root_rel}")
        exists = root.exists()
        if expected == "present" and not exists:
            raise PackagingError(f"required links root is absent: {root_rel}")
        if expected == "absent" and exists:
            raise PackagingError(f"links root configured absent now exists: {root_rel}")
        states.append((root_rel, expected))
        if not exists:
            continue
        if root.is_symlink() or not root.is_dir():
            raise PackagingError(f"links root is not a real directory: {root_rel}")
        for child in sorted(root.iterdir(), key=lambda path: os.fsencode(path.name)):
            if child.is_dir():
                raise PackagingError(f"nested directory is forbidden below links root: {child.relative_to(workspace)}")
            assert_regular(child)
            files.append((child.relative_to(workspace).as_posix(), child))
    return states, files


def add_file_record(digest, path: str, file_path: Path, file_sha256: str | None = None) -> None:
    path_bytes = path.encode("utf-8")
    if len(path_bytes) > 0xFFFFFFFF:
        raise PackagingError(f"path too long: {path}")
    size = file_path.stat().st_size
    digest.update(struct.pack(">I", len(path_bytes)))
    digest.update(path_bytes)
    digest.update(struct.pack(">Q", size))
    digest.update(bytes.fromhex(file_sha256 or sha256_file(file_path)))


def tree_hashes(workspace: Path, config: dict) -> tuple[str, str, list[tuple[str, Path]]]:
    states, files = scan_roots(workspace, config)
    file_digests = {file_path: sha256_file(file_path) for _, file_path in files}
    source = hashlib.sha256(MAGIC)
    for root, state in states:
        root_bytes = root.encode("utf-8")
        source.update(struct.pack(">I", len(root_bytes)))
        source.update(root_bytes)
        source.update(b"\x01" if state == "present" else b"\x00")
    for path, file_path in sorted(files, key=lambda item: item[0].encode("utf-8")):
        add_file_record(source, path, file_path, file_digests[file_path])

    packaged_files = []
    collisions = {}
    for source_path, file_path in files:
        packaged_path = f"links/{file_path.name}"
        if packaged_path in collisions:
            raise PackagingError(
                f"packaged-path collision for {packaged_path}: {collisions[packaged_path]} and {source_path}"
            )
        collisions[packaged_path] = source_path
        packaged_files.append((packaged_path, file_path))
    packaged = hashlib.sha256(MAGIC)
    for path, file_path in sorted(packaged_files, key=lambda item: item[0].encode("utf-8")):
        add_file_record(packaged, path, file_path, file_digests[file_path])
    return source.hexdigest(), packaged.hexdigest(), packaged_files


def validate_lineage(
    workspace: Path,
    config: dict,
    lineage: object,
    computed_trees: tuple[str, str, list[tuple[str, Path]]] | None = None,
) -> dict:
    if not isinstance(lineage, dict) or lineage.get("schema_version") != 1:
        raise PackagingError("manual_links_lineage.json schema_version must be 1")
    lineage_path = workspace / LINEAGE_NAME
    if lineage_path.read_bytes() != canonical_bytes(lineage) + b"\n":
        raise PackagingError("manual_links_lineage.json must be canonical JSON with one trailing LF")
    required = {
        "schema_version", "sefaria", "seforim_tool_commit",
        "source_links_tree_sha256", "packaged_links_tree_sha256", "config_sha256",
    }
    if set(lineage) != required:
        raise PackagingError(f"lineage keys differ from schema: {set(lineage) ^ required}")
    if not isinstance(lineage["seforim_tool_commit"], str) or not COMMIT_RE.fullmatch(lineage["seforim_tool_commit"]):
        raise PackagingError("lineage.seforim_tool_commit must be a full Git SHA")
    sefaria = lineage["sefaria"]
    if not isinstance(sefaria, dict):
        raise PackagingError("lineage.sefaria must be an object")
    sefaria_keys = {"tag", "release_metadata_sha256", "run_id", "run_attempt", "archive", "applied_changelog_chain"}
    if set(sefaria) != sefaria_keys:
        raise PackagingError(f"lineage.sefaria keys differ from schema: {set(sefaria) ^ sefaria_keys}")
    if not isinstance(sefaria["tag"], str) or not sefaria["tag"]:
        raise PackagingError("lineage.sefaria.tag must be non-empty")
    if not isinstance(sefaria["release_metadata_sha256"], str) or not SHA256_RE.fullmatch(sefaria["release_metadata_sha256"]):
        raise PackagingError("lineage.sefaria.release_metadata_sha256 must be a SHA-256")
    if any(isinstance(sefaria[field], bool) or not isinstance(sefaria[field], int) or sefaria[field] <= 0 for field in ("run_id", "run_attempt")):
        raise PackagingError("lineage Sefaria run identity must contain positive integers")
    if not isinstance(sefaria["applied_changelog_chain"], list):
        raise PackagingError("lineage applied_changelog_chain must be an array")
    archive = sefaria["archive"]
    if not isinstance(archive, dict) or set(archive) != {"sha256", "size", "parts"}:
        raise PackagingError("lineage.sefaria.archive has unexpected keys")
    if not isinstance(archive["sha256"], str) or not SHA256_RE.fullmatch(archive["sha256"]):
        raise PackagingError("lineage.sefaria.archive.sha256 must be a SHA-256")
    if isinstance(archive["size"], bool) or not isinstance(archive["size"], int) or archive["size"] < 0:
        raise PackagingError("lineage.sefaria.archive.size must be non-negative")
    if not isinstance(archive["parts"], list) or not archive["parts"]:
        raise PackagingError("lineage.sefaria.archive.parts must be non-empty")
    part_names = []
    for index, part in enumerate(archive["parts"]):
        if not isinstance(part, dict) or set(part) != {"name", "sha256", "size"}:
            raise PackagingError(f"lineage archive part {index} is invalid")
        if not isinstance(part["name"], str) or Path(part["name"]).name != part["name"]:
            raise PackagingError(f"lineage archive part {index} name is invalid")
        if not isinstance(part["sha256"], str) or not SHA256_RE.fullmatch(part["sha256"]):
            raise PackagingError(f"lineage archive part {index} hash is invalid")
        if isinstance(part["size"], bool) or not isinstance(part["size"], int) or part["size"] < 0:
            raise PackagingError(f"lineage archive part {index} size is invalid")
        part_names.append(part["name"])
    if part_names != sorted(part_names, key=os.fsencode) or len(part_names) != len(set(part_names)):
        raise PackagingError("lineage archive parts must be unique and bytewise-sorted")
    if sum(part["size"] for part in archive["parts"]) != archive["size"]:
        raise PackagingError("lineage archive size differs from part sizes")
    for index, node in enumerate(sefaria["applied_changelog_chain"]):
        expected_node_keys = {"tag", "metadata_sha256", "previous", "changelog_name", "changelog_sha256"}
        if not isinstance(node, dict) or set(node) != expected_node_keys:
            raise PackagingError(f"lineage changelog node {index} has unexpected keys")
        if not isinstance(node["tag"], str) or not node["tag"]:
            raise PackagingError(f"lineage changelog node {index} tag is invalid")
        for field in ("metadata_sha256", "changelog_sha256"):
            if not isinstance(node[field], str) or not SHA256_RE.fullmatch(node[field]):
                raise PackagingError(f"lineage changelog node {index} {field} is invalid")
        if not isinstance(node["changelog_name"], str) or Path(node["changelog_name"]).name != node["changelog_name"]:
            raise PackagingError(f"lineage changelog node {index} asset name is invalid")
        previous = node["previous"]
        if not isinstance(previous, dict) or set(previous) != {"tag", "metadata_sha256"}:
            raise PackagingError(f"lineage changelog node {index} previous pointer is invalid")
        if not isinstance(previous["tag"], str) or not previous["tag"]:
            raise PackagingError(f"lineage changelog node {index} previous tag is invalid")
        if not isinstance(previous["metadata_sha256"], str) or not SHA256_RE.fullmatch(previous["metadata_sha256"]):
            raise PackagingError(f"lineage changelog node {index} previous digest is invalid")
    for field in ("source_links_tree_sha256", "packaged_links_tree_sha256", "config_sha256"):
        if not isinstance(lineage.get(field), str) or not SHA256_RE.fullmatch(lineage[field]):
            raise PackagingError(f"lineage.{field} must be a SHA-256")
    source_hash, packaged_hash, _ = computed_trees or tree_hashes(workspace, config)
    actual_config = sha256_file(workspace / CONFIG_NAME)
    expected = {
        "source_links_tree_sha256": source_hash,
        "packaged_links_tree_sha256": packaged_hash,
        "config_sha256": actual_config,
    }
    for field, value in expected.items():
        if lineage[field] != value:
            raise PackagingError(f"lineage mismatch for {field}: expected {value}, got {lineage[field]}")
    return {**expected, "lineage_sha256": sha256_file(lineage_path)}


def copy_regular_tree(source: Path, destination: Path, overwrite: bool) -> None:
    if source.is_symlink() or not source.is_dir():
        raise PackagingError(f"book root is not a real directory: {source}")
    for root, directories, names in os.walk(source, followlinks=False):
        root_path = Path(root)
        for directory in directories:
            path = root_path / directory
            if path.is_symlink():
                raise PackagingError(f"symlink directory is forbidden: {path}")
        for name in names:
            path = root_path / name
            assert_regular(path)
            relative = path.relative_to(source)
            target = destination / relative
            if target.exists() and not overwrite:
                raise PackagingError(f"staging collision: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def manifest(workspace: Path, config: dict) -> dict:
    result = {}
    for name in ("metadata.json", CONFIG_NAME, LINEAGE_NAME, TOOLCHAIN_NAME):
        path = workspace / name
        if path.is_file():
            result[name] = {"hash": sha256_file(path)}
    for root_rel in BOOK_ROOTS:
        root = workspace / root_rel
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().encode("utf-8")):
            if path.is_file() and not path.is_symlink():
                result[path.relative_to(workspace).as_posix()] = {"hash": sha256_file(path)}
    _, files = scan_roots(workspace, config)
    for path, file_path in files:
        result[path] = {"hash": sha256_file(file_path)}
    return result


def write_reproducible_zip(source: Path, output: Path) -> None:
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix().encode("utf-8")):
            if not path.is_file():
                continue
            name = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            with path.open("rb") as source_handle, archive.open(info, "w", force_zip64=True) as output_handle:
                shutil.copyfileobj(source_handle, output_handle, length=1024 * 1024)


def package(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    config = validate_config(load_json(workspace / CONFIG_NAME))
    lineage_path = workspace / LINEAGE_NAME
    if not lineage_path.is_file():
        raise PackagingError("manual_links_lineage.json is required before packaging")
    computed_trees = tree_hashes(workspace, config)
    hashes = validate_lineage(workspace, config, load_json(lineage_path), computed_trees)
    _, _, links = computed_trees

    output = Path(args.output).resolve()
    with tempfile.TemporaryDirectory(prefix="otzaria-package-") as temporary:
        staging = Path(temporary)
        books = staging / "אוצריא"
        for root_rel in BOOK_ROOTS:
            root = workspace / root_rel
            if root.exists():
                # Preserve the legacy source precedence for books.  Link files use
                # create-new semantics below and can never be overwritten.
                copy_regular_tree(root, books, overwrite=True)
        links_dir = staging / "links"
        links_dir.mkdir(parents=True, exist_ok=True)
        for packaged_path, source in links:
            target = staging / packaged_path
            if target.exists():
                raise PackagingError(f"unexpected link staging collision: {packaged_path}")
            shutil.copyfile(source, target)

        manifest_path = staging / "files_manifest.json"
        manifest_path.write_bytes(canonical_bytes(manifest(workspace, config)))
        for name in ("metadata.json", CONFIG_NAME, LINEAGE_NAME, TOOLCHAIN_NAME):
            source = workspace / name
            if source.is_file():
                shutil.copyfile(source, staging / name)
        write_reproducible_zip(staging, output)

    result = {
        "schema_version": 1,
        "asset": {"name": output.name, "size": output.stat().st_size, "sha256": sha256_file(output)},
        "runtime": {
            "python": platform.python_version(),
            "zlib": zlib.ZLIB_VERSION,
            "zip_compression": "deflate-9",
        },
        "toolchain": load_json(workspace / TOOLCHAIN_NAME),
        **hashes,
    }
    Path(args.result).write_bytes(canonical_bytes(result))
    return 0


def check(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    config = validate_config(load_json(workspace / CONFIG_NAME))
    source_hash, packaged_hash, files = tree_hashes(workspace, config)
    result = {
        "config_sha256": sha256_file(workspace / CONFIG_NAME),
        "source_links_tree_sha256": source_hash,
        "packaged_links_tree_sha256": packaged_hash,
        "packaged_file_count": len(files),
    }
    if args.require_lineage:
        lineage_path = workspace / LINEAGE_NAME
        if not lineage_path.is_file():
            raise PackagingError("manual_links_lineage.json is required")
        result.update(validate_lineage(workspace, config, load_json(lineage_path)))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--workspace", default=".")
    check_parser.add_argument("--require-lineage", action="store_true")
    check_parser.set_defaults(func=check)
    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--workspace", default=".")
    package_parser.add_argument("--output", required=True)
    package_parser.add_argument("--result", required=True)
    package_parser.set_defaults(func=package)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PackagingError as exc:
        print(f"manual links packaging error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
