<div dir="rtl">

# מטא-דאטה של ספר

קובץ הספר נושא רק את שם התצוגה (`<h1>`) ואת מבנהו. **מחבר, תיאור, תקופה, מקום ותאריך
דפוס, סדר, דור — כל אלה חיים מחוץ לקובץ**, ומתחברים לספר לפי **התאמת שם**. לכן השם
הוא המפתח, וכל סטייה בו מנתקת את החיבור.

מקורות: `all_metadata.json` ו-`ForDB/` ב-repo הספרייה,
`sefariaToOtzaria/סקריפטים/otzaria/{utils,get_from_export}.py`,
`.github/scripts/validate_fordb_book_names.py`, ו-`lib/migration/generator/generator.dart`
ב-repo התוכנה.

## 1. מי מחזיק מה

| קובץ | תפקיד |
|---|---|
| `all_metadata_with_file_paths.json` | הקנוני ב-repo — כל הרשומות + נתיב הקובץ בפועל; משמש את ה-CI. |
| `all_metadata.json` (שורש) | אותו תוכן בלי נתיבי קבצים. |
| `ForDB/all_metadata.json` | העותק שנצרך בבנייה (`SeedAllMetadataPostProcess`). |
| `ForDB/book_renames.csv` | `שם ישן,שם חדש` — שינוי שם ספר. |
| `ForDB/book_moves.csv` | `name,Source path,Destination path` — **רק לספרי ספריא**. |
| `ForDB/category_renames.csv` | `שם ישן,שם חדש` לקטגוריות. |
| `ForDB/category_moves.csv` | `Source path,Destination parent path`. |
| `ForDB/generations.csv` | `שם ספר,קבוצת דור`. |
| `ForDB/sefaria_metadata_changes.csv` | דריסת תיאור/מחבר של ספר ספריא. |
| `ForDB/sefaria_category_changes.csv` | דריסת תיאורי קטגוריות של ספריא. |
| `SourcesBooks.csv` | אינוונטר: `שם הקובץ,נתיב הקובץ,תיקיית המקור,מספר שורות`. |
| `<Source>/otzaria_metadata.json` | מטא-דאטה מקומית למקור (למשל `National-LibraryToOtzaria`). |

## 2. שדות `all_metadata.json`

רשומה לספר (כ-7,400 רשומות; כ-5,900 מהן עם שדות ההרחבה).

| שדה | משמעות |
|---|---|
| `title` | **מפתח ההתאמה** — שם הספר. |
| `enTitle`, `original_title` | שם אנגלי / שם המקור בייצוא. |
| `authors`, `heAuthors` | מערכי מחברים. |
| `heDesc`, `heShortDesc`, `heDescNew` | תיאור מלא/קצר; `heDescNew` = נוסח מעודכן. |
| `enDesc`, `enShortDesc` | מקבילים באנגלית. |
| `categories`, `heCategories` | שרשרת קטגוריות מהמקור (אינה מחליפה את נתיב התיקייה). |
| `era`, `heEra` | תקופה — תנאים/אמוראים/גאונים/ראשונים/אחרונים/מחברי זמננו (מיפוי `era_dict` בסקריפט ספריא). |
| `pubDate`, `pubDateHeb`, `pubDateStringHe/En` | שנת דפוס: מספר, עברי, מחרוזת תצוגה. |
| `compDate`, `compDateHeb`, `compDateStringHe/En` | שנת חיבור. |
| `pubPlace`, `compPlace`, `pubPlaceStringHe/En`, `compPlaceStringHe/En` | מקומות. |
| `publisher` | מו"ל; `sefaria` לרשומות ספריא. |
| `series`, `heSeries`, `series-index` | סדרה ומיקום בה (`collectiveTitle` בספריא). |
| `extraTitlesHe`, `extraTitlesEn` | שמות נוספים — מזינים חיפוש וזיהוי הפניות. |
| `language` | לרוב `he`. |
| `order` | סדר בתוך הקטגוריה; ריק → 999. |
| `Sourcefolder` | תיקיית המקור (`sefaria`, `Dicta`, `MoreBooks`…). |

## 3. השם — הכלל שקובע הכול

**זהות הספר נגזרת משם הקובץ**, לא מה-`<h1>` (`generator.dart`:
`path.basenameWithoutExtension`). שם הקובץ עצמו נוצר בסקריפטים דרך `sanitize_filename`
(`sefariaToOtzaria/סקריפטים/otzaria/utils.py`; משוכפל ב-`validate_fordb_book_names.py`):

```python
filename = re.sub(r'[֑-ׇ]', '', filename)   # ניקוד וטעמים
filename = re.sub(r'[\\/:*"״?<>|]', "", filename)     # תווים אסורים בשם קובץ
filename = filename.replace("_", " ").replace("''", "").replace("'", "")
filename.strip()
```

לכן `<h1>שו"ת מהרש"ם חלק ג</h1>` יושב בקובץ `שות מהרשם חלק ג.txt` — **וזה תקין**.
ה-`<h1>` נועד לתצוגה ויכול לשאת גרשיים, נקודתיים וכל תו שאסור בשם קובץ.

### מלכודת הגרשיים בהפניות

הכתיב שבו מפנים לספר (`path_2` בקישורים, `book://` בטקסט) אינו נגזר משם הקובץ בדיסק:

- **ספר אוצריא** עובר בייבוא גם `normalizeBookTitle` שמאחד `"`, `''`, `׳׳` לגרשיים
  עבריים `״` (U+05F4).
- **ספר ספריא** שומר את כותרת ספריא הגולמית — לפעמים `"` ASCII, לפעמים `״`. אין כלל
  ואין מפת נרמול בקוד.

**לכן:** אל תסיקו שם ספר מהקובץ. שאלו בהתאמה מדויקת — `scripts/query_db.py book "<שם>"`
— ורק אז כתבו אותו.

## 4. קטגוריה ומיקום

- **הקטגוריה = נתיב התיקייה בפועל** תחת `…/ספרים/אוצריא/`.
- **ספר של המאגר** (Dicta, MoreBooks, OnYourWay, Orayta, ToratEmet, pninim, Ben-Yehuda,
  wikisource, tashma, wikiJewishBooks, National-Library): להעביר את **הקובץ ב-git**.
  `ForDB/book_moves.csv` אינו מיועד לספרים אלה.
- **ספר של ספריא** (`source.name='Sefaria'`): אין קובץ מקומי — הוא נוצר בבנייה מה-API.
  להעביר **רק** דרך `ForDB/book_moves.csv`, בהתאמה מדויקת בבתים (`״` U+05F4 מול `"`).
- שינוי שם/מיקום קטגוריה — `category_renames.csv` / `category_moves.csv`.
- סדר בתוך קטגוריה — `order`; ברירת מחדל 999 (בסוף, לפי א-ב).
- שני קבצים שונים באותו שם מנוקה מתנגשים (אותו `title`) — `check_duplicates.py` מאתר.

## 5. דורות

`ForDB/generations.csv` = `שם ספר,קבוצת דור` (ראשונים/אחרונים/…). משמש לסינון ותצוגה
(`lib/data/cache/generation_cache.dart`). השם חייב להתאים **בדיוק** לשם הספר במאגר,
אחרת השורה יתומה וה-CI מסיר/מפיל אותה.

## 6. מלכודות שנתפסות ב-CI

`.github/workflows/validate-fordb-book-names.yml` → `.github/scripts/validate_fordb_book_names.py`:

| בעיה | מה קורה |
|---|---|
| שם ב-`generations.csv` / `book_moves.csv` שאינו קיים | שורה יתומה → מוסרת ב-`--fix`. |
| **דליפת מקור**: רשומת ספר ספריא עם `Sourcefolder` שאינו `sefaria` | שלב ה-seed דורס את `book.sourceId`, ו"אודות הספר" מציג מקור שגוי. |
| שני קבצים באותו שם מנוקה | התנגשות `title` — שגיאה. |
| `book_renames.csv` שהמקור שלו לא קיים | שינוי-שם יתום. |

```bash
python .github/scripts/validate_fordb_book_names.py          # בדיקה
python .github/scripts/validate_fordb_book_names.py --fix    # רק תיקונים דטרמיניסטיים
```

## 7. תקלה היסטורית שכדאי להכיר

ב-`db_version=19` (אוגוסט 2026) 26 ספרים נחתו בקטגוריות זרות, **אף שקובצי המקור היו
תקינים**: תיקיות שנוצרו עבור יעדי `book_moves.csv` חטפו מזהי קטגוריה שמורים,
וה-`INSERT OR IGNORE` נבלע בשקט. סימן ההיכר: הקטגוריה ה"נכונה" פשוט אינה קיימת,
והמזהה שלה תפוס. תוקן ב-SeforimLibrary. מסקנה: כשמדווחים על ספר "במקום הלא נכון" —
בדקו גם את הנתיב ב-repo וגם את הקטגוריה בפועל (`scripts/query_db.py book "<שם>"`).

## 8. רישיון — חלק מהמטא-דאטה

לכל מקור רישיון משלו (ספריא GPL-3.0, דיקטה CC BY-SA 4.0, תורת אמת CC BY-NC-SA 2.5,
פנינים GNU FDL 1.3, תא שמע כל הזכויות שמורות, אוצר הספרים היהודי השיתופי בהרשאה
מפורשת בלבד, והתוכן המקורי של הפרויקט תחת Personal Use License 1.0). מוסיפים ספר
ממקור חדש — ודאו שהרישיון מתועד ב-`README.md` של הספרייה.

</div>
