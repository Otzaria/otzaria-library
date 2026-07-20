#!/usr/bin/env python3
"""Strict contracts for cross-repository release and result artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TAG_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class ContractError(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"


def load_json(path: Path, *, require_canonical: bool = True) -> object:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    if require_canonical and raw != canonical_bytes(value):
        raise ContractError(f"{path} is not canonical JSON with exactly one trailing LF")
    return value


def require_exact_keys(value: object, keys: set[str], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else type(value).__name__
        raise ContractError(f"{field} does not match its exact schema: {actual}")
    return value


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty string")
    return value


def require_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ContractError(f"{field} must be a lowercase SHA-256")
    return value


def require_commit(value: object, field: str) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise ContractError(f"{field} must be a full lowercase Git commit")
    return value


def require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractError(f"{field} must be a positive integer")
    return value


def validate_descriptor(value: object, field: str) -> dict:
    descriptor = require_exact_keys(value, {"name", "size", "sha256"}, field)
    name = require_string(descriptor["name"], f"{field}.name")
    if Path(name).name != name:
        raise ContractError(f"{field}.name must be a basename")
    size = descriptor["size"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ContractError(f"{field}.size must be a non-negative integer")
    require_sha(descriptor["sha256"], f"{field}.sha256")
    return descriptor


def validate_descriptors(value: object, field: str) -> list[dict]:
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    for index, descriptor in enumerate(value):
        validate_descriptor(descriptor, f"{field}[{index}]")
    names = [item["name"] for item in value]
    if names != sorted(names, key=os.fsencode) or len(names) != len(set(names)):
        raise ContractError(f"{field} must have unique, bytewise-sorted names")
    return value


def validate_runtime(value: object) -> dict:
    runtime = require_exact_keys(value, {"python", "zlib", "zip_compression"}, "packaging_runtime")
    for field in runtime:
        require_string(runtime[field], f"packaging_runtime.{field}")
    return runtime


def validate_toolchain(value: object) -> dict:
    toolchain = require_exact_keys(
        value,
        {"schema_version", "python", "zlib_build", "zlib_runtime", "gnu_tar", "zstd"},
        "packaging_toolchain",
    )
    if type(toolchain["schema_version"]) is not int or toolchain["schema_version"] != 1:
        raise ContractError("packaging_toolchain.schema_version must be 1")
    for field in ("python", "zlib_build", "zlib_runtime", "gnu_tar", "zstd"):
        require_string(toolchain[field], f"packaging_toolchain.{field}")
    return toolchain


PROVENANCE_KEYS = {
    "schema_version", "correlation_id", "target_commit", "tag", "asset",
    "auxiliary_assets", "packaging_runtime", "packaging_toolchain",
    "config_sha256", "source_links_tree_sha256", "packaged_links_tree_sha256",
    "lineage_sha256",
}


def validate_provenance(value: object) -> dict:
    provenance = require_exact_keys(value, PROVENANCE_KEYS, "release provenance")
    if type(provenance["schema_version"]) is not int or provenance["schema_version"] != 1:
        raise ContractError("release provenance schema_version must be 1")
    require_string(provenance["correlation_id"], "correlation_id")
    require_commit(provenance["target_commit"], "target_commit")
    if (
        not isinstance(provenance["tag"], str)
        or not TAG_RE.fullmatch(provenance["tag"])
        or not provenance["tag"].startswith("library-links-")
    ):
        raise ContractError("tag is unsafe")
    validate_descriptor(provenance["asset"], "asset")
    validate_descriptors(provenance["auxiliary_assets"], "auxiliary_assets")
    if provenance["asset"]["name"] != "otzaria_latest.zip":
        raise ContractError("primary asset name must be otzaria_latest.zip")
    if [item["name"] for item in provenance["auxiliary_assets"]] != [
        "otzaria_dicta_latest.zip", "talmud_bavli_latest.tar.zst"
    ]:
        raise ContractError("auxiliary asset names differ from the exact release contract")
    validate_runtime(provenance["packaging_runtime"])
    validate_toolchain(provenance["packaging_toolchain"])
    for field in ("config_sha256", "source_links_tree_sha256", "packaged_links_tree_sha256", "lineage_sha256"):
        require_sha(provenance[field], field)
    return provenance


RECOVERY_KEY_FIELDS = (
    "target_commit", "lineage_sha256", "config_sha256",
    "source_links_tree_sha256", "packaged_links_tree_sha256",
)


def recovery_key(provenance: dict) -> tuple[str, ...]:
    validate_provenance(provenance)
    return tuple(provenance[field] for field in RECOVERY_KEY_FIELDS)


def fresh_provenance(packaging: dict, auxiliary_assets: list[dict], correlation_id: str, target: str, tag: str) -> dict:
    return {
        "schema_version": 1,
        "correlation_id": correlation_id,
        "target_commit": target,
        "tag": tag,
        "asset": packaging["asset"],
        "auxiliary_assets": auxiliary_assets,
        "packaging_runtime": packaging["runtime"],
        "packaging_toolchain": packaging["toolchain"],
        "config_sha256": packaging["config_sha256"],
        "source_links_tree_sha256": packaging["source_links_tree_sha256"],
        "packaged_links_tree_sha256": packaging["packaged_links_tree_sha256"],
        "lineage_sha256": packaging["lineage_sha256"],
    }


def assert_fresh_bytes_match(recorded: dict, fresh: dict) -> None:
    """A matching input tuple must reproduce every byte-bearing field exactly."""
    validate_provenance(recorded)
    validate_provenance(fresh)
    if recovery_key(recorded) != recovery_key(fresh):
        raise ContractError("recorded and fresh provenance do not have the same recovery key")
    compared = (
        "asset", "auxiliary_assets", "packaging_runtime", "packaging_toolchain",
    )
    differing = [field for field in compared if recorded[field] != fresh[field]]
    if differing:
        raise ContractError(
            "same immutable input tuple produced different release bytes/toolchain: "
            + ", ".join(differing)
        )


def classify_recovery_release(recorded: dict, fresh: dict, actual_target: str, draft: bool) -> str:
    """Classify one release without ever permitting a second release per target/key."""
    validate_provenance(recorded)
    validate_provenance(fresh)
    require_commit(actual_target, "actual release target")
    same_key = recovery_key(recorded) == recovery_key(fresh)
    expected_target = fresh["target_commit"]
    if draft and (actual_target == expected_target or same_key):
        raise ContractError("a partial draft already targets this commit or recovery key")
    if actual_target == expected_target and not same_key:
        raise ContractError(
            "a published release already targets the expected commit with a different recovery key"
        )
    if same_key and actual_target != expected_target:
        raise ContractError("release provenance recovery key disagrees with the actual tag target")
    return "match" if same_key else "ignore"


OTZARIA_RESULT_KEYS = PROVENANCE_KEYS | {
    "status", "child_run_id", "child_run_attempt", "expected_commit",
    "release_provenance_sha256", "release_correlation_id",
}


def validate_otzaria_result(value: object) -> dict:
    result = require_exact_keys(value, OTZARIA_RESULT_KEYS, "Otzaria pipeline result")
    provenance = {key: result[key] for key in PROVENANCE_KEYS}
    provenance["correlation_id"] = result["release_correlation_id"]
    validate_provenance(provenance)
    require_string(result["correlation_id"], "correlation_id")
    require_string(result["release_correlation_id"], "release_correlation_id")
    if result["status"] not in {"published", "reused"}:
        raise ContractError("Otzaria result status must be published or reused")
    require_positive_int(result["child_run_id"], "child_run_id")
    require_positive_int(result["child_run_attempt"], "child_run_attempt")
    require_commit(result["expected_commit"], "expected_commit")
    if result["expected_commit"] != result["target_commit"]:
        raise ContractError("expected_commit differs from target_commit")
    require_sha(result["release_provenance_sha256"], "release_provenance_sha256")
    return result


SEFORIM_RESULT_KEYS = {
    "schema_version", "status", "correlation_id", "child_run_id", "child_run_attempt",
    "source_commit", "sefaria_tag", "sefaria_release_metadata_sha256",
    "sefaria_archive_sha256", "otzaria_tag", "otzaria_asset_sha256",
    "fordb_archive_sha256", "fordb_tag",
    "expected_links_commit", "otzaria_target_commit", "release_tag",
    "build_provenance_sha256", "config_sha256", "source_links_tree_sha256",
    "packaged_links_tree_sha256", "lineage_sha256", "assets",
}


def validate_seforim_result(value: object) -> dict:
    result = require_exact_keys(value, SEFORIM_RESULT_KEYS, "Seforim pipeline result")
    if (
        type(result["schema_version"]) is not int
        or result["schema_version"] != 1
        or result["status"] not in {"published", "reused"}
    ):
        raise ContractError("invalid Seforim result schema/status")
    require_string(result["correlation_id"], "correlation_id")
    require_positive_int(result["child_run_id"], "child_run_id")
    require_positive_int(result["child_run_attempt"], "child_run_attempt")
    for field in ("source_commit", "expected_links_commit", "otzaria_target_commit"):
        require_commit(result[field], field)
    for field in (
        "sefaria_release_metadata_sha256", "sefaria_archive_sha256", "otzaria_asset_sha256",
        "fordb_archive_sha256",
        "build_provenance_sha256", "config_sha256", "source_links_tree_sha256",
        "packaged_links_tree_sha256", "lineage_sha256",
    ):
        require_sha(result[field], field)
    for field in ("sefaria_tag", "otzaria_tag", "fordb_tag", "release_tag"):
        if not isinstance(result[field], str) or not TAG_RE.fullmatch(result[field]):
            raise ContractError(f"{field} is unsafe")
    if result["fordb_tag"] != f"fordb-sha256-{result['fordb_archive_sha256']}":
        raise ContractError("fordb_tag is not content-addressed by fordb_archive_sha256")
    validate_descriptors(result["assets"], "assets")
    provenance_assets = [item for item in result["assets"] if item["name"] == "build_provenance.json"]
    if len(provenance_assets) != 1 or provenance_assets[0]["sha256"] != result["build_provenance_sha256"]:
        raise ContractError("assets must contain exactly one matching build_provenance.json")
    return result


def verify_sidecar(json_path: Path, sidecar_path: Path, validator) -> dict:
    value = load_json(json_path)
    validator(value)
    try:
        sidecar = sidecar_path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {sidecar_path}: {exc}") from exc
    expected = hashlib.sha256(json_path.read_bytes()).hexdigest().encode("ascii") + b"\n"
    if sidecar != expected:
        raise ContractError(f"{sidecar_path} is not the exact SHA-256 sidecar")
    return value


def expect(value: dict, field: str, expected: object) -> None:
    if value[field] != expected:
        raise ContractError(f"{field} mismatch: expected {expected!r}, got {value[field]!r}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    provenance_parser = sub.add_parser("validate-provenance")
    provenance_parser.add_argument("path")
    compare_parser = sub.add_parser("compare-fresh")
    compare_parser.add_argument("--recorded", required=True)
    compare_parser.add_argument("--fresh", required=True)
    classify_parser = sub.add_parser("classify-recovery")
    classify_parser.add_argument("--recorded", required=True)
    classify_parser.add_argument("--fresh", required=True)
    classify_parser.add_argument("--actual-target", required=True)
    classify_parser.add_argument("--draft", choices=("true", "false"), required=True)
    otzaria_parser = sub.add_parser("validate-otzaria-result")
    otzaria_parser.add_argument("--json", required=True)
    otzaria_parser.add_argument("--sha256", required=True)
    for name in ("correlation-id", "expected-commit", "run-id", "run-attempt"):
        otzaria_parser.add_argument(f"--{name}", required=True)
    seforim_parser = sub.add_parser("validate-seforim-result")
    seforim_parser.add_argument("--json", required=True)
    seforim_parser.add_argument("--sha256", required=True)
    for name in (
        "correlation-id", "run-id", "run-attempt", "source-commit", "sefaria-tag",
        "sefaria-release-metadata-sha256", "sefaria-archive-sha256", "otzaria-tag",
        "otzaria-asset-sha256", "fordb-archive-sha256", "fordb-tag", "expected-links-commit",
        "otzaria-target-commit", "config-sha256", "source-links-tree-sha256",
        "packaged-links-tree-sha256", "lineage-sha256",
    ):
        seforim_parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-provenance":
            validate_provenance(load_json(Path(args.path)))
        elif args.command == "compare-fresh":
            assert_fresh_bytes_match(load_json(Path(args.recorded)), load_json(Path(args.fresh)))
        elif args.command == "classify-recovery":
            print(classify_recovery_release(
                load_json(Path(args.recorded)),
                load_json(Path(args.fresh)),
                args.actual_target,
                args.draft == "true",
            ))
        elif args.command == "validate-otzaria-result":
            result = verify_sidecar(Path(args.json), Path(args.sha256), validate_otzaria_result)
            expect(result, "correlation_id", args.correlation_id)
            expect(result, "expected_commit", args.expected_commit)
            expect(result, "child_run_id", int(args.run_id))
            expect(result, "child_run_attempt", int(args.run_attempt))
        else:
            result = verify_sidecar(Path(args.json), Path(args.sha256), validate_seforim_result)
            expected = {
                "correlation_id": args.correlation_id,
                "child_run_id": int(args.run_id),
                "child_run_attempt": int(args.run_attempt),
                "source_commit": args.source_commit,
                "sefaria_tag": args.sefaria_tag,
                "sefaria_release_metadata_sha256": args.sefaria_release_metadata_sha256,
                "sefaria_archive_sha256": args.sefaria_archive_sha256,
                "otzaria_tag": args.otzaria_tag,
                "otzaria_asset_sha256": args.otzaria_asset_sha256,
                "fordb_archive_sha256": args.fordb_archive_sha256,
                "fordb_tag": args.fordb_tag,
                "expected_links_commit": args.expected_links_commit,
                "otzaria_target_commit": args.otzaria_target_commit,
                "config_sha256": args.config_sha256,
                "source_links_tree_sha256": args.source_links_tree_sha256,
                "packaged_links_tree_sha256": args.packaged_links_tree_sha256,
                "lineage_sha256": args.lineage_sha256,
            }
            for field, expected_value in expected.items():
                expect(result, field, expected_value)
        return 0
    except (ContractError, ValueError) as exc:
        print(f"pipeline result contract error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
