import subprocess
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("reconcile_sagas.sh")


class ReconcileSagasContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
