import unittest
from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / "workflows" / "saga-continue.yml"
RULE_SCRIPT = Path(__file__).with_name("select_earliest_successful_child.sh")


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

    def test_s2_selects_the_canonical_child_then_checks_ancestry(self):
        step = self.step("Re-download authoritative Otzaria result for S2")
        self.assertIn("gh api --paginate", step)
        self.assertIn(
            "bash .github/scripts/select_earliest_successful_child.sh", step
        )
        self.assertIn('compare/$EXPECTED_COMMIT...$child_head', step)
        self.assertIn('pipeline-result-run-$run_id-$attempt', step)
        self.assertIn('validate-otzaria-result', step)
        self.assertIn('--correlation-id "$CORRELATION_ID" --expected-commit "$EXPECTED_COMMIT"', step)
        self.assertNotIn("find_exact_workflow_run.sh", step)

    def test_s2_fails_closed_when_no_child_of_the_correlation_succeeded(self):
        """Adopting a duplicate is not the same as accepting an empty set."""
        step = self.step("Re-download authoritative Otzaria result for S2")
        self.assertIn('if [ "$scan_rc" -eq 1 ]; then', step)
        self.assertIn(
            '::error::Expected a successful Otzaria child for the canonical '
            'correlation; found none.',
            step,
        )
        self.assertIn('[ "$scan_rc" -eq 0 ] || exit "$scan_rc"', step)

    def test_s2_delegates_the_canonical_child_rule_to_the_shared_script(self):
        """S2 must name the child reconcile_sagas.sh names: a gate that refuses
        what the reconciler already adopted can never be satisfied, and the
        saga then fails on every scheduled tick until an operator intervenes."""
        step = self.step("Re-download authoritative Otzaria result for S2")
        self.assertNotIn('$4=="success"', step)
        self.assertNotIn('[ "$count" -ne 1 ]', step)
        self.assertIn("-f event=workflow_dispatch -f per_page=100", step)
        self.assertIn(
            "select(.display_title==env.TITLE) | "
            "[(.id|tostring),.created_at,.status,(.conclusion//\"-\")] | @tsv",
            step,
        )
        rule = "awk -F'\\t' '$3==\"completed\" && $4==\"success\" && !found++ {print $1}'"
        self.assertEqual(RULE_SCRIPT.read_text(encoding="utf-8").count(rule), 1)

    def test_all_durable_handoffs_use_releases(self):
        self.assertNotIn("actions/upload-artifact", self.workflow)
        self.assertNotIn("actions/download-artifact", self.workflow)
        self.assertNotIn("gh run download", self.workflow)
        self.assertIn("pipeline-result-run-$CALLBACK_CHILD_RUN_ID-$CALLBACK_CHILD_RUN_ATTEMPT", self.workflow)
        self.assertIn("saga-state-$correlation_sha-attempt-$REQUEST_SAGA_RUN_ATTEMPT", self.workflow)


if __name__ == "__main__":
    unittest.main()
