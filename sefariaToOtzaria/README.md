# סקריפטי ספריא עברו ל־book-sources

כל `סקריפטים/` הועתק, זהה בבתים, ל־[Otzaria/book-sources](https://github.com/Otzaria/book-sources/tree/main/sefariaToOtzaria/סקריפטים)
(מקומיט `0deef2fa43a4bcecd0024085ff2f209b67b9dc69`). ראו [פרטי ההעברה והאימות](https://github.com/Otzaria/book-sources/blob/main/docs/MIGRATION_SEFARIA.md).

מכאן נמחקו מה שאף קוד בספרייה אינו משתמש בו: הייבוא מה־API (`main.py`, `new_book.py`,
`main_old.py`, `old_toc.py` והמצב שלהם: `toc.json`, `old.json`, `not_in_*.json`,
`not_downloaded.json`, `eroor/`), כלי עזר חד־פעמיים ו־`old/`. מריצים אותם מ־book-sources.

**נשארים כאן, כי קוד של הספרייה משתמש בהם:**

- `סקריפטים/from_export/`, `סקריפטים/otzaria/` — `.github/workflows/sefaria-export.yml` מריץ אותם (`export.py` מייבא את `otzaria/`). העותק כאן הוא זה שרץ; תיקונים נעשים כאן.
- `סקריפטים/test_get_from_export.py` — הבדיקה של `otzaria/` ב־`python-tests.yml`.
- `סקריפטים/books_metadata.json`, `סקריפטים/folder_metadata.json` — הפלט של `from_export`.
- `סקריפטים/metadata.json` — `metadata/metadata_import.py` קורא אותו.

ההעברה אינה נוגעת בשורשי האריזה `sefaria_export/` ו־`sefaria_api/` שב־`BOOK_ROOTS`.
