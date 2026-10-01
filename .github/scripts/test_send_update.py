"""Self-test for the library changelog (`send_update/main.py`).

`main.py` runs its whole job at import time, so the changelog is exercised the
way the workflow runs it: a throwaway git repository holding the exact shape that
produced the duplicated delete list in version 168, with `zoneinfo` and `pyluach`
stubbed on the script's own sys.path.  `requests`, the forum client and Yemot are
stubbed too, only to prove that no channel is contacted.  No network call is made
and nothing outside the temporary directory is touched.
"""

import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
MAIN = REPO / "send_update" / "main.py"

WATCHED = "DictaToOtzaria/ערוך/ספרים/אוצריא"
OUTSIDE = "extraBooks/דיקטה ערוך"
VERSION_FILE = "MoreBooks/ספרים/אוצריא/אודות התוכנה/גירסת ספריה.txt"

MOVED_OUT = [
    "שות/אחרונים/אגודת אזוב/שות אגודת אזוב אורח חיים.txt",
    "שות/אחרונים/אגודת אזוב/שות אגודת אזוב יורה דעה.txt",
]
MOVED_IN = "מדרש/ספר שחזר פנימה.txt"
MODIFIED = "מדרש/ספר קיים.txt"
ADDED = "מדרש/ספר חדש.txt"

# Channel stubs: any import or call of them prints "STUB-", which the no-channel test forbids.
REQUESTS_STUB = '''\
print("STUB-REQUESTS imported")


def post(url, json=None, timeout=None, **kwargs):
    print(f"STUB-CHAT post url={url}")
'''

FORUM_STUB = '''\
print("STUB-FORUM imported")


class OtzariaForumClient:
    def __init__(self, username, password):
        print(f"STUB-FORUM client user={username}")

    def login(self):
        print("STUB-FORUM login")

    def send_post(self, content, topic_id):
        print(f"STUB-FORUM post topic={topic_id} chars={len(content)}")

    def logout(self):
        print("STUB-FORUM logout")
'''

YEMOT_STUB = '''\
print("STUB-YEMOT imported")


def split_and_send(content, date, token, path, name):
    print(f"STUB-YEMOT sections={len(content)}")
'''

# Asia/Jerusalem needs the tzdata package on Windows, which the changelog only
# uses to stamp a Hebrew date.  Stub it so the test is identical on every host.
ZONEINFO_STUB = '''\
from datetime import timedelta, timezone


def ZoneInfo(key):
    return timezone(timedelta(hours=3), key)
'''

PYLUACH_STUB = '''\
class HebrewDate:
    @classmethod
    def from_pydate(cls, value):
        return cls()

    def hebrew_date_string(self):
        return "כ״ג באלול תשפ״ו"
'''


def load_function(name):
    """Import one pure helper out of main.py without running the module: the
    module resolves BEFORE_SHA from git and rewrites the changelog at import."""
    source = MAIN.read_text(encoding="utf-8")
    start = source.index(f"def {name}")
    end = source.index("\ndef ", start + 1)
    from collections.abc import Sequence

    namespace = {"Sequence": Sequence}
    exec(compile(source[start:end], str(MAIN), "exec"), namespace)  # noqa: S102
    return namespace[name]


def git(root, *args):
    result = subprocess.run(
        [
            "git",
            "-c", "user.email=selftest@example.invalid",
            "-c", "user.name=selftest",
            "-c", "commit.gpgsign=false",
            "-c", "core.quotepath=true",
            "-c", "diff.renames=true",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise AssertionError(f"git {args[0]} failed: {result.stderr}")
    return result.stdout


def write(root, relative, text):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class AnnouncementTest(unittest.TestCase):
    """One fixture, several runs: building the repository is the slow part
    and no run mutates anything the next run reads."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name) / "library"
        root.mkdir()
        cls.root = root

        git(root, "init", "-q", "-b", "main")
        stubs = root / "send_update"
        stubs.mkdir()
        shutil.copyfile(MAIN, stubs / "main.py")
        (stubs / "requests.py").write_text(REQUESTS_STUB, encoding="utf-8")
        (stubs / "otzaria_forum.py").write_text(FORUM_STUB, encoding="utf-8")
        (stubs / "yemot.py").write_text(YEMOT_STUB, encoding="utf-8")
        (stubs / "zoneinfo.py").write_text(ZONEINFO_STUB, encoding="utf-8")
        (stubs / "pyluach").mkdir()
        (stubs / "pyluach" / "__init__.py").write_text("", encoding="utf-8")
        (stubs / "pyluach" / "dates.py").write_text(PYLUACH_STUB, encoding="utf-8")

        write(root, VERSION_FILE, "167")
        for index, book in enumerate(MOVED_OUT):
            write(root, f"{WATCHED}/{book}", f"תשובה מספר {index}\n" * 40)
        write(root, f"{WATCHED}/{MODIFIED}", "מדרש קיים\n" * 40)
        write(root, f"{OUTSIDE}/{Path(MOVED_IN).name}", "ספר שחזר פנימה\n" * 40)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "גרסת ספרייה 167")

        # The exact shape of version 168: two books moved OUT of a watched folder.
        # The pathspec-restricted delete diff and the unrestricted rename diff both
        # report them, which is what printed 4 bullets for 2 files.
        for book in MOVED_OUT:
            target = root / OUTSIDE / Path(book).name
            target.parent.mkdir(parents=True, exist_ok=True)
            git(root, "mv", f"{WATCHED}/{book}", f"{OUTSIDE}/{Path(book).name}")
        # ... and the mirror image, a book moved IN, which had the same defect.
        (root / WATCHED / Path(MOVED_IN).parent).mkdir(parents=True, exist_ok=True)
        git(root, "mv", f"{OUTSIDE}/{Path(MOVED_IN).name}", f"{WATCHED}/{MOVED_IN}")
        write(root, f"{WATCHED}/{MODIFIED}", "מדרש קיים\n" * 40 + "שורה חדשה\n")
        write(root, f"{WATCHED}/{ADDED}", "ספר חדש\n" * 40)
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "sync forum-controlled sources")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def announce(self):
        env = dict(
            os.environ,
            PYTHONUTF8="1",
            PYTHONIOENCODING="utf-8",
        )
        return subprocess.run(
            [sys.executable, "send_update/main.py"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def section(self, stdout, label):
        """Return the bullets published under one changelog heading."""
        body = stdout.split(f"## {label}\n", 1)[1]
        bullets = []
        for line in body.split("\n"):
            if not line.startswith("* "):
                break
            bullets.append(line[2:])
        return bullets

    def listed(self, stdout, label):
        line = next(line for line in stdout.splitlines() if line.startswith(f"{label}: ["))
        return ast.literal_eval(line.split(": ", 1)[1])

    def test_a_book_moved_out_of_the_library_is_announced_deleted_once(self):
        result = self.announce()
        self.assertEqual(result.returncode, 0, result.stderr)
        deleted = self.listed(result.stdout, "deleted")
        self.assertEqual(deleted, MOVED_OUT, result.stdout)
        self.assertEqual(self.section(result.stdout, "נמחקו הקבצים הבאים:"), MOVED_OUT)

    def test_a_book_moved_into_the_library_is_announced_added_once(self):
        result = self.announce()
        self.assertEqual(result.returncode, 0, result.stderr)
        added = self.listed(result.stdout, "added")
        self.assertEqual(added, [ADDED, MOVED_IN], result.stdout)
        self.assertEqual(self.section(result.stdout, "התווספו הקבצים הבאים:"), [ADDED, MOVED_IN])

    def test_the_other_two_sections_are_unchanged(self):
        result = self.announce()
        self.assertEqual(self.listed(result.stdout, "modified"), [MODIFIED])
        self.assertEqual(self.listed(result.stdout, "renamed"), [])
        published = (self.root / VERSION_FILE).with_name("עדכוני ספריה.md")
        self.assertTrue(
            published.read_text(encoding="utf-8").startswith("# גירסת ספרייה 168"),
            published.read_text(encoding="utf-8")[:80],
        )

    def test_every_list_is_labelled(self):
        """Four bare `[]` reprs cannot be told apart when diagnosing a bad publish."""
        result = self.announce()
        for label in ("added", "modified", "deleted", "renamed"):
            self.assertIn(f"{label}: [", result.stdout)

    def test_the_library_update_contacts_no_channel(self):
        """Announcements come from SeforimLibrary once a release is really published."""
        result = self.announce()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("STUB-", result.stdout)
        self.assertNotIn("notifications:", result.stdout)


class DeepenTest(unittest.TestCase):
    """`get_last_version_commit_sha` deepens a shallow checkout until the previous
    'גרסת ספרייה' commit is genuinely in view.  It runs in the prepare child the weekly
    head watches, so a transient fetch failure must be retried rather than treated like
    the genuine "no version commit in range" answer.  Everything here is local git — an
    origin repository and `--depth=1` clones of it over `file://` — and no network."""

    # main.py publishes at import, so only the region above `BEFORE_SHA = …` is exec'd;
    # it needs nothing but subprocess and time.  The overrides file is exec'd into the
    # same namespace afterwards, which is how the deepen loop's `run_git` is made flaky
    # and its backoff made instant without a knob in the shipped script.
    DRIVER = '''\
import subprocess
import sys
import time

source = open(sys.argv[1], encoding="utf-8").read()
prelude = source[source.index("VERSION_FILE = "):source.index("BEFORE_SHA = ")]
namespace = {"subprocess": subprocess, "time": time}
exec(compile(prelude, sys.argv[1], "exec"), namespace)
exec(compile(open(sys.argv[2], encoding="utf-8").read(), sys.argv[2], "exec"), namespace)
print("SHA=" + namespace["get_last_version_commit_sha"]())
'''

    INSTANT = "DEEPEN_BACKOFF_SECONDS = 0\n"
    FLAKY_FETCH = INSTANT + '''\
_real_run_git = run_git
_failures = {failures}


def run_git(*args):
    global _failures
    if args[0] == "fetch" and _failures > 0:
        _failures -= 1
        return subprocess.CompletedProcess(args, 1, "", "fatal: the remote end hung up unexpectedly")
    return _real_run_git(*args)
'''

    VERSION_MESSAGE = "גרסת ספרייה 167"
    HISTORY = 30
    VERSION_AT = 2   # 27 commits behind HEAD: two 25-commit steps away, never one
    TAGGED = 5       # handoff tags on the oldest commits, out of the depth-1 window

    # Every directory here is scratch git repositories, and git writes into a
    # repository from processes the test never waits on -- auto maintenance
    # after a fetch is the usual one.  Losing that race leaves a file inside a
    # `.git` that rmtree has already walked, and the rmdir then fails with
    # ENOTEMPTY *after* the case itself passed.  A runner's /tmp is thrown away
    # whole, so a stray object file is nothing; failing a green test over it is.
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(cls._tmp.name)
        cls.with_version, cls.version_sha = cls.build_origin(root / "with-version", True)
        cls.without_version, _ = cls.build_origin(root / "without-version", False)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @staticmethod
    def build_origin(root, with_version_commit):
        """Empty commits: the deepen loop only ever reads commit messages."""
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        sha = None
        for index in range(DeepenTest.HISTORY):
            versioned = with_version_commit and index == DeepenTest.VERSION_AT
            message = DeepenTest.VERSION_MESSAGE if versioned else f"sync {index}"
            git(root, "commit", "-q", "--allow-empty", "-m", message)
            if versioned:
                sha = git(root, "rev-parse", "HEAD").strip()
            if index < DeepenTest.TAGGED:
                git(root, "tag", f"handoff-{index}")
        return root, sha

    def setUp(self):
        self._case = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._case.cleanup)
        self.case = Path(self._case.name)
        (self.case / "drive.py").write_text(self.DRIVER, encoding="utf-8")

    def clone(self, origin):
        target = self.case / "checkout"
        git(self.case, "clone", "-q", "--depth=1", "--branch", "main",
            origin.as_uri(), str(target))
        return target

    def deepen(self, origin, overrides=INSTANT):
        checkout = self.clone(origin)
        script = self.case / "overrides.py"
        script.write_text(overrides, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.case / "drive.py"), str(MAIN), str(script)],
            cwd=checkout,
            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result.checkout = checkout
        return result

    def test_a_version_commit_beyond_the_window_is_found_by_deepening(self):
        result = self.deepen(self.with_version)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"SHA={self.version_sha}", result.stdout)
        self.assertIn("after deepening the history to 30 commits", result.stdout)

    def test_the_deepen_fetch_leaves_the_handoff_tags_alone(self):
        """~87 handoff tags live in this repository; re-negotiating them on every
        25-commit step is pure cost, and a plain `--deepen` does drag in the ones the
        newly fetched commits carry."""
        result = self.deepen(self.with_version)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(result.checkout, "tag", "-l").split(), [])

    def test_a_transient_fetch_failure_is_retried_instead_of_failing_the_child(self):
        result = self.deepen(self.with_version, self.FLAKY_FETCH.format(failures=2))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"SHA={self.version_sha}", result.stdout)
        self.assertIn("(attempt 1/3), retrying", result.stdout)
        self.assertIn("(attempt 2/3), retrying", result.stdout)
        self.assertNotIn("::error::", result.stdout)

    def test_a_fetch_that_never_recovers_is_still_a_hard_error(self):
        result = self.deepen(self.with_version, self.FLAKY_FETCH.format(failures=99))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "::error::git fetch --no-tags --deepen=25 failed 3 times", result.stdout
        )
        self.assertEqual(result.stdout.count("), retrying"), 2, result.stdout)
        self.assertNotIn("SHA=", result.stdout)

    def test_no_version_commit_in_range_stays_a_hard_error(self):
        """The retry must not soften the case the deepen loop exists to catch."""
        result = self.deepen(self.without_version)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("::error::no 'גרסת ספרייה' commit", result.stdout)
        self.assertIn("refusing to fall back to HEAD^", result.stdout)


class VersionCommitMatchTest(unittest.TestCase):
    """Only the bot's subject line marks a version.  A newer commit whose body quotes
    the phrase (b49ce978 did, and so did the first draft of the National-Library fix)
    must not become BEFORE_SHA: everything between the two would vanish from the
    changelog on a green build."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(cls._tmp.name) / "decoy"
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        git(root, "commit", "-q", "--allow-empty", "-m", "sync 0")
        git(root, "commit", "-q", "--allow-empty", "-m", cls.VERSION_MESSAGE)
        cls.version_sha = git(root, "rev-parse", "HEAD").strip()
        git(root, "commit", "-q", "--allow-empty", "-m", "rename books")
        for decoy in (
            "fix(weekly): diff from the previous\n\nthe previous \"גרסת ספרייה\" commit is the base",
            "גרסת ספרייה הבאה תכלול את השינוי",
            "chore\n\nגרסת ספרייה 999",
        ):
            git(root, "commit", "-q", "--allow-empty", "-m", decoy)
        cls.origin = root

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    VERSION_MESSAGE = DeepenTest.VERSION_MESSAGE
    DRIVER = DeepenTest.DRIVER
    setUp = DeepenTest.setUp
    clone = DeepenTest.clone
    deepen = DeepenTest.deepen

    def test_a_body_or_subject_that_only_quotes_the_phrase_is_not_a_version(self):
        result = self.deepen(self.origin)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"SHA={self.version_sha}", result.stdout)


class DedupeTest(unittest.TestCase):
    def setUp(self):
        self.dedupe = load_function("dedupe_preserving_order")

    def test_the_first_occurrence_wins_and_the_diff_order_survives(self):
        self.assertEqual(self.dedupe(["b", "a", "b", "c", "a"]), ["b", "a", "c"])

    def test_an_already_unique_list_is_returned_unchanged(self):
        self.assertEqual(self.dedupe(["a", "b"]), ["a", "b"])

    def test_an_empty_list_stays_empty(self):
        self.assertEqual(self.dedupe([]), [])


if __name__ == "__main__":
    unittest.main()
