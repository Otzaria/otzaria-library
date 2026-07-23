import unittest

import sefaria_release_chain as chain


class SefariaReleaseChainTest(unittest.TestCase):
    def metadata(self):
        digest = "0" * 64
        return {
            "schema_version": 1,
            "tag": "new",
            "run_id": 1,
            "run_attempt": 1,
            "source_commit": "1" * 40,
            "previous": {"tag": "old", "metadata_sha256": digest},
            "archive": {"sha256": digest, "size": 0, "parts": [{"name": "a.tar.zst", "size": 0, "sha256": digest}]},
            "manifest": {"name": "manifest.txt", "size": 0, "sha256": digest},
            "titles": {"name": "titles.json", "size": 0, "sha256": digest},
            "changelog": {"name": "changelog_diff.json", "size": 0, "sha256": digest, "old_tag": "old", "new_tag": "new"},
        }

    def test_valid_metadata(self):
        self.assertEqual("new", chain.validate_metadata(self.metadata(), "new")["tag"])

    def test_boolean_schema_version_fails(self):
        value = self.metadata()
        value["schema_version"] = True
        with self.assertRaises(chain.ChainError):
            chain.validate_metadata(value, "new")

    def test_wrong_changelog_boundary_fails(self):
        value = self.metadata()
        value["changelog"]["old_tag"] = "fork"
        with self.assertRaises(chain.ChainError):
            chain.validate_metadata(value, "new")

    def test_parts_must_be_sorted(self):
        value = self.metadata()
        value["archive"]["parts"] = [
            {"name": "z", "size": 0, "sha256": "0" * 64},
            {"name": "a", "size": 0, "sha256": "0" * 64},
        ]
        with self.assertRaises(chain.ChainError):
            chain.validate_metadata(value, "new")

    def test_delayed_ancestor_is_classified_as_stale_dispatch(self):
        target = [("old", "1" * 64), ("root", "2" * 64)]
        committed = [("new", "3" * 64), ("old", "1" * 64), ("root", "2" * 64)]
        self.assertEqual("stale_dispatch", chain.classify_non_descendant(target, committed))

    def test_disjoint_immutable_chains_are_classified_as_fork(self):
        target = [("branch-a", "1" * 64), ("shared-root", "2" * 64)]
        committed = [("branch-b", "3" * 64), ("shared-root", "2" * 64)]
        self.assertEqual("fork", chain.classify_non_descendant(target, committed))


if __name__ == "__main__":
    unittest.main()
