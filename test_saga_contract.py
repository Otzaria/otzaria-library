import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parent / ".github" / "scripts" / "saga_contract.py"
SPEC = importlib.util.spec_from_file_location("saga_contract", SCRIPT)
saga_contract = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(saga_contract)


class SagaContractTest(unittest.TestCase):
    correlation = "sefaria:123:2:export-v1:" + "a" * 64

    def value(self):
        fordb_sha = "b" * 64
        return {
            "schema_version": 1,
            "correlation_id": self.correlation,
            "correlation_sha256": hashlib.sha256(self.correlation.encode()).hexdigest(),
            "saga_run_id": 456,
            "saga_run_attempt": 1,
            "expected_links_commit": "c" * 40,
            "seforim_tool_commit": "d" * 40,
            "sefaria_tag": "export-v1",
            "sefaria_release_metadata_sha256": "a" * 64,
            "sefaria_archive_sha256": "e" * 64,
            "fordb_tag": "fordb-sha256-" + fordb_sha,
            "fordb_archive_sha256": fordb_sha,
            "fordb_provenance_sha256": "f" * 64,
        }

    def write(self, directory: Path, value=None, raw=None):
        value = self.value() if value is None else value
        data = raw if raw is not None else (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
        (directory / "saga-state.json").write_bytes(data)
        (directory / "saga-state.sha256").write_text(hashlib.sha256(data).hexdigest() + "\n")

    def validate(self, directory: Path):
        return saga_contract.validate(directory, 456, 1, self.correlation)

    def test_valid_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root)
            self.assertEqual(self.validate(root)["fordb_archive_sha256"], "b" * 64)

    def test_boolean_schema_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = self.value()
            value["schema_version"] = True
            self.write(root, value)
            with self.assertRaises(SystemExit):
                self.validate(root)

    def test_run_attempt_is_part_of_the_artifact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root)
            with self.assertRaises(SystemExit):
                saga_contract.validate(root, 456, 2, self.correlation)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = json.dumps(self.value(), sort_keys=True, separators=(",", ":"))
            raw = raw[:-1] + ',"schema_version":1}\n'
            self.write(root, raw=raw.encode())
            with self.assertRaises(SystemExit):
                self.validate(root)

    def test_correlation_must_agree_with_pinned_sefaria(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = self.value()
            value["sefaria_tag"] = "different-v1"
            self.write(root, value)
            with self.assertRaises(SystemExit):
                self.validate(root)

    def test_fordb_tag_must_match_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = self.value()
            value["fordb_tag"] = "fordb-sha256-" + "0" * 64
            self.write(root, value)
            with self.assertRaises(SystemExit):
                self.validate(root)


class SagaWorkflowContractTest(unittest.TestCase):
    root = Path(__file__).parent

    def workflow(self, name):
        return (self.root / ".github" / "workflows" / name).read_text(encoding="utf-8")

    def test_s0_persists_before_one_ambiguous_dispatch(self):
        workflow = self.workflow("sync-manual-links.yml")
        segment = workflow.split("- name: Dispatch exact Otzaria publisher and return immediately", 1)[1]
        self.assertEqual(1, segment.count("gh workflow run update-library.yml"))
        self.assertNotIn("for attempt in", segment)
        self.assertIn("reconciler will observe before retrying", segment)
        self.assertIn("retention-days: 90", workflow)

    def test_s1_never_blindly_retries_an_ambiguous_dispatch(self):
        workflow = self.workflow("saga-continue.yml")
        segment = workflow.split("- name: Idempotently dispatch exact pinned Seforim build", 1)[1]
        segment = segment.split("- name: Re-download authoritative Otzaria result for S2", 1)[0]
        self.assertEqual(1, segment.count("gh workflow run manual-generate-release.yml"))
        self.assertNotIn("for attempt in", segment)
        self.assertIn("No blind duplicate dispatch", segment)

    def test_weekly_export_dispatch_is_exactly_adoptable(self):
        workflow = self.workflow("weekly-pipeline.yml")
        self.assertIn("sparse-checkout: .github/scripts", workflow)
        self.assertIn('export_correlation="weekly:${GITHUB_RUN_ID}:${GITHUB_RUN_ATTEMPT}"', workflow)
        self.assertIn('-f orchestration_id="$export_correlation"', workflow)
        self.assertIn('export_title="Sefaria immutable export orchestration=$export_correlation"', workflow)
        self.assertIn('find_exact_run Otzaria/SefariaExport release.yml "$export_title"', workflow)

    def test_update_library_does_not_download_lfs_twice(self):
        workflow = self.workflow("update-library.yml")
        self.assertEqual(2, workflow.count("lfs: true"))
        self.assertNotIn("git lfs pull", workflow)
        self.assertNotIn("git lfs checkout", workflow)

    def test_update_library_allows_only_drafts_to_lack_tag_refs(self):
        workflow = self.workflow("update-library.yml")
        self.assertIn(
            'tag_target="$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/tags/${encoded_tag}" '
            "--jq '.object.sha' 2>/dev/null || true)\"",
            workflow,
        )
        self.assertIn('if [[ "$is_draft" != true && -z "$tag_target" ]]; then', workflow)
        self.assertIn("Published release $tag has no resolvable Git tag ref", workflow)

    def test_update_fordb_only_hydrates_sparse_inputs(self):
        workflow = self.workflow("update-fordb.yml")
        self.assertNotIn("lfs: true", workflow)
        self.assertIn("sparse-checkout-cone-mode: false", workflow)
        for path in (
            "/ForDB/",
            "/.github/scripts/",
            "/all_metadata_with_file_paths.json",
            "/fordb_latest_pointer.json",
        ):
            self.assertIn(path, workflow)
        self.assertIn(
            'git lfs pull --include="ForDB/**,all_metadata_with_file_paths.json" --exclude=""',
            workflow,
        )
        self.assertNotIn("git lfs pull\n", workflow)
        self.assertNotIn("git lfs checkout", workflow)
        self.assertIn('jq -r --arg tag "$immutable_tag"', workflow)
        self.assertNotIn('jq -er --arg tag "$immutable_tag"', workflow)
        self.assertIn('for _ in $(seq 1 12); do', workflow)
        self.assertIn(
            '[[ "$(jq -r .target_commitish fordb-verify/release.json)" == "$provenance_source" ]]',
            workflow,
        )
        self.assertNotIn('IMMUTABLE_TAG="$immutable_tag" SOURCE_COMMIT="$GITHUB_SHA"', workflow)

if __name__ == "__main__":
    unittest.main()
