import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).parent
SCRIPT = ROOT / ".github" / "scripts" / "find_exact_workflow_run.sh"


class WorkflowRunFinderTest(unittest.TestCase):
    def run_finder(self, rows="", *, fail=False):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "gh"
            fake.write_text(textwrap.dedent("""\
                #!/usr/bin/env bash
                [[ " $* " == *" --paginate "* ]] || exit 91
                [ -z "${MOCK_FAIL:-}" ] || exit 90
                printf '%s' "${MOCK_ROWS:-}"
            """))
            fake.chmod(0o755)
            env = dict(
                os.environ,
                PATH=tmp + os.pathsep + os.environ["PATH"],
                FIND_RUN_ATTEMPTS="1",
                MOCK_ROWS=rows,
                MOCK_FAIL="1" if fail else "",
            )
            return subprocess.run(
                ["bash", str(SCRIPT), "Owner/repo", "workflow.yml", "exact title", "a" * 40],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_one_unique_database_id_is_returned(self):
        result = self.run_finder("123\n123\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "123\n")

    def test_zero_and_duplicate_database_ids_are_distinct_failures(self):
        self.assertEqual(self.run_finder("").returncode, 1)
        result = self.run_finder("123\n456\n")
        self.assertEqual(result.returncode, 3)
        self.assertIn("Multiple", result.stderr)

    def test_listing_failure_is_not_zero_matches(self):
        result = self.run_finder(fail=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("listing failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
