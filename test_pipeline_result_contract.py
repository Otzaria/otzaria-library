import hashlib
import tempfile
import unittest
from pathlib import Path

import pipeline_result_contract as contract


class PipelineResultContractTest(unittest.TestCase):
    def provenance(self):
        return {
            "schema_version": 1,
            "correlation_id": "sefaria:1:1:t:" + "0" * 64,
            "target_commit": "1" * 40,
            "tag": "library-links-1",
            "asset": {"name": "otzaria_latest.zip", "size": 2, "sha256": "2" * 64},
            "auxiliary_assets": [
                {"name": "otzaria_dicta_latest.zip", "size": 3, "sha256": "3" * 64},
                {"name": "talmud_bavli_latest.tar.zst", "size": 4, "sha256": "4" * 64},
            ],
            "packaging_runtime": {"python": "3.12.10", "zlib": "1.3", "zip_compression": "deflate-9"},
            "packaging_toolchain": {
                "schema_version": 1, "python": "3.12.10", "zlib_build": "1.3",
                "zlib_runtime": "1.3", "gnu_tar": "1.35", "zstd": "1.5.7",
            },
            "config_sha256": "5" * 64,
            "source_links_tree_sha256": "6" * 64,
            "packaged_links_tree_sha256": "7" * 64,
            "lineage_sha256": "8" * 64,
        }

    def test_same_recovery_key_with_changed_bytes_is_fatal(self):
        recorded = self.provenance()
        fresh = self.provenance()
        fresh["asset"] = {**fresh["asset"], "sha256": "9" * 64}
        with self.assertRaises(contract.ContractError):
            contract.assert_fresh_bytes_match(recorded, fresh)

    def test_toolchain_drift_is_fatal_for_same_key(self):
        recorded = self.provenance()
        fresh = self.provenance()
        fresh["packaging_toolchain"] = {**fresh["packaging_toolchain"], "zstd": "1.5.6"}
        with self.assertRaises(contract.ContractError):
            contract.assert_fresh_bytes_match(recorded, fresh)

    def test_boolean_schema_versions_are_rejected(self):
        provenance = self.provenance()
        provenance["schema_version"] = True
        with self.assertRaises(contract.ContractError):
            contract.validate_provenance(provenance)
        provenance = self.provenance()
        provenance["packaging_toolchain"]["schema_version"] = True
        with self.assertRaises(contract.ContractError):
            contract.validate_provenance(provenance)

    def test_result_rejects_extra_fields(self):
        result = {**self.provenance(),
            "status": "published", "child_run_id": 1, "child_run_attempt": 1,
            "expected_commit": "1" * 40, "release_provenance_sha256": "9" * 64,
            "release_correlation_id": self.provenance()["correlation_id"],
            "extra": True,
        }
        with self.assertRaises(contract.ContractError):
            contract.validate_otzaria_result(result)

    def test_sidecar_and_trailing_lf_are_exact(self):
        result = {**self.provenance(),
            "status": "reused", "child_run_id": 1, "child_run_attempt": 2,
            "expected_commit": "1" * 40, "release_provenance_sha256": "9" * 64,
            "release_correlation_id": self.provenance()["correlation_id"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "pipeline-result.json"
            sidecar = root / "pipeline-result.sha256"
            path.write_bytes(contract.canonical_bytes(result))
            sidecar.write_bytes(hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
            self.assertEqual(result, contract.verify_sidecar(path, sidecar, contract.validate_otzaria_result))
            sidecar.write_bytes(sidecar.read_bytes().rstrip())
            with self.assertRaises(contract.ContractError):
                contract.verify_sidecar(path, sidecar, contract.validate_otzaria_result)

    def test_reuse_accepts_a_new_current_correlation(self):
        recorded = self.provenance()
        fresh = self.provenance()
        fresh["correlation_id"] = "sefaria:2:1:new:" + "a" * 64
        self.assertEqual(
            "match",
            contract.classify_recovery_release(recorded, fresh, fresh["target_commit"], False),
        )
        contract.assert_fresh_bytes_match(recorded, fresh)
        result = {
            **recorded,
            "correlation_id": fresh["correlation_id"],
            "release_correlation_id": recorded["correlation_id"],
            "status": "reused",
            "child_run_id": 2,
            "child_run_attempt": 1,
            "expected_commit": "1" * 40,
            "release_provenance_sha256": "9" * 64,
        }
        self.assertEqual(result, contract.validate_otzaria_result(result))

    def test_same_target_with_different_recovery_key_is_fatal(self):
        recorded = self.provenance()
        fresh = self.provenance()
        recorded["lineage_sha256"] = "f" * 64
        with self.assertRaises(contract.ContractError):
            contract.classify_recovery_release(recorded, fresh, fresh["target_commit"], False)

    def test_unrelated_target_with_different_key_is_ignored(self):
        recorded = self.provenance()
        fresh = self.provenance()
        recorded["lineage_sha256"] = "f" * 64
        self.assertEqual(
            "ignore",
            contract.classify_recovery_release(recorded, fresh, "e" * 40, False),
        )

    def test_same_key_with_wrong_actual_tag_target_is_fatal(self):
        with self.assertRaises(contract.ContractError):
            contract.classify_recovery_release(
                self.provenance(), self.provenance(), "e" * 40, False
            )

    def test_exact_seforim_child_schema_is_accepted(self):
        value = {
            "schema_version": 1,
            "status": "published",
            "correlation_id": "sefaria:1:1:t:" + "0" * 64,
            "child_run_id": 10,
            "child_run_attempt": 2,
            "source_commit": "1" * 40,
            "sefaria_tag": "sefaria-1",
            "sefaria_release_metadata_sha256": "2" * 64,
            "sefaria_archive_sha256": "3" * 64,
            "otzaria_tag": "library-links-1",
            "otzaria_asset_sha256": "4" * 64,
            "fordb_archive_sha256": "c" * 64,
            "fordb_tag": "fordb-sha256-" + "c" * 64,
            "expected_links_commit": "5" * 40,
            "otzaria_target_commit": "5" * 40,
            "release_tag": "release-1",
            "build_provenance_sha256": "6" * 64,
            "lineage_sha256": "7" * 64,
            "config_sha256": "8" * 64,
            "source_links_tree_sha256": "9" * 64,
            "packaged_links_tree_sha256": "a" * 64,
            "assets": [
                {"name": "build_provenance.json", "size": 1, "sha256": "6" * 64},
                {"name": "seforim.tar.zst", "size": 2, "sha256": "b" * 64},
            ],
        }
        self.assertEqual(value, contract.validate_seforim_result(value))
        value["schema_version"] = True
        with self.assertRaises(contract.ContractError):
            contract.validate_seforim_result(value)


if __name__ == "__main__":
    unittest.main()
