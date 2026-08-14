from pathlib import Path
import unittest


WORKFLOWS = Path(__file__).parents[1] / "workflows"
SCRIPTS = Path(__file__).parent


class ReleaseConsumerContractTest(unittest.TestCase):
    def test_fordb_consumers_ignore_workflow_handoff_prereleases(self):
        for name in ("update-fordb.yml", "validate-fordb-book-names.yml"):
            workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
            self.assertIn("--exclude-pre-releases", workflow, name)
            self.assertIn("--exclude-drafts", workflow, name)

    def test_manual_links_marker_has_a_github_stable_release_asset_name(self):
        workflow = (WORKFLOWS / "sync-manual-links.yml").read_text(encoding="utf-8")
        publish = workflow.split(
            "      - name: Publish immutable manual-links refresh report release\n", 1
        )[1].split("\n  start-saga:", 1)[0]
        self.assertIn(
            "manual-links-refresh-artifact/manual-links-refresh-complete", publish
        )
        self.assertNotIn(
            "manual-links-refresh-artifact/.manual-links-refresh-complete", publish
        )

    def test_release_publisher_rejects_asset_names_github_would_normalize(self):
        helper = (SCRIPTS / "publish_release_handoff.sh").read_text(encoding="utf-8")
        self.assertIn("release asset basename is unsafe or would be normalized by GitHub", helper)
        self.assertIn("^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$", helper)
        self.assertIn('repos/$GITHUB_REPOSITORY/releases/tags/$tag', helper)
        self.assertIn("targetCommitish:.target_commitish", helper)
        self.assertNotIn('gh release view "$tag" --json', helper)


if __name__ == "__main__":
    unittest.main()
