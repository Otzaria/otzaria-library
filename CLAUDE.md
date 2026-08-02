# otzaria-library — מה באמת נכנס לשחרור

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

מוגדר ב־[manual_links_packaging.py:33-47](manual_links_packaging.py#L33-L47). כל שורש
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
wikiJewishBooksToOtzaria/ספרים/אוצריא
wikisourceToOtzaria/ספרים/אוצריא
ToratEmetToOtzaria/ספרים/אוצריא
pninimToOtzaria/ספרים/אוצריא
National-LibraryToOtzaria/ספרים/אוצריא
```

אותה רשימה משוכפלת כ־`PACKAGED_PREFIXES` ב־[validate_fordb_book_names.py:135](.github/scripts/validate_fordb_book_names.py#L135)
(שם היא כוללת גם את `DictaToOtzaria/לא ערוך/`, שנכנס רק ל־zip הדיקטה). **אם משנים
אחת — צריך לעדכן את השנייה.**

### מה *לא* נארז

- `extraBooks/`, `KSK/`, `docxToOtzaria/`, `MoreBooks/ספרים/` שאינו תחת `אוצריא/`
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
  pninim / Ben-Yehuda / wikisource / tashma / wikiJewishBooks / National-Library):
  הקטגוריה נגזרת מ**נתיב התיקייה הפיזי בתוך `BOOK_ROOTS`**. מזיזים את הקובץ ב־git.
  `ForDB/book_moves.csv` **לא** מיועד לספרים אלה.
- **ספר של ספריא** (`source.name='Sefaria'`): אין קובץ מקומי, הוא נוצר בזמן הבנייה
  מה־API. מזיזים רק דרך `ForDB/book_moves.csv`. הצרכן הוא
  `SeforimLibrary/generator/sefariasqlite/.../RenameCategoriesPostProcess.kt`;
  ההתאמה מדויקת בבתים (שימו לב לגרשיים `״` U+05F4 מול `"`).

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
