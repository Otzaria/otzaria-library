# מפרט: פיצול event-driven של release-and-build (ארכיטקטורה 5)

**סטטוס: מומש מקומית; ממתין ל-push ול-canary חי.** ‏המסלול הסמכותי ב-
‏sync-manual-links.yml הוא כעת S0 קצר, וה-job הסינכרוני הישן הוסר. השלבים
הארוכים ממשיכים דרך callbacks מאומתים ו-reconciler מתוזמן, בלי הורה מתארח שממתין
לשרשרת ארוכה מתקרת 360 הדקות.

## שלבים

| שלב | ‏workflow | עושה | מסיים |
|---|---|---|---|
| S0 | sync-manual-links / start-saga | מעלה **saga-state artifact**, כולל ForDB pin, משגר update-library באופן idempotent ומגלה run מדויק | מיד אחרי הגילוי |
| S1 | saga-continue (`repository_dispatch` + `workflow_dispatch` לגיבוי) | אימות מלא של update-library ושל release הבלתי-משתנה, אימות ForDB המוצמד, שיגור SeforimLibrary + גילוי מדויק | מיד |
| S2 | saga-continue (type=`seforim-published`) | ‏validate-seforim-result + אימות נכסי release (שורות 492‑525) | סוף הסאגה |

## חוזה ה-callbacks (אפס אמון ב-payload)

- ‏update-library ו-manual-generate-release שולחים callback רק אחרי ש-artifact
  התוצאה המאומת קיים: ‏
  `gh api repos/Otzaria/otzaria-library/dispatches -f event_type=... -f client_payload[correlation_id]=... -f client_payload[run_id]=...` ‏(PIPELINE_TOKEN).
- ה-payload הוא **מפתח חיפוש בלבד**: ‏saga-continue מושך את ה-run מ-GitHub ומאמת
  ‏conclusion + ‏head_sha + ‏run_attempt + ‏displayTitle (התאמה מדויקת עם ה-correlation),
  מוריד את ה-artifact ומאמת ‏schema + ‏sha256 — בדיוק הבדיקות הקיימות, ללא קיצור.
- ‏callback כפול / stage שכבר בוצע → ‏no-op אידמפוטנטי לפי **recovery key** ‏
  `correlation_id + stage`. **‏artifact לבדו אינו mutex**: שני callbacks יכולים לראות
  "אין artifact" ולרוץ פעמיים. לכן שכבתיים:
  1. **‏mutex אמיתי:** ‏`concurrency: group: saga-<correlation64>-<stage>` על ריצת
     ה-continuation, עם `cancel-in-progress: false` ‏+ ‏`queue: max` — ‏GitHub מסדר
     את שני ה-callbacks; השני נכנס רק אחרי שהראשון סיים.
  2. **בדיקה חוזרת בתוך המנעול:** הצעד הראשון של ה-continuation בודק מחדש את
     ‏recovery state (ה-artifact ‏`saga-stage-…` **וגם** קיום תוצר-השלב עצמו —
     ‏release/‏run שכבר שוגר, בזהות child מדויקת) ויוצא בשקט אם השלב כבר בוצע.
     אידמפוטנטיות לעולם אינה נשענת על "artifact קיים" בלבד — תמיד מאמתים את
     התוצר האמיתי.

## saga-state

‏artifact ‏`saga-state-<correlation64>-attempt-<run_attempt>` שמעלה S0 (בריצת sync-manual-links, ‏retention 90 יום):
כל הפינים ש-S0 מזרים — ‏expected_links_commit, ‏seforim_tool_commit,
‏sefaria_tag/metadata_sha/archive_sha, ‏ForDB tag/archive/provenance sha, ‏correlation_id — חתום
ב-sha256 צמוד. ‏S1/S2 טוענים אותו מריצת ה-sync (מזוהה בהתאמת כותרת מדויקת על ה-correlation),
לעולם לא מה-payload.

## reconciler (הרחבת reconcile-pipeline או תאום ב-otzaria-library)

כל 15 דק', לכל ‏saga-state פתוח (אין S2 מוצלח): אם ריצת-הבת של השלב הנוכחי
‏completed:success אך ה-continuation לא רץ (callback אבד) → משגר את ‏saga-continue עם אותו
מפתח (workflow_dispatch); אם נכשלה → מסמן את הסאגה ככשל (loud). ‏>1 ריצת-בת תואמת → ‏
fail-loud, בלי לבחור. callback כפול נשמר תחת mutex אחד; ה-reconciler אינו מוסיף
delivery נוסף כשאחד כבר פעיל, ומריץ מחדש databaseId שנכשל. חלון: 90 יום,
זהה ל-retention של state ושל תוצרי הילדים הדרושים לאימות חוזר.

## weekly-pipeline

‏watch_run על sync-manual-links יראה הצלחה כבר ב-S0 — ההצלחה האמיתית של השבועי נמדדת
מעתה ב-S2. ‏weekly עובר לעקוב אחרי ‏saga-stage-S2 (או פשוט מפסיק לחכות: הסאגה מנוהלת
ע"י ה-callbacks+reconciler, וה-weekly רק מצית).

## נלווים שנבנים באותו מהלך (מהביקורת השביעית)

- **‏Kaggle intent store + ‏provisioner יחיד:** ‏intent של relink נשמר עמיד (record
  ממופתח-request-id); ‏provisioner בודד (תחת מנעול ה-admission) בוחר intent ממתין רק
  כשה-Linker פנוי; ה-reconciler מבצע ‏re-dispatch ל-intent שנדחה/אבד במקום לדרוש
  ‏rerun ידני.
- **‏watchdog לפי heartbeat:** ‏link_books.py כותב heartbeat פר-ספר/אצווה; ה-watchdog
  הורג רק worker ש**אין לו heartbeat** מעבר לסף — לעולם לא "ספר שלא הסתיים" (ספר ענק
  ובריא חי שעות בלגיטימיות).
- **פרסום content-addressed:** ‏payload מתפרסם בשם ממוען-תוכן (‏sha256), **ללא**
  ‏`--clobber`; ‏Kaggle מחשב ומעלה ‏artifact בלבד, ו-publisher קצר ואמין (ללא GPU)
  מאמת ומפרסם — מפריד compute מ-publish וגם מוציא את זכות-הכתיבה מהסשן.

## דרישות תשתית

- ‏repository_dispatch מגיע רק ל-default branch — ‏saga-continue חייב לשבת ב-main של
  ‏otzaria-library לפני canary.
- ‏PIPELINE_TOKEN בשני מאגרי-הבת צריך ‏contents:write (קיים) — ‏repo dispatch דורש אותו.
- ‏`workflow_run` אינו חוצה מאגרים — לכן dispatch מאומת, לא event.

## בדיקות קבלה (לפני push של המימוש)

1. ‏callback כפול → ‏continuation שני מזהה recovery key ומסיים בשקט (בלי dispatch כפול).
2. ‏payload מזויף (run_id של ריצה זרה) → נדחה בהתאמת כותרת/‏correlation.
3. אובדן callback (מדומה ע"י אי-שליחה) → ה-reconciler משלים את השלב.
4. כשל ילד → הסאגה מסומנת ככשל, אין continuation.
5. שני saga-state פתוחים במקביל → כל אחד ממשיך לפי המפתח שלו בלבד.

**לפני הפעלה חיה:** יש לדחוף את ארבעת המאגרים (כולל SefariaExport, שמחזיק
`downstream_intent.json` ו-reconciler לשיגור-השורש), להריץ פעם אחת `update-fordb` כדי
ליצור את release ה-content-addressed הראשון ואת `fordb_latest_pointer.json`, ורק
אחר כך לבצע canary ידני של S0→S1→S2. ה-reconciler וה-callbacks יושבים ב-default
branch, ולכן אינם ניתנים להוכחה מלאה בריצה מקומית בלבד.
