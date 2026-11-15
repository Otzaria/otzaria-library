# כלי אורייתא עברו ל־book-sources

הממיר (`orayta_convert.py`), מפריד המילים של חק לישראל (`split_hok_targum.py`), הבדיקות שלהם, קובצי ה־OBK הגולמיים (`books/`), `list.csv` ו־`שונות/` נמצאים כעת ב־[Otzaria/book-sources](https://github.com/Otzaria/book-sources/tree/main/OraytaToOtzaria/סקריפטים).

הריצו את הכלים מתוך book-sources עם `REPO_ROOT` המצביע ל־checkout של **otzaria-library**; ראו [הוראות ההרצה וההגירה](https://github.com/Otzaria/book-sources/blob/main/docs/MIGRATION_ORAYTA.md).

`ספרים/` ו־`post_convert_fixes.tsv` נשארים כאן. הממיר קורא את התיקונים מכאן (`post_convert_fixes.py` שבשורש ו־`post_convert_fixes.tsv` שבתיקייה הזו), ו־`split_hok_targum.py` מתקן את ספרי חק לישראל שכאן. אין להריץ אותם כש־`REPO_ROOT` מצביע לריפו המקורות.
