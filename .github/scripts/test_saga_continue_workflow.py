import unittest
from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / "workflows" / "saga-continue.yml"


class SagaContinueWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def step(self, name):
        marker = f"      - name: {name}\n"
        self.assertEqual(self.workflow.count(marker), 1)
        return self.workflow.split(marker, 1)[1].split("\n      - ", 1)[0]

    def test_both_jobs_use_bounded_sparse_checkouts(self):
        self.assertEqual(self.workflow.count("          fetch-depth: 1\n"), 2)
        self.assertEqual(self.workflow.count("          sparse-checkout: |\n"), 2)
        self.assertNotIn("          fetch-depth: 0\n", self.workflow)
        self.assertIn("            .github/scripts\n", self.workflow)
        self.assertIn("            pipeline_result_contract.py\n", self.workflow)

    def test_s2_selects_one_successful_child_then_checks_ancestry(self):
        step = self.step("Re-download authoritative Otzaria result for S2")
        self.assertIn("gh api --paginate", step)
        self.assertIn('.status=="completed" and .conclusion=="success"', step)
        self.assertIn('[ "$count" -ne 1 ]', step)
        self.assertIn('compare/$EXPECTED_COMMIT...$child_head', step)
        self.assertIn('validate-otzaria-result', step)
        self.assertNotIn("find_exact_workflow_run.sh", step)

    def test_all_durable_handoffs_use_releases(self):
        self.assertNotIn("actions/upload-artifact", self.workflow)
        self.assertNotIn("actions/download-artifact", self.workflow)
        self.assertNotIn("gh run download", self.workflow)
        self.assertIn("pipeline-result-run-$CALLBACK_CHILD_RUN_ID-$CALLBACK_CHILD_RUN_ATTEMPT", self.workflow)
        self.assertIn("saga-state-$correlation_sha-attempt-$REQUEST_SAGA_RUN_ATTEMPT", self.workflow)


if __name__ == "__main__":
    unittest.main()
