from pathlib import Path
import unittest


WORKFLOWS = Path(__file__).parents[1] / "workflows"


class ReleaseConsumerContractTest(unittest.TestCase):
    def test_fordb_consumers_ignore_workflow_handoff_prereleases(self):
        for name in ("update-fordb.yml", "validate-fordb-book-names.yml"):
            workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("--exclude-pre-releases", workflow, name)
            self.assertIn("--exclude-drafts", workflow, name)


if __name__ == "__main__":
    unittest.main()
