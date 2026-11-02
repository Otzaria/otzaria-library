# משנה תורה ומפרשיו - צינור הפקה

פרויקט להורדת מפרשי הרמב"ם מאתר rambam.genizah.org, התאמתם לטקסט "משנה תורה" שבאוצריא, וייצור קבצי טקסט עם קישורי בין-מקורות (Cross-Reference) למפרשים.

## פלט

קבצים סופיים תחת התיקייה final.

```
mefarshim/<name>.txt           קובץ HTML פתוח לכל מפרש, עם היררכיה מלאה (ספר → הלכות → פרק → אות) וטקסט המפרש
links/<name>_links.json        מערך קישורים: כל שורה במפרש מצביעה לשורה המקבילה במשנה תורה באוצריא
metadata.json                  מילון של כל המפרשים הייחודיים (שם, מחבר, שנת דפוס, סוג)
```

## דרישות

```
Python      ≥ 3.12
חבילות     requests, tqdm, beautifulsoup4, python-dotenv  (מותקנות מ-pyproject.toml)
טקסט       משנה תורה של אוצריא בתיקייה משנה תורה/<ספר>/<הלכות ...>.txt
חשבון      משתמש פעיל ב-sso.genizah.org עם הרשאת קריאה ל-rambam.genizah.org
```

## Git LFS

הקובץ output.json גדול ונשמר ב-Git LFS (ראה .gitattributes). נדרש [Git LFS](https://git-lfs.com/) מותקן לפני clone, אחרת תקבל pointer file במקום התוכן.

התקנה חד-פעמית למשתמש.

```bash
git lfs install
```

clone עם משיכת LFS.

```bash
git clone <repo-url>
```

אם clone נעשה לפני התקנת LFS, משוך עכשיו.

```bash
git lfs pull
```

## התקנה עם uv

[uv](https://docs.astral.sh/uv/) הוא מנהל חבילות וסביבות וירטואליות מהיר ל-Python. הפרויקט מוגדר ב-pyproject.toml ו-uv מתקין את כל התלויות אוטומטית.

התקנת uv (Windows PowerShell).

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

התקנת uv (macOS / Linux).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

סנכרון תלויות. uv יוצר .venv אוטומטית, מתקין Python 3.12 אם חסר, ומתקין את כל החבילות מ-pyproject.toml.

```bash
uv sync
```

הרצת סקריפט. uv מפעיל את הסקריפט בתוך הסביבה הווירטואלית של הפרויקט בלי צורך ב-activate.

```bash
uv run python download.py
uv run python get_hierarchy.py
uv run python compare.py
uv run python parser.py
```

הוספת חבילה חדשה.

```bash
uv add <package>
```

## קובץ סביבה

נדרש קובץ env בתיקייה final עם שם משתמש וסיסמה לאתר.

```
GENIZAH_USERNAME=your_username
GENIZAH_PASSWORD=your_password
```

הערות.

```
final/.env.example       תבנית להעתקה
final/.env               נטען אוטומטית ע"י download.py דרך python-dotenv
.gitignore               מחריג את .env מ-git
```

## מבנה התיקייה

```
final/
├── download.py              # שלב 1 — הורדת JSON מהאתר
├── get_hierarchy.py         # שלב 2 — בניית היררכיות (רמב"ם + אוצריא)
├── compare.py               # שלב 3 — השוואת שמות בין שני המקורות
├── parser.py                # שלב 5 — בניית קבצי המפרשים והקישורים
├── mapping/                 # שלב 4 — מיפויי שם ידניים
│   ├── rambam_books.json
│   ├── rambam_halachot.json
│   ├── rambam_prakim.json
│   └── rambam_ot.json
├── output.json              # פלט שלב 1 (JSON גולמי)
├── rambam_hierarchy.json    # פלט שלב 2
├── otzaria_hierarchy.json   # פלט שלב 2
├── mefarshim/               # פלט שלב 5 — קבצי טקסט מעוצבים
├── links/                   # פלט שלב 5 — קבצי JSON של קישורים
├── .env                     # סודות (לא מסונכרן)
├── .env.example             # תבנית
└── משנה תורה/               # קלט חיצוני: טקסט אוצריא
```

## הצינור - שלב אחר שלב

### שלב 1 - הורדה

קובץ הסקריפט.

```
download.py
```

מבצע התחברות SSO לאתר genizah.org ומוריד את כל הרמב"ם עם המפרשים אל output.json.

זרימת ה-login (JSONP).

```
1. GetLoginUIT                                   שם משתמש + סיסמה → אסימון UIT
2. GetUserPermission + GetUserInfo               דגלי הרשאות + פרופיל
3. Account/SSOSignIn?UIT=...                     מנפיק עוגיית סשן ASP.NET באתר rambam.genizah.org
                                                 בלעדיו ה-API מחזיר 403
```

שאיבת הנתונים מתבצעת ב-4 רמות מקוננות.

```
GetDivisions(level=1)                            ספרים
GetDivisions(level=2, parent_id=...)             הלכות
GetDivisions(level=3, parent_id=...)             פרקים
GetDivisions(level=4, parent_id=...)             אותות (פסקאות)
GetMefarshimByDivisionDetailId(...)              רשימת מפרשים לכל אות
```

הכתיבה אל output.json מתבצעת בזרם. כל ספר ראשי נכתב מיד עם סיומו דרך f.flush().

ריצה.

```bash
python download.py
```

### שלב 2 - בניית היררכיות

קובץ הסקריפט.

```
get_hierarchy.py
```

יוצר שתי מפות עץ במבנה זהה (ספר → הלכות → פרק → אות).

```
rambam_hierarchy.json     נבנה מ-output.json. נשמרים רק אותות עם mefarshim לא ריק
otzaria_hierarchy.json    נבנה מסריקת תיקיית "משנה תורה"
```

חוקי הסריקה לאוצריא.

```
<h2>...</h2>              שם הפרק
שורה (אות)                נרשם מספר השורה כ-line_index לקישור עתידי
```

מבנה הפלט.

```
otzaria_hierarchy[ספר][הלכות][פרק][אות] = מספר שורה
```

### שלב 3 - השוואת שמות

קובץ הסקריפט.

```
compare.py
```

מייצא ארבע קבוצות (ספרים, הלכות, פרקים, אותות) משני המקורות לקבצי טקסט ממוינים.

```
otzaria_books.txt        rambam_books.txt
otzaria_halachot.txt     rambam_halachot.txt
otzaria_prakim.txt       rambam_prakim.txt
otzaria_ot.txt           rambam_ot.txt
```

במקביל יוצר תבניות JSON ריקות למילוני המיפוי.

```
rambam_books.json
rambam_halachot.json
rambam_prakim.json
rambam_ot.json
```

המטרה - לאתר בעין הפרשים בשמות. לדוגמה "ספר קרבנות" ברמב"ם מול "ספר קורבנות" באוצריא.

### שלב 4 - מילוי המיפוי

תיקיית הקבצים.

```
mapping/
```

ידני. כל קובץ הוא מילון מהשם ב-rambam לשם ב-otzaria.

```jsonc
// mapping/rambam_books.json
{
  "ספר קרבנות": "ספר קורבנות",
  "ספר המדע": "ספר מדע"
}
```

קבצים נדרשים.

```
rambam_books.json
rambam_halachot.json
rambam_prakim.json
rambam_ot.json
```

ערך זהה למפתח = שם זהה בשני המקורות.

### שלב 5 - בניית הפלט

קובץ הסקריפט.

```
parser.py
```

הצעד הסופי. עובר על output.json, משטח לפי CodeMefareshId, ויוצר עבור כל מפרש.

#### 5א - קבצי מפרשים

נתיב הפלט.

```
mefarshim/<name>.txt
```

קובץ HTML עם היררכיית כותרות.

```
<h1>     שם המפרש
<h2>     ספר
<h3>     הלכות
<h4>     פרק
<h5>     אות
body     תוכן MHLogicalUnitText (נורמליזציה של תגיות span)
```

מיפוי מחלקות span של האתר לתגיות פלט (span_styles.py).

```
B          → <b>
Z          → <b>      ציטוט מדברי הרמב"ם
S          → <small>
H          → <span style="color:#1B1464">
N, R       → <span style="color:#999">
```

עדיפויות. רק צבע אחד נבחר, לפי הסדר H ואז N ואז R. תגיות סמנטיות B, Z, S קוננות בתוך הצבע. B ו-Z יחד נותנים <b> אחד, ו-<b> בתוך <b> נפתח.

Z מודגש כמו הדיבור המתחיל בשאר מפרשי הרמב"ם (עד נובמבר 2026 הוא נכתב <i>; italic_quotes_to_bold.py המיר את הספרים שבמאגר). חריג: ב"שקל הקודש" האתר מסמן ב-Z גם את שכבת הערות המקורות, וקטע Z שנפתח בסימן הערה ("(א) רש"ס...") נשאר שם <i>.

#### 5ב - קבצי קישורים

נתיב הפלט.

```
links/<name>_links.json
```

לכל שורה בקובץ המפרש (אחרי apply_span_styles) נרשמת רשומת link.

```json
{
  "line_index_1": 42,
  "heRef_2": "ספר מדע, הלכות יסודי התורה, פרק א, א",
  "path_2": "משנה תורה, הלכות יסודי התורה.txt",
  "line_index_2": 17,
  "Conection Type": "commentary"
}
```

המיפוי משתמש בארבעת קבצי mapping לתרגום שמות רמב"ם ↔ אוצריא, וב-otzaria_hierarchy.json לאיתור line_index_2.

## סדר ריצה מלא

```bash
python download.py        # שלב 1 - יוצר output.json (קורא .env)
python get_hierarchy.py   # שלב 2 - יוצר rambam_hierarchy.json + otzaria_hierarchy.json
python compare.py         # שלב 3 - יוצר קבצי השוואה .txt
# שלב 4 - ידני: מלא את mapping/*.json לפי הפערים מ-3
python parser.py          # שלב 5 - יוצר mefarshim/*.txt + links/*.json + metadata.json
```

## הערות

```
download.py        4 לולאות tqdm מקוננות. ריצה מלאה ארוכה. שמור את output.json כ-checkpoint
parser.py          assert mef_entry == text_entry מוודא metadata עקבי. נפילה = שינוי מבני ב-API
Missing link       שורה ללא link מודפסת לקונסולה ומדולגת ב-_links.json (נשארת ב-.txt)
```
