import json
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
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return relative


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


if __name__ == "__main__":
    unittest.main()
