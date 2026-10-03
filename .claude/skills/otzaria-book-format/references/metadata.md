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
| `ForDB/all_metadata.json` | העותק שנצרך בבנייה (`SeedAllMetadataPostProcess`) — **רק** `pubDate` / `pubPlaceStringHe`; אין בו שדות תיאור. |
| `ForDB/book_renames.csv` | `שם ישן,שם חדש` — שינוי שם ספר. |
| `ForDB/book_moves.csv` | `name,Source path,Destination path` — **רק לספרי ספריא**. |
| `ForDB/category_renames.csv` | `שם ישן,שם חדש` לקטגוריות. |
| `ForDB/category_moves.csv` | `Source path,Destination parent path`. |
| `ForDB/book_info.csv` | `bookName,authorName,generationName,subGenerationName,startYear,endYear`. |
| `ForDB/sefaria_metadata_changes.csv` | **הדרך היחידה של תיאור ספר ל־DB — לכל ספר**, גם ממקורות אוצריא (למרות השם). ר' "תיאור הספר" בסעיף 2. |
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
| `heDesc`, `heShortDesc`, `heDescNew` | תיאור מלא/קצר — **לא לכתוב כאן**: הבנייה לא קוראת תיאור מקובץ זה. תיאור נכתב ב־`ForDB/sefaria_metadata_changes.csv` (ר' למטה). |
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

### תיאור הספר — רק ב־`ForDB/sefaria_metadata_changes.csv`

**לא** ב־`metadata.json` שבשורש ולא ב־`all_metadata.json` / `ForDB/all_metadata.json`. המחולל
(SeforimLibrary) קורא את `metadata.json` דרך המחלקה `BookMetadata`, שאין בה שדה `heDesc` —
`heDesc` שנכתב שם נזרק בשקט ולא מגיע ל־`seforim.db` (`heShortDesc` שם אמנם עובד, אבל שומרים
מקור אמת אחד). ב־`ForDB/all_metadata.json` אין שדות תיאור בכלל (הוא מזין רק `pubDate` /
`pubPlaceStringHe`). הדרך היחידה של תיאור ל־DB — **לכל הספרים**, גם ממקורות אוצריא למרות שם
הקובץ — היא `ForDB/sefaria_metadata_changes.csv`, שנצרך ב־`SeedAllMetadataPostProcess.kt`.

- **עמודות** (שורת כותרת): `categoryPath,title,author,heShortDesc,heDesc,heDescNew`. הצרכן
  קורא **לפי מיקום**: עמודה 2 `title` (מפתח ההתאמה), עמודה 4 `heShortDesc` → `book.heShortDesc`
  (בדיאלוג פרטי הספר), עמודה 6 `heDescNew` → `book.heDesc` (התיאור הארוך, בטולטיפ של
  הספרייה). עמודה 5 `heDesc` = הטקסט המקורי של ספריא, לעיון בלבד — **ריקה** בספרים שלנו.
  `categoryPath` ו־`author` אינפורמטיביות (לא נקראות) — ממלאים אותן לקורא האנושי: נתיב
  הקטגוריה (נתיב התיקייה תחת `אוצריא/`) והמחבר.
- **`title` = שם הספר בדיוק כפי שיהיה ב־`seforim.db`**: שם קובץ ה־`.txt` בלי סיומת, אחרי
  `normalizeHebrewLabel` של המחולל: trim; `“ ”` → `"`, `‘ ’` → `'`; ואז `"` → `״` (U+05F4),
  `''` → `״`, `׳׳` → `״`, backtick → `׳` (U+05F3); כיווץ רווחים. גרש ASCII בודד `'` **לא**
  מומר. מעבר לזה — בלי ניקוי. אי־התאמה אינה שגיאה: השורה פשוט לא מתאימה לשום ספר, בשקט
  (WARN בבנייה בלבד). שני ספרים באותו שם ב־DB — השורה מדולגת.
- **שורה אחת לכל שם** (שם כפול — השורה האחרונה גוברת). תא ריק = "השאר את הערך הקיים" — אי
  אפשר לרוקן שדה דרך ה־CSV.
- **פורמט:** UTF-8 בלי BOM, סופי שורה LF, **כל** שדה במירכאות (`csv.QUOTE_ALL`). עורכים רק
  ב־`csv` של Python — לא ביד ולא ב־`sed`; כתיבה מחדש כזו עושה round-trip זהה בית־בבית:

  ```python
  import csv
  p = 'ForDB/sefaria_metadata_changes.csv'
  with open(p, encoding='utf-8', newline='') as f:
      rows = list(csv.reader(f))
  # עדכון/הוספה: [categoryPath, title, author, heShortDesc, '', heDescNew]
  with open(p, 'w', encoding='utf-8', newline='') as f:
      csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n').writerows(rows)
  ```

  `make_metadata.py --he-short-desc … --he-desc … --desc-csv ForDB/sefaria_metadata_changes.csv`
  עושה בדיוק את זה (ולא כותב תיאור לרשומת ה־JSON).
- הוולידטור (`.github/scripts/validate_fordb_book_names.py`) בודק את עמודת `title` מול הספרייה
  הארוזה — קובץ הספר חייב להתקיים תחת שורש נארז (`BOOK_ROOTS`).

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

`ForDB/book_info.csv` = `bookName,authorName,generationName,subGenerationName,startYear,endYear` (ראשונים/אחרונים/…). משמש לסינון ותצוגה
(`lib/data/cache/generation_cache.dart`). השם חייב להתאים **בדיוק** לשם הספר במאגר,
אחרת השורה יתומה וה-CI מסיר/מפיל אותה.

## 6. מלכודות שנתפסות ב-CI

`.github/workflows/validate-fordb-book-names.yml` → `.github/scripts/validate_fordb_book_names.py`:

| בעיה | מה קורה |
|---|---|
| שם ב-`book_info.csv` / `book_moves.csv` שאינו קיים | שורה יתומה → מוסרת ב-`--fix`. |
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

### רישום מידע קנוני

`book_info.csv` מכיל שש עמודות ושורה לכל `(bookName,authorName)`. סדר קנוני: שם ספר ואז מחבר; LF וכל שדה נתון מצוטט. דורות נתמכים: תורה שבכתב, חז"ל, ראשונים, אחרונים, מחברי זמננו. שדות לא ידועים ריקים. אין להשתמש בשנות הדפוס בתור שנות חיי המחבר.

`make_metadata.py --title "שם" --author "מחבר" --generation אחרונים --book-info-csv /path/ForDB/book_info.csv` מוסיף רק זהויות חסרות ומשמר כל מחבר, דור ושנים קיימים. `--sub-generation`, `--start-year`, `--end-year` מיועדים לערכים ידועים. בשלב המעבר בלבד הכותב מעדכן גם קובץ דורות ישן קיים מתוך המידע הקנוני; אין לערוך אותו בנפרד.
