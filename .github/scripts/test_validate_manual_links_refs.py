import json
import tempfile
import unittest
from pathlib import Path

import validate_manual_links_refs as validator


class ValidateManualLinksRefsTest(unittest.TestCase):
    def test_adapter_roots_are_checked_after_lineage_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            config = {
                "links_roots": [
                    {"path": "Regular/links", "expected_state": "present"},
                    {"path": "MoreBooks/links", "expected_state": "present"},
                    {"path": "Absent/links", "expected_state": "absent"},
                ],
                "bootstrap_adapters": {
                    "MoreBooks/links": "morebooks_heref_v1",
                },
            }
            (workspace / validator.CONFIG_NAME).write_text(
                json.dumps(config), encoding="utf-8"
            )

            self.assertEqual(
                ["Regular/links", "MoreBooks/links"],
                validator.synced_roots(workspace),
            )

    def test_missing_ref_in_adapter_root_is_still_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            relative = "MoreBooks/links/example_links.json"
            path = workspace / relative
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps([{"path_2": "כתובות.txt", "line_index_2": 3}]),
                encoding="utf-8",
            )

            problems = validator.check_file(workspace, relative, {"כתובות"})

            self.assertEqual(1, len(problems))
            self.assertIn("new_target_ref_required", problems[0])


if __name__ == "__main__":
    unittest.main()
