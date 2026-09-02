import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import validate_manual_links_refs as validator


DICTA = "DictaToOtzaria/ערוך/links"


def config():
    return {
        "schema_version": 1,
        "seforim_tool_ref": "refs/heads/otzaria",
        "links_roots": [
            {"path": "Regular/links", "expected_state": "present"},
            {"path": "MoreBooks/links", "expected_state": "present"},
            {"path": DICTA, "expected_state": "present"},
            {"path": "Absent/links", "expected_state": "absent"},
        ],
        "bootstrap_adapters": {"MoreBooks/links": "morebooks_heref_v1"},
    }


def workspace_with(temporary):
    workspace = Path(temporary)
    (workspace / validator.CONFIG_NAME).write_text(
        json.dumps(config(), ensure_ascii=False), encoding="utf-8"
    )
    return workspace


def write_records(workspace, relative, records):
    # indent=2 is how the committed link files are formatted; git's rename
    # similarity is line-based, so the fixture must match to behave like one.
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return relative


def git(workspace, *args):
    return subprocess.run(
        ["git", *args], cwd=workspace, check=True, capture_output=True
    ).stdout.decode("utf-8")


def git_fixture(workspace):
    """A repository whose rename detection does not depend on the caller's config."""
    git(workspace, "init", "-q", "-b", "main")
    git(workspace, "config", "user.email", "gate@example.invalid")
    git(workspace, "config", "user.name", "gate")
    git(workspace, "config", "commit.gpgsign", "false")
    git(workspace, "config", "diff.renames", "true")


class ValidateManualLinksRefsTest(unittest.TestCase):
    def test_adapter_roots_are_checked_after_lineage_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)

            self.assertEqual(
                ["Regular/links", "MoreBooks/links", DICTA],
                validator.synced_roots(validator.load_config(workspace)),
            )

    def test_invalid_config_is_a_loud_failure_not_a_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            broken = config()
            broken["links_roots"][0]["expected_state"] = "maybe"
            (workspace / validator.CONFIG_NAME).write_text(
                json.dumps(broken, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaises(ValueError):
                validator.load_config(workspace)

    def test_missing_ref_in_adapter_root_is_still_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            relative = write_records(
                workspace,
                "MoreBooks/links/example_links.json",
                [{"path_2": "כתובות.txt", "line_index_2": 3}],
            )

            problems = validator.check_file(workspace, relative, {"כתובות"})

            self.assertEqual(1, len(problems))
            self.assertIn("new_target_ref_required", problems[0])

    def test_a_gershayim_target_is_sefaria_owned_and_needs_ref_2(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            relative = write_records(
                workspace,
                f"{DICTA}/ערוך_links.json",
                [{"path_2": 'רש"י על שבת.txt', "line_index_2": 3}],
            )

            problems = validator.check_file(workspace, relative, {'רש"י על שבת'})

            self.assertEqual(1, len(problems))
            self.assertIn("new_target_ref_required", problems[0])

    def test_a_gershayim_target_with_ref_2_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            relative = write_records(
                workspace,
                f"{DICTA}/ערוך_links.json",
                [{"path_2": 'רש"י על שבת.txt', "line_index_2": 3, "ref_2": "Rashi on Shabbat 2a:1"}],
            )

            self.assertEqual([], validator.check_file(workspace, relative, {'רש"י על שבת'}))

    def test_the_quote_stripped_spelling_is_not_a_sefaria_book(self):
        # The comparison is verbatim: no gershayim folding in either direction.
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            relative = write_records(
                workspace,
                f"{DICTA}/ערוך_links.json",
                [{"path_2": "רשי על שבת.txt", "line_index_2": 3, "ref_2": "Rashi on Shabbat 2a:1"}],
            )

            problems = validator.check_file(workspace, relative, {'רש"י על שבת'})

            self.assertEqual(1, len(problems))
            self.assertIn("ref_2 side classification changed", problems[0])

    def test_extensionless_target_names_no_book(self):
        # Mirrors targetTitleOrNull: without .txt the value addresses no book at all.
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            relative = write_records(
                workspace,
                f"{DICTA}/ערוך_links.json",
                [{"path_2": 'רש"י על שבת', "line_index_2": 3}],
            )

            self.assertEqual([], validator.check_file(workspace, relative, {'רש"י על שבת'}))

    def test_a_renamed_and_rewritten_file_is_still_validated(self):
        # git calls this R, not M: an A/M-only filter waved the rewrite through.
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            git_fixture(workspace)
            old = write_records(
                workspace,
                "MoreBooks/links/וזה לשונו - שובבי''ם_links.json",
                [
                    {"path_1": "אורח חיים.txt", "line_index_1": index,
                     "path_2": "רש״י על שבת.txt", "line_index_2": index}
                    for index in range(120)
                ],
            )
            git(workspace, "add", "-A")
            git(workspace, "commit", "-qm", "base")
            base = git(workspace, "rev-parse", "HEAD").strip()

            new = "MoreBooks/links/וזה לשונו - שובבי״ם_links.json"
            git(workspace, "mv", old, new)
            write_records(
                workspace,
                new,
                [
                    {"path_1": "אורח חיים.txt", "line_index_1": index,
                     "path_2": 'רש"י על שבת.txt', "line_index_2": index}
                    for index in range(120)
                ],
            )
            git(workspace, "add", "-A")
            git(workspace, "commit", "-qm", "rename and rewrite")

            # Guard the fixture: the whole point is a change git classifies as R.
            status = git(workspace, "diff", "--name-status", base, "HEAD", "--")
            self.assertTrue(status.startswith("R"), status)

            roots = validator.synced_roots(validator.load_config(workspace))
            self.assertEqual([new], validator.changed_link_files(workspace, base, roots))
            problems = validator.check_file(workspace, new, {'רש"י על שבת'})
            self.assertEqual(120, len(problems))

    def test_a_deleted_required_root_is_caught_though_no_file_is_checked(self):
        # A deletion carries no records, but an absent required root aborts the sync.
        with tempfile.TemporaryDirectory() as temporary:
            workspace = workspace_with(temporary)
            config = validator.load_config(workspace)
            for root in validator.synced_roots(config):
                write_records(workspace, f"{root}/example_links.json", [])
            validator.assert_roots_intact(workspace, config)

            (workspace / "MoreBooks/links/example_links.json").unlink()
            (workspace / "MoreBooks/links").rmdir()

            with self.assertRaises(ValueError):
                validator.assert_roots_intact(workspace, config)


if __name__ == "__main__":
    unittest.main()
