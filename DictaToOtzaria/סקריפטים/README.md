# סקריפטי דיקטה — הועברו ל־book-sources

הקוד של ייבוא דיקטה, הבדיקות, כלי העריכה (`עריכת ספרים/`) ונתוני הקלט הקבועים
(`sefaria_fp.dat`, `dicta_placement_table.json`, `dicta_word_freq.tsv.gz`) הועברו
למאגר הפרטי [Otzaria/book-sources](https://github.com/Otzaria/book-sources), לתיקייה
`DictaToOtzaria/סקריפטים/`, בהעתקה זהה בבתים מקומיט
`0deef2fa43a4bcecd0024085ff2f209b67b9dc69` של המאגר הזה. התיעוד המלא (`README.md`) ופרטי ההעברה
(`docs/MIGRATION_DICTA.md`) נמצאים שם.

## מה נשאר כאן

| קובץ | למה כאן |
| --- | --- |
| `dicta_state.json` | **מקור האמת** של הייבוא: רשומה לכל `fileName` של דיקטה. הזרימה החודשית מעדכנת אותו ומחייבת אותו במאגר הזה, יחד עם הספרים שהיא כותבת. גם `metadata/metadata_import.py` קורא אותו. |
| `dicta_pages.json` | hash של אותיות כל דף, לכל ספר. מתעדכן ומחויב באותה ריצה. |

אין להעביר או לשנות את שם הקבצים: הזרימה ו־`dicta_sync.py` מחפשים אותם בדיוק בנתיב הזה.

## הזרימה החודשית

`.github/workflows/dicta-import.yml` נשאר במאגר הזה. בכל job הוא משכפל את
`DictaToOtzaria/סקריפטים/` מ־book-sources (ענף `main`, עם `PIPELINE_TOKEN`) אל `$RUNNER_TEMP`,
ומריץ אותו עם `REPO_ROOT` = הצ'ק־אאוט של הספרייה. הספרים, המרשמים וקובצי המצב נכתבים ומחויבים
כאן כמו קודם; `extra_books` לא השתנה.

## הרצה מקומית

```bash
git clone https://github.com/Otzaria/book-sources ../book-sources   # פרטי
REPO_ROOT="$PWD" python3 "../book-sources/DictaToOtzaria/סקריפטים/dicta_sync.py" report
REPO_ROOT="$PWD" python3 -m unittest discover -s "../book-sources/DictaToOtzaria/סקריפטים/tests"
```
