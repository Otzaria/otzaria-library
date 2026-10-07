# -*- coding: utf-8 -*-
"""End-to-end tests for following book renames instead of deleting ForDB rows.

Every scenario builds a throw-away git repository shaped like otzaria-library
(packaged roots, ForDB/, metadata.json, links roots in the formats found in
the real tree), makes commits, and runs the real validator in a subprocess
with --fix and --rename-base, the way the workflow does.  The Sefaria catalogue
is stubbed, so the tests run offline.

The first scenario replays the incident behind this code: e6bb6a79 renamed
'אמת ואמונה - מנחם מנדל מקוצק.txt' to 'אמת ואמונה.txt', 884e5f79 moved it into
a sub-folder, and the CI then deleted its generations row (bccfea27) while the
author, the description and the manual links kept pointing at the old name.
"""

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fordb_book_renames as renames
import validate_fordb_book_names as validator

SCRIPTS = os.path.dirname(os.path.abspath(__file__))

OLD = "אמת ואמונה - מנחם מנדל מקוצק"
NEW = "אמת ואמונה"
# Another book whose title starts with OLD + " ": its heRef_2 must never be rewritten.
TRAP = OLD + " על התורה"
OTHER = "ספר אחר"
LEAVES = "ספר שהועבר"
SEFARIA_ONLY = "ספר מספריא"

HASIDUT = "OnYourWayToOtzaria/ספרים/אוצריא/חסידות"
RISHONIM = "MoreBooks/ספרים/אוצריא/ראשונים"
LINKS = "MoreBooks/links"


def book_text(title, lines=60):
    body = [f"<h1>{title}</h1>"]
    body += [f"פרק {i} שורה מספר {i} של הספר, עם תוכן ייחודי {i * 7919 % 1009}" for i in range(lines)]
    return "\n".join(body) + "\n"


def one_record_per_line(records):
    """metadata.json keeps one compact object per line, not json.dump(indent=...)."""
    return "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records) + "\n]"


def base_files():
    links_of_old = [
        {"line_index_1": 1, "heRef_2": OTHER + " א", "path_2": OTHER + ".txt", "line_index_2": 1,
         "Conection Type": "commentary"},
    ]
    links_of_other = [
        # path_2 and heRef_2 both carry the title: both follow.
        {"line_index_1": 1, "heRef_2": OLD + " א, ב", "path_2": OLD + ".txt", "line_index_2": 2,
         "Conection Type": "commentary"},
        # heRef_2 is a free label here: only path_2 follows.
        {"line_index_1": 2, "heRef_2": "פירוש על הספר", "path_2": OLD + ".txt", "line_index_2": 3,
         "Conection Type": "commentary"},
        # A different book whose title begins with OLD: untouched.
        {"line_index_1": 3, "heRef_2": TRAP + " א", "path_2": TRAP + ".txt", "line_index_2": 4,
         "Conection Type": "commentary"},
        # A path_2 that carries folders: only the last component changes.
        {"line_index_1": 4, "heRef_2": OLD, "path_2": "חסידות/" + OLD + ".txt", "line_index_2": 5,
         "Conection Type": "commentary"},
    ]
    return {
        f"{HASIDUT}/{OLD}.txt": book_text(OLD),
        f"{HASIDUT}/{TRAP}.txt": book_text(TRAP),
        f"{RISHONIM}/{OTHER}.txt": book_text(OTHER),
        f"{RISHONIM}/{LEAVES}.txt": book_text(LEAVES),
        "extraBooks/ישנים/placeholder.txt": book_text("placeholder"),
        "ForDB/book_moves.csv": (
            "name,Source path,Destination path\n"
            f'"{OLD}",חסידות,חסידות/נוספים\n'
        ),
        # כמו הקובץ שהאתר כותב: הכול במירכאות, ושורה לכל מחבר של אותו ספר.
        "ForDB/book_info.csv": (
            "bookName,authorName,generationName,subGenerationName,startYear,endYear\n"
            f'"{OTHER}","","ראשונים","","",""\n'
            f'"{OLD}","מנחם מנדל מקוצק","אחרונים","אחרוני האחרונים","1787","1859"\n'
            f'"{OLD}","עורך ""הוצאה""","אחרונים","","",""\n'
            f'"{SEFARIA_ONLY}","","אחרונים","","",""\n'
            f'"{LEAVES}","","אחרונים","","",""\n'
        ),
        "ForDB/book_renames.csv": "ספר ישן מספריא,ספר חדש מספריא\n",
        "ForDB/sefaria_metadata_changes.csv": (
            '"categoryPath","title","author","heShortDesc","heDesc","heDescNew"\n'
            f'"חסידות","{OLD}","מנחם מנדל מקוצק","קצר","תיאור ""מצוטט""\nבשתי שורות","חדש"\n'
            f'"ראשונים","{OTHER}","","","",""\n'
        ),
        "ForDB/all_metadata.json": json.dumps(
            [
                {"title": OLD, "Sourcefolder": "OnYourWay", "pubDate": "1850"},
                {"title": OTHER, "Sourcefolder": "MoreBooks", "pubDate": "1500"},
            ],
            ensure_ascii=False, indent=2,
        ) + "\n",
        "metadata.json": one_record_per_line(
            [
                {"title": OTHER, "author": "מחבר אחר", "heDesc": None},
                {"title": OLD, "author": "מנחם מנדל מקוצק", "heDesc": "תיאור"},
            ]
        ),
        "all_metadata_with_file_paths.json": json.dumps(
            [
                {"title": OLD, "Sourcefolder": "OnYourWay", "file_path": "חסידות\\" + OLD + ".txt"},
                {"title": OTHER, "Sourcefolder": "MoreBooks", "file_path": "ראשונים\\" + OTHER + ".txt"},
                {"title": SEFARIA_ONLY, "Sourcefolder": "sefaria"},
            ],
            ensure_ascii=False, indent=2,
        ) + "\n",
        "manual_links_sync.json": json.dumps(
            {"links_roots": [
                {"path": LINKS, "expected_state": "present"},
                {"path": "OnYourWayToOtzaria/links", "expected_state": "absent"},
            ]},
            ensure_ascii=False, indent=2,
        ) + "\n",
        f"{LINKS}/{OLD}_links.json": json.dumps(links_of_old, ensure_ascii=False, indent=1),
        f"{LINKS}/{OTHER}_links.json": json.dumps(links_of_other, ensure_ascii=False, indent=4) + "\n",
    }


SEFARIA_STUB = [SEFARIA_ONLY, "ספר ישן מספריא", "ספר חדש מספריא"]

RUNNER = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import validate_fordb_book_names as v
v.SEFARIA_FETCH = True
stub = set(json.loads(sys.argv[2]))
v.fetch_sefaria_titles = lambda: set(stub)
sys.argv = ["validate_fordb_book_names.py"] + sys.argv[3:]
sys.exit(v.main())
"""


class FixtureRepo:
    """A git repository shaped like otzaria-library, with the validator committed in it."""

    def __init__(self, root):
        self.root = root
        os.makedirs(root)
        self.git("init", "-q", "-b", "main")
        files = dict(base_files())
        for name in ("validate_fordb_book_names.py", "fordb_book_renames.py", "book_info_contract.py"):
            with open(os.path.join(SCRIPTS, name), encoding="utf-8") as handle:
                files[f".github/scripts/{name}"] = handle.read()
        self.write(files)
        self.base = self.commit("base")

    # -- git -------------------------------------------------------------
    def git(self, *args, cwd=None):
        result = subprocess.run(
            ["git", "-C", cwd or self.root, "-c", "user.name=t", "-c", "user.email=t@t",
             "-c", "commit.gpgsign=false", "-c", "core.quotepath=off", *args],
            capture_output=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def write(self, files):
        for rel, content in files.items():
            full = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)

    def move(self, old, new):
        os.makedirs(os.path.dirname(os.path.join(self.root, new)), exist_ok=True)
        self.git("mv", old, new)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as handle:
            return handle.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    # -- validator -------------------------------------------------------
    def run_validator(self, *args, cwd=None, sefaria=SEFARIA_STUB):
        where = cwd or self.root
        env = dict(os.environ, PYTHONIOENCODING="utf-8", SEFARIA_FETCH="1", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-c", RUNNER, os.path.join(where, ".github", "scripts"),
             json.dumps(sefaria, ensure_ascii=False), *args],
            capture_output=True, cwd=where, env=env,
        )
        return result.returncode, result.stdout.decode("utf-8") + result.stderr.decode("utf-8")

    def touched(self, cwd=None):
        path = os.path.join(cwd or self.root, "fordb_touched.txt")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            return [p for p in handle.read().split("\0") if p]


def csv_rows(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def generation_rows(text):
    """[שם ספר, דור] לכל שורת book_info.csv, בלי הכותרת."""
    return [[row[0], row[2]] for row in csv_rows(text)[1:]]


def rename_incident(repo):
    """e6bb6a79 (rename + heading edit, R099) then 884e5f79 (folder move) then noise."""
    repo.move(f"{HASIDUT}/{OLD}.txt", f"{HASIDUT}/{NEW}.txt")
    content = repo.read(f"{HASIDUT}/{NEW}.txt").replace(f"<h1>{OLD}</h1>", f"<h1>{NEW}</h1>")
    repo.write({f"{HASIDUT}/{NEW}.txt": content})
    rename_commit = repo.commit("שינוי שם")
    repo.move(f"{HASIDUT}/{NEW}.txt", f"{HASIDUT}/ספרי חסידות נוספים/{NEW}.txt")
    repo.commit("שינוי מיקום")
    repo.write({f"{RISHONIM}/{OTHER}.txt": book_text(OTHER, lines=61)})
    repo.commit("עריכה")
    return rename_commit


class FixtureTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fordb-renames-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = FixtureRepo(os.path.join(self.tmp, "repo"))

    def assertOnlyTouched(self, expected, cwd=None):
        expected = list(expected)
        if "ForDB/book_info.csv" in expected:
            expected.append("ForDB/book_info_identity.json")
        self.assertEqual(sorted(self.repo.touched(cwd)), sorted(expected))
        status = self.repo.git("status", "--porcelain", "-z", "--untracked-files=all", cwd=cwd)
        changed = set()
        for entry in status.split("\0"):
            if entry:
                changed.add(entry[3:])
        reports = {"fordb_touched.txt", "fordb_commit_message.txt", "fordb_renamed.json", "fordb_removed.json"}
        self.assertEqual(changed - reports, set(expected))


class IncidentReplayTest(FixtureTestCase):
    """The אמת ואמונה incident, followed instead of deleted."""

    def setUp(self):
        super().setUp()
        self.rename_commit = rename_incident(self.repo)
        self.code, self.output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)

    def test_the_run_succeeds_and_deletes_nothing(self):
        self.assertEqual(self.code, 0, self.output)
        self.assertFalse(self.repo.exists("fordb_removed.json"), self.output)

    def test_book_info_rows_are_renamed_in_place(self):
        self.assertEqual(
            generation_rows(self.repo.read("ForDB/book_info.csv")),
            [[NEW, "אחרונים"], [NEW, "אחרונים"], [OTHER, "ראשונים"],
             [SEFARIA_ONLY, "אחרונים"], [LEAVES, "אחרונים"]],
        )

    def test_every_book_info_row_of_the_book_follows_it_and_keeps_its_quoting(self):
        self.assertEqual(
            self.repo.read("ForDB/book_info.csv"),
            renames.sort_csv_records(base_files()["ForDB/book_info.csv"].replace(f'"{OLD}",', f'"{NEW}",').encode("utf-8"), ("bookName", "authorName")).decode("utf-8"),
        )

    def test_book_moves_keeps_its_quoting(self):
        self.assertEqual(
            self.repo.read("ForDB/book_moves.csv"),
            f'name,Source path,Destination path\n"{NEW}",חסידות,חסידות/נוספים\n',
        )

    def test_description_row_is_renamed_and_its_multiline_field_survives(self):
        rows = csv_rows(self.repo.read("ForDB/sefaria_metadata_changes.csv"))
        self.assertEqual(rows[1], ["חסידות", NEW, "מנחם מנדל מקוצק", "קצר", 'תיאור "מצוטט"\nבשתי שורות', "חדש"])
        self.assertEqual(rows[2][1], OTHER)

    def test_metadata_files_are_renamed_byte_for_byte(self):
        for rel in ("ForDB/all_metadata.json", "metadata.json"):
            original = base_files()[rel]
            self.assertEqual(self.repo.read(rel), original.replace(json.dumps(OLD, ensure_ascii=False),
                                                                   json.dumps(NEW, ensure_ascii=False)), rel)

    def test_canonical_metadata_follows_the_title_and_the_folder(self):
        records = json.loads(self.repo.read("all_metadata_with_file_paths.json"))
        self.assertEqual(records[0]["title"], NEW)
        self.assertEqual(records[0]["file_path"], "חסידות\\ספרי חסידות נוספים\\" + NEW + ".txt")
        self.assertEqual(records[1]["file_path"], "ראשונים\\" + OTHER + ".txt")

    def test_links_file_of_the_book_is_renamed_unchanged(self):
        self.assertFalse(self.repo.exists(f"{LINKS}/{OLD}_links.json"))
        self.assertEqual(self.repo.read(f"{LINKS}/{NEW}_links.json"), base_files()[f"{LINKS}/{OLD}_links.json"])

    def test_links_pointing_at_the_book_follow_it(self):
        records = json.loads(self.repo.read(f"{LINKS}/{OTHER}_links.json"))
        self.assertEqual([r["path_2"] for r in records],
                         [NEW + ".txt", NEW + ".txt", TRAP + ".txt", "חסידות/" + NEW + ".txt"])
        self.assertEqual([r["heRef_2"] for r in records], [NEW + " א, ב", "פירוש על הספר", TRAP + " א", NEW])

    def test_links_file_keeps_its_indentation(self):
        text = self.repo.read(f"{LINKS}/{OTHER}_links.json")
        self.assertEqual(text, base_files()[f"{LINKS}/{OTHER}_links.json"]
                         .replace(f'"{OLD}.txt"', f'"{NEW}.txt"')
                         .replace(f'"{OLD} א, ב"', f'"{NEW} א, ב"')
                         .replace(f'"חסידות/{OLD}.txt"', f'"חסידות/{NEW}.txt"')
                         .replace(f'"heRef_2": "{OLD}"', f'"heRef_2": "{NEW}"'))

    def test_exactly_the_title_keyed_files_are_touched(self):
        self.assertOnlyTouched([
            "ForDB/book_info.csv", "ForDB/book_moves.csv", "ForDB/sefaria_metadata_changes.csv",
            "ForDB/all_metadata.json", "metadata.json", "all_metadata_with_file_paths.json",
            f"{LINKS}/{OLD}_links.json", f"{LINKS}/{NEW}_links.json", f"{LINKS}/{OTHER}_links.json",
        ])

    def test_reports_name_the_commit_that_renamed_the_file(self):
        report = json.loads(self.repo.read("fordb_renamed.json"))
        self.assertEqual([(r["old"], r["new"], r["commit"]) for r in report], [(OLD, NEW, self.rename_commit)])
        message = self.repo.read("fordb_commit_message.txt")
        self.assertTrue(message.startswith("ci(fordb): follow book renames\n\n"), message)
        self.assertIn(f"{OLD} → {NEW} (renamed in {self.rename_commit[:10]})", message)

    def test_a_second_run_after_committing_is_a_no_op(self):
        for report in ("fordb_touched.txt", "fordb_commit_message.txt", "fordb_renamed.json"):
            os.unlink(os.path.join(self.repo.root, report))
        self.repo.commit("ci(fordb): follow book renames")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.repo.touched(), [])
        self.assertEqual(self.repo.git("status", "--porcelain"), "")


class ReportOnlyTest(FixtureTestCase):
    def test_a_pull_request_reports_the_plan_and_writes_nothing(self):
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--rename-base", self.repo.base)
        # The row is checked under its new name, as it will be after the merge.
        self.assertEqual(code, 0, output)
        self.assertIn("ייושרו אוטומטית במיזוג ל-main", output)
        self.assertEqual(self.repo.git("status", "--porcelain"), "")

    def test_a_real_orphan_still_fails_a_pull_request(self):
        self.repo.move(f"{RISHONIM}/{LEAVES}.txt", f"extraBooks/ישנים/{LEAVES} (ישן).txt")
        self.repo.commit("העברה ל-extraBooks")
        code, output = self.repo.run_validator("--rename-base", self.repo.base)
        self.assertEqual(code, 1, output)
        self.assertEqual(self.repo.git("status", "--porcelain"), "")


class OldBehaviourIsKeptTest(FixtureTestCase):
    def test_a_rename_outside_the_range_is_still_removed_as_an_orphan(self):
        rename_commit = rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", rename_commit)
        self.assertEqual(code, 0, output)
        removed = json.loads(self.repo.read("fordb_removed.json"))
        self.assertIn({"file": "ForDB/book_info.csv", "name": OLD, "reason": "orphan"}, removed)
        self.assertFalse(self.repo.exists("fordb_renamed.json"))

    def test_every_book_info_row_of_an_orphan_is_removed_and_the_rest_keep_their_bytes(self):
        rename_commit = rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", rename_commit)
        self.assertEqual(code, 0, output)
        removed = json.loads(self.repo.read("fordb_removed.json"))
        self.assertEqual([r for r in removed if r["file"] == "ForDB/book_info.csv"],
                         [{"file": "ForDB/book_info.csv", "name": OLD, "reason": "orphan"}] * 2)
        self.assertEqual(
            self.repo.read("ForDB/book_info.csv"),
            "bookName,authorName,generationName,subGenerationName,startYear,endYear\n"
            f'"{OTHER}","","ראשונים","","",""\n'
            f'"{SEFARIA_ONLY}","","אחרונים","","",""\n'
            f'"{LEAVES}","","אחרונים","","",""\n',
        )

    def test_a_book_moved_out_of_the_library_is_removed_not_renamed(self):
        self.repo.move(f"{RISHONIM}/{LEAVES}.txt", f"extraBooks/ישנים/{LEAVES} (ישן).txt")
        self.repo.commit("העברה ל-extraBooks")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(self.repo.read("fordb_removed.json")),
                         [{"file": "ForDB/book_info.csv", "name": LEAVES, "reason": "orphan"}])
        self.assertOnlyTouched(["ForDB/book_info.csv"])
        self.assertTrue(self.repo.read("fordb_commit_message.txt").startswith(
            "ci(fordb): remove inputs that cannot be applied\n"))

    def test_no_usable_base_falls_back_with_a_warning(self):
        rename_incident(self.repo)
        code, output = self.repo.run_validator(
            "--fix", "--rename-base", "0" * 40, "--rename-base", "deadbeef")
        self.assertEqual(code, 0, output)
        self.assertIn("אין בסיס זמין למעקב", output)
        self.assertIn({"file": "ForDB/book_info.csv", "name": OLD, "reason": "orphan"},
                      json.loads(self.repo.read("fordb_removed.json")))

    def test_the_first_usable_base_wins(self):
        rename_incident(self.repo)
        code, output = self.repo.run_validator(
            "--fix", "--rename-base", "", "--rename-base", "deadbeef", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertFalse(self.repo.exists("fordb_removed.json"))
        self.assertIn([NEW, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))


class HistoryShapesTest(FixtureTestCase):
    def test_a_chain_of_renames_lands_on_the_final_name(self):
        middle = "אמת ואמונה (ביניים)"
        self.repo.move(f"{HASIDUT}/{OLD}.txt", f"{HASIDUT}/{middle}.txt")
        self.repo.commit("1")
        self.repo.move(f"{HASIDUT}/{middle}.txt", f"{HASIDUT}/{NEW}.txt")
        self.repo.commit("2")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertIn([NEW, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))
        self.assertTrue(self.repo.exists(f"{LINKS}/{NEW}_links.json"))

    def test_delete_and_re_add_in_separate_commits_is_seen_by_the_net_diff(self):
        content = self.repo.read(f"{HASIDUT}/{OLD}.txt")
        self.repo.git("rm", "-q", f"{HASIDUT}/{OLD}.txt")
        self.repo.commit("מחיקה")
        self.repo.write({f"{HASIDUT}/{NEW}.txt": content})
        self.repo.commit("הוספה")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertFalse(self.repo.exists("fordb_removed.json"), output)
        self.assertIn([NEW, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))

    def test_a_split_into_several_books_is_not_a_rename(self):
        content = self.repo.read(f"{HASIDUT}/{OLD}.txt").splitlines(keepends=True)
        self.repo.git("rm", "-q", f"{HASIDUT}/{OLD}.txt")
        self.repo.write({
            f"{HASIDUT}/{NEW} א.txt": "".join(content[:20]),
            f"{HASIDUT}/{NEW} ב.txt": "".join(content[20:40]),
            f"{HASIDUT}/{NEW} ג.txt": "".join(content[40:]),
        })
        self.repo.commit("פיצול")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertIn({"file": "ForDB/book_info.csv", "name": OLD, "reason": "orphan"},
                      json.loads(self.repo.read("fordb_removed.json")))
        self.assertFalse(self.repo.exists("fordb_renamed.json"))


class UnsafeRenamesAreHeldTest(FixtureTestCase):
    """Anything the follower cannot decide is neither renamed nor deleted — the run fails."""

    def assertHeld(self, code, output):
        self.assertEqual(code, 1, output)
        self.assertIn("לא יושרו אוטומטית ולא נמחקו", output)
        self.assertIn([OLD, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))
        self.assertFalse(self.repo.exists("fordb_removed.json"))

    def test_an_old_name_that_went_two_ways_is_ambiguous(self):
        self.repo.move(f"{HASIDUT}/{OLD}.txt", f"{HASIDUT}/{NEW}.txt")
        self.repo.commit("1")
        self.repo.write({f"{HASIDUT}/{OLD}.txt": book_text(OLD + " מהדורה שנייה")})
        self.repo.commit("2")
        self.repo.move(f"{HASIDUT}/{OLD}.txt", f"{HASIDUT}/{NEW} מהדורה שנייה.txt")
        self.repo.commit("3")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertHeld(code, output)
        self.assertIn("כמה יעדים", output)

    def test_a_name_that_book_renames_touches_is_left_to_a_human(self):
        self.repo.write({"ForDB/book_renames.csv": f"{OLD},{OLD} (מתוקן)\n"})
        self.repo.commit("book_renames")
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 1, output)
        self.assertIn("book_renames.csv", output)
        self.assertIn([OLD, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))

    def test_a_links_file_already_taken_by_the_new_name_blocks_everything_for_that_name(self):
        self.repo.write({f"{LINKS}/{NEW}_links.json": "[]\n"})
        self.repo.commit("קישורים קיימים")
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertHeld(code, output)
        self.assertIn("כבר קיים", output)
        # all-or-nothing: not even metadata.json was half-renamed
        self.assertIn(OLD, json.loads(self.repo.read("ForDB/all_metadata.json"))[0]["title"])
        self.assertIn(f'"title":"{OLD}"', self.repo.read("metadata.json"))


class ExistingEntriesForTheNewNameTest(FixtureTestCase):
    def test_a_new_blank_author_row_preserves_every_existing_coauthor(self):
        rows = self.repo.read("ForDB/book_info.csv") + f'"{NEW}","","ראשונים","","",""\n'
        self.repo.write({"ForDB/book_info.csv": rows})
        self.repo.write({"metadata.json": one_record_per_line([
            {"title": OTHER, "author": "מחבר אחר", "heDesc": None},
            {"title": OLD, "author": "מנחם מנדל מקוצק", "heDesc": "תיאור"},
            {"title": NEW, "author": "מחבר חדש", "heDesc": None},
        ])})
        self.repo.commit("הכנה")
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        generations = generation_rows(self.repo.read("ForDB/book_info.csv"))
        self.assertNotIn([OLD, "אחרונים"], generations)
        self.assertIn([NEW, "ראשונים"], generations)
        self.assertEqual([r for r in generations if r[0] == NEW], [[NEW, "ראשונים"], [NEW, "אחרונים"], [NEW, "אחרונים"]])
        # metadata is never deleted: the stale entry stays, the explicit one is untouched
        metadata = json.loads(self.repo.read("metadata.json"))
        self.assertEqual([m["title"] for m in metadata], [OTHER, OLD, NEW])


class BookInfoIdentityRegressionTest(FixtureTestCase):
    def test_target_author_deduplicates_only_itself_and_preserves_other_authors(self):
        source = self.repo.read("ForDB/book_info.csv")
        rows = csv_rows(source)
        original = [r for r in rows[1:] if r[0] == OLD]
        target = [NEW, *original[0][1:]]
        buf = io.StringIO(newline="")
        csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(target)
        self.repo.write({"ForDB/book_info.csv": source + buf.getvalue()})
        self.repo.commit("target author metadata")
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        actual = csv_rows(self.repo.read("ForDB/book_info.csv"))
        self.assertEqual([r for r in actual if r[0] == NEW], sorted([[NEW, *original[1][1:]], target], key=lambda r: tuple(r[:2])))
        ledger = json.loads(self.repo.read("ForDB/book_info_identity.json"))
        self.assertEqual([e["old"]["authorName"] for e in ledger["events"]], sorted(r[1] for r in original))
        first = self.repo.read("ForDB/book_info_identity.json")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertEqual(code, 0, output)
        self.assertEqual(self.repo.read("ForDB/book_info_identity.json"), first)

    def test_conflicting_same_author_metadata_blocks_entire_rename_without_pruning(self):
        source = self.repo.read("ForDB/book_info.csv")
        row = next(r for r in csv_rows(source)[1:] if r[0] == OLD)
        row[0], row[2], row[3], row[4] = NEW, "ראשונים", "ראשוני הראשונים", "100"
        buf = io.StringIO(newline="")
        csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(row)
        source += buf.getvalue()
        self.repo.write({"ForDB/book_info.csv": source})
        self.repo.commit("conflicting target author")
        rename_incident(self.repo)
        before = self.repo.read("metadata.json")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
        self.assertNotEqual(code, 0, output)
        self.assertIn("conflicting metadata", output)
        self.assertEqual(self.repo.read("ForDB/book_info.csv"), source)
        self.assertEqual(self.repo.read("metadata.json"), before)
        self.assertFalse(self.repo.exists("ForDB/book_info_identity.json"))

    def test_identity_ledger_schema_and_historical_prefix_fail_before_any_write(self):
        event = {"id": 1, "kind": "rename", "old": {"bookName": "מקור", "authorName": "מחבר"},
                 "new": {"bookName": "יעד", "authorName": "מחבר"}, "commit": self.repo.base}
        ledger = {"schemaVersion": 1, "events": [event]}
        self.repo.write({"ForDB/book_info_identity.json": json.dumps(ledger, ensure_ascii=False) + "\n"})
        self.repo.commit("trusted ledger prefix")
        rename_incident(self.repo)
        before = self.repo.read("metadata.json")
        cases = [dict(ledger, schemaVersion=True), dict(ledger, extra=True),
                 {"schemaVersion": 1, "events": [dict(event, id=True)]},
                 {"schemaVersion": 1, "events": [dict(event, commit=None)]},
                 {"schemaVersion": 1, "events": [dict(event, commit="source-not-sha")]},
                 {"schemaVersion": 1, "events": [dict(event, new={"bookName": "rewritten", "authorName": "מחבר"})]},
                 {"schemaVersion": 1, "events": []},
                 {"schemaVersion": 1, "events": [dict(event, new={"bookName": "יעד", "authorName": "A\ud800B"})]}]
        for malformed in cases:
            with self.subTest(ledger=malformed):
                self.repo.write({"ForDB/book_info_identity.json": json.dumps(malformed, ensure_ascii=True) + "\n"})
                code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(self.repo.read("metadata.json"), before)
                self.assertIn(OLD, self.repo.read("ForDB/book_info.csv"))

    def test_identity_ledger_allows_well_formed_astral_unicode(self):
        ledger = {"schemaVersion": 1, "events": [{"id": 1, "kind": "rename",
                  "old": {"bookName": "ספר 📖", "authorName": "מחבר 😀"},
                  "new": {"bookName": "ספר 📖", "authorName": "מחבר 😃"},
                  "commit": self.repo.base}]}
        self.assertEqual(validator.validate_identity_ledger(ledger), ledger)

    def test_publisher_checkout_rejects_committed_identity_history_rewrite(self):
        workflow = Path(SCRIPTS).parent / "workflows" / "update-fordb.yml"
        checkout = workflow.read_text(encoding="utf-8").split("uses: actions/checkout@", 1)[1].split("- name:", 1)[0]
        depth_match = re.search(r"fetch-depth:\s*(\d+)", checkout)
        depth = int(depth_match.group(1)) if depth_match else 1
        event = {"id": 1, "kind": "rename", "old": {"bookName": "מקור", "authorName": "מחבר"},
                 "new": {"bookName": "יעד", "authorName": "מחבר"}, "commit": self.repo.base}
        ledger = {"schemaVersion": 1, "events": [event]}
        self.repo.write({"ForDB/book_info_identity.json": json.dumps(ledger, ensure_ascii=False) + "\n"})
        self.repo.commit("trusted ledger prefix")
        event["new"]["bookName"] = "שכתוב"
        self.repo.write({"ForDB/book_info_identity.json": json.dumps(ledger, ensure_ascii=False) + "\n"})
        self.repo.commit("rewrite historical destination")
        clone = Path(self.tmp) / "publisher-checkout"
        self.repo.git("clone", "-q", "--depth", str(depth), Path(self.repo.root).as_uri(), str(clone))
        before = {str(path.relative_to(clone)): path.read_bytes() for path in (clone / "ForDB").iterdir()}
        code, output = self.repo.run_validator("--fix", cwd=str(clone))
        self.assertNotEqual(code, 0, output)
        self.assertIn("append-only", output)
        self.assertEqual({str(path.relative_to(clone)): path.read_bytes() for path in (clone / "ForDB").iterdir()}, before)

    def test_multiline_author_survives_orphan_pruning_byte_for_byte(self):
        for newline in ("\n", "\r", "\r\n"):
            with self.subTest(newline=newline):
                source = self.repo.read("ForDB/book_info.csv")
                # Restore the fixture for each independently executed prune.
                source = base_files()["ForDB/book_info.csv"].replace(f'"{OTHER}","",', f'"{OTHER}","עורך' + newline + 'הוצאה",')
                source += '"יתום","עורך\nאחר","ראשונים","","",""\n'
                self.repo.write({"ForDB/book_info.csv": source})
                code, output = self.repo.run_validator("--fix")
                if newline == "\n":
                    self.assertEqual(code, 0, output)
                    self.assertEqual(Path(self.repo.root, "ForDB/book_info.csv").read_bytes(), source[:source.rindex('"יתום"')].encode("utf-8"))
                else:
                    self.assertNotEqual(code, 0, output)
                    self.assertEqual(Path(self.repo.root, "ForDB/book_info.csv").read_bytes(), source.encode("utf-8"))


    def test_malformed_source_rejects_before_any_rename_write(self):
        rename_incident(self.repo)
        for suffix in ('"יתום","unterminated', '"יתום","author"junk,"ראשונים","","",""\n',
                       '"יתום","author","ראשונים"\n'):
            with self.subTest(suffix=suffix):
                malformed = base_files()["ForDB/book_info.csv"] + suffix
                self.repo.write({"ForDB/book_info.csv": malformed})
                before = self.repo.read("metadata.json")
                code, output = self.repo.run_validator("--fix", "--rename-base", self.repo.base)
                self.assertNotEqual(code, 0, output)
                self.assertEqual(self.repo.read("metadata.json"), before)
                self.assertEqual(self.repo.read("ForDB/book_info.csv"), malformed)


class RespellTest(FixtureTestCase):
    """6cdb121d gave 'הגהות הבח' a curly ” and the CI deleted its row (3d96022b)."""

    PLAIN = "הגהות הבח על מסכת ברכות"
    CURLY = "הגהות הב”ח על מסכת ברכות"
    DB = "הגהות הב״ח על מסכת ברכות"

    def setUp(self):
        super().setUp()
        self.repo.write({
            f"{RISHONIM}/{self.PLAIN}.txt": book_text(self.PLAIN),
            "ForDB/book_info.csv": self.repo.read("ForDB/book_info.csv") + f'"{self.PLAIN}","","אחרונים","","",""\n',
        })
        self.base = self.repo.commit("הגהות")

    def test_a_quote_only_rename_is_respelled_not_deleted(self):
        self.repo.move(f"{RISHONIM}/{self.PLAIN}.txt", f"{RISHONIM}/{self.CURLY}.txt")
        self.repo.commit("גרשיים")
        code, output = self.repo.run_validator("--fix", "--rename-base", self.base)
        self.assertEqual(code, 0, output)
        self.assertIn([self.DB, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))
        self.assertIn("[איות בלבד]", output)

    def test_a_spelling_still_used_by_sefaria_is_not_touched(self):
        self.repo.move(f"{RISHONIM}/{self.PLAIN}.txt", f"{RISHONIM}/{self.CURLY}.txt")
        self.repo.commit("גרשיים")
        code, output = self.repo.run_validator(
            "--fix", "--rename-base", self.base, sefaria=SEFARIA_STUB + [self.PLAIN])
        # left to the spelling check, which reports it and fails the run — as before
        self.assertEqual(code, 1, output)
        self.assertIn("מאויתים אחרת מ-book.title", output)
        self.assertIn([self.PLAIN, "אחרונים"], generation_rows(self.repo.read("ForDB/book_info.csv")))
        self.assertFalse(self.repo.exists("fordb_renamed.json"), output)
        self.assertNotIn("[איות בלבד]", output)


ONYOURWAY = "OnYourWayToOtzaria"


def scoped_csv(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


class SourceScopedTablesTest(FixtureTestCase):
    """book_protection.csv / book_banners.csv: rows keyed by sourceName + bookName."""

    def write_tables(self, protection=(), banners=(), renames=None):
        files = {
            "ForDB/book_protection.csv": scoped_csv(["sourceName", "bookName", "level"], protection),
            "ForDB/book_banners.csv": scoped_csv(["sourceName", "bookName", "text"], banners),
        }
        if renames is not None:
            files["ForDB/book_renames.csv"] = renames
        self.repo.write(files)
        return self.repo.commit("באנר והגנה")

    def test_a_rename_follows_only_the_rows_of_its_own_source(self):
        base = self.write_tables(
            protection=[[ONYOURWAY, OLD, "1"], ["MoreBooks", OTHER, "1"]],
            banners=[[ONYOURWAY, "", "שורה\nשנייה"], ["MoreBooks", OLD, "באנר"]],
        )
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--fix", "--rename-base", base)
        self.assertEqual(code, 0, output)
        self.assertEqual(csv_rows(self.repo.read("ForDB/book_protection.csv"))[1:],
                         [[ONYOURWAY, NEW, "1"], ["MoreBooks", OTHER, "1"]])
        # Same title under another source is a different book: untouched, and only a warning.
        self.assertEqual(csv_rows(self.repo.read("ForDB/book_banners.csv"))[1:],
                         [[ONYOURWAY, "", "שורה\nשנייה"], ["MoreBooks", OLD, "באנר"]])
        self.assertIn("::warning::ForDB/book_banners.csv", output)
        self.assertIn("ForDB/book_protection.csv", self.repo.touched())
        self.assertNotIn("ForDB/book_banners.csv", self.repo.touched())

    def test_a_pull_request_checks_the_row_under_its_new_name(self):
        base = self.write_tables(protection=[[ONYOURWAY, OLD, "1"]])
        rename_incident(self.repo)
        code, output = self.repo.run_validator("--rename-base", base)
        self.assertEqual(code, 0, output)

    def test_valid_rows_and_source_defaults_pass(self):
        self.write_tables(protection=[["KSK", "", "1"], ["MoreBooks", OTHER, "2"]],
                          banners=[["MoreBooks", "", "טקסט [כאן](https://x/{title})"]])
        code, output = self.repo.run_validator()
        self.assertEqual(code, 0, output)
        self.assertNotIn("::warning::ForDB/book_banners.csv", output)

    def test_a_protected_book_of_another_source_fails(self):
        self.write_tables(protection=[[ONYOURWAY, OTHER, "1"]])
        code, output = self.repo.run_validator()
        self.assertEqual(code, 1, output)
        self.assertIn(f"אין ספר כזה במקור {ONYOURWAY}", output)

    def test_an_unknown_source_fails_in_both_files(self):
        self.write_tables(protection=[["NoSuchSource", "", "1"]], banners=[["NoSuchSource", "", "x"]])
        code, output = self.repo.run_validator()
        self.assertEqual(code, 1, output)
        self.assertEqual(output.count("sourceName אינו מקור נארז"), 2, output)

    def test_an_invalid_level_fails(self):
        self.write_tables(protection=[["MoreBooks", OTHER, "0"]])
        code, output = self.repo.run_validator()
        self.assertEqual(code, 1, output)
        self.assertIn("level חייב להיות", output)

    def test_a_missing_banner_book_only_warns(self):
        self.write_tables(banners=[["MoreBooks", "ספר שאינו קיים", "x"]])
        code, output = self.repo.run_validator()
        self.assertEqual(code, 0, output)
        self.assertIn("::warning::ForDB/book_banners.csv", output)

    def test_book_name_is_the_title_after_book_renames(self):
        renames = "ספר ישן מספריא,ספר חדש מספריא\n" + f"{OTHER},{OTHER} מחודש\n"
        self.write_tables(protection=[["MoreBooks", f"{OTHER} מחודש", "1"]], renames=renames)
        code, output = self.repo.run_validator()
        self.assertEqual(code, 0, output)
        self.write_tables(protection=[["MoreBooks", OTHER, "1"]], renames=renames)
        code, output = self.repo.run_validator()
        self.assertEqual(code, 1, output)

    def test_the_tables_are_optional(self):
        code, output = self.repo.run_validator()
        self.assertEqual(code, 0, output)


class SparsePartialCloneTest(unittest.TestCase):
    """The workflow's checkout: blobless, sparse (ForDB + scripts only), history available.

    Nothing outside the sparse set exists on disk; the follower must pull in
    metadata.json and the links roots itself, and git must lazily fetch the
    blobs rename detection needs.  The commit is then staged exactly as the
    workflow stages it."""

    def test_the_workflow_checkout_follows_and_stages_the_rename(self):
        tmp = tempfile.mkdtemp(prefix="fordb-sparse-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        origin = FixtureRepo(os.path.join(tmp, "origin"))
        rename_incident(origin)
        origin.git("config", "uploadpack.allowFilter", "true")
        origin.git("config", "uploadpack.allowAnySHA1InWant", "true")

        work = os.path.join(tmp, "work")
        origin.git("clone", "-q", "--filter=blob:none", "--no-checkout", "--sparse",
                   "file://" + origin.root, work, cwd=tmp)
        origin.git("sparse-checkout", "set", "--no-cone", "/ForDB/", "/.github/scripts/",
                   "/all_metadata_with_file_paths.json", "/manual_links_packaging.py", cwd=work)
        # the same command actions/checkout runs after `sparse-checkout set`
        origin.git("checkout", "-q", "--force", "-B", "main", "origin/main", cwd=work)
        self.assertFalse(os.path.exists(os.path.join(work, "metadata.json")))
        self.assertFalse(os.path.exists(os.path.join(work, LINKS)))

        code, output = origin.run_validator("--fix", "--rename-base", origin.base, cwd=work)
        self.assertEqual(code, 0, output)
        self.assertIn("נוספו ל-sparse-checkout", output)

        origin.git("add", "-A", "--pathspec-from-file=fordb_touched.txt", "--pathspec-file-nul", cwd=work)
        origin.git("commit", "-q", "-F", "fordb_commit_message.txt", cwd=work)
        status = origin.git("show", "--format=", "--name-status", "-M", "HEAD", cwd=work)
        entries = sorted(line.split("\t", 1)[1] for line in status.splitlines() if line)
        self.assertEqual(entries, sorted([
            "ForDB/all_metadata.json", "ForDB/book_info.csv", "ForDB/book_info_identity.json", "ForDB/book_moves.csv",
            "ForDB/sefaria_metadata_changes.csv", "all_metadata_with_file_paths.json", "metadata.json",
            f"{LINKS}/{OTHER}_links.json", f"{LINKS}/{OLD}_links.json\t{LINKS}/{NEW}_links.json",
        ]))
        self.assertTrue(any(line.startswith("R100") for line in status.splitlines()), status)


class EditorUnitTest(unittest.TestCase):
    def test_csv_edit_keeps_every_other_byte(self):
        data = ('\ufeffa,b\r\n"x ""q""",1\r\ny,"multi\nline"\r\nz,3').encode("utf-8")
        out = renames.edit_csv(data, {(1, 0): "X", (3, 0): "Z,z"}, drop_records=[2])
        self.assertEqual(out.decode("utf-8"), '\ufeffa,b\r\n"X",1\r\n"Z,z",3')

    def test_json_edit_keeps_style_and_escapes(self):
        data = '[{"t":"\\u05d0","n":1},\n {"t": "ב" , "k":{"t":"x"}}]'.encode("utf-8")
        with self.assertRaises(renames.EditVerificationError):
            # a nested "t" makes token↔record mapping unprovable
            renames.edit_json_records(data, {(0, "t"): "ג"})
        flat = '[{"t":"\\u05d0","n":1},\n {"t": "ב" }]'.encode("utf-8")
        out = renames.edit_json_records(flat, {(0, "t"): "ג", (1, "t"): "ד"})
        self.assertEqual(out.decode("utf-8"), '[{"t":"\\u05d2","n":1},\n {"t": "ד" }]')

    def test_boundary_rewrite_matches_manual_links_refresh(self):
        self.assertEqual(renames._boundary_rewrite("א ב", "א", "ג"), "ג ב")
        self.assertEqual(renames._boundary_rewrite("א, ב", "א", "ג"), "ג, ב")
        self.assertEqual(renames._boundary_rewrite("א", "א", "ג"), "ג")
        self.assertIsNone(renames._boundary_rewrite("אב", "א", "ג"))


class SanitizeKeyIsStableUnderDbTitleTest(unittest.TestCase):
    """A row written in its DB spelling must keep the key of the file it names."""

    CASES = [
        "הגהות הב”ח", "ר’ סעדיה", "ר`ן", "נר שמואל ח׳׳א", "ר``ן", 'הב"ח', "מהרי''ק",
        "ראש יוסף על  ברכות", "  רווחים  ", "תנך", "שער\u00a0המלך", "‘ציטוט’",
    ]

    def test_crafted_cases(self):
        for raw in self.CASES:
            self.assertEqual(validator.sanitize_title(validator.db_title(raw)),
                             validator.sanitize_title(raw), raw)

    def test_the_packaged_tree(self):
        for path in validator.list_tracked_paths():
            if path.startswith(validator.PACKAGED_PREFIXES) and path.endswith(".txt"):
                name = renames.stem(path)
                self.assertEqual(validator.sanitize_title(validator.db_title(name)),
                                 validator.sanitize_title(name), path)


if __name__ == "__main__":
    unittest.main()
