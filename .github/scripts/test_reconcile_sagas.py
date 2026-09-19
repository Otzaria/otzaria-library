import subprocess
from pathlib import Path
import tempfile
import unittest
import os


SCRIPT = Path(__file__).with_name("reconcile_sagas.sh")
RULE_SCRIPT = Path(__file__).with_name("select_earliest_successful_child.sh")
RETIRED = Path(__file__).with_name("retired_sagas.txt")
WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "reconcile-sagas.yml"
SAGA_CONTINUE = Path(__file__).resolve().parents[1] / "workflows" / "saga-continue.yml"

# Annotations that belong to the reconciler itself rather than to one saga.
SAGA_LESS_ANNOTATIONS = (
    "must be a full commit SHA",
    "must be a positive integer",
    "must be an RFC3339 UTC instant",
    "invalid retired saga id",
    "cannot list saga roots",
    "saga reconciliation failure(s)",
)


# `core.autocrlf` checks the shell scripts out with CRLF on a Windows clone, and
# bash cannot execute those.  Only the cases that run a script from disk are
# affected; every other case reads the reconciler as text.
def crlf_checkout(name):
    return b"\r\n" in SCRIPT.with_name(name).read_bytes()


NEEDS_LF = unittest.skipIf(
    crlf_checkout("find_exact_workflow_run.sh"), "lookup script is checked out with CRLF"
)
NEEDS_LF_RULE = unittest.skipIf(
    crlf_checkout(RULE_SCRIPT.name), "canonical-child rule is checked out with CRLF"
)

# The 10 s retry loop is asserted on the source, not waited for in a self-test.
SETTINGS = (
    "export SAGA_SINCE=2026-08-01T00:00:00Z\n"
    "export SAGA_FIND_CHILD_ATTEMPTS=1\n"
    # A fixed alert cutoff: the GNU `date -d` default is neither portable nor
    # deterministic.  Runs that concluded before it are past the window.
    "export SAGA_ALERT_CUTOFF=2026-09-18T00:00:00Z\n"
)


def run_bash(script, cwd=None):
    """Run a bash script piped through stdin.  A `bash -c` argument is rewritten by
    the shell's own command-line parsing on a Windows checkout, and text-mode pipes
    rewrite every newline there; binary stdin survives both."""
    result = subprocess.run(
        ["bash", "/dev/stdin"],
        input=script.encode("utf-8"),
        capture_output=True,
        cwd=cwd,
    )
    result.stdout = result.stdout.decode("utf-8", "replace")
    result.stderr = result.stderr.decode("utf-8", "replace")
    return result


def run_functions(stub, snippet):
    """Run snippet against the reconciler's own functions with `gh` stubbed out.
    $0 is the pipe, so HERE is restored to the scripts directory this runs in."""
    prelude = SCRIPT.read_text(encoding="utf-8").split("for saga_run in $RUNS; do", 1)[0]
    return run_bash(
        SETTINGS + stub + prelude + '\nHERE="$PWD"\nset +e\n' + snippet,
        cwd=str(SCRIPT.parent),
    )


# The two databaseIds of the 2026-09-02 duplicate incident.  The newer run also
# carries the newer id, as GitHub always assigns them in creation order.
OLDER = "33551831316\\t2026-09-01T19:50:24Z"
NEWER = "33625936953\\t2026-09-02T11:41:43Z"


def duplicate_stub(*rows):
    """`gh` answering the duplicate listing with these exact-title TSV rows."""
    listing = "".join(row + "\\n" for row in rows)
    return (
        "gh() {\n"
        "  case \"$*\" in\n"
        "    *sync-manual-links.yml/runs*) printf '' ;;\n"
        f"    *update-library.yml/runs*) printf '{listing}' ;;\n"
        "    *) return 99 ;;\n"
        "  esac\n"
        "}\n"
    )


NEEDS_LF_MAIN = unittest.skipIf(
    crlf_checkout(SCRIPT.name), "reconciler is checked out with CRLF"
)


def continuation_stub(row, created):
    """`gh` answering the continuation lookup the way the API does: it honours the
    narrowing the reconciler asks for.  A stub that returns the row whatever the
    query says turns every case below into a tautology -- it would pass against
    the checkout-SHA narrowing this change removed."""
    return (
        "ROW='" + row + "'\n"
        "ROW_CREATED='" + created + "'\n"
        "gh() {\n"
        "  case \"$*\" in\n"
        "    *sync-manual-links.yml/runs*) printf '' ;;\n"
        "    *saga-continue.yml/runs*)\n"
        # Delivered at an earlier control-plane commit: a checkout-narrowed
        # lookup matches nothing, which is exactly the bug being fixed.
        "      case \"$*\" in *head_sha*) return 0 ;; esac\n"
        "      case \"$*\" in *created_at*)\n"
        "        [ -n \"${SINCE:-}\" ] || { echo 'stub: lookup passed no SINCE' >&2; return 1; }\n"
        "        [ \"$ROW_CREATED\" '>' \"$SINCE\" ] || [ \"$ROW_CREATED\" = \"$SINCE\" ] || return 0 ;;\n"
        "      esac\n"
        "      printf '%b\\n' \"$ROW\" ;;\n"
        "    *'workflow run saga-continue.yml'*) printf 'DISPATCHED\\n' ;;\n"
        "    *'run rerun'*) printf 'RERAN\\n' ;;\n"
        "    *) return 99 ;;\n"
        "  esac\n"
        "}\n"
    )


CYCLE_NEW = "34508533290"
CYCLE_OLD = "33279324264"
CORR = {
    CYCLE_NEW: "sefaria:" + CYCLE_NEW + ":1:2026-09-10_20-32:" + "a" * 64,
    CYCLE_OLD: "sefaria:" + CYCLE_OLD + ":1:2026-08-30_01-46:" + "b" * 64,
}


def fake_gh(listing, roots, completed):
    """`gh` for one end-to-end tick.  `listing` is the root ids in the order the
    API hands them over, `roots` maps a root id to (attempt start, cycle), and
    `completed` is the cycles that have a successful S2 continuation.  Anything
    else is an unexpected call and fails the tick loudly."""
    out = ["#!/usr/bin/env bash", 'case "$*" in']
    out.append(
        "  *sync-manual-links.yml/runs*) printf '"
        + "".join(str(r) + "\\n" for r in listing)
        + "' ;;"
    )
    for rid, (started, cycle) in roots.items():
        out.append(
            "  *actions/runs/%s*) printf '%s\\t1\\t%s\\tsync-manual-links correlation=%s\\n' ;;"
            % (rid, (str(rid) * 40)[:40], started, CORR[cycle])
        )
    out.append('  *saga-continue.yml/runs*)')
    out.append('    case "$TITLE" in')
    for cycle in completed:
        out.append("      *%s*) printf '999\\n' ;;" % CORR[cycle])
    out.append("      *) printf '' ;;")
    out.append("    esac ;;")
    out.append('  *) echo "unexpected gh call: $*" >&2; exit 99 ;;')
    out.append("esac")
    return "\n".join(out) + "\n"


class ReconcileSagasContractTest(unittest.TestCase):
    def run_tick(self, script):
        """Run the real reconciler against a `gh` on PATH."""
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            fake = bindir / "gh"
            fake.write_text(script, encoding="utf-8")
            fake.chmod(0o755)
            retired = Path(tmp) / "retired.txt"
            retired.write_text("# no tombstones\n", encoding="utf-8")
            env = dict(os.environ)
            env["PATH"] = str(bindir) + os.pathsep + env["PATH"]
            env["SAGA_SINCE"] = "2026-08-01T00:00:00Z"
            env["SAGA_RETIRED_FILE"] = str(retired)
            env["SAGA_ALERT_CUTOFF"] = "2026-09-18T00:00:00Z"
            result = subprocess.run(
                ["bash", str(SCRIPT)], capture_output=True, env=env, cwd=tmp
            )
            return (
                result.returncode,
                result.stdout.decode("utf-8", "replace")
                + result.stderr.decode("utf-8", "replace"),
            )

    def resolve_duplicates(self, *rows):
        return run_functions(
            duplicate_stub(*rows),
            "SAGA_REF=$(saga_ref 33550764239); "
            "value=$(resolve_duplicate_child repo update-library.yml title); status=$?; "
            "printf 'STATUS=%s VALUE=%s\\n' \"$status\" \"$value\"",
        )

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

    def test_superseded_root_is_tombstoned_in_the_format_the_script_reads(self):
        """The zombie root can never be closed; `grep -Fxq` needs it on its own line."""
        lines = RETIRED.read_text(encoding="utf-8").splitlines()
        ids = [line for line in lines if line.strip() and not line.startswith("#")]
        self.assertIn("33550764239", ids)
        for entry in ids:
            self.assertRegex(entry, r"^[1-9][0-9]*$")
        comments = "\n".join(line for line in lines if line.startswith("#"))
        self.assertIn("33635772841", comments)

    def test_active_seforim_row_preserves_head_sha(self):
        source = SCRIPT.read_text(encoding="utf-8")
        function = source.split("find_seforim_child() {", 1)[1].split(
            "\ndispatch_continuation() {", 1
        )[0]
        self.assertIn('(.conclusion//"-")', function)
        self.assertNotIn('(.conclusion//"")', function)

        result = run_bash(
            "IFS=$'\\t' read -r id status conclusion head <<'ROW'\n"
            "30328903115\tin_progress\t-\tb64f8583cc910dc5cd7b5f846fed153c39626751\n"
            "ROW\n"
            "printf '%s\\n' \"$id|$status|$conclusion|$head\"\n"
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
        stub = (
            "gh() {\n"
            "  case \"$*\" in\n"
            "    *sync-manual-links.yml/runs*) printf '' ;;\n"
            "    *manual-generate-release.yml/runs*) "
            "printf '42\\tcompleted\\tfailure\\tpayload\\n' ;;\n"
            "    *compare*) printf 'identical\\n' ;;\n"
            "    *) return 99 ;;\n"
            "  esac\n"
            "}\n"
        )
        result = run_functions(
            stub,
            "value=$(find_seforim_child title payload); status=$?; "
            "printf '%s|%s\\n' \"$status\" \"$value\"",
        )
        self.assertEqual(result.stdout.strip(), "0|42", result.stderr)

    def test_missing_child_lookup_keeps_a_retry_budget(self):
        """One incomplete listing must never be read as a missing child."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("FIND_CHILD_ATTEMPTS=${SAGA_FIND_CHILD_ATTEMPTS:-6}", source)
        body = source.split("find_child() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('FIND_RUN_ATTEMPTS="$FIND_CHILD_ATTEMPTS"', body)
        self.assertNotIn("FIND_RUN_ATTEMPTS=1", body)

    @NEEDS_LF
    def test_redispatch_needs_the_miss_confirmed_by_a_second_listing(self):
        stub = (
            "gh() {\n"
            "  case \"$*\" in\n"
            "    *sync-manual-links.yml/runs*) printf '' ;;\n"
            "    *update-library.yml/runs*event=workflow_dispatch*) printf '' ;;\n"
            "    *update-library.yml/runs*) printf '33551831316\\n' ;;\n"
            "    *) printf 'DISPATCHED\\n' ;;\n"
            "  esac\n"
            "}\n"
            "export -f gh\n"
        )
        result = run_functions(
            stub,
            "SAGA_REF=$(saga_ref 33550764239); "
            "value=$(ensure_otzaria_child title expected corr 33550764239 1); status=$?; "
            "printf 'STATUS=%s VALUE=%s\\n' \"$status\" \"$value\"",
        )
        self.assertIn("STATUS=0 VALUE=33551831316", result.stdout, result.stderr)
        self.assertNotIn("DISPATCHED", result.stdout + result.stderr)

    @NEEDS_LF
    def test_a_twice_confirmed_miss_dispatches_one_child(self):
        stub = (
            "gh() {\n"
            "  case \"$*\" in\n"
            "    *sync-manual-links.yml/runs*) printf '' ;;\n"
            "    *update-library.yml/runs*) printf '' ;;\n"
            "    *) printf 'DISPATCHED\\n' ;;\n"
            "  esac\n"
            "}\n"
            "export -f gh\n"
        )
        result = run_functions(
            stub,
            "SAGA_REF=$(saga_ref 33550764239); "
            "value=$(ensure_otzaria_child title expected corr 33550764239 1); status=$?; "
            "printf 'STATUS=%s VALUE=%s\\n' \"$status\" \"$value\"",
        )
        self.assertIn("STATUS=0 VALUE=\n", result.stdout, result.stderr)
        self.assertEqual(result.stderr.count("DISPATCHED"), 1, result.stderr)
        self.assertIn(
            "redispatched missing Otzaria child for saga=33550764239 "
            "(https://github.com/Otzaria/otzaria-library/actions/runs/33550764239)",
            result.stderr,
        )

    @NEEDS_LF_RULE
    def test_duplicate_exact_children_resolve_to_the_earliest_success(self):
        """Nothing can merge two children back into one, and failing every tick
        only hides the sagas that do need an operator."""
        result = self.resolve_duplicates(
            f"{NEWER}\\tcompleted\\tsuccess", f"{OLDER}\\tcompleted\\tsuccess"
        )
        self.assertIn("STATUS=0 VALUE=33551831316\n", result.stdout, result.stderr)
        warnings = [line for line in result.stderr.splitlines() if "::warning::" in line]
        self.assertEqual(len(warnings), 1, result.stderr)
        self.assertIn("saga=33550764239", warnings[0])
        self.assertIn("33551831316,33625936953", warnings[0])
        self.assertIn("canonical child 33551831316", warnings[0])

    @NEEDS_LF_RULE
    def test_a_terminal_success_outranks_an_older_active_duplicate(self):
        """Adoption follows the success even when it is not the earliest run:
        that is the one child S2 can validate a signed result for."""
        result = self.resolve_duplicates(
            f"{NEWER}\\tcompleted\\tsuccess", f"{OLDER}\\tin_progress\\t-"
        )
        self.assertIn("STATUS=0 VALUE=33625936953\n", result.stdout, result.stderr)

    @NEEDS_LF_RULE
    def test_a_terminal_success_outranks_an_older_failed_duplicate(self):
        result = self.resolve_duplicates(
            f"{NEWER}\\tcompleted\\tsuccess", f"{OLDER}\\tcompleted\\tfailure"
        )
        self.assertIn("STATUS=0 VALUE=33625936953\n", result.stdout, result.stderr)

    @NEEDS_LF_RULE
    def test_the_single_active_duplicate_is_adopted_over_an_older_failure(self):
        """The 2026-09-02 shape.  Adopting the older failure sends it to the
        bounded rerun beside a run that is still live, and a second success is
        exactly what no later tick can undo."""
        result = self.resolve_duplicates(
            f"{NEWER}\\tin_progress\\t-", f"{OLDER}\\tcompleted\\tfailure"
        )
        self.assertIn("STATUS=0 VALUE=33625936953\n", result.stdout, result.stderr)

    @NEEDS_LF_RULE
    def test_several_active_duplicates_fail_closed_for_an_operator(self):
        result = self.resolve_duplicates(
            f"{NEWER}\\tin_progress\\t-", f"{OLDER}\\tqueued\\t-"
        )
        self.assertIn("STATUS=1 VALUE=\n", result.stdout, result.stderr)
        self.assertIn(
            "::error::saga=33550764239 "
            "(https://github.com/Otzaria/otzaria-library/actions/runs/33550764239): "
            "duplicate exact children 33551831316,33625936953 are still active",
            result.stderr,
        )
        self.assertNotIn("::warning::", result.stderr)

    @NEEDS_LF_RULE
    def test_wholly_failed_duplicates_resolve_to_the_newest_database_id(self):
        """The bounded rerun has to act on the current control head, never
        replay the older failure at its older head."""
        result = self.resolve_duplicates(
            f"{NEWER}\\tcompleted\\tfailure", f"{OLDER}\\tcompleted\\tfailure"
        )
        self.assertIn("STATUS=0 VALUE=33625936953\n", result.stdout, result.stderr)

    def test_the_duplicate_listing_is_narrowed_by_the_lookup_script_event(self):
        """A helper that reports several children while the resolver sees one
        would split the two halves of a single decision."""
        body = SCRIPT.read_text(encoding="utf-8").split(
            "resolve_duplicate_child() {", 1
        )[1].split("\n}\n", 1)[0]
        self.assertIn("-f event=workflow_dispatch -f per_page=100", body)
        finder = SCRIPT.with_name("find_exact_workflow_run.sh").read_text(encoding="utf-8")
        self.assertIn('run_event="${FIND_RUN_EVENT:-workflow_dispatch}"', finder)

    def test_one_canonical_child_rule_is_shared_with_saga_continue_s2(self):
        """A reconciler that adopts a duplicate child while S2 refuses every set
        larger than one wedges the saga forever, so exactly one file may hold
        the selection rule and both callers must feed it the same rows."""
        rule = "awk -F'\\t' '$3==\"completed\" && $4==\"success\" && !found++ {print $1}'"
        rows_jq = (
            "select(.display_title==env.TITLE) | "
            "[(.id|tostring),.created_at,.status,(.conclusion//\"-\")] | @tsv"
        )
        helper = RULE_SCRIPT.read_text(encoding="utf-8")
        reconciler = SCRIPT.read_text(encoding="utf-8")
        continuation = SAGA_CONTINUE.read_text(encoding="utf-8")
        self.assertEqual(helper.count(rule), 1, helper)
        self.assertNotIn(rule, reconciler)
        self.assertNotIn(rule, continuation)
        self.assertIn('bash "$HERE/select_earliest_successful_child.sh"', reconciler)
        self.assertIn(
            "bash .github/scripts/select_earliest_successful_child.sh", continuation
        )
        resolver = reconciler.split("resolve_duplicate_child() {", 1)[1].split("\n}\n", 1)[0]
        s2 = continuation.split(
            "- name: Re-download authoritative Otzaria result for S2", 1
        )[1].split("\n      - name: ", 1)[0]
        for caller in (resolver, s2):
            self.assertIn(rows_jq, caller)
            self.assertIn("-f event=workflow_dispatch -f per_page=100", caller)

    def test_exhausted_recovery_budget_is_reported_as_a_failure(self):
        """A watchdog that stays green over a saga nobody is recovering is useless."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("MAX_RERUN_ATTEMPTS=${SAGA_MAX_RERUN_ATTEMPTS:-2}", source)
        self.assertIn('echo "::error::$SAGA_REF: $label $rid exhausted', source)
        self.assertIn('echo "::error::$SAGA_REF: continuation $rid exhausted', source)
        self.assertNotIn('echo "::warning::$label $rid exhausted', source)
        self.assertNotIn('echo "::warning::continuation $rid exhausted', source)

        stub = (
            "gh() {\n"
            "  case \"$*\" in\n"
            "    *sync-manual-links.yml/runs*) printf '' ;;\n"
            "    *actions/runs/33282121922*) printf '2\\n' ;;\n"
            "    *) printf 'RERAN\\n' ;;\n"
            "  esac\n"
            "}\n"
        )
        result = run_functions(
            stub,
            "SAGA_REF=$(saga_ref 33281342283); "
            "rerun_failed_child Otzaria/SeforimLibrary 33282121922 'Seforim child'; "
            "printf 'STATUS=%s\\n' \"$?\"",
        )
        self.assertIn("STATUS=1", result.stdout, result.stderr)
        self.assertNotIn("RERAN", result.stdout + result.stderr)
        self.assertIn(
            "::error::saga=33281342283 "
            "(https://github.com/Otzaria/otzaria-library/actions/runs/33281342283): "
            "Seforim child 33282121922 exhausted the bounded 2-attempt recovery budget",
            result.stdout,
        )

    def exhausted_child(self, concluded):
        stub = (
            "gh() {\n"
            "  case \"$*\" in\n"
            "    *sync-manual-links.yml/runs*) printf '' ;;\n"
            "    *actions/runs/35284011355*) printf '2\\t" + concluded + "\\n' ;;\n"
            "    *) printf 'RERAN\\n' ;;\n"
            "  esac\n"
            "}\n"
        )
        return run_functions(
            stub,
            "SAGA_REF=$(saga_ref 35282394990); "
            "rerun_failed_child Otzaria/SeforimLibrary 35284011355 'Seforim child'; "
            "printf 'STATUS=%s QUIETED=%s\\n' \"$?\" \"$QUIETED\"",
        )

    def test_an_exhausted_state_goes_quiet_after_the_alert_window(self):
        """2026-09-18: a Seforim child that burned its budget at 23:50Z kept the
        scheduled tick red about eight times a day, re-announcing a state the first
        tick had already reported and no tick could change.  Past the window it is
        still named -- as a warning and in the tail count -- but fails nothing."""
        result = self.exhausted_child("2026-09-17T23:50:21Z")
        out = result.stdout + result.stderr
        self.assertIn("STATUS=0 QUIETED=1", result.stdout, result.stderr)
        self.assertIn(
            "::warning::saga=35282394990 "
            "(https://github.com/Otzaria/otzaria-library/actions/runs/35282394990): "
            "Seforim child 35284011355 exhausted the bounded 2-attempt recovery budget "
            "at 2026-09-17T23:50:21Z; still awaiting operator recovery",
            result.stdout,
        )
        self.assertNotIn("::error::", out)
        # Quiet is not a licence to retry: the budget is still spent.
        self.assertNotIn("RERAN", out)

    def test_an_exhausted_state_inside_the_window_still_fails_the_tick(self):
        """The first ticks after the budget runs out are the announcement."""
        result = self.exhausted_child("2026-09-18T06:00:00Z")
        out = result.stdout + result.stderr
        self.assertIn("STATUS=1 QUIETED=0", result.stdout, result.stderr)
        self.assertIn("::error::saga=35282394990", result.stdout)
        self.assertNotIn("RERAN", out)

    def test_an_unreadable_conclusion_time_alerts(self):
        """Quiet must be proven; a missing or malformed instant is fresh."""
        for concluded in ("", "yesterday", "2026-09-17 23:50:21"):
            with self.subTest(concluded=concluded):
                result = self.exhausted_child(concluded)
                self.assertIn("STATUS=1 QUIETED=0", result.stdout, result.stderr)
                self.assertIn("::error::saga=35282394990", result.stdout)

    def test_an_exhausted_continuation_goes_quiet_as_reported_not_failed(self):
        """Same window for a continuation, returned as 2 -- reported, nothing
        delivered -- so the caller neither counts a failure nor logs a recovery."""
        result = run_functions(
            continuation_stub(
                "77\\tcompleted\\tfailure\\t2\\t2026-09-17T23:50:21Z",
                "2026-09-17T23:40:00Z",
            ),
            "SAGA_ATTEMPT_STARTED_AT=2026-09-17T23:30:00Z; "
            "SAGA_REF=$(saga_ref 35282394990); "
            "ensure_continuation seforim-published corr 35282394990 1 99; "
            "printf 'STATUS=%s QUIETED=%s\\n' \"$?\" \"$QUIETED\"",
        )
        out = result.stdout + result.stderr
        self.assertIn("STATUS=2 QUIETED=1", result.stdout, result.stderr)
        self.assertIn("::warning::saga=35282394990", result.stdout)
        self.assertNotIn("::error::", out)
        self.assertNotIn("RERAN", out)
        self.assertNotIn("DISPATCHED", out)

    def test_the_alert_window_outlasts_the_tick_gap(self):
        """GitHub delivers the schedule about eight times a day, median gap ~3 h.
        A window shorter than the widest gap could let a state go quiet before a
        single tick had failed for it."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ALERT_WINDOW_HOURS=${SAGA_ALERT_WINDOW_HOURS:-12}", source)
        self.assertIn("SAGA_ALERT_WINDOW_HOURS must be a positive integer", source)
        self.assertIn("SAGA_ALERT_CUTOFF must be an RFC3339 UTC instant", source)

    def test_a_continuation_is_identified_by_correlation_and_root_attempt(self):
        """Narrowing by the reconciler's own checkout cut on an axis with no
        relation to the saga: it hid every continuation delivered before the last
        push to main, so a stage that had already succeeded read as absent."""
        source = SCRIPT.read_text(encoding="utf-8")
        body = source.split("ensure_continuation() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn(
            "select(.display_title==env.TITLE and .created_at>=env.SINCE)", body
        )
        self.assertNotIn("HEAD_SHA", body)
        self.assertNotIn("head_sha", body)
        # Nothing may reintroduce the narrowing: its only consumer is gone.
        self.assertNotIn("CONTROL_HEAD", source)
        # The cut instant is fail-closed; an unparsable one would silently widen
        # the lookup back to every attempt the saga ever had.
        loop = source.split("for saga_run in $RUNS; do", 1)[1]
        self.assertIn("invalid start instant for its current attempt", loop)

    def test_a_succeeded_continuation_is_never_delivered_again(self):
        """The 2026-08-14T06:03Z shape: an S1 callback that had arrived normally
        at 01:31Z, inside the same root attempt, was dispatched again at 06:03Z
        only because main had moved in between."""
        result = run_functions(
            continuation_stub("77\\tcompleted\\tsuccess\\t1", "2026-08-14T01:31:31Z"),
            "SAGA_ATTEMPT_STARTED_AT=2026-08-14T01:10:36Z; "
            "SAGA_REF=$(saga_ref 31759784341); "
            "ensure_continuation otzaria-published corr 31759784341 1 99; "
            "printf 'STATUS=%s\\n' \"$?\"",
        )
        output = result.stdout + result.stderr
        # 2, not 0: nothing was delivered, so the caller must not log a recovery.
        self.assertIn("STATUS=2", result.stdout, result.stderr)
        self.assertNotIn("DISPATCHED", output)
        self.assertNotIn("RERAN", output)
        self.assertIn("paused for operator recovery", output)

    def test_a_continuation_from_a_superseded_attempt_is_replaced_not_rerun(self):
        """`gh run rerun` replays a run's ORIGINAL inputs.  Re-running a
        continuation left over from attempt N while the root sits at attempt N+1
        replays saga_run_attempt=N, fails the assertion saga-continue makes
        against the root, and burns the bounded budget into a permanent red tick.
        Five roots here have run at attempt>1, the newest at attempt 6."""
        result = run_functions(
            continuation_stub("77\\tcompleted\\tfailure\\t1", "2026-09-10T18:20:00Z"),
            "SAGA_ATTEMPT_STARTED_AT=2026-09-10T21:00:00Z; "
            "SAGA_REF=$(saga_ref 34513220990); "
            "ensure_continuation otzaria-published corr 34513220990 6 99; "
            "printf 'STATUS=%s\\n' \"$?\"",
        )
        output = result.stdout + result.stderr
        self.assertIn("STATUS=0", result.stdout, result.stderr)
        self.assertIn("DISPATCHED", output)
        self.assertNotIn("RERAN", output)

    def test_a_failed_continuation_of_the_current_attempt_is_still_rerun(self):
        """The cut must not cost the bounded retry its only candidate."""
        result = run_functions(
            continuation_stub("77\\tcompleted\\tfailure\\t1", "2026-09-10T21:05:00Z"),
            "SAGA_ATTEMPT_STARTED_AT=2026-09-10T21:00:00Z; "
            "SAGA_REF=$(saga_ref 34513220990); "
            "ensure_continuation otzaria-published corr 34513220990 6 99; "
            "printf 'STATUS=%s\\n' \"$?\"",
        )
        output = result.stdout + result.stderr
        self.assertIn("STATUS=0", result.stdout, result.stderr)
        self.assertIn("RERAN", output)
        self.assertNotIn("DISPATCHED", output)

    def test_a_finished_saga_is_recognised_before_its_state_is_reproved(self):
        """A finished saga has nothing left to reconcile, yet re-proving it cost a
        compare call, a release download and a contract check on every one of the
        ~8 ticks a day, over a 90-day window, for a weekly pipeline."""
        loop = SCRIPT.read_text(encoding="utf-8").split("for saga_run in $RUNS; do", 1)[1]
        corr = "corr=${saga_title#sync-manual-links correlation=}"
        completion = 'completion_title="saga-continue stage=seforim-published correlation=$corr"'
        compare = 'gh api "repos/$REPO/compare/$STATE_CONTRACT_COMMIT...$saga_head"'
        download = 'gh release download "$release_tag"'
        self.assertLess(loop.index(corr), loop.index(completion))
        self.assertLess(loop.index(completion), loop.index(compare))
        self.assertLess(loop.index(completion), loop.index(download))

    def test_a_cycle_that_a_finished_cycle_overtook_is_skipped_without_alerting(self):
        """One abandoned 2026-08-30 cycle produced 55 consecutive red ticks across
        eight days -- while later cycles shipped -- until an operator hand-wrote a
        tombstone for it."""
        source = SCRIPT.read_text(encoding="utf-8")
        loop = source.split("for saga_run in $RUNS; do", 1)[1]
        # The rule is only sound if a finished cycle is always reached first.
        self.assertIn("| sort -rn)", source)
        self.assertIn("\nSUPERSEDING_CYCLE=\n", source)
        marked = "SUPERSEDING_CYCLE=$saga_cycle"
        guard = ('if [ -n "$SUPERSEDING_CYCLE" ] && '
                 '[ "$saga_cycle" -lt "$SUPERSEDING_CYCLE" ]; then')
        self.assertIn(marked, loop)
        # The cycle's age is the export run its correlation names.  Ordering by
        # root run id instead inverts whenever an operator re-dispatches an older
        # cycle after a newer one finished, which silences the newer stuck cycle.
        self.assertIn("saga_cycle=${corr#sefaria:}", loop)
        self.assertIn('[ "$saga_cycle" -gt "$SUPERSEDING_CYCLE" ]', loop)
        self.assertLess(loop.index(marked), loop.index(guard))
        branch = loop.split(guard, 1)[1].split("\n  fi\n", 1)[0]
        self.assertIn("superseded $SAGA_REF", branch)
        self.assertIn("$SUPERSEDING_CYCLE", branch)
        # Silence is the whole point: an annotation here is the noise it removes.
        self.assertNotIn("::error::", branch)
        self.assertNotIn("::warning::", branch)
        # A stuck cycle that is still the newest one must still reach the
        # operator-action failures below.
        self.assertLess(loop.index(guard), loop.index('rerun_failed_child "$REPO" "$ot_run"'))

    @NEEDS_LF_MAIN
    def test_an_overtaken_cycle_is_skipped_end_to_end(self):
        """The source assertions above cannot see the loop carry the supersession
        across iterations, nor the sort reach the finished cycle first.  The roots
        are handed over oldest-first here on purpose."""
        code, out = self.run_tick(
            fake_gh(
                [100, 200],
                {200: ("2026-09-10T18:15:38Z", CYCLE_NEW),
                 100: ("2026-08-29T23:35:42Z", CYCLE_OLD)},
                [CYCLE_NEW],
            )
        )
        self.assertEqual(code, 0, out)
        self.assertIn("complete saga=200 correlation=sefaria:" + CYCLE_NEW, out)
        self.assertIn(
            "superseded saga=100 "
            "(https://github.com/Otzaria/otzaria-library/actions/runs/100): "
            "export cycle " + CYCLE_OLD + " is older than completed cycle "
            + CYCLE_NEW + " (saga=200); skipped",
            out,
        )
        self.assertIn(
            "1 unfinished saga(s) skipped as overtaken by a completed cycle", out
        )
        self.assertIn("saga reconciliation complete", out)
        # The silence is the contract: no annotation of any kind.
        self.assertNotIn("::error::", out)
        self.assertNotIn("::warning::", out)

    @NEEDS_LF_MAIN
    def test_an_older_cycle_redispatched_later_supersedes_nothing(self):
        """Re-dispatching a root is routine here, so an operator re-running an
        OLD cycle after a newer one finished gives the old cycle the higher root
        id.  Ordering the rule by root id would silence the newer stuck cycle --
        exactly the silent loss this watchdog exists to prevent."""
        code, out = self.run_tick(
            fake_gh(
                [300, 200],
                {300: ("2026-09-12T09:00:00Z", CYCLE_OLD),
                 200: ("2026-09-10T18:15:38Z", CYCLE_NEW)},
                [CYCLE_OLD],
            )
        )
        self.assertIn("complete saga=300 correlation=sefaria:" + CYCLE_OLD, out)
        self.assertNotIn("superseded", out)
        # Not silenced: it reached the real reconciliation path and failed there.
        self.assertIn("cannot establish its saga-state contract ancestry", out)
        self.assertEqual(code, 1, out)

    def test_every_saga_annotation_names_its_root_run(self):
        """Diagnosis must not require reconstructing loop order from the log."""
        source = SCRIPT.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "::error::" not in line and "::warning::" not in line:
                continue
            if any(known in line for known in SAGA_LESS_ANNOTATIONS):
                continue
            self.assertIn("$SAGA_REF", line)
        self.assertIn("printf 'saga=%s (https://github.com/%s/actions/runs/%s)'", source)

    def test_self_test_cannot_block_recovery_but_still_fails_the_job(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("id: selftest", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("run: python3 .github/scripts/test_reconcile_sagas.py", workflow)
        self.assertIn("always() && steps.selftest.outcome == 'failure'", workflow)
        around = workflow.split("run: bash .github/scripts/reconcile_sagas.sh", 1)
        self.assertEqual(len(around), 2)
        self.assertIn("id: selftest", around[0])
        self.assertIn("steps.selftest.outcome", around[1])


if __name__ == "__main__":
    unittest.main()
