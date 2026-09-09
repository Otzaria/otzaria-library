"""Self-test for the published library announcement (`send_update/main.py`).

`main.py` runs its whole job at import time, so the announcement is exercised the
way the workflow runs it: a throwaway git repository holding the exact shape that
produced the duplicated delete list in version 168, with `requests`, the forum
client, Yemot and `zoneinfo` replaced by stubs on the script's own sys.path.  No
network call is made and nothing outside the temporary directory is touched.
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

REQUESTS_STUB = '''\
import os


class HTTPError(Exception):
    pass


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(f"{self.status_code} Server Error for the stub webhook")


def post(url, json=None, timeout=None, **kwargs):
    print(f"STUB-CHAT post timeout={timeout} chars={len(json['text'])}")
    mode = os.getenv("STUB_CHAT_MODE", "ok")
    if mode == "raise":
        raise ConnectionError("google chat webhook unreachable")
    if mode == "status":
        return _Response(503)
    return _Response(200)
'''

FORUM_STUB = '''\
import os


class OtzariaForumClient:
    def __init__(self, username, password):
        print(f"STUB-FORUM client user={username}")

    def login(self):
        if os.getenv("STUB_FORUM_MODE") == "raise":
            raise RuntimeError("forum login refused")

    def send_post(self, content, topic_id):
        print(f"STUB-FORUM post topic={topic_id} chars={len(content)}")

    def logout(self):
        print("STUB-FORUM logout")
'''

YEMOT_STUB = '''\
import os


def split_and_send(content, date, token, path, name):
    if os.getenv("STUB_YEMOT_MODE") == "raise":
        raise RuntimeError("yemot upload failed")
    print(f"STUB-YEMOT sections={len(content)}")
'''

# Asia/Jerusalem needs the tzdata package on Windows, which the announcement only
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
    module resolves BEFORE_SHA from git and posts to three services at import."""
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
    """One fixture, several deliveries: building the repository is the slow part
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

    def announce(self, **modes):
        env = dict(
            os.environ,
            PYTHONUTF8="1",
            PYTHONIOENCODING="utf-8",
            USER_NAME="selftest user",
            PASSWORD="selftest password",
            TOKEN_YEMOT="selftest token",
            GOOGLE_CHAT_URL="https://chat.invalid/hook",
        )
        env.pop("STUB_CHAT_MODE", None)
        env.pop("STUB_FORUM_MODE", None)
        env.pop("STUB_YEMOT_MODE", None)
        env.update(modes)
        return subprocess.run(
            [sys.executable, "send_update/main.py"],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def section(self, stdout, label):
        """Return the bullets published under one announcement heading."""
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

    def test_a_healthy_run_reports_every_channel_delivered(self):
        result = self.announce()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("notifications: chat=ok forum=ok yemot=ok", result.stdout)
        self.assertNotIn("::warning::", result.stdout)
        self.assertIn("STUB-CHAT post timeout=30", result.stdout)

    def test_a_chat_outage_no_longer_fails_the_step_or_the_weekly_head(self):
        """`requests.post` had no timeout, no status check and no guard, and it ran
        before the two guarded sends."""
        result = self.announce(STUB_CHAT_MODE="raise")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("::warning::chat notification failed:", result.stdout)
        self.assertIn("google chat webhook unreachable", result.stdout)
        self.assertIn("STUB-FORUM post", result.stdout)
        self.assertIn("STUB-YEMOT", result.stdout)
        self.assertIn("notifications: chat=FAILED forum=ok yemot=ok", result.stdout)

    def test_a_chat_error_response_is_a_failed_delivery_not_a_silent_success(self):
        result = self.announce(STUB_CHAT_MODE="status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("::warning::chat notification failed:", result.stdout)
        self.assertIn("503", result.stdout)
        self.assertIn("notifications: chat=FAILED forum=ok yemot=ok", result.stdout)

    def test_a_forum_failure_is_annotated_instead_of_printed_to_bare_stdout(self):
        result = self.announce(STUB_FORUM_MODE="raise")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("::warning::forum notification failed:", result.stdout)
        self.assertIn("forum login refused", result.stdout)
        self.assertIn("STUB-FORUM logout", result.stdout)
        self.assertIn("notifications: chat=ok forum=FAILED yemot=ok", result.stdout)

    def test_a_yemot_failure_is_annotated_and_still_exits_zero(self):
        """A red build here makes the saga reconciler re-run the whole cycle."""
        result = self.announce(STUB_YEMOT_MODE="raise")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("::warning::yemot notification failed:", result.stdout)
        self.assertIn("notifications: chat=ok forum=ok yemot=FAILED", result.stdout)

    def test_every_channel_down_is_still_a_green_library_update(self):
        result = self.announce(
            STUB_CHAT_MODE="raise", STUB_FORUM_MODE="raise", STUB_YEMOT_MODE="raise"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("::warning::"), 3, result.stdout)
        self.assertIn("notifications: chat=FAILED forum=FAILED yemot=FAILED", result.stdout)


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
