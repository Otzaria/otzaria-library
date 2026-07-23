# Queue policy — קבוצות ה-concurrency של הפייפליין השבועי

מדיניות מוצהרת לכל קבוצת concurrency בשרשרת. שלושה מחלקות:

- **persist-all (`queue: max`)** — כל intent חייב להישמר; ‏dispatch מאוחר לעולם לא דורס
  ‏pending שמזין בנייה ממתינה.
- **latest-only (ברירת מחדל: slot ממתין יחיד)** — הריצות זהות/גנריות; ‏pending אחד מספיק,
  ומאוחר שמחליף אותו אינו מאבד מידע.
- **serialize + reconciler** — הקבוצה מסדרת publisher על משאב משותף; העמידות ארוכת-הטווח
  אינה התור אלא ה-reconciler (ראו הסתייגויות).

| Repo | Workflow | Group | מדיניות | הנמקה |
|---|---|---|---|---|
| SefariaExport | release.yml | `sefaria-export-release` | persist-all (`queue: max`) | כל export שבועי הוא intent נפרד; ה-release נושא downstream intent בלתי-משתנה. |
| SefariaExport | reconcile-downstream.yml | `sefaria-downstream-reconcile` | latest-only | ticks זהים; ה-intents נשמרים לצמיתות כנכסי release. |
| otzaria-library | weekly-pipeline.yml | `weekly-otzaria-pipeline` | latest-only | טריגר שבועי גנרי; שני orchestrators זהים — pending יחיד מספיק. |
| otzaria-library | sync-manual-links.yml | `manual-links-sync` | persist-all (`queue: max`) | סאגה יקרה (שעות); dispatch שבועי מאוחר אסור שידרוס סאגה ממתינה. |
| otzaria-library | sync-manual-links.yml + update-library.yml + update-fordb.yml + monthly_update.yml + sefaria-export.yml (job) | `otzaria-main-writer` | persist-all (`queue: max`) | קבוצת writer משותפת לכל כותבי main; כל ריצה נושאת intent אחר. |
| otzaria-library | update-library.yml (job) | `otzaria-release-publisher` | persist-all (`queue: max`) | ‏publisher מסודר; intents שונים לכל ריצה. |
| otzaria-library | saga-continue.yml (job) | `saga-<correlation-sha>-<stage>` | persist-all + idempotent | callbacks הם at-least-once; mutex לפי שלב ובדיקה חוזרת של התוצר מונעים dispatch כפול. |
| otzaria-library | reconcile-sagas.yml | `reconcile-sagas` | latest-only | ticks זהים; intent הסאגה נשמר ב-artifact של S0. |
| SeforimLibrary | manual-generate-release.yml | `seforim-manual-release` | persist-all (`queue: max`) + serialize | בניית release על tmpfs משותף — publisher יחיד; כל intent נשמר. |
| LinkerToOtzaria | relink.yml | `linker-relink` | persist-all (`queue: max`) + serialize | כל server relink (כולל dry) חולק משאב host; Kaggle dry מקבל קבוצה ייחודית. פרסום release/baseline עבר ל-publisher נפרד. |
| LinkerToOtzaria | relink.yml (publish job) | `linker-release-publisher` | persist-all (`queue: max`) | מפרסם payload content-addressed ומעדכן baseline רק לאחר אימות bytes. |
| LinkerToOtzaria | kaggle-relink.yml | `kaggle-intent-intake` | persist-all (`queue: max`) | intake קצר בלבד: כל intent נשמר כ-artifact; הוא אינו מקים GPU. |
| LinkerToOtzaria | kaggle-provisioner.yml | `kaggle-provisioner` | latest-only | ticks/wake-ups הם תצפיות חלופיות; ה-intents עצמם נשמרים ב-artifacts. |
| LinkerToOtzaria | kaggle-provisioner.yml (job) + relink.yml | `linker-relink` | shared admission mutex | ה-provisioner מחזיק את אותו mutex מהבדיקה דרך JIT+dispatch+push; הילד ממתין מאחוריו ולכן server relink לא יכול להיכנס לחלון TOCTOU. |
| LinkerToOtzaria | reconcile-pipeline.yml | `reconcile-pipeline` | latest-only | ‏ticks זהים; אידמפוטנטי. |

**‏Kaggle intents:** כל dispatch נשמר תחילה ב-artifact קנוני ל-30 יום. provisioner
מתוזמן וממוסגר בוחר את ה-intent הישן ביותר שאין לו child; child פעיל משאיר אותו ממתין,
child מוצלח מסומן כמושלם, ו-child שנכשל הופך את ה-tick לאדום במקום להיעלם.

## הסתייגויות (הכרחיות להבנה)

1. **`queue: max` אינו durability מוחלט** — עד ‏100 ‏pending, כפוף ל-expiry/ביטולים/
   ‏outages של GitHub. שכבת העמידות האמיתית היא ‏reconcile-pipeline (ב-LinkerToOtzaria)
   ‏+ ‏reuse-reconcile של הבנייה (dispatch חוזר מזהה build זהה שהושלם ומחזיר אותו).
2. **‏actionlint 1.7.12 אינו מכיר `queue:`** (נוסף ב-GitHub ‏2026-05-07) — אין gate מקומי
   שמאמת את המפתח; ה-canary הראשון אחרי push הוא האימות.
3. **אין להקים GPU בתוך intake.** ‏`queue: max` בטוח רק מפני ש-kaggle-relink שומר
   intent קצר; `kaggle-provisioner` הוא בעל ה-admission היחיד שמבצע JIT+push.
