# otzaria-library — מה באמת נכנס לשחרור

**מוסיפים ספר חדש?** קראו קודם את [ADDING_BOOKS.md](ADDING_BOOKS.md) — רשימת
המלכודות שנשברות בשקט (ספר הערות נלווה, פורמט שלושת המרשמים, הוולידטורים
שקוראים git ולא את עץ העבודה).

מאגר זה מכיל הרבה יותר קבצים ממה שמגיע למשתמשים. לפני כל בדיקה או תיקון של
**מיקום ספר**, **שם ספר** או **קישורים** — ודאו קודם שהקובץ שאתם נוגעים בו הוא זה
שנארז. עותקים מקבילים באותו שם קיימים כמעט תמיד, ורובם לא נארזים.

## נכסי השחרור

הכל נבנה ב־`.github/workflows/update-library.yml` (job `package`, מצב
`links_sync_mode`):

| נכס | נבנה על ידי | מה בפנים |
| --- | --- | --- |
| `otzaria_latest.zip` | `create_release_archives.sh` → `manual_links_packaging.py package` | **הספרייה עצמה**: מיזוג `BOOK_ROOTS` לעץ אחד בשם `אוצריא/`, `links/`, `files_manifest.json`, `metadata.json`, `manual_links_sync.json`, `manual_links_lineage.json`, `packaging_toolchain.json` |
| `otzaria_dicta_latest.zip` | `create_auxiliary_archives.sh` | `DictaToOtzaria/לא ערוך/ספרים` בלבד (חומר גלם, לא הספרייה) |
| `talmud_bavli_latest.tar.zst` | `create_auxiliary_archives.sh` | קובצי ה־PDF שתחת `MoreBooks/ספרים/אוצריא/תלמוד בבלי`, משוטחים |
| `fordb_latest.zip` | `.github/workflows/update-fordb.yml` | תיקיית `ForDB/` (ה־CSV־ים) |

## הספרים: `BOOK_ROOTS`

מוגדר ב־[manual_links_packaging.py:34-50](manual_links_packaging.py#L34-L50). כל שורש
מועתק אל תוך אותו עץ יעד `אוצריא/`, לפי הסדר, עם `overwrite=True` — שורש מאוחר יותר
דורס קובץ באותו נתיב יחסי:

```
Ben-YehudaToOtzaria/ספרים/אוצריא
DictaToOtzaria/ערוך/ספרים/אוצריא
OnYourWayToOtzaria/ספרים/אוצריא
OraytaToOtzaria/ספרים/אוצריא
tashmaToOtzaria/ספרים/אוצריא
sefariaToOtzaria/sefaria_export/ספרים/אוצריא
sefariaToOtzaria/sefaria_api/ספרים/אוצריא
MoreBooks/ספרים/אוצריא
KSK/ספרים/אוצריא
wikiJewishBooksToOtzaria/ספרים/אוצריא
wikisourceToOtzaria/ספרים/אוצריא
ToratEmetToOtzaria/ספרים/אוצריא
pninimToOtzaria/ספרים/אוצריא
National-LibraryToOtzaria/ספרים/אוצריא
yam-HaHachmaToOtzaria/ספרים/אוצריא
```

אותה רשימה משוכפלת כ־`PACKAGED_PREFIXES` ב־[validate_fordb_book_names.py:186](.github/scripts/validate_fordb_book_names.py#L186)
(שם היא כוללת גם את `DictaToOtzaria/לא ערוך/`, שנכנס רק ל־zip הדיקטה). **אם משנים
אחת — צריך לעדכן את השנייה.**

יש עוד שני עותקים, בשלב ה־prepare: `folders` ב־`send_update/main.py` (יומן `עדכוני ספריה.md`)
ו־`folders` + `mapping` ב־`sync_and_merge_folders.py` (`SourcesBooks.csv`, `library_csv/` ומונה
הגרסה). מקור שחסר שם נארז כרגיל, אבל השינויים בו לא מופיעים ביומן. כך היה עם National-Library
מיוני עד אוקטובר 2026. `test_source_lists_contract.py` אוכף ששתי הרשימות שוות ל־`BOOK_ROOTS`,
חוץ משני שורשי ספריא הריקים.

### מה *לא* נארז

- `extraBooks/`, `docxToOtzaria/`, `MoreBooks/ספרים/` שאינו תחת `אוצריא/`
- `KSK/` שאינו תחת `ספרים/אוצריא/` — תיקיית הסקריפטים של קובץ שיטות קמאי
- כל `<source>/ספרים/<משהו שאינו אוצריא>/` — למשל `OraytaToOtzaria/ספרים/לא רלוונטי/`
- `DictaToOtzaria/לא ערוך/` — נכנס רק ל־`otzaria_dicta_latest.zip`, לא לספרייה
- כלי עבודה: `linker/`, `linker-eval/`, `metadata/`, `library_csv/`, `send_update/`, `סקריפטים שונות/`

## הקישורים: `links_roots`

מוגדר ב־[manual_links_sync.json](manual_links_sync.json) (`links_roots`), עם
`expected_state` של `present`/`absent` לכל שורש — סטייה מהמצב המוצהר מפילה את
האריזה. קבצים שטוחים בלבד: תת־תיקייה מתחת לשורש links היא שגיאה קשה.
כל הקבצים ממוזגים לתיקייה `links/` אחת ב־zip, וללא דריסה (התנגשות = שגיאה).

## איפה מתקנים מיקום של ספר

תלוי במקור הספר (עמודת `source` ב־`seforim.db`):

- **ספר של המאגר הזה** (Dicta / MoreBooks / OnYourWay / Orayta / ToratEmet /
  pninim / Ben-Yehuda / wikisource / tashma / wikiJewishBooks / National-Library /
  yam-HaHachma / KSK):
  הקטגוריה נגזרת מ**נתיב התיקייה הפיזי בתוך `BOOK_ROOTS`**. מזיזים את הקובץ ב־git.
  `ForDB/book_moves.csv` **לא** מיועד לספרים אלה.
- **ספר של ספריא** (`source.name='Sefaria'`): אין קובץ מקומי, הוא נוצר בזמן הבנייה
  מה־API. מזיזים רק דרך `ForDB/book_moves.csv`. הצרכן הוא
  `SeforimLibrary/generator/sefariasqlite/.../RenameCategoriesPostProcess.kt`;
  ההתאמה מדויקת בבתים (שימו לב לגרשיים `״` U+05F4 מול `"`).

## איפה מתקנים שם של מחבר

`author.name` הוא המפתח הייחודי — שתי צורות כתיב של אותו אדם הן שני מחברים, ומאז
שנוסף חיפוש לפי מחבר זה אומר שחצי מספריו לא נמצאים. התיקון תלוי במקור:

- **ספר של המאגר הזה**: השם מגיע משדה `author` (או `authors[]`) ב־[metadata.json](metadata.json)
  **שבשורש המאגר** — לא מ־`heAuthors` ב־`ForDB/all_metadata.json`, ש*אינו* נצרך
  בבניית טבלת המחברים. עורכים את `metadata.json`; את `all_metadata.json` מעדכנים
  במקביל רק לשם עקביות — אבל **לא רק** לשם עקביות: קיים נוהג של סנכרון ידני
  `heAuthors` → `metadata.json` (ר' `a5a627d6`, יולי 2026), שמסיר תארי כבוד בדרך.
  סנכרון כזה בעתיד יוריד את ה־"רבי" מ־`רבי יעקב בן יעקב משה לורברבוים מליסא`
  ויפצל אותו שוב מצד ספריא, ששם ה־CSV כן שומר אותו. לפני סנכרון כזה — לבדוק
  מול `ForDB/sefaria_author_changes.csv`.
- **ספר של ספריא**: השם מגיע מה־schema של ספריא, ואי אפשר לערוך אותו כאן. מוסיפים
  שורה ל־[ForDB/sefaria_author_changes.csv](ForDB/sefaria_author_changes.csv)
  (`שם בספריא,שם קנוני`), שנצרך ב־`SefariaDirectImporter` **בזמן הייבוא** — לפני
  ש־`upsertAuthor` מקצה מזהה, כדי שלא ייווצרו שתי שורות שצריך למזג אחר כך.

ניקוד, טעמים, תווי BIDI בלתי־נראים ורווחים כפולים **אינם** צריכים שורה ב־CSV:
`normalizeAuthorName` ב־SeforimLibrary מסיר אותם משני הצדדים. גרשיים וגרש נשמרים.
ה־CSV שמור למקרים שרק אדם יכול להכריע בהם — ושם צריך זהירות: `אברהם שמואל בנימין
סופר` ו־`סופר, שמעון בן אברהם שמואל בנימין` דומים הרבה יותר זה לזה מאשר שתי
הצורות של יעקב מליסא, והם אב ובן.

## שינוי שם של קובץ ספר קיים

שם ספר אוצריא ב־DB הוא שם הקובץ, ולכן שינוי שם מנתק אותו מכל שורה שמזהה אותו לפי
שם. ב־push ל־main ה־CI (`validate-fordb-book-names.yml`, [fordb_book_renames.py](.github/scripts/fordb_book_renames.py))
עוקב אחרי זה בעצמו: לכל קובץ `.txt` נארז ששונה בשמו מאז הריצה המוצלחת האחרונה, הוא
מחליף את השם הישן בחדש ב־`book_info.csv` (כל השורות של הספר), `book_moves.csv`,
`sefaria_metadata_changes.csv`, `ForDB/all_metadata.json`, `metadata.json`,
`all_metadata_with_file_paths.json`, ובשורשי ה־links הנארזים (שם קובץ ה־`_links.json`,
`path_2`, ו־`heRef_2` כשהוא מתחיל בשם). שינוי שמשנה רק גרשיים (`הבח` → `הב”ח`) מתוקן
באיות ה־DB.

מה הוא **לא** עושה: פיצול ספר לכמה קבצים, או העברה ל־`extraBooks`, אינם שינוי שם, ולכן
השורות נמחקות כיתומות כמו קודם. שם ישן שהוביל לשני יעדים, שמופיע ב־`book_renames.csv`,
או שקובץ הקישורים החדש שלו כבר קיים, **אינו מיושר וגם אינו נמחק**, והריצה נכשלת.
הקישורים האוטומטיים אינם שמורים במאגר: הם נוצרים מחדש ב־LinkerToOtzaria בכל בנייה
(תיקיות `linker_links/` הישנות נמחקו בספטמבר 2026, ואין לבדוק או לשחזר אותן).

## בדיקה מהירה: עץ הזיפ מול ה־DB הבנוי

הקטגוריה שמופיעה באפליקציה נקבעת ב־SeforimLibrary, לא כאן. כשמדווחים על ספר
"במקום הלא נכון", בדקו את שניהם — הנתיב במאגר יכול להיות תקין וה־DB עדיין שגוי:

```bash
python3 - <<'PY'
import sqlite3, os
db = os.path.expanduser('~/Downloads/seforim.db')   # DB בנוי כלשהו
c = sqlite3.connect(db)
cats = {r[0]: (r[1], r[2]) for r in c.execute("select id,parentId,title from category")}
def path(cid):
    p = []
    while cid:
        par, t = cats[cid]; p.append(t); cid = par
    return "/".join(reversed(p))
for t, cid, s in c.execute(
        "select b.title,b.categoryId,s.name from book b left join source s on s.id=b.sourceId "
        "where b.title like ? order by b.title", ('%אור הישר%',)):
    print(f"{t}\t| {path(cid)}\t| {s}")
PY
```

### תקלה ידועה: ספרים שנופלים לקטגוריה זרה לגמרי

ב־`db_version=19` (אוגוסט 2026) 26 ספרים נחתו בתיקיות לא קשורות — למשל
`אור הישר על נדה` תחת `מחשבת ישראל/אחרונים/רמחל`, `אור הישר/סדר נזיקין` תחת
`מורה נבוכים`, `אור הישר/מסכתות קטנות` תחת `תנא דבי אליהו`, ושני ספרי
`אודות התוכנה` תחת `שות מהרשם`. **קובצי המקור כאן היו תקינים.**

הסיבה: התיקיות שנוצרות אוטומטית עבור יעדי `book_moves.csv` נכתבות עם rowid
משתמע, בעוד שלב אוצריא מקצה מזהי קטגוריה מ־`InMemoryIdAllocator` מתמיד. מאחר ש־
`renameCategories` רץ כעת *לפני* `appendOtzaria`, התיקיות החדשות חטפו את המזהים
השמורים, וה־`INSERT OR IGNORE` של שלב אוצריא נבלע בשקט — בעוד הספרים עדיין נכתבו
עם אותו `categoryId`. תוקן ב־SeforimLibrary (`ensureCounterAtLeast(CATEGORY, …)`
ב־`GenerateLines.kt` + אימות־אחרי־הכנסה ב־`IdAllocatorBindings.upsertCategory`).
הסימן המזהה: הקטגוריה ה"נכונה" פשוט **לא קיימת** ב־DB, והמזהה שלה תפוס בידי
תיקייה שנוצרה מ־`book_moves.csv`.
