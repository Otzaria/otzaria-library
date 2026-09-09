"""Self-test for the weekly orchestration head.

The step body is extracted from `weekly-pipeline.yml` and its functions are run
against a stubbed `gh`, the same way `test_reconcile_sagas.py` runs the
reconciler's: the head is only observable through what it prints, so the
assertions are on its output, not on its source, wherever that is possible.
"""

import subprocess
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "weekly-pipeline.yml"
STEP = "Prepare Otzaria sources, then export Sefaria"
# Everything above this line is definitions; below it the head dispatches for real.
MAIN_MARKER = 'prepare_correlation="weekly:'
# SefariaExport is a sibling checkout on an operator machine, not a dependency of
# this repository; when it is there, the verified step name is checked against it.
EXPORT_RELEASE = (
    Path(__file__).resolve().parents[3] / "SefariaExport" / ".github" / "workflows" / "release.yml"
)
DISPATCH_STEP = "Dispatch exact manual-link synchronization"

# `$RUNNER_TEMP` and the run identity exist on every runner; a self-test has to
# supply them before the step's `set -u` reads them.  `sleep` is replaced by a
# clock that advances `SECONDS`, so a 10-minute heartbeat is asserted in
# milliseconds and the 60s cadence never runs.
SETTINGS = (
    "export RUNNER_TEMP=\"$(mktemp -d)\"\n"
    "trap 'rm -rf \"$RUNNER_TEMP\"' EXIT\n"
    "export GITHUB_RUN_ID=33987355439\n"
    "export GITHUB_RUN_ATTEMPT=1\n"
    "sleep() { echo \"SLEEP $1\"; SECONDS=$((SECONDS + $1)); }\n"
    # Every poll happens inside `state="$(gh …)"`, i.e. a subshell, so the poll
    # counter has to live in a file to survive back to the assertions.
    ': >"$RUNNER_TEMP/polls"\n'
    "polls() { wc -l <\"$RUNNER_TEMP/polls\" | tr -d ' '; }\n"
)


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def step_body(name=STEP):
    """Return the `run: |` block of one step, dedented to column 0."""
    marker = f"      - name: {name}\n"
    text = workflow_text()
    assert text.count(marker) == 1, f"{name} is not a unique step"
    rest = text.split(marker, 1)[1].split("        run: |\n", 1)[1]
    lines = []
    for line in rest.split("\n"):
        if line.strip() and not line.startswith(" " * 10):
            break
        lines.append(line[10:])
    return "\n".join(lines)


def run_bash(script):
    """Run a script piped through stdin.  A `bash -c` argument is rewritten by the
    shell's own command-line parsing on a Windows checkout, and text-mode pipes
    rewrite every newline there; binary stdin survives both."""
    result = subprocess.run(
        ["bash", "/dev/stdin"],
        input=script.encode("utf-8"),
        capture_output=True,
    )
    result.stdout = result.stdout.decode("utf-8", "replace")
    result.stderr = result.stderr.decode("utf-8", "replace")
    return result


def run_functions(stub, snippet):
    """Run a snippet against the head's own functions with `gh` stubbed out."""
    prelude = step_body().split(MAIN_MARKER, 1)[0]
    return run_bash(SETTINGS + stub + prelude + "\nset +e\n" + snippet)


def run_whole_step(stub):
    """Run the entire step, dispatch and all, against a stubbed `gh` and lookup."""
    return run_bash(SETTINGS + stub + step_body())


def poll_stub(script, jobs="  export · Run export pipeline via Docker Compose [failure]"):
    """A `gh` whose run-state answers come from `script`, a bash case body keyed on
    the poll number, plus a fixed jobs listing (the head asks jq to format it, so a
    stub returns the formatted line directly)."""
    return (
        "gh() {\n"
        '  case "$*" in\n'
        '    *"/jobs?per_page=100"*)\n'
        f"      printf '%s\\n' '{jobs}' ;;\n"
        '    *"actions/runs/"*)\n'
        '      echo x >>"$RUNNER_TEMP/polls"\n'
        '      case "$(polls)" in\n'
        f"{script}\n"
        "      esac ;;\n"
        "    *) return 99 ;;\n"
        "  esac\n"
        "}\n"
    )


class WatchRunTest(unittest.TestCase):
    def test_a_failed_child_is_reported_with_its_url_and_failed_steps(self):
        """`##[error]sefaria-export run … concluded failure` was the whole post-mortem."""
        result = run_functions(
            poll_stub("        *) printf 'completed:failure\\n' ;;"),
            "watch_run Otzaria/SefariaExport 33986948151 sefaria-export; "
            'echo "STATUS=$?"',
        )
        url = "https://github.com/Otzaria/SefariaExport/actions/runs/33986948151"
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn(f"sefaria-export run 33986948151: {url}", result.stdout)
        self.assertIn(f"sefaria-export concluded failure after 00:00 — {url}", result.stdout)
        self.assertIn("Run export pipeline via Docker Compose", result.stdout)
        self.assertIn(
            f"::error::sefaria-export run 33986948151 concluded failure — {url}",
            result.stdout,
        )

    def test_a_transient_error_is_printed_once_per_class_not_once_per_poll(self):
        """`wait-err.txt` was grepped for HTTP 401 and never printed."""
        result = run_functions(
            poll_stub(
                "        1|2|3|4|5) echo 'gh: Server Error (HTTP 502)' >&2; return 1 ;;\n"
                "        6) printf 'in_progress:\\n' ;;\n"
                "        *) printf 'completed:success\\n' ;;"
            ),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"',
        )
        self.assertIn("STATUS=0", result.stdout, result.stderr)
        printed = [line for line in result.stdout.splitlines() if "poll transient" in line]
        self.assertEqual(len(printed), 1, result.stdout)
        self.assertIn("gh: Server Error (HTTP 502)", printed[0])
        self.assertIn("poll recovered", result.stdout)
        self.assertIn("after 5 transient poll(s)", result.stdout)

    def test_a_sustained_transient_outage_is_bounded(self):
        result = run_functions(
            poll_stub("        *) echo 'gh: Server Error (HTTP 502)' >&2; return 1 ;;"),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"; echo "POLLS=$(polls)"',
        )
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("POLLS=30", result.stdout)
        self.assertIn("30 consecutive transient polls", result.stdout)
        self.assertIn("gh: Server Error (HTTP 502)", result.stdout)

    def test_a_deleted_run_is_fatal_and_never_polls_for_four_hours(self):
        """404 used to fall through to `*) sleep 60`, i.e. a silent 4-hour burn."""
        result = run_functions(
            poll_stub("        *) echo 'gh: Not Found (HTTP 404)' >&2; return 1 ;;"),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"; echo "POLLS=$(polls)"',
        )
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("POLLS=3", result.stdout)
        self.assertIn("3 consecutive missing polls", result.stdout)
        self.assertIn("a deleted run cannot reappear", result.stdout)

    def test_a_permission_403_is_fatal_but_a_rate_limit_403_only_backs_off(self):
        """A PAT that lost actions:read answers 403, not 401, and cannot heal; a
        secondary rate limit answers 403 too and heals on its own."""
        forbidden = run_functions(
            poll_stub(
                "        *) echo 'gh: Resource not accessible by personal access "
                "token (HTTP 403)' >&2; return 1 ;;"
            ),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"; echo "POLLS=$(polls)"',
        )
        self.assertIn("STATUS=1", forbidden.stdout, forbidden.stderr)
        self.assertIn("POLLS=5", forbidden.stdout)
        self.assertIn("5 consecutive forbidden polls", forbidden.stdout)
        self.assertIn("actions:read", forbidden.stdout)

        throttled = run_functions(
            poll_stub(
                "        1|2|3|4|5|6|7) echo 'gh: You have exceeded a secondary rate "
                "limit (HTTP 403)' >&2; return 1 ;;\n"
                "        *) printf 'completed:success\\n' ;;"
            ),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"',
        )
        self.assertIn("STATUS=0", throttled.stdout, throttled.stderr)
        self.assertIn("poll throttled", throttled.stdout)
        naps = [line.split()[1] for line in throttled.stdout.splitlines() if line.startswith("SLEEP ")]
        self.assertEqual(naps[:7], ["60", "120", "180", "240", "300", "360", "420"], throttled.stdout)

    def test_a_rate_limit_backoff_is_capped_and_still_bounded(self):
        result = run_functions(
            poll_stub("        *) echo 'gh: API rate limit exceeded (HTTP 403)' >&2; return 1 ;;"),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"; echo "POLLS=$(polls)"',
        )
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("POLLS=20", result.stdout)
        self.assertIn("20 consecutive throttled polls", result.stdout)
        naps = [line.split()[1] for line in result.stdout.splitlines() if line.startswith("SLEEP ")]
        self.assertEqual(max(int(nap) for nap in naps), 600, result.stdout)

    def test_401_still_fails_on_the_first_poll_and_prints_the_reason(self):
        result = run_functions(
            poll_stub("        *) echo 'gh: Bad credentials (HTTP 401)' >&2; return 1 ;;"),
            "watch_run Otzaria/otzaria-library 33987363603 update-library; "
            'echo "STATUS=$?"; echo "POLLS=$(polls)"',
        )
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("POLLS=1", result.stdout)
        self.assertIn("token rejected (HTTP 401)", result.stdout)
        self.assertIn("gh: Bad credentials (HTTP 401)", result.stdout)

    def test_a_long_watch_prints_a_heartbeat_every_ten_minutes(self):
        """49m29s of silence and a wedged loop are indistinguishable in a log."""
        result = run_functions(
            poll_stub(
                "        1|2|3|4|5|6|7|8|9|1?|2?) printf 'in_progress:\\n' ;;\n"
                "        *) printf 'completed:success\\n' ;;",
                jobs="export · Run export pipeline via Docker Compose",
            ),
            "watch_run Otzaria/SefariaExport 33986948151 sefaria-export",
        )
        beats = [line for line in result.stdout.splitlines() if " elapsed · " in line]
        self.assertEqual(len(beats), 2, result.stdout)
        self.assertIn("sefaria-export 00:10 elapsed · in_progress", beats[0])
        self.assertIn("sefaria-export 00:20 elapsed · in_progress", beats[1])
        for beat in beats:
            self.assertIn("Run export pipeline via Docker Compose", beat)
            self.assertIn(
                "https://github.com/Otzaria/SefariaExport/actions/runs/33986948151", beat
            )
        self.assertIn("sefaria-export succeeded after 00:29", result.stdout)


class DispatchStepVerificationTest(unittest.TestCase):
    """`completed:success` never proved that the child's dispatch step ran."""

    def verify(self, jobs_answer):
        stub = (
            "gh() {\n"
            '  case "$*" in\n'
            f"    *\"/jobs?per_page=100\"*) {jobs_answer} ;;\n"
            "    *) return 99 ;;\n"
            "  esac\n"
            "}\n"
        )
        return run_functions(
            stub,
            "require_child_step_success Otzaria/SefariaExport 33987734987 "
            f"'{DISPATCH_STEP}'; " + 'echo "STATUS=$?"',
        )

    def test_a_dispatch_step_that_ran_is_accepted(self):
        result = self.verify("printf 'success\\n'")
        self.assertIn("STATUS=0", result.stdout, result.stderr)
        self.assertIn(f'verified: "{DISPATCH_STEP}" concluded success', result.stdout)
        self.assertNotIn("::error::", result.stdout)

    def test_a_skipped_dispatch_step_fails_the_head(self):
        result = self.verify("printf 'skipped\\n'")
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("::error::", result.stdout)
        self.assertIn(f'its "{DISPATCH_STEP}" step concluded skipped', result.stdout)
        self.assertIn("the weekly chain stops here", result.stdout)

    def test_a_renamed_or_absent_step_is_not_silently_accepted(self):
        result = self.verify("printf ''")
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn(f'reports no step named "{DISPATCH_STEP}"', result.stdout)

    def test_an_unreadable_jobs_listing_is_not_a_pass(self):
        result = self.verify("echo 'gh: Not Found (HTTP 404)' >&2; return 1")
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("cannot list the jobs of", result.stdout)
        self.assertIn("gh: Not Found (HTTP 404)", result.stdout)

    def test_the_head_verifies_before_it_claims_the_chain_progressed(self):
        body = step_body()
        claim = "SefariaExport succeeded and dispatched exact manual-link synchronization"
        verify = f"require_child_step_success Otzaria/SefariaExport \"$export_run\" '{DISPATCH_STEP}'"
        self.assertIn(verify, body)
        self.assertIn(claim, body)
        self.assertLess(body.index(verify), body.index(claim))

    @unittest.skipUnless(EXPORT_RELEASE.is_file(), "no sibling SefariaExport checkout")
    def test_the_verified_step_name_exists_in_sefaria_export(self):
        """A rename there turns this head's guarantee into a false alarm; the head
        fails loudly for it, but the name still has to be the current one."""
        release = EXPORT_RELEASE.read_text(encoding="utf-8")
        self.assertIn(f"- name: {DISPATCH_STEP}\n", release)


class ResolveChildTest(unittest.TestCase):
    """`set -euo pipefail` turned every non-zero from the lookup helper into an
    abort with no message; exit 3 is the one that means this head dispatched twice."""

    TITLE = "Sefaria immutable export orchestration=weekly:33987355439:1"

    def resolve(self, rc, ids="33986948151\n33986948152\n"):
        stub = (
            f"FINDER_RC={rc}\n"
            f"FINDER_IDS='{ids}'\n"
            "bash() {\n"
            '  case "$*" in\n'
            "    *find_exact_workflow_run.sh*) return \"$FINDER_RC\" ;;\n"
            '    *) command bash "$@" ;;\n'
            "  esac\n"
            "}\n"
            "gh() { printf '%s' \"$FINDER_IDS\"; }\n"
        )
        return run_functions(
            stub,
            "value=$(resolve_child sefaria-export Otzaria/SefariaExport release.yml "
            f"'{self.TITLE}' deadbeef); " + 'echo "STATUS=$? VALUE=$value"',
        )

    def test_a_collision_names_the_identity_and_every_matching_run(self):
        result = self.resolve(3)
        self.assertIn("STATUS=1 VALUE=", result.stdout, result.stderr)
        errors = [line for line in result.stderr.splitlines() if line.startswith("::error::")]
        self.assertEqual(len(errors), 1, result.stderr)
        self.assertIn(self.TITLE, errors[0])
        self.assertIn("this head dispatched twice", errors[0])
        self.assertIn("refusing to guess", errors[0])
        self.assertIn(
            "https://github.com/Otzaria/SefariaExport/actions/runs/33986948151", errors[0]
        )
        self.assertIn(
            "https://github.com/Otzaria/SefariaExport/actions/runs/33986948152", errors[0]
        )

    def test_a_collision_that_cannot_be_listed_still_reports_the_identity(self):
        result = self.resolve(3, ids="")
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertIn("none could be listed", result.stderr)

    def test_a_missing_child_and_a_broken_listing_are_distinct_messages(self):
        missing = self.resolve(1)
        self.assertIn("STATUS=1", missing.stdout, missing.stderr)
        self.assertIn("no run carries the exact dispatch identity", missing.stderr)
        broken = self.resolve(2)
        self.assertIn("helper exit 2", broken.stderr)

    def test_diagnosis_goes_to_stderr_so_command_substitution_cannot_eat_it(self):
        result = self.resolve(3)
        self.assertNotIn("::error::", result.stdout)


class WholeStepTest(unittest.TestCase):
    """Both children green, end to end, with the lookup helper and `gh` stubbed."""

    CLAIM = "SefariaExport succeeded and dispatched exact manual-link synchronization"

    def orchestrate(self, dispatch_step_conclusion):
        stub = (
            "bash() {\n"
            '  case "$*" in\n'
            "    *find_exact_workflow_run.sh*) echo 33987363603 ;;\n"
            '    *) command bash "$@" ;;\n'
            "  esac\n"
            "}\n"
            "gh() {\n"
            '  case "$*" in\n'
            "    *commits/main*|*commits/master*) echo deadbeefdeadbeefdeadbeefdeadbeefdeadbeef ;;\n"
            '    *"workflow run"*) echo "DISPATCHED" ;;\n'
            f"    *\"/jobs?per_page=100\"*) printf '{dispatch_step_conclusion}\\n' ;;\n"
            "    *\"actions/runs/\"*) printf 'completed:success\\n' ;;\n"
            "    *) return 99 ;;\n"
            "  esac\n"
            "}\n"
        )
        return run_whole_step(stub)

    def test_a_dispatched_chain_is_claimed_only_after_it_is_verified(self):
        result = self.orchestrate("success")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("DISPATCHED"), 2, result.stdout)
        self.assertIn(f'verified: "{DISPATCH_STEP}"', result.stdout)
        self.assertIn(
            f"{self.CLAIM}: https://github.com/Otzaria/SefariaExport/actions/runs/33987363603",
            result.stdout,
        )

    def test_a_green_export_that_skipped_the_dispatch_stops_the_head(self):
        result = self.orchestrate("skipped")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("::error::", result.stdout)
        self.assertIn("step concluded skipped", result.stdout)
        self.assertNotIn(self.CLAIM, result.stdout)


class WorkflowContractTest(unittest.TestCase):
    def test_the_workflow_parses(self):
        try:
            import yaml
        except ImportError:  # pragma: no cover - PyYAML is not a repo dependency
            self.skipTest("PyYAML is not installed")
        document = yaml.safe_load(workflow_text())
        job = document["jobs"]["orchestrate"]
        self.assertEqual(job["timeout-minutes"], 240)
        self.assertEqual(job["steps"][1]["name"], STEP)

    def test_the_dead_fifth_argument_is_gone_from_the_only_caller(self):
        """find_exact_workflow_run.sh reads $1-$4; the head threaded a computed
        timestamp and the literal "unused" into a $5 nothing ever read."""
        body = step_body()
        self.assertNotIn("prepare_time", body)
        self.assertNotIn('"unused"', body)
        self.assertNotIn("dispatched_at", body)
        call = [
            line
            for line in body.splitlines()
            if "find_exact_workflow_run.sh" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(len(call), 1, body)
        self.assertIn(
            'find_exact_workflow_run.sh "$repo" "$workflow" "$title" "$head_sha"', call[0]
        )

    def test_both_children_are_resolved_through_the_exit_code_aware_helper(self):
        body = step_body()
        self.assertEqual(body.count("resolve_child update-library "), 1)
        self.assertEqual(body.count("resolve_child sefaria-export "), 1)
        self.assertNotIn("find_exact_run", body)

    def test_the_checkout_git_init_no_longer_prints_a_default_branch_hint(self):
        """13 `hint:` lines per head log; this job runs no `git init` of its own, so
        the only reachable configuration for actions/checkout's is git's env config."""
        text = workflow_text()
        self.assertIn("GIT_CONFIG_COUNT: '1'", text)
        self.assertIn("GIT_CONFIG_KEY_0: init.defaultBranch", text)
        self.assertIn("GIT_CONFIG_VALUE_0: main", text)

    def test_the_watch_loop_prints_every_poll_error_it_classifies(self):
        body = step_body()
        self.assertIn('WATCH_ERR="$RUNNER_TEMP/wait-err.txt"', body)
        # The old loop read the file exactly once, to grep it for HTTP 401.
        self.assertGreaterEqual(body.count('head -n 1 "$WATCH_ERR"'), 4)


if __name__ == "__main__":
    unittest.main()
