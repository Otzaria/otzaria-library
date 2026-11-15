# "סקריפטים שונות" עברו ל־book-sources

הסקריפטים שהיו כאן נמצאים כעת ב־[Otzaria/book-sources](https://github.com/Otzaria/book-sources/tree/main/%D7%A1%D7%A7%D7%A8%D7%99%D7%A4%D7%98%D7%99%D7%9D%20%D7%A9%D7%95%D7%A0%D7%95%D7%AA), באותו נתיב יחסי ובלי שינוי תוכן:
ייבוא אספקלריה (`aspaklaria.py`, `aspaklaria_fixes.py` והבדיקה שלו), `encyclopedia.py`, `fix_books_cli.py`, `fix_books_gui.py`,
`fix_wiki_headers.py`, `merge_folders.py`, `pdf_links.py` ו־`סנכרון אופליין/`.

ראו [מסמך ההעברה](https://github.com/Otzaria/book-sources/blob/main/docs/MIGRATION_MISC_SCRIPTS.md). הבדיקה `test_aspaklaria_fixes` רצה שם
ב־`misc-scripts-tests.yml`. הסקריפטים עובדים מול תיקיית העבודה או נתיב שמזינים להם; כדי להריץ אותם על הספרייה, הצביעו במפורש
על checkout של otzaria-library.

`merge_folders.py` לא היה חלק מהאריזה: השחרור ממזג את השורשים ב־`sync_and_merge_folders.py` וב־`manual_links_packaging.py`,
ושניהם נשארים כאן. כלי תיקון שכבת הטקסט של PDF עברו קודם לכן (ר' `pdf-text-layer/README.md`).
התיקייה הזו אינה נארזת.
