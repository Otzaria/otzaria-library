"""Self-test for the manual-links sync observability layer.

Cycle 33987355439 ran the 818s sync stage and left six usable lines in the log:
every count had to be recovered afterwards from a release asset (audit OBS-1), the
534MB chain verification printed nothing at all (OBS-2), the packaging gate's
diagnostics were redirected to /dev/null (SWAL-1), and the stage rsynced and staged
nine link roots to produce a one-line commit (NOOP-1).

The two summary scripts are run for real - against the verbatim report asset from
release `manual-links-refresh-report-run-33990185407-1` - because they are only
observable through what they print; the workflow-level fixes are asserted on the
workflow, which cannot be executed here.
"""

import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"
SUMMARY = HERE / "manual_links_refresh_summary.sh"
CHAIN_SUMMARY = HERE / "sefaria_chain_summary.sh"
SAMPLE = HERE / "manual_links_refresh_report.sample.json"
SYNC_WORKFLOW = WORKFLOWS / "sync-manual-links.yml"
FORDB_WORKFLOW = WORKFLOWS / "validate-fordb-book-names.yml"

# `.manual-links-refresh-complete` of run 33990185407 attempt 1 pins the report it
# describes; the fixture is that exact asset, so the schema under test is the real one.
SAMPLE_SHA256 = "9aa2b43037bafdaa64a69f77227a342fb0a8e4417130f944e038758a3510e479"

REFRESH_STEP = "Refresh, apply, commit and push atomically"
CHAIN_STEP = "Fetch and verify Sefaria metadata chain and archive"


def posix(path):
    """Git-bash reads a drive path fine, but only with forward slashes."""
    return str(path).replace("\\", "/")


def _usable_bash():
    """The first bash that can actually run these scripts.  On Windows the bash on
    PATH is `C:\\WINDOWS\\system32\\bash.exe` (WSL), which sees neither the drive
    paths nor the Windows `jq`; Git-bash does both."""
    import os
    import shutil

    candidates = [
        shutil.which("bash"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\msys64\usr\bin\bash.exe",
        r"C:\cygwin64\bin\bash.exe",
    ]
    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "command -v jq && command -v git"],
                capture_output=True, timeout=120,
            )
        except OSError:  # pragma: no cover - a candidate that cannot be executed
            continue
        if probe.returncode == 0:
            return candidate
    return None


BASH = _usable_bash()


def run_script(script, *args):
    """Run a shell script from an LF copy.  `core.autocrlf` checks the scripts out
    with CRLF on a Windows clone and bash cannot execute those; reading as text
    normalizes the newlines and `write_bytes` keeps them normalized.  (The `bash
    /dev/stdin` trick the other self-tests use does not survive a Windows pipe.)"""
    body = script.read_text(encoding="utf-8")
    workspace = tempfile.mkdtemp(prefix="manual-links-obs-run-")
    try:
        runnable = Path(workspace) / script.name
        runnable.write_bytes(body.encode("utf-8"))
        result = subprocess.run(
            [BASH, posix(runnable), *[posix(arg) for arg in args]], capture_output=True
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    result.stdout = result.stdout.decode("utf-8", "replace")
    result.stderr = result.stderr.decode("utf-8", "replace")
    return result


def sync_text():
    return SYNC_WORKFLOW.read_text(encoding="utf-8")


def step_body(name, workflow=None):
    """Return the `run: |` block of one step, dedented to column 0."""
    text = workflow if workflow is not None else sync_text()
    marker = f"      - name: {name}\n"
    assert text.count(marker) == 1, f"{name} is not a unique step"
    rest = text.split(marker, 1)[1].split("        run: |\n", 1)[1]
    lines = []
    for line in rest.split("\n"):
        if line.strip() and not line.startswith(" " * 10):
            break
        lines.append(line[10:])
    return "\n".join(lines)


@unittest.skipIf(BASH is None, "no bash with jq and git on this machine")
class ScriptTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="manual-links-obs-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def sample(self):
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def summarize(self, report, tool_checkout=None):
        path = self.tmp / "manual_links_refresh_report.json"
        if isinstance(report, (dict, list)):
            path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        else:
            path.write_text(report, encoding="utf-8")
        decision = self.tmp / "decision"
        args = [path, decision]
        if tool_checkout is not None:
            args.append(tool_checkout)
        result = run_script(SUMMARY, *args)
        result.decision = decision.read_text(encoding="utf-8").strip() if decision.exists() else None
        return result

    def chain(self, result_document):
        directory = self.tmp / "sefaria-chain"
        directory.mkdir(exist_ok=True)
        (directory / "chain-result.json").write_text(
            json.dumps(result_document, ensure_ascii=False), encoding="utf-8"
        )
        return run_script(CHAIN_SUMMARY, directory)

    def git_history(self, count):
        """A throwaway repository whose commits stand in for the tool's own."""
        repo = self.tmp / "tool"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", posix(repo)], check=True, capture_output=True)
        shas = []
        for index in range(count):
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                 "commit", "-q", "--allow-empty", "-m", f"commit {index}"],
                cwd=repo, check=True, capture_output=True,
            )
            shas.append(
                subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                               check=True, capture_output=True, text=True).stdout.strip()
            )
        return repo, shas


class RefreshSummaryTest(ScriptTestCase):
    def test_the_fixture_is_the_published_asset_byte_for_byte(self):
        self.assertEqual(hashlib.sha256(SAMPLE.read_bytes()).hexdigest(), SAMPLE_SHA256)

    def test_every_count_the_audit_had_to_download_now_reaches_the_log(self):
        result = self.summarize(self.sample())
        self.assertEqual(result.returncode, 0, result.stderr)
        line = result.stdout.splitlines()[0]
        for fragment in (
            "status=ok",
            "mode=refresh",
            "payloads 240 loaded/235 accepted/5 blacklisted",
            "anchors 17980 checked, 0 drifted, 0 relocated, 0 unrelocatable (cap 50)",
            "records 184927 scanned, 0 shifted, 0 enriched",
            "files 425 scanned, 0 changed, 0 renamed",
            "refs 0 missing, 0 renamed, 0 duplicate",
            "packaging collisions 0",
        ):
            self.assertIn(fragment, line)

    def test_the_summary_stays_a_summary(self):
        """Six lines of signal replaced six lines of noise; a firehose is a regression."""
        result = self.summarize(self.sample())
        self.assertLessEqual(len(result.stdout.strip().splitlines()), 6)

    def test_the_lineage_line_names_both_sefaria_and_tool_moves(self):
        result = self.summarize(self.sample())
        lineage = result.stdout.splitlines()[1]
        self.assertIn("sefaria 2026-09-04_12-50-33860162971-1 -> 2026-09-05_22-40-33987734987-1", lineage)
        self.assertIn("tool 9c70191 -> 2aadf7a", lineage)
        self.assertIn("packaged tree unchanged", lineage)
        self.assertIn("source tree unchanged", lineage)

    def test_the_crossed_tool_commits_are_counted_from_the_checkout(self):
        repo, shas = self.git_history(4)
        report = self.sample()
        report["input_lineage"]["seforim_tool_commit"] = shas[0]
        report["output_lineage"]["seforim_tool_commit"] = shas[3]
        result = self.summarize(report, tool_checkout=repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(3 commit(s) crossed)", result.stdout)

    def test_an_unknown_tool_commit_drops_the_count_instead_of_the_stage(self):
        repo, _ = self.git_history(1)
        result = self.summarize(self.sample(), tool_checkout=repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tool 9c70191 -> 2aadf7a", result.stdout)
        self.assertNotIn("commit(s) crossed", result.stdout)

    def test_a_blacklisted_payload_count_says_the_titles_are_not_in_the_report(self):
        result = self.summarize(self.sample())
        self.assertIn("5 Sefaria payload(s) blacklisted", result.stdout)
        self.assertIn("the count only, not the titles", result.stdout)

    def test_an_unusable_report_fails_loudly(self):
        result = self.summarize({"status": "ok"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("::error::manual-links refresh report is unusable", result.stdout)


class TreeSyncDecisionTest(ScriptTestCase):
    """NOOP-1: the rsync over nine roots and the `git add` of every root may only be
    skipped when the report proves the tool wrote nothing into the output tree."""

    def test_an_untouched_tree_stages_only_the_lineage(self):
        result = self.summarize(self.sample())
        self.assertEqual(result.decision, "true")
        self.assertIn("staging manual_links_lineage.json only", result.stdout)

    def test_a_rewritten_file_forces_the_full_sync(self):
        report = self.sample()
        report["files"]["changed"] = 3
        result = self.summarize(report)
        self.assertEqual(result.decision, "false")
        self.assertIn("syncing every present links root", result.stdout)

    def test_a_renamed_file_forces_the_full_sync(self):
        report = self.sample()
        report["files"]["renamed"] = 1
        self.assertEqual(self.summarize(report).decision, "false")

    def test_a_moved_packaged_tree_digest_forces_the_full_sync(self):
        report = self.sample()
        report["output_lineage"]["packaged_links_tree_sha256"] = "0" * 64
        self.assertEqual(self.summarize(report).decision, "false")

    def test_a_moved_source_tree_digest_forces_the_full_sync(self):
        report = self.sample()
        report["output_lineage"]["source_links_tree_sha256"] = "0" * 64
        self.assertEqual(self.summarize(report).decision, "false")

    def test_a_bootstrap_without_input_lineage_forces_the_full_sync(self):
        report = self.sample()
        report["input_lineage"] = None
        result = self.summarize(report)
        self.assertEqual(result.decision, "false")
        self.assertIn("bootstrap (no input lineage)", result.stdout)

    def test_a_missing_digest_forces_the_full_sync(self):
        report = self.sample()
        del report["output_lineage"]["packaged_links_tree_sha256"]
        del report["input_lineage"]["packaged_links_tree_sha256"]
        self.assertEqual(self.summarize(report).decision, "false")


class AnchorWarningTest(ScriptTestCase):
    def unrelocatable(self, count, listed=None):
        report = self.sample()
        report["anchors"]["unrelocatable"] = count
        report["records"]["anchors_unrelocatable"] = [
            {
                "file": f"sefariaToOtzaria/links/book{index}_links.json",
                "record_index": index,
                "ref_1": f"Book {index}.1",
                "line_index_1": index,
                "start": 10 + index,
                "content_length": 400,
                "stored_hash": "a" * 64,
                "actual_hash": "b" * 64,
                "reason": "missing_anchor_context",
                "around_start": "…",
            }
            for index in range(count if listed is None else listed)
        ]
        return report

    def test_unrelocatable_anchors_are_named(self):
        result = self.summarize(self.unrelocatable(2))
        self.assertIn("::warning::manual-links: 2 record anchor(s) could not be re-anchored (cap 50)", result.stdout)
        self.assertIn("sefariaToOtzaria/links/book0_links.json[0] ref_1=Book 0.1", result.stdout)
        self.assertIn("reason=missing_anchor_context", result.stdout)

    def test_unrelocatable_detail_is_bounded(self):
        result = self.summarize(self.unrelocatable(120, listed=50))
        detail = [l for l in result.stdout.splitlines() if "unrelocatable anchor:" in l]
        self.assertEqual(len(detail), 20)
        self.assertIn("100 further unrelocatable anchor(s) not listed", result.stdout)

    def test_relocations_are_listed_and_bounded(self):
        report = self.sample()
        report["anchors"]["relocated"] = 40
        report["records"]["anchors_relocated"] = 40
        report["records"]["anchors_relocations"] = [
            {
                "file": f"sefariaToOtzaria/links/book{index}_links.json",
                "record_index": index,
                "ref_1": f"Book {index}.1",
                "line_index_1": index,
                "old_start": 1,
                "new_start": 7,
                "strategy": "both_sides",
            }
            for index in range(40)
        ]
        result = self.summarize(report)
        detail = [l for l in result.stdout.splitlines() if "relocated anchor:" in l]
        self.assertEqual(len(detail), 10)
        self.assertIn("start 1 -> 7 via=both_sides", result.stdout)
        self.assertIn("30 further relocation(s) not listed", result.stdout)

    def test_drift_and_collisions_warn(self):
        report = self.sample()
        report["anchors"]["drifted"] = 4
        report["packaging_collisions"] = 2
        result = self.summarize(report)
        self.assertIn("::warning::manual-links: 4 anchor(s) drifted", result.stdout)
        self.assertIn("::warning::manual-links: 2 packaging collision(s)", result.stdout)

    def test_reported_failures_warn(self):
        report = self.sample()
        report["failures"] = ["something/gave.json: exploded"]
        result = self.summarize(report)
        self.assertIn("::warning::manual-links: the report lists 1 failure entr(ies)", result.stdout)
        self.assertIn("something/gave.json: exploded", result.stdout)


class ChainSummaryTest(ScriptTestCase):
    def hop(self, index):
        return {
            "tag": f"2026-09-{index:02d}_00-00-1000{index}-1",
            "metadata_sha256": f"{index:064d}",
            "previous": {"tag": f"2026-09-{index - 1:02d}_00-00-1000{index - 1}-1",
                         "metadata_sha256": f"{index - 1:064d}"},
            "changelog_name": "changelog_diff.json",
            "changelog_sha256": f"{index:064d}",
        }

    def result_document(self, hops):
        return {
            "schema_version": 1,
            "target_tag": "2026-09-05_22-40-33987734987-1",
            "target_metadata_sha256": "a7e94ec679cef30f4a93e3cfce2c7b0ec4de25fdc822786a3e3723e95ae8b26e",
            "archive": {
                "sha256": "a800f644bd55fd56b965ea3b05fc490d04e69fbec920ed46733a124db367fac6",
                "size": 534274304,
                "parts": [{"name": "sefaria-exports.tar.zst", "sha256": "a" * 64, "size": 534274304}],
            },
            "applied_changelog_chain": hops,
        }

    def test_every_hop_and_the_archive_are_named(self):
        result = self.chain(self.result_document([self.hop(5)]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("target 2026-09-05_22-40-33987734987-1 metadata a7e94ec679ce", result.stdout)
        self.assertIn("1 changelog hop(s) walked", result.stdout)
        self.assertIn("sefaria chain hop 1/1: 2026-09-04_00-00-10004-1 -> 2026-09-05_00-00-10005-1"
                      " via changelog_diff.json", result.stdout)
        self.assertIn("archive 1 part(s), 534274304 byte(s), expected sha256 a800f644bd55", result.stdout)

    def test_a_chain_with_no_hop_says_so(self):
        result = self.chain(self.result_document([]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no changelog hop to apply", result.stdout)

    def test_a_long_chain_is_bounded(self):
        result = self.chain(self.result_document([self.hop(index) for index in range(1, 26)]))
        hops = [line for line in result.stdout.splitlines() if "sefaria chain hop " in line]
        self.assertEqual(len(hops), 10)
        self.assertIn("15 further hop(s) not listed", result.stdout)

    def test_the_whole_summary_stays_short(self):
        result = self.chain(self.result_document([self.hop(index) for index in range(1, 26)]))
        self.assertLessEqual(len(result.stdout.strip().splitlines()), 13)

    def test_an_unusable_result_fails_loudly(self):
        result = self.chain({"schema_version": 1})
        self.assertEqual(result.returncode, 2)
        self.assertIn("::error::sefaria chain result is unusable", result.stdout)


class PackagingSummaryLineTest(ScriptTestCase):
    """The gate's pretty-printer, run for real.  It sits under `set -euo pipefail`
    inside the retry loop; jq slices null to null instead of erroring, so one field
    the tool stops emitting used to print the literal `null` where a digest belongs -
    a gate whose only record in the log was untrue."""

    def summary_line(self):
        body = step_body(REFRESH_STEP)
        lines = [line for line in body.splitlines() if line.lstrip().startswith("jq -r ")]
        self.assertEqual(len(lines), 1, body)
        return lines[0].strip()

    def render(self, document):
        report = self.tmp / "check_result.json"
        if isinstance(document, (dict, list)):
            report.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        else:
            report.write_text(document, encoding="utf-8")
        script = self.tmp / "summary.sh"
        script.write_text(
            'set -euo pipefail\ncheck_result="$1"\n' + self.summary_line() + "\n",
            encoding="utf-8",
        )
        return run_script(script, report)

    def complete(self):
        return {
            "packaged_file_count": 4211,
            "source_links_tree_sha256": "a" * 64,
            "packaged_links_tree_sha256": "b" * 64,
            "config_sha256": "c" * 64,
            "lineage_sha256": "d" * 64,
        }

    def test_a_complete_result_is_rendered_the_way_it_always_was(self):
        result = self.render(self.complete())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("manual-links packaging: 4211 packaged file(s)", result.stdout)
        for prefix in ("a", "b", "c", "d"):
            self.assertIn(prefix * 12, result.stdout)
        self.assertNotIn("?", result.stdout)

    def test_a_missing_digest_is_named_rather_than_printed_as_null(self):
        """The line already exited 0 without the defaults; what it printed was `null`."""
        for field in sorted(self.complete()):
            document = self.complete()
            del document[field]
            result = self.render(document)
            self.assertEqual(result.returncode, 0, f"{field}: {result.stderr}")
            self.assertIn("manual-links packaging: ", result.stdout)
            self.assertIn("?", result.stdout, field)
            self.assertNotIn("null", result.stdout, field)

    def test_an_empty_object_still_prints_a_line(self):
        result = self.render({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("?"), 5, result.stdout)

    def test_a_zero_count_is_not_defaulted_away(self):
        """`// "?"` fires on null and false only; 0 packaged files is a real answer."""
        document = self.complete()
        document["packaged_file_count"] = 0
        result = self.render(document)
        self.assertIn("manual-links packaging: 0 packaged file(s)", result.stdout)

    def test_a_check_result_that_is_not_json_is_still_loud(self):
        """Why `// "?"` and not `|| true` on the line: the defaults cover a field the
        tool stopped emitting, they do not swallow an unreadable gate result."""
        result = self.render("this is not json")
        self.assertNotEqual(result.returncode, 0, result.stdout)


class SyncWorkflowContractTest(unittest.TestCase):
    def test_the_refresh_step_prints_the_report_and_obeys_its_decision(self):
        body = step_body(REFRESH_STEP)
        self.assertIn("bash .github/scripts/manual_links_refresh_summary.sh", body)
        self.assertIn('"$output/manual_links_refresh_report.json" "$identical"', body)
        self.assertIn('"$GITHUB_WORKSPACE/seforim-tool"', body)
        self.assertIn('if [[ "$(cat "$identical")" != true ]]; then', body)
        self.assertIn("sync_trees=true", body)

    def test_the_expensive_branch_is_the_one_that_became_conditional(self):
        body = step_body(REFRESH_STEP)
        rsync = body.split("rsync --archive --delete", 1)[0]
        # The rsync loop now sits inside the "trees moved" arm, not directly inside `ok`.
        self.assertIn('if [[ "$(cat "$identical")" != true ]]; then', rsync)
        self.assertIn("roots=()\n", body)
        self.assertIn('if [[ "$sync_trees" == true ]]; then', body)

    def test_the_lineage_commit_is_byte_identical_to_before(self):
        """NOOP-1 may only remove work: same file, same content, same message."""
        body = step_body(REFRESH_STEP)
        self.assertIn('cp "$output/manual_links_lineage.json" "$worktree/manual_links_lineage.json"', body)
        self.assertIn('git -C "$worktree" add -- manual_links_lineage.json ${roots[@]+"${roots[@]}"}', body)
        self.assertIn('message="chore(manual-links): sync Sefaria $SEFARIA_TAG"', body)
        self.assertIn('[[ "$MODE" == refresh ]] || message="chore(manual-links): migrate lineage at Sefaria $SEFARIA_TAG"', body)
        self.assertIn('if ! git -C "$worktree" diff --cached --quiet; then', body)

    def test_both_allowlist_gates_still_run_on_every_path(self):
        body = step_body(REFRESH_STEP)
        self.assertIn("updater changed paths outside the strict allowlist", body)
        self.assertIn("staged paths outside strict allowlist", body)
        self.assertIn("--workspace \"$worktree\" --require-lineage", body)

    def test_the_packaging_gate_output_is_no_longer_discarded(self):
        body = step_body(REFRESH_STEP)
        self.assertNotIn("--require-lineage >/dev/null", body)
        self.assertIn('> "$check_result"', body)
        self.assertIn("::error::manual-links packaging gate failed", body)
        self.assertIn("manual-links packaging: ", body)

    def test_the_base64_push_credential_is_masked(self):
        body = step_body(REFRESH_STEP)
        auth = body.split('auth="$(printf', 1)[1]
        self.assertIn('echo "::add-mask::$auth"', auth.split("success=false", 1)[0])

    def test_the_refresh_report_release_is_tagged_at_the_pushed_commit(self):
        text = sync_text()
        publish = text.split(
            "      - name: Publish immutable manual-links refresh report release\n", 1
        )[1].split("\n  start-saga:", 1)[0]
        self.assertIn("SYNC_COMMIT: ${{ steps.apply.outputs.expected_links_commit }}", publish)
        self.assertIn('"$SYNC_COMMIT" manual-links-refresh-artifact/manual_links_refresh_report.json', publish)
        self.assertNotIn('"$GITHUB_SHA"', publish)

    def test_the_saga_state_release_keeps_the_run_head_on_purpose(self):
        """reconcile_sagas.sh establishes contract ancestry from the saga run's own
        head_sha, so saga state stays targeted at that same commit."""
        text = sync_text()
        saga = text.split("      - name: Publish immutable saga state release\n", 1)[1]
        self.assertIn('"$GITHUB_SHA" saga-state/saga-state.json', saga)

    def test_explicit_fetches_do_not_drag_every_handoff_tag(self):
        text = sync_text()
        self.assertIn("git fetch --no-tags origin main", text)
        self.assertIn('git fetch --no-tags origin "$branch"', text)
        # Every fetch in the step must skip the tag refspec (audit NOISE-2);
        # a future legitimate fetch is fine as long as it carries --no-tags.
        for fetch in re.findall(r"git fetch.*", text):
            self.assertIn("--no-tags", fetch, fetch)

    def test_the_chain_step_reports_the_walk_the_verification_and_the_extract(self):
        body = step_body(CHAIN_STEP)
        self.assertIn("bash .github/scripts/sefaria_chain_summary.sh sefaria-chain", body)
        self.assertIn("sefaria chain: verified sha256 ok", body)
        self.assertIn("sefaria chain: extracted $extracted; export root", body)

    def test_the_deprecated_node20_action_majors_are_gone(self):
        for workflow in (SYNC_WORKFLOW, FORDB_WORKFLOW):
            text = workflow.read_text(encoding="utf-8")
            for pinned in ("actions/checkout@v4", "actions/setup-python@v5", "actions/setup-java@v4"):
                self.assertNotIn(pinned, text, workflow.name)

    def test_every_run_body_is_valid_yaml_and_valid_bash(self):
        try:
            import yaml
        except ImportError:  # pragma: no cover - PyYAML is not a repo dependency
            self.skipTest("PyYAML is not installed")
        if BASH is None:  # pragma: no cover - no usable shell on this machine
            self.skipTest("no bash with jq and git on this machine")
        for workflow in (SYNC_WORKFLOW, FORDB_WORKFLOW):
            document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
            for job, spec in document["jobs"].items():
                for step in spec.get("steps", []):
                    body = step.get("run")
                    # A `${{ }}` expression is not shell; those steps are checked by
                    # their own assertions instead.
                    if not body or "${{" in body:
                        continue
                    workspace = tempfile.mkdtemp(prefix="manual-links-obs-syntax-")
                    try:
                        candidate = Path(workspace) / "step.sh"
                        candidate.write_bytes(body.encode("utf-8"))
                        check = subprocess.run(
                            [BASH, "-n", posix(candidate)], capture_output=True
                        )
                    finally:
                        shutil.rmtree(workspace, ignore_errors=True)
                    self.assertEqual(
                        check.returncode, 0,
                        f"{workflow.name}:{job}:{step.get('name')} {check.stderr.decode('utf-8', 'replace')}",
                    )


if __name__ == "__main__":
    unittest.main()
