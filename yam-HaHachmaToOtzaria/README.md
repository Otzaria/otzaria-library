<div dir="rtl">

# ים החכמה → אוצריא

<img src="logo.png" alt="ים החכמה" width="120" />

ספרים ממאגר הספרים התורני **["ים החכמה"](https://github.com/torahtyh/yam-HaHachma)**.

## הרישיון ומה הוא מחייב אותנו

נוסח מלא: [LICENSE-yam-HaHachma.md](LICENSE-yam-HaHachma.md). העתקה למאגרים
תורניים **חינמיים** מותרת בלי רשות מראש, בכפוף לארבעה תנאים:

| התנאי | איפה אנחנו עומדים בו |
| --- | --- |
| קרדיט למאגר + קישור בכל ספר שהועתק — והרישיון מוסיף ש**אין צורך** לקרדיט בגוף הספר | סעיף "ים החכמה" ב-[README.md](../README.md) הראשי, ומסך "אודות הספר" באפליקציה. אין `BookSourceBanner` — במכוון |
| שם המאגר והלוגו בקטגוריה שבה מוצגים הספרים | `book_source_dialog.dart` ו-`about_settings_data.dart` ב-repo התוכנה; הלוגו נארז כ-`assets/logo_books/yam_hahachma_logo.png` |
| להעתיק את **כל** ספרי המאגר ולא לברור מתוכם, למעט כפילויות וספרים שכבר יש לנו | הועתקו כולם |
| להעביר להם הערות ותיקונים | `emailRecipientsFor` ב-`error_report_dialog.dart` שולח דיווח על ספר מהמקור הזה גם ל-`y025837086@gmail.com` וגם אלינו |

שם המקור ב-`seforim.db` הוא **`yam-HaHachmaToOtzaria`** — הוא נגזר אוטומטית מרכיב
הנתיב הראשון של מפתחות `files_manifest.json` (`Generator.kt` ב-SeforimLibrary),
ולכן אין צורך לרשום אותו בשום מקום ב-SeforimLibrary.

## אם מושכים מהם עדכון

תנאי הרישיון נוגעים להיקף ההעתקה בנקודת ההעתקה, ו**אין בהם דרישה לסנכרון מתמשך**.
משיכת עדכון היא החלטה שלנו. כשמחליטים לעשות זאת:

1. `git pull` על העותק המקומי של [yam-HaHachma](https://github.com/torahtyh/yam-HaHachma).
2. לכל ספר חדש: להריץ את הכלים שב-[scripts/](scripts/) ואחריהם
   `.claude/skills/otzaria-book-format/scripts/validate_book.py` עד 0 שגיאות.
3. `make_metadata.py --check-name` **לפני** שקובעים שם קובץ — התנגשות שם עם ספר
   קיים היא שגיאה קשה שמפילה את האריזה (כך נולד השם `הליכות עולם - כללי הגמרא`).
4. להוסיף רשומה ל-`metadata.json`, `all_metadata.json`,
   `all_metadata_with_file_paths.json`, `ForDB/all_metadata.json`
   ושורה ל-`ForDB/generations.csv`.

## התאמות שנדרשו לספרים

המאגר כבר מעוצב בסגנון אוצריא (`<h1>`–`<h3>`, `<b>`, שורה = יחידת תוכן), אבל שתי
תקלות חזרו בו:

* **כותרות באמצע שורה** — `<hN>` שנדבק לסוף פסקה או שנשאר לו טקסט אחריו. אוצריא
  מזהה כותרת רק בתחילת שורה, וטקסט שאחרי `</hN>` נבלע לשם הכותרת בתוכן העניינים.
  תיקון: [scripts/split_inline_headings.py](scripts/split_inline_headings.py).
* **כותרות תלושות** — מילה או אות שהיא חלק מהמשפט וקיבלה `<hN>` רק כי בדפוס היא
  הודפסה בשורה נפרדת. תיקון: [scripts/unwrap_stray_headings.py](scripts/unwrap_stray_headings.py).

שני הכלים משנים **חלוקת שורות ותגים בלבד** — לא מילה מלשון הספר.

</div>
