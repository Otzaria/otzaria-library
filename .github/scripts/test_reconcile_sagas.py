import subprocess
from pathlib import Path
import unittest
import os


SCRIPT = Path(__file__).with_name("reconcile_sagas.sh")


class ReconcileSagasContractTest(unittest.TestCase):
    def test_reconciler_reads_release_state_not_actions_artifacts(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('gh release download "$release_tag"', source)
        self.assertIn('release_tag="saga-state-$correlation_sha-attempt-$saga_attempt"', source)
        self.assertNotIn("/artifacts", source)
        self.assertNotIn("gh run download", source)

    def test_scheduled_scan_excludes_pre_release_contract_roots(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("SAGA_STATE_RELEASE_ROLLOUT_AT", source)
        self.assertIn('.created_at >= \\"$STATE_RELEASE_ROLLOUT_AT\\"', source)

    def test_explicit_retirement_precedes_any_recovery_action(self):
        source = SCRIPT.read_text(encoding="utf-8")
        loop = source.split("for saga_run in $RUNS; do", 1)[1]
        retirement = 'grep -Fxq "$saga_run" "$RETIRED_SAGAS_FILE"'
        metadata_lookup = 'saga_meta=$(gh api "repos/$REPO/actions/runs/$saga_run"'

        self.assertIn('RETIRED_SAGAS_FILE=${SAGA_RETIRED_FILE:-', source)
        self.assertIn(retirement, loop)
        self.assertLess(loop.index(retirement), loop.index(metadata_lookup))
        self.assertIn("retired saga=$saga_run skipped by explicit operator tombstone", loop)

    def test_active_seforim_row_preserves_head_sha(self):
        source = SCRIPT.read_text(encoding="utf-8")
        function = source.split("find_seforim_child() {", 1)[1].split(
            "\ndispatch_continuation() {", 1
        )[0]
        self.assertIn('(.conclusion//"-")', function)
        self.assertNotIn('(.conclusion//"")', function)

        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    "IFS=$'\\t' read -r id status conclusion head; "
                    "printf '%s\\n' \"$id|$status|$conclusion|$head\""
                ),
            ],
            input=(
                "30328903115\tin_progress\t-\t"
                "b64f8583cc910dc5cd7b5f846fed153c39626751\n"
            ),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout.strip(),
            (
                "30328903115|in_progress|-|"
                "b64f8583cc910dc5cd7b5f846fed153c39626751"
            ),
        )

    def test_terminal_failed_seforim_child_is_returned_not_reported_missing(self):
        """A failed exact child must reach the bounded retry path exactly once."""
        functions = SCRIPT.read_text(encoding="utf-8").split("for saga_run in $RUNS; do", 1)[0]
        with self.subTest("failed child is selected"):
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        "gh() {\n"
                        "  case \"$*\" in\n"
                        "    *sync-manual-links.yml/runs*) printf '' ;;\n"
                        "    *manual-generate-release.yml/runs*) "
                        "printf '42\\tcompleted\\tfailure\\tpayload\\n' ;;\n"
                        "    *compare*) printf 'identical\\n' ;;\n"
                        "    *) return 99 ;;\n"
                        "  esac\n"
                        "}\n"
                        "source /dev/stdin\n"
                        "value=$(find_seforim_child title payload); status=$?; "
                        "printf '%s|%s\\n' \"$status\" \"$value\""
                    ),
                ],
                input=functions,
                text=True,
                capture_output=True,
                env={**os.environ, "SAGA_SINCE": "2026-08-01T00:00:00Z"},
                check=True,
            )
        self.assertEqual(result.stdout.strip(), "0|42")

    def test_exhausted_recovery_is_a_warning_not_a_recurring_failure(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("MAX_RERUN_ATTEMPTS=${SAGA_MAX_RERUN_ATTEMPTS:-2}", source)
        self.assertIn("awaiting operator recovery", source)
        self.assertNotIn('echo "::error::continuation $rid exhausted', source)
        self.assertNotIn('echo "::error::$label $rid exhausted', source)


if __name__ == "__main__":
    unittest.main()
