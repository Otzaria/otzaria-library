# -*- coding: utf-8 -*-
"""בדיקות ל־dicta_sync / dicta_replay / dicta_gate / dicta_place / dicta_fp.

    python3 -m unittest discover -s "DictaToOtzaria/סקריפטים/tests" -v
ללא רשת. בדיקות שקוראות את המאגר (git, manual_links_sync.json) רק קוראות.
"""
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import dicta_fp  # noqa: E402
import dicta_gate  # noqa: E402
import dicta_place  # noqa: E402
import dicta_replay  # noqa: E402
import dicta_sync as SY  # noqa: E402

BODY = ("אמר רבי יוחנן כל המקיים נפש אחת מישראל כאילו קיים עולם מלא ולכן נברא אדם יחידי "
        "ללמדך שכל המאבד נפש אחת מעלה עליו הכתוב כאילו איבד עולם מלא ומפני שלום הבריות")


def book_zip(pages):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i, words in enumerate(pages, start=2):
            html = "<html><body dir='rtl'>" + "<span> </span>".join(f"<span>{w}</span>" for w in words.split()) + "</body></html>"
            zf.writestr(f"book-{i:03d}__ocr_data.html", html)
    return buf.getvalue()


class FingerprintTest(unittest.TestCase):
    def test_keys_ignore_markup_nikud_finals(self):
        self.assertEqual(dicta_fp.keys("<b>שָׁלוֹם</b> עולם."), ["שלומ", "עולמ"])

    def test_coverage_layout_independent(self):
        a = dicta_fp.fingerprint(BODY * 20, mod=1)
        b = dicta_fp.fingerprint("\n".join(BODY.split()) * 20, mod=1)
        self.assertEqual(dicta_fp.coverage(a, b), 1.0)

    def test_html_keys_join_glued_spans(self):
        self.assertEqual(dicta_fp.html_keys("<span> בין</span><span>מטה</span><span> </span><span>לזה</span>"),
                         ["בינמטה", "לזה"])

    def test_letters_hash_ignores_word_joins(self):
        self.assertEqual(dicta_fp.letters_hash("ו לפי"), dicta_fp.letters_hash("<b>ולפי</b>"))


class ReplayTest(unittest.TestCase):
    def test_fix_carries_to_new_segmentation(self):
        tail = " וזה המעשה בחכם אחד שהלך בדרך ומצא אבן טובא מאד ושמח בה הרבה"
        old = BODY + tail
        new = BODY + tail.replace("טובא", "טובה")  # תיקון OCR מלאכותי
        fixes, st = dicta_replay.extract(old, new, strict_pair=False)
        self.assertEqual(len(fixes), 1)
        fresh = "\n".join(old.split())  # מילה בשורה — קיטוע שונה לגמרי
        out, ast = dicta_replay.apply(fixes, fresh)
        self.assertEqual(ast.get("applied"), 1)
        self.assertIn("טובה", out)
        self.assertNotIn("טובא", out)
        self.assertEqual(out.count("\n"), fresh.count("\n"))

    def test_mass_pattern_blocked(self):
        words = [f"מילה{chr(0x05d0 + i % 20)} סי ענין" for i in range(30)]
        old = " ".join(words)
        new = old.replace(" סי ", " סימן ").replace("סימן ענין", "סימןענין")
        fixes, st = dicta_replay.extract(old, new, strict_pair=False)
        self.assertEqual(fixes, [])
        self.assertGreater(st.get("mass_pattern", 0), 0)

    def test_other_edition_pair_rejected(self):
        fixes, st = dicta_replay.extract(BODY * 5, BODY * 2, strict_pair=True)
        self.assertEqual(fixes, [])
        self.assertEqual(st.get("pair_rejected"), 1)


class GateTest(unittest.TestCase):
    def good_book(self):
        lines = ["<h1>ספר</h1>", "מחבר"]
        for i in range(40):
            lines += [f"<h2>סימן {i}</h2>", BODY + ":"]
        return "\n".join(lines) + "\n"

    def test_structured_book_passes(self):
        r = dicta_gate.evaluate(self.good_book(), self.good_book())
        self.assertTrue(r["pass"], r["checks"])

    def test_raw_book_fails(self):
        raw = "<h1>ספר</h1>\nמחבר\n" + "\n".join([BODY + ":"] * 80) + "\n"
        r = dicta_gate.evaluate(raw)
        self.assertFalse(r["pass"])
        self.assertFalse(r["checks"]["headings"])

    def test_word_joins_are_not_lost_words(self):
        self.assertEqual(dicta_gate.lost_words("ו לפי זה", "ולפי זה"), 0)
        self.assertEqual(dicta_gate.lost_words("ולפי זה אמר", "ולפי זה"), 1)
        self.assertEqual(dicta_gate.lost_words("<span> בין</span><span>מטה</span>", "ביןמטה", source_is_html=True), 0)
        # אות פתיחה גדולה: <b>י</b>סודי בפלט = "יסודי" במקור (A1, 15 ספרים)
        self.assertEqual(dicta_gate.lost_words("<span>יסודי</span><span> </span><span>הדת</span>",
                                               "<h1>ס</h1>\n<b>י</b>סודי הדת", source_is_html=True), 0)


class PlaceTest(unittest.TestCase):
    PLACED = [
        {"name": "בית יצחק יורה דעה חלק א", "author": "יצחק", "cat": 'שאלות ותשובות (שו"ת)', "sub": "אחרונים - מערב",
         "dirs": ["שות/אחרונים/בית יצחק"]},
        {"name": "ספר א", "author": "א", "cat": "הלכה ומנהג", "sub": "x", "dirs": ["הלכה/אחרונים"]},
        {"name": "ספר ב", "author": "ב", "cat": "הלכה ומנהג", "sub": "x", "dirs": ["הלכה/אחרונים"]},
        {"name": "ספר ג", "author": "ג", "cat": "הלכה ומנהג", "sub": "x", "dirs": ["הלכה/אחרונים"]},
    ]

    def test_stem(self):
        self.assertEqual(dicta_place.stem("בית יצחק יורה דעה חלק ב"), "בית יצחק")
        self.assertEqual(dicta_place.stem('ים של שלמה על בבא קמא'), "ים של שלמה")

    def test_series_is_tier_a(self):
        p = dicta_place.Placer(self.PLACED, ["שות/אחרונים", "הלכה/אחרונים"])
        path, rule, tier = p.predict({"name": "בית יצחק יורה דעה חלק ב", "author": "יצחק",
                                      "cat": 'שאלות ותשובות (שו"ת)', "sub": "אחרונים - מערב"})
        self.assertEqual((path, rule, tier), ("שות/אחרונים/בית יצחק", "R1-series", "A"))

    def test_rambam_rule(self):
        p = dicta_place.Placer(self.PLACED, [])
        self.assertEqual(p.predict({"name": "חידושים", "cat": 'רמב"ם ומפרשיו'})[:2],
                         ("הלכה/משנה תורה/מפרשים", "R3-rambam"))

    def test_unknown_falls_back(self):
        p = dicta_place.Placer(self.PLACED, [])
        self.assertEqual(p.predict({"name": "משהו", "cat": "כללי", "sub": "ביוגרפיה", "author": "ז"})[2], None)


class DestinationTest(unittest.TestCase):
    BOOK = {"category": "חסידות"}

    def test_matrix(self):
        conf = ("חסידות/ספרי חסידות נוספים", "R1-series", "A")
        unsure = ("חסידות/ספרי חסידות נוספים", "R4-table", "B")
        none = (None, "fallback", None)
        d = SY.destination
        self.assertEqual(d("X", self.BOOK, True, conf, True), (f"{SY.ERUKH}/חסידות/ספרי חסידות נוספים/X.txt", SY.EDITED))
        self.assertEqual(d("X", self.BOOK, True, unsure, True), (f"{SY.ERUKH_UNSORTED}/חסידות/X.txt", SY.EDITED_UNSORTED))
        self.assertEqual(d("X", self.BOOK, False, unsure, True), (f"{SY.RAW}/חסידות/ספרי חסידות נוספים/X.txt", SY.RAW_S))
        self.assertEqual(d("X", self.BOOK, False, none, True), (f"{SY.RAW_UNSORTED}/חסידות/X.txt", SY.RAW_S))
        self.assertEqual(d("X", self.BOOK, True, conf, False)[1], SY.RAW_S)  # --no-promote


class PackagingContractTest(unittest.TestCase):
    """"ערוך/ספרים/לא ממויין" חייב להישאר מחוץ לכל מה שנארז או נבדק מול הספרייה."""

    def test_unsorted_is_not_packaged(self):
        roots = SY.packaged_roots()
        self.assertFalse(SY.is_packaged(f"{SY.ERUKH_UNSORTED}/חסידות/X.txt", roots))
        self.assertTrue(SY.is_packaged(f"{SY.ERUKH}/חסידות/X.txt", roots))
        self.assertFalse(SY.is_packaged(f"{SY.EXTRA}/חסידות/X.txt", roots))
        for r in roots:
            self.assertTrue(r.endswith("/ספרים/אוצריא/"), r)

    def test_validator_prefixes_end_in_otzaria(self):
        sys.path.insert(0, os.path.join(SY.REPO, ".github", "scripts"))
        import validate_fordb_book_names as V  # noqa: E402
        for p in V.PACKAGED_PREFIXES:
            self.assertTrue(p.endswith("/ספרים/אוצריא/"), p)
        self.assertFalse(any(f"{SY.ERUKH_UNSORTED}/x.txt".startswith(p) for p in V.PACKAGED_PREFIXES))


class StateTest(unittest.TestCase):
    def test_diff_books_by_filename(self):
        st = {"books": {"a": {"dicta": {"displayName": "א", "OCRDataURL": "u1"}, "repo": {"status": "raw"}},
                        "gone": {"dicta": {"displayName": "ג"}, "repo": {"status": "raw"}}}}
        books = [{"fileName": "a", "displayName": "א חדש", "OCRDataURL": "u2"}, {"fileName": "b", "displayName": "ב"},
                 {"fileName": "b", "displayName": "ב"}]
        d = SY.diff_books(st, books)
        self.assertEqual(d["new"], ["b"])
        self.assertEqual(d["removed"], ["gone"])
        self.assertEqual(d["duplicates"], ["b"])
        self.assertEqual({(c["field"]) for c in d["changes"]}, {"displayName", "OCRDataURL"})

    def test_zip_signature_and_ranges(self):
        data = book_zip([BODY, BODY + " נוסף", BODY])
        remote, pages = SY.zip_signature(data)
        self.assertEqual(remote["n_pages"], 3)
        self.assertEqual(remote["pages"], ["2-4"])
        self.assertEqual(SY.expand(["2-4", 7]), {2, 3, 4, 7})
        self.assertEqual(SY.ranges([1, 2, 3, 5]), ["1-3", 5])

    def test_missing_pages(self):
        other = "ויהי בימי שפוט השופטים ויהי רעב בארץ וילך איש מבית לחם יהודה לגור בשדי מואב הוא ואשתו ושני בניו"
        data = book_zip([BODY, other, BODY.replace("אדם", "איש")])
        text = BODY + "\n" + BODY.replace("אדם", "איש")
        self.assertEqual(SY.missing_pages(data, text), [3])

    def test_title_key(self):
        self.assertEqual(SY.title_key('צל"ח ביצה'), SY.title_key("צלח ביצה"))
        self.assertEqual(SY.title_key("שׁוּ״ת  הרי״ף"), SY.title_key("שות הריף"))


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "ForDB"))
        meta = [{"title": "קיים", "author": "רבי יוסף קארו"}]
        with open(os.path.join(self.d, "metadata.json"), "w", encoding="utf-8") as f:
            f.write("[\n" + ",\n".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")) for m in meta) + "\n]\n")
        for rel in ("ForDB/all_metadata.json", "all_metadata_with_file_paths.json"):
            with open(os.path.join(self.d, rel), "w", encoding="utf-8") as f:
                f.write(json.dumps([{"title": "קיים"}], ensure_ascii=False, indent=2) + "\n")
        with open(os.path.join(self.d, "ForDB/book_info.csv"), "w", encoding="utf-8", newline="") as f:
            f.write('bookName,authorName,generationName,subGenerationName,startYear,endYear\n"קיים","רבי יוסף קארו","אחרונים","","",""\n')

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_register_formats(self):
        book = {"displayName": "ספר חדש", "author": "יוסף קארו", "category": "הלכה ומנהג", "subcategory": "ראשונים",
                "printYear": "1925-1931", "fileName": "new"}
        touched = SY.register_packaged(book, "הלכה/ראשונים/ספר חדש.txt", repo=self.d)
        self.assertEqual(len(touched), 4)
        meta = open(os.path.join(self.d, "metadata.json"), encoding="utf-8").read()
        self.assertTrue(meta.endswith("}\n]\n"))
        self.assertIn('"author":"רבי יוסף קארו"', meta)  # מחבר קנוני קיים, לא כפילות
        fp = json.load(open(os.path.join(self.d, "all_metadata_with_file_paths.json"), encoding="utf-8"))
        self.assertEqual(fp[-1]["file_path"], "הלכה\\ראשונים\\ספר חדש.txt")
        self.assertEqual(fp[-1]["pubDate"], [1925])
        rows = list(csv.reader(open(os.path.join(self.d, "ForDB/book_info.csv"), encoding="utf-8", newline="")))
        self.assertIn(["ספר חדש", "רבי יוסף קארו", "ראשונים", "", "", ""], rows)
        self.assertEqual(rows[1:], sorted(rows[1:], key=lambda r: (r[0], r[1])))
        self.assertNotIn(b"\r", open(os.path.join(self.d, "ForDB/book_info.csv"), "rb").read())
        self.assertFalse(os.path.exists(os.path.join(self.d, "ForDB/generations.csv")))
        # אידמפוטנטי
        self.assertEqual(SY.register_packaged(book, "הלכה/ראשונים/ספר חדש.txt", repo=self.d), [])

    def test_transition_projects_new_source_to_existing_legacy_without_overwriting_coauthors(self):
        info = os.path.join(self.d, "ForDB/book_info.csv")
        with open(info, "w", encoding="utf-8", newline="") as f:
            f.write('bookName,authorName,generationName,subGenerationName,startYear,endYear\n"ספר חדש","עורך","מחברי זמננו","","1900","1980"\n"ספר חדש","רבי יוסף קארו","מחברי זמננו","מחברי זמננו","1800","1888"\n')
        with open(info, "rb") as f:
            before = f.read()
        legacy = os.path.join(self.d, "ForDB/generations.csv")
        with open(legacy, "w", encoding="utf-8", newline="") as f:
            f.write("שם ספר,קבוצת דור\nספר חדש,ראשונים\n")
        SY.register_packaged({"author": "יוסף קארו", "subcategory": "ראשונים"}, "ספר חדש.txt", repo=self.d)
        with open(info, "rb") as f:
            self.assertEqual(f.read(), before)
        with open(legacy, encoding="utf-8") as f:
            self.assertIn(["ספר חדש", "מחברי זמננו"], list(csv.reader(f)))

    def test_malformed_book_info_fails_before_other_registries_are_written(self):
        paths = [os.path.join(self.d, p) for p in ("metadata.json", "ForDB/all_metadata.json", "all_metadata_with_file_paths.json")]
        before = [open(p, "rb").read() for p in paths]
        with open(os.path.join(self.d, "ForDB/book_info.csv"), "w", encoding="utf-8") as f:
            f.write('bookName,authorName,generationName,subGenerationName,startYear,endYear\n"ספר","unterminated')
        with self.assertRaises(ValueError):
            SY.register_packaged({"author": "מחבר", "subcategory": "ראשונים"}, "ספר חדש.txt", repo=self.d)
        self.assertEqual([open(p, "rb").read() for p in paths], before)

    def test_refuses_foreign_format(self):
        with open(os.path.join(self.d, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump([{"title": "קיים"}], f, indent=1)
        with self.assertRaises(ValueError):
            SY.register_packaged({"displayName": "x"}, "a/x.txt", repo=self.d)


OTHER = ("ויהי בימי שפוט השופטים ויהי רעב בארץ וילך איש מבית לחם יהודה לגור בשדי מואב הוא ואשתו ושני בניו "
         "ושם האיש אלימלך ושם אשתו נעמי ושם שני בניו מחלון וכליון אפרתים מבית לחם יהודה ויבאו שדי מואב ויהיו שם")


class ContentDupTest(unittest.TestCase):
    """כפילות תוכן גם בשם אחר — אותם ספים כמו ב־bootstrap (≥50% מהספר החדש בקובץ אחד)."""

    def index(self, items, path):
        ix = dicta_fp.FingerprintIndex(mod=1)
        for key, text in items:
            ix.add(key, dicta_fp.fingerprint(text, mod=1))
        ix.save(path)
        return dicta_fp.FingerprintIndex.load(path)

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.lib = self.index([("MoreBooks/ספרים/אוצריא/הלכה/שם אחר.txt", BODY * 3),
                               (f"{SY.ERUKH}/חסידות/ערוך.txt", OTHER * 3)], os.path.join(self.d, "lib.dat"))
        self.sef = self.index([("ספר של ספריא", "ויאמר משה אל העם זכור את היום הזה אשר יצאתם ממצרים מבית עבדים "
                                                 "כי בחזק יד הוציא יהוה אתכם מזה ולא יאכל חמץ היום אתם יצאים")],
                              os.path.join(self.d, "sef.dat"))
        self.cd = SY.ContentDup(self.lib, self.sef)

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_roundtrip(self):
        self.assertEqual(len(self.lib.books), 2)
        self.assertEqual(self.lib.header["mod"], 1)

    def test_packaged_under_another_name(self):
        r = self.cd.check(BODY)
        self.assertEqual(r["status"], SY.DUP_PKG)
        self.assertTrue(r["path"].endswith("שם אחר.txt"))

    def test_already_edited(self):
        self.assertEqual(self.cd.check(OTHER)["status"], SY.EDITED)

    def test_sefaria(self):
        r = self.cd.check("ויאמר משה אל העם זכור את היום הזה אשר יצאתם ממצרים מבית עבדים כי בחזק יד הוציא יהוה אתכם מזה")
        self.assertEqual(r["status"], SY.DUP_SEF)

    def test_partial_and_new(self):
        mixed = BODY + " " + " ".join(f"מלה{chr(0x05d0 + i % 22)}{chr(0x05d0 + i // 22 % 22)}" for i in range(60))
        self.assertEqual(self.cd.check(mixed)["status"], SY.PARTIAL)
        self.assertIsNone(self.cd.check(" ".join(f"חדש{chr(0x05d0 + i % 22)}{chr(0x05d0 + i // 22 % 22)}" for i in range(80)))["status"])


class AuthorLineTest(unittest.TestCase):
    class Fake:
        meta_authors = ({"ספר קיים": "רבי יוסף קארו"}, {"רבי יוסף קארו", "יצחק טייב"})

    def fix(self, text, title, author, head=None):
        return SY.Importer.author_line(self.Fake(), text, title, author, head=head)

    def test_title_entry_wins(self):
        self.assertEqual(self.fix("<h1>ספר קיים</h1>\nיוסף קארו\nגוף", "ספר קיים", "יוסף קארו")[0].split("\n")[1],
                         "רבי יוסף קארו")

    def test_same_person_other_spelling(self):
        self.assertEqual(self.fix("<h1>ס</h1>\nרבי יצחק טייב\nגוף", "ס", "רבי יצחק טייב")[0].split("\n")[1], "יצחק טייב")

    def test_unknown_is_reported(self):
        text, note = self.fix("<h1>ס</h1>\nפלוני\nגוף", "ס", "פלוני")
        self.assertEqual(text.split("\n")[1], "פלוני")
        self.assertIn("not in metadata.json", note)


def page_json(words, bold_first=False, para=False):
    toks = []
    for i, w in enumerate(words.split()):
        if i:
            toks.append({"str": " ", "pStr": " ", "sep": True})
        toks.append({"str": w, "pStr": w, "sep": False, "display": [{"c": w.strip(".:"), "bold": bold_first and i == 0}],
                     **({"markedParagraph": True} if para and i == 0 else {})})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p.json", json.dumps({"tokens": toks}, ensure_ascii=False))
    return buf.getvalue()


class TruncatedZipTest(unittest.TestCase):
    """zip מלא של דיקטה שחסרים בו דפים לעומת pages.json → השלמה מקובצי הדפים הבודדים."""

    def test_page_json_to_html(self):
        h = SY.page_json_to_html(json.loads(zipfile.ZipFile(io.BytesIO(page_json("סימן א. אמר רבי", True, True))).read("p.json")))
        self.assertIn('<span class="bold marked-paragraph">סימן</span>', h)
        self.assertIn("<span>א.</span>", h)  # הפיסוק שייך למילה, כמו ב־zip המלא
        self.assertEqual(dicta_fp.html_keys(h), ["סימנ", "א", "אמר", "רבי"])

    def test_missing_pages_are_fetched(self):
        data = book_zip([BODY])                      # רק דף 2
        order = ["book-002.zip", "book-003.zip"]
        got = []
        full, info = SY.complete_zip(data, order, "https://x/book",
                                     fetch=lambda url: got.append(url) or page_json(OTHER))
        self.assertEqual(info["missing"], ["book-003"])
        self.assertEqual(info["fetched"], ["book-003"])
        self.assertEqual(got, ["https://x/book/book-003.zip"])
        remote, pages = SY.zip_signature(full)
        self.assertEqual(remote["pages"], ["2-3"])

    def test_empty_zip_is_completed(self):
        full, info = SY.complete_zip(b"PK\x05\x06" + b"\0" * 18, ["b-001.zip"], "u", fetch=lambda url: page_json(BODY))
        self.assertEqual(SY.zip_signature(full)[0]["n_pages"], 1)

    def test_unavailable_page_marks_truncated(self):
        def fail(url):
            raise OSError("404")
        full, info = SY.complete_zip(book_zip([BODY]), ["book-002.zip", "book-003.zip"], "u", fetch=fail)
        self.assertEqual(info["failed"], ["book-003"])

        class Fake:
            st = {"books": {}}
            summary = __import__("collections").defaultdict(list)
            recorded = {}

            def _record(self, fn, book, remote, pagemap, repo):
                self.recorded[fn] = repo
        f = Fake()
        self.assertTrue(SY.Importer.truncated(f, "b", {}, info, {}, {}))
        self.assertEqual(f.recorded["b"]["status"], SY.PARTIAL)
        self.assertEqual(f.recorded["b"]["truncated"]["missing"], 1)


class QaFixesTest(unittest.TestCase):
    """תיקוני סקירת ה־QA (HIGH/MED)."""

    def test_reconvert_refuses_hand_edits(self):
        self.assertTrue(SY.human_edit_reasons("x", "y", [], {"pair_rejected": 1}, {}))
        self.assertTrue(SY.human_edit_reasons("x", "y", [{}, {}], {}, {"applied": 1}))
        self.assertTrue(SY.human_edit_reasons("<h1>a</h1>\n<h2>b</h2>\n<h2>c</h2>\nd", "<h1>a</h1>\nd", [], {}, {}))
        self.assertEqual(SY.human_edit_reasons("<h1>a</h1>\nd", "<h1>a</h1>\n<h2>x</h2>\nd", [{}], {}, {"applied": 1}), [])

    def fake(self, status):
        class F:
            pass
        f = F()
        f.st = {"books": {"b": {"repo": {"status": status}, "remote": {"text_sig": "s1"}},
                          "c": {"repo": {"status": "raw"}, "remote": {"text_sig": "s2"}}}}
        f.plan = {"books": {"b": {"OCRDataURL": "u"}}}
        f.summary = __import__("collections").defaultdict(list)
        f.taken = set()
        return f

    def test_stale_plan_is_skipped(self):
        f = self.fake("raw")          # כבר יובא מאז שנבנתה התכנית
        SY.Importer.do_import(f, "b", "why")
        self.assertIn("skipped (state changed since the plan)", f.summary)

    def test_same_text_sig(self):
        f = self.fake("absent")
        self.assertEqual(SY.Importer.same_text_as(f, "x", "s2"), "c")
        self.assertIsNone(SY.Importer.same_text_as(f, "c", "s2"))

    def test_books_json_sanity(self):
        self.assertTrue(SY.check_books_json({"a": 1}, 10))
        self.assertTrue(SY.check_books_json([], 1000))
        self.assertTrue(SY.check_books_json([{"fileName": "a"}], 1))
        self.assertEqual(SY.check_books_json([{"fileName": "a", "OCRDataURL": "u"}], 1), [])

    def test_removed_is_a_flag_not_a_status(self):
        st = {"books": {"a": {"dicta": {}, "repo": {"status": "edited", "removed_upstream": "2026-10-02"}}}}
        self.assertEqual(SY.diff_books(st, [])["removed"], [])

    def test_same_book_by_content(self):
        self.assertTrue(SY.same_book(BODY * 3, "\n".join((BODY * 3).split())))
        self.assertFalse(SY.same_book(BODY * 3, OTHER * 3))
        self.assertFalse(SY.same_book(None, BODY))

    def test_best_match_prefers_content_then_path(self):
        orig = SY.read_repo_text
        texts = {"extraBooks/דיקטה/א/סדר נשים/X.txt": BODY * 3, "extraBooks/דיקטה/X.txt": BODY * 2 + OTHER,
                 "extraBooks/דיקטה/ב/X.txt": OTHER * 3}
        SY.read_repo_text = texts.get
        try:
            self.assertEqual(SY.best_match(BODY * 3, list(texts), "DictaToOtzaria/ערוך/ספרים/אוצריא/א/סדר נשים/X.txt"),
                             "extraBooks/דיקטה/א/סדר נשים/X.txt")
            self.assertIsNone(SY.best_match(BODY * 3, ["extraBooks/דיקטה/ב/X.txt"], "x/X.txt"))
        finally:
            SY.read_repo_text = orig

    def test_large_block_deletion_is_exact(self):
        # בלי diff -d ה־diff של macOS "מוותר" ומדווח מחיקה ענקית (בית שערים: 308K במקום 41K)
        a = [f"w{i}" for i in range(60000)]
        b = a[:10000] + a[30000:]
        b[35000] = "x"
        c, _ = dicta_replay.classify(dicta_replay.opcodes(a, b), a, b)
        self.assertEqual(c["del_words"], 20000)
        self.assertEqual(c["subst"], 1)

    def test_slot_by_location(self):
        self.assertEqual(SY.slot_of(f"{SY.ERUKH}/x/a.txt"), "edited")
        self.assertEqual(SY.slot_of(f"{SY.ERUKH_UNSORTED}/x/a.txt"), "unsorted")
        self.assertEqual(SY.slot_of(f"{SY.RAW}/x/a.txt"), "raw")
        self.assertEqual(SY.slot_of(f"{SY.EXTRA}/x/a.txt"), "extra")

    def test_best_match_raw_prefers_raw_copy(self):
        orig = SY.read_repo_text
        texts = {f"{SY.ERUKH}/ש/X.txt": BODY * 3, f"{SY.EXTRA}/ש/X.txt": BODY * 3}
        SY.read_repo_text = texts.get
        try:
            self.assertEqual(SY.best_match(BODY * 3, list(texts), f"{SY.RAW}/ש/X.txt"), f"{SY.EXTRA}/ש/X.txt")
            self.assertEqual(SY.best_match(BODY * 3, list(texts), f"{SY.ERUKH}/old/X.txt", prefer_edited=True),
                             f"{SY.ERUKH}/ש/X.txt")
        finally:
            SY.read_repo_text = orig

    def test_systemic_failure(self):
        class F:
            attempted, failed = 10, 1
        self.assertFalse(SY.Importer.systemic_failure(F()))
        F.failed = 6
        self.assertTrue(SY.Importer.systemic_failure(F()))

    def test_sanitize_curly_quotes(self):
        self.assertEqual(SY.sanitize_filename("צל\u201cח \u2018ביצה\u2019"), "צלח 'ביצה'")

    def test_new_author_without_honorific(self):
        self.assertEqual(SY.canonical_author("רבי פלוני אלמוני", {"אחר"}), "פלוני אלמוני")
        self.assertEqual(SY.canonical_author("פלוני אלמוני", {"רבי פלוני אלמוני"}), "רבי פלוני אלמוני")

    def test_atomic_write(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.json")
        SY.write_atomic(p, "abc")
        self.assertEqual(open(p, encoding="utf-8").read(), "abc")
        self.assertEqual(os.listdir(d), ["x.json"])
        shutil.rmtree(d)


class LinksGuardTest(unittest.TestCase):
    def test_existing_links_source_is_flagged(self):
        src, _tgt = SY.links_index()
        if not src:
            self.skipTest("no links roots in this checkout")
        name = sorted(src)[0]
        row = SY.links_guard([f"{SY.ERUKH}/x/{name}.txt"])[0]
        self.assertTrue(row["links_source"])
        self.assertTrue(row["packaged"])


if __name__ == "__main__":
    unittest.main()
