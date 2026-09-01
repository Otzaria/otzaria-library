import hashlib
import json
import struct
import tempfile
import unittest
import argparse
import zipfile
from pathlib import Path

import manual_links_packaging as packaging


class ManualLinksPackagingTest(unittest.TestCase):
    def write_config(self, root: Path, roots, aliases=None):
        config = {
            "schema_version": 1,
            "seforim_tool_ref": "refs/heads/otzaria",
            "links_roots": roots,
            "bootstrap_adapters": {},
            "he_title_aliases": aliases or {},
            "bootstrap_file_renames": [],
            "bootstrap_record_overrides": [],
        }
        (root / packaging.CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")
        return packaging.validate_config(config)

    def test_boolean_config_schema_version_is_rejected(self):
        with self.assertRaises(packaging.PackagingError):
            packaging.validate_config({"schema_version": True})

    def test_he_title_aliases_are_an_explicit_per_root_one_to_one_bridge(self):
        roots = [{"path": "links", "expected_state": "present"}]
        base = {
            "schema_version": 1,
            "seforim_tool_ref": "refs/heads/otzaria",
            "links_roots": roots,
            "bootstrap_adapters": {},
            "bootstrap_file_renames": [],
            "bootstrap_record_overrides": [],
        }
        rejected = [
            None,
            [],
            {"links": {}},
            {"other": {"רשי על שבת": "רש\"י על שבת"}},
            {"links": {"רשי על שבת": "רשי על שבת"}},
            {"links": {"רשי על שבת": "רש\"י על שבת", "רשי על עירובין": "רש\"י על שבת"}},
            {"links": {"רשי על שבת": "רש\"י על שבת", "רש\"י על שבת": "רשבם"}},
            {"links": {"רשי על שבת": " רש\"י על שבת "}},
            {"links": {"a/b": "רש\"י על שבת"}},
            {"links": {"רשי על שבת": 1}},
        ]
        for index, aliases in enumerate(rejected):
            config = dict(base)
            if aliases is not None:
                config["he_title_aliases"] = aliases
            with self.assertRaises(packaging.PackagingError, msg=f"alias case {index} must fail"):
                packaging.validate_config(config)

        accepted = dict(base, he_title_aliases={"links": {"רשי על שבת": "רש\"י על שבת"}})
        self.assertEqual(
            {"links": {"רשי על שבת": "רש\"י על שבת"}},
            packaging.validate_config(accepted)["he_title_aliases"],
        )

    def test_collision_after_flattening_is_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one", "two"):
                (root / name).mkdir()
                (root / name / "same.json").write_text(name, encoding="utf-8")
            config = self.write_config(root, [
                {"path": "one", "expected_state": "present"},
                {"path": "two", "expected_state": "present"},
            ])
            with self.assertRaises(packaging.PackagingError):
                packaging.tree_hashes(root, config)

    def test_absent_root_is_part_of_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self.write_config(root, [{"path": "missing", "expected_state": "absent"}])
            source, packaged, files = packaging.tree_hashes(root, config)
            expected = hashlib.sha256(packaging.MAGIC)
            path = b"missing"
            expected.update(struct.pack(">I", len(path)))
            expected.update(path)
            expected.update(b"\x00")
            self.assertEqual(expected.hexdigest(), source)
            self.assertEqual(hashlib.sha256(packaging.MAGIC).hexdigest(), packaged)
            self.assertEqual([], files)

    def test_tree_framing_matches_terra_golden(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "r").mkdir()
            (root / "r" / "x.json").write_bytes(b"{}")
            config = self.write_config(root, [
                {"path": "r", "expected_state": "present"},
                {"path": "a", "expected_state": "absent"},
            ])
            source, packaged, _ = packaging.tree_hashes(root, config)
            self.assertEqual("a1c8de6378768a32171c5ab13895bae224a95ede6f1092b5448e142ecdc8dba1", source)
            self.assertEqual("1906874d85febfbb60fd0167cf17da50e6fdcb572ebf109a2c4842c0664b6c5a", packaged)

    def test_all_utf8_sorted_root_states_precede_all_globally_sorted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z").mkdir()
            (root / "z" / "b.json").write_bytes(b"2")
            (root / "a").mkdir()
            (root / "a" / "é.json").write_bytes(b"1")
            config = self.write_config(root, [
                {"path": "z", "expected_state": "present"},
                {"path": "m", "expected_state": "absent"},
                {"path": "a", "expected_state": "present"},
            ])
            source, packaged, _ = packaging.tree_hashes(root, config)
            self.assertEqual("d40f6615f82dd76ff65fd667ca6d6a520822960f89d4868528c8978ab385a9dc", source)
            self.assertEqual("0cb2cd925172882ec75b3bbe4dfbcdde5864e39dd3bd3e761ad5ed1670bdbe48", packaged)

    def test_nested_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "links" / "nested").mkdir(parents=True)
            config = self.write_config(root, [{"path": "links", "expected_state": "present"}])
            with self.assertRaises(packaging.PackagingError):
                packaging.tree_hashes(root, config)

    def test_reproducible_zip_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "א.txt").write_text("same", encoding="utf-8")
            first, second = root / "one.zip", root / "two.zip"
            packaging.write_reproducible_zip(source, first)
            packaging.write_reproducible_zip(source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_package_requires_and_embeds_matching_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            links = root / "source-links"
            links.mkdir()
            (links / "one_links.json").write_text("[]", encoding="utf-8")
            config = self.write_config(root, [{"path": "source-links", "expected_state": "present"}])
            source_hash, packaged_hash, _ = packaging.tree_hashes(root, config)
            config_hash = packaging.sha256_file(root / packaging.CONFIG_NAME)
            lineage = {
                "schema_version": 1,
                "sefaria": {
                    "tag": "2026-01-01_00-00-1-1",
                    "release_metadata_sha256": "0" * 64,
                    "run_id": 1,
                    "run_attempt": 1,
                    "archive": {
                        "sha256": "1" * 64,
                        "size": 0,
                        "parts": [{"name": "export.tar.zst", "sha256": "3" * 64, "size": 0}],
                    },
                    "applied_changelog_chain": [],
                },
                "seforim_tool_commit": "2" * 40,
                "source_links_tree_sha256": source_hash,
                "packaged_links_tree_sha256": packaged_hash,
                "config_sha256": config_hash,
            }
            (root / packaging.LINEAGE_NAME).write_bytes(packaging.canonical_bytes(lineage) + b"\n")
            (root / packaging.TOOLCHAIN_NAME).write_text(
                '{"schema_version":1,"python":"3.12.10","zlib_build":"1.3","zlib_runtime":"1.3","gnu_tar":"1.35","zstd":"1.5.7"}\n',
                encoding="utf-8",
            )
            output = root / "release.zip"
            result = root / "result.json"
            packaging.package(argparse.Namespace(workspace=str(root), output=str(output), result=str(result)))
            with zipfile.ZipFile(output) as archive:
                self.assertIn("links/one_links.json", archive.namelist())
                self.assertIn(packaging.CONFIG_NAME, archive.namelist())
                self.assertIn(packaging.LINEAGE_NAME, archive.namelist())
                self.assertIn(packaging.TOOLCHAIN_NAME, archive.namelist())
            self.assertEqual(packaging.sha256_file(output), json.loads(result.read_text())["asset"]["sha256"])

    def test_seforim_tool_is_resolved_from_the_configured_ref_and_pinned(self):
        root = Path(__file__).resolve().parent
        workflow = (root / ".github/workflows/sync-manual-links.yml").read_text(encoding="utf-8")
        self.assertIn("ref=\"$(jq -r '.seforim_tool_ref' manual_links_sync.json)\"", workflow)
        self.assertIn('git ls-remote https://github.com/Otzaria/SeforimLibrary.git "$ref"', workflow)
        self.assertIn('ref: ${{ steps.tool.outputs.sha }}', workflow)
        self.assertIn('git merge-base --is-ancestor "$TOOL_SHA" "origin/$branch"', workflow)
        self.assertNotIn("repos/Otzaria/SeforimLibrary/commits/otzaria", workflow)

    def test_free_disk_space_action_is_pinned_to_a_full_commit(self):
        root = Path(__file__).resolve().parent
        expected = "jlumbroso/free-disk-space@54081f138730dfa15788a46383842cd2f914a1be"
        for name in ("update-library.yml", "sync-manual-links.yml"):
            workflow = (root / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn(expected, workflow)
            self.assertNotIn("jlumbroso/free-disk-space@main", workflow)


if __name__ == "__main__":
    unittest.main()
