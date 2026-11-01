"""Run both workflow download blocks with real producer helpers and a local gh fixture.

Set SEFORIM_TOOL_DIR to a SeforimLibrary checkout (the workflows do this after
checking out seforim-tool). No network, Gradle, or large database is needed.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

SCRIPTS = Path(__file__).resolve().parent
WORKFLOWS = SCRIPTS.parent / "workflows"
TOOL = Path(os.environ.get("SEFORIM_TOOL_DIR", SCRIPTS.parents[2] / "SeforimLibrary")).resolve()
COMMANDS = ("bash", "jq", "zstd", "unzstd", "sha256sum")
AVAILABLE = all(shutil.which(name) for name in COMMANDS) and all(
    (TOOL / ".github/scripts" / name).is_file()
    for name in ("db_asset_names.sh", "assemble_split_asset.sh")
)
GH_FIXTURE = r'''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
root = pathlib.Path(os.environ["FIXTURE_RELEASE"])
if args[:2] == ["release", "list"]:
    print(os.environ.get("FIXTURE_TAGS", "v-fixture"))
elif args[:2] == ["release", "view"]:
    per_tag = root / ("view-" + args[2] + ".json")
    print((per_tag if per_tag.is_file() else root / "release.json").read_text())
elif args[:2] == ["release", "download"]:
    name = args[args.index("-p") + 1]
    if args[2] in os.environ.get("FIXTURE_EMPTY_TAGS", "").split():
        sys.exit("no assets match the file pattern")
    dest = pathlib.Path(args[args.index("-D") + 1])
    with open(os.environ["FIXTURE_LOG"], "a") as log:
        log.write(name + "\n")
    source = root / name
    if not source.is_file():
        sys.exit("no assets match: " + name)
    dest.mkdir(parents=True, exist_ok=True)
    if os.environ.get("FIXTURE_PARTIAL") == name:
        (dest / name).write_bytes(b"partial download")
        sys.exit("connection interrupted")
    shutil.copyfile(source, dest / name)
else:
    sys.exit("unexpected gh command: " + repr(args))
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(AVAILABLE, "needs bash/jq/zstd/sha256sum and SEFORIM_TOOL_DIR producer helpers")
class ReleasedForDbDownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / "release"
        self.release.mkdir()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(GH_FIXTURE)
        gh.chmod(0o755)
        scripts = self.root / ".github/scripts"
        scripts.mkdir(parents=True)
        for helper in ("download_released_fordb_db.sh", "select_released_db_tag.sh"):
            (scripts / helper).symlink_to(SCRIPTS / helper)
        (self.root / "seforim-tool").symlink_to(TOOL, target_is_directory=True)
        self.env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                        GH_TOKEN="fixture", FIXTURE_RELEASE=str(self.release),
                        FIXTURE_LOG=str(self.root / "downloads.log"))
        self.db = b"released database\x00" * 40
        self.state = b"matching allocator state\x00" * 20

    def compress(self, data):
        return subprocess.run(["zstd", "-q", "-c"], input=data, check=True, capture_output=True).stdout

    def write_json(self, name, value):
        (self.release / name).write_text(json.dumps(value))

    def publish_metadata(self):
        self.write_json("release.json", {"assets": [
            {"name": path.name, "size": path.stat().st_size, "digest": "sha256:" + sha(path.read_bytes())}
            for path in self.release.iterdir() if path.name != "release.json"
        ]})

    def publish(self, schema=7, split=False):
        self.name = f"seforim-schema{schema}.db.zst"
        self.manifest_name = self.name + ".manifest.json"
        archive = self.compress(self.db)
        if split:
            parts = []
            for i, offset in enumerate(range(0, len(archive), 13)):
                name = f"{self.name}.part-{i:03}"
                data = archive[offset:offset + 13]
                (self.release / name).write_bytes(data)
                parts.append({"name": name, "size": len(data), "sha256": sha(data)})
            self.write_json(self.manifest_name, {"schemaVersion": 1, "archive": self.name,
                            "size": len(archive), "sha256": sha(archive), "parts": parts})
        else:
            (self.release / self.name).write_bytes(archive)
        (self.release / "seforim.db.buildstate.zst").write_bytes(self.compress(self.state))
        self.write_json("build_provenance.json", {"db_schema": {"db_schema_version": schema},
                                                "otzaria_target_commit": "a" * 40})
        self.publish_metadata()

    def mutate_manifest(self, mutate):
        manifest = json.loads((self.release / self.manifest_name).read_text())
        mutate(manifest)
        self.write_json(self.manifest_name, manifest)
        self.publish_metadata()

    def run_workflows(self, success):
        for workflow, step in (
            ("validate-fordb-book-names.yml", "Validate every ForDB file with the real runtime consumers"),
            ("update-fordb.yml", "Dry-run every candidate input against the last released seforim.db"),
        ):
            with self.subTest(workflow=workflow):
                shutil.rmtree(self.root / "dbdir", ignore_errors=True)
                text = (WORKFLOWS / workflow).read_text()
                block = text.split(f"      - name: {step}\n", 1)[1].split("        run: |\n", 1)[1]
                # Everything up to the next validation phase is the actual workflow shell.
                block = textwrap.dedent(block.split("          CANDIDATE_SHA=", 1)[0])
                result = subprocess.run(["bash", "-c", block], cwd=self.root, env=self.env,
                                        text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                dest = self.root / "dbdir"
                if success:
                    self.assertEqual((dest / "seforim.db").read_bytes(), self.db)
                    self.assertEqual((dest / "seforim.db.buildstate").read_bytes(), self.state)
                    self.assertEqual(sorted(p.name for p in dest.iterdir()),
                                     ["build_provenance.json", "seforim.db", "seforim.db.buildstate"])
                else:
                    self.assertEqual(list(dest.iterdir()), [], result.stdout + result.stderr)

    def test_schema6_and_schema7_single_and_split(self):
        for schema in (6, 7):
            for split in (False, True):
                with self.subTest(schema=schema, split=split):
                    for path in self.release.iterdir():
                        path.unlink()
                    self.publish(schema, split)
                    self.run_workflows(True)

    def publish_vectors_release_first(self):
        """A final vectors QA release is newer than the DB release and has no DB asset."""
        self.publish()
        self.write_json("view-vectors-qa.json", {"assets": [
            {"name": "gates.json"}, {"name": "validation.json"},
            {"name": "otzaria-vectors-0e87cbd9-v35-base.oxv.zst"}]})
        self.env["FIXTURE_TAGS"] = "vectors-qa\nv-fixture"
        self.env["FIXTURE_EMPTY_TAGS"] = "vectors-qa"

    def test_final_release_without_a_db_is_skipped(self):
        self.publish_vectors_release_first()
        self.run_workflows(True)

    def test_selector_skips_releases_missing_any_required_asset(self):
        self.publish()
        names = {"build_provenance.json", "seforim.db.buildstate.zst", self.name}
        for missing in sorted(names):
            self.write_json(f"view-no-{missing}.json", {"assets": [
                {"name": n} for n in sorted(names - {missing})]})
        self.env["FIXTURE_TAGS"] = "\n".join([f"no-{m}" for m in sorted(names)] + ["v-fixture"])
        result = subprocess.run(["bash", str(SCRIPTS / "select_released_db_tag.sh"), str(TOOL)],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "v-fixture"), result.stderr)

    def test_selector_fails_when_no_release_has_a_db(self):
        self.publish_vectors_release_first()
        self.env["FIXTURE_TAGS"] = "vectors-qa"
        result = subprocess.run(["bash", str(SCRIPTS / "select_released_db_tag.sh"), str(TOOL)],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_highest_schema_wins_over_compatibility_archive(self):
        self.publish()
        (self.release / "seforim-schema6.db.zst").write_bytes(self.compress(b"old DB"))
        self.publish_metadata()
        self.run_workflows(True)
        self.assertNotIn("seforim-schema6.db.zst", (self.root / "downloads.log").read_text())

    def test_single_archive_must_match_release_digest(self):
        self.publish()
        (self.release / self.name).write_bytes(self.compress(b"substituted DB"))
        self.run_workflows(False)

    def test_missing_single_archive_digest_fails_closed(self):
        self.publish()
        metadata = json.loads((self.release / "release.json").read_text())
        for asset in metadata["assets"]:
            if asset["name"] == self.name:
                asset["digest"] = None
        self.write_json("release.json", metadata)
        self.run_workflows(False)

    def test_buildstate_must_match_release_digest(self):
        self.publish()
        (self.release / "seforim.db.buildstate.zst").write_bytes(self.compress(b"wrong state"))
        self.run_workflows(False)

    def test_provenance_must_match_release_digest(self):
        self.publish()
        self.write_json("build_provenance.json", {"db_schema": {"db_schema_version": 6}})
        self.run_workflows(False)

    def test_provenance_schema_must_match_archive(self):
        self.publish()
        self.write_json("build_provenance.json", {"db_schema": {"db_schema_version": 6}})
        self.publish_metadata()
        self.run_workflows(False)

    def test_split_manifest_must_match_release_digest(self):
        self.publish(split=True)
        (self.release / self.manifest_name).write_text("{}")
        self.run_workflows(False)

    def test_corrupt_split_part_fails_without_publishing_outputs(self):
        self.publish(split=True)
        (self.release / f"{self.name}.part-001").write_bytes(b"corrupt")
        self.run_workflows(False)

    def test_missing_split_part_fails_without_publishing_outputs(self):
        self.publish(split=True)
        (self.release / f"{self.name}.part-001").unlink()
        self.run_workflows(False)

    def test_whole_split_archive_digest_is_checked(self):
        self.publish(split=True)
        self.mutate_manifest(lambda m: m.update(sha256="0" * 64))
        self.run_workflows(False)

    def test_unsafe_part_name_rejected_before_download(self):
        self.publish(split=True)
        self.mutate_manifest(lambda m: m["parts"][0].update(name="../outside"))
        self.run_workflows(False)
        self.assertNotIn("../outside", (self.root / "downloads.log").read_text())

    def test_duplicate_part_name_rejected_before_download(self):
        self.publish(split=True)
        self.mutate_manifest(lambda m: m["parts"].append(m["parts"][0]))
        self.run_workflows(False)

    def test_manifest_archive_name_must_match_selected_asset(self):
        self.publish(split=True)
        self.mutate_manifest(lambda m: m.update(archive="other.db.zst"))
        self.run_workflows(False)

    def test_partial_download_is_removed(self):
        self.publish()
        self.env["FIXTURE_PARTIAL"] = self.name
        self.run_workflows(False)

    def test_invalid_compression_never_publishes_a_partial_database(self):
        self.publish()
        (self.release / self.name).write_bytes(b"not a zstd stream")
        self.publish_metadata()
        self.run_workflows(False)


if __name__ == "__main__":
    unittest.main()
