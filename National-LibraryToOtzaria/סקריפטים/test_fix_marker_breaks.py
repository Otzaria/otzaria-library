# -*- coding: utf-8 -*-
"""בדיקות לכללי ההפרדה של fix_marker_breaks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fix_marker_breaks import fix_text, is_hebrew_numeral, is_siman_label

H = '<span style="color:#1B1464">'


def run(src):
    return fix_text(src)[0]


CASES_BR = [
    # הבאג שדווח בספר 'תבונה'
    (f'{H}חלק שני סימן א</span><b>זה </b>לשונו:',
     f'{H}חלק שני סימן א</span><br/><b>זה </b>לשונו:'),
    (f'{H}סימן א</span><b>וז"ל </b>',
     f'{H}סימן א</span><br/><b>וז"ל </b>'),
    # תווית עם רווח תלוי — הרווח נגזם וה-<br/> מחליף אותו
    (f'{H}סימן א </span><b>אשר </b>שאלת',
     f'{H}סימן א</span><br/><b>אשר </b>שאלת'),
    # מספור טהור עם נקודה
    (f'{H}רצב. </span><b>ברמב"ם </b>בפ"ז',
     f'{H}רצב.</span><br/><b>ברמב"ם </b>בפ"ז'),
    # תווית לפני ציטוט נטוי
    (f'{H}סימן יט</span><i>אין המומין פוסלין</i>',
     f'{H}סימן יט</span><br/><i>אין המומין פוסלין</i>'),
]

CASES_SPACE = [
    # כותרת אל כותרת — רווח, לא שבירה
    (f'{H}סימן רלג</span>{H}בענין השומע</span><br/><b>כתב </b>',
     f'{H}סימן רלג</span> {H}בענין השומע</span><br/><b>כתב </b>'),
    # כותרת תיאורית דבוקה לגוף בלי רווח כלל
    (f'{H}בענין תוספות שביעית</span><b>רמב"ם </b>שמיטה',
     f'{H}בענין תוספות שביעית</span> <b>רמב"ם </b>שמיטה'),
]

CASES_UNCHANGED = [
    # משפט רציף שגלש לתוך הכותרת — שבירה כאן הייתה משבשת
    f'{H}שורש תקרובת ע"א ותקרובת </span><i>ע"א אינה בטלה לעולם.</i>',
    f'{H}פרט רוב וקרוב גוזל </span><i>הנמצא קרוב לשובך</i>',
    # כבר מופרד כראוי
    f'{H}סימן א</span><br/><b>וז"ל </b>',
    f'{H}סימן א</span> <b>וז"ל </b>',
    f'{H}סימן א</span>\n<b>וז"ל </b>',
    # סוף קובץ
    f'{H}סימן א</span>',
    # תג לא-כותרת אינו מטופל כאן כלל
    '<span style="color:#999">הערה</span><b>טקסט</b>',
    # פיסוק צמוד שייך לתווית ומפריד בעצמו
    f'{H}סימן יב</span>: <i>מותר להרוג המוסר</i>',
    f'{H}סימן יב</span>. <b>וז"ל </b>',
    # הרווח נמצא בתוך הכותרת הראשונה — אין להוסיף רווח שני בין התגים
    f'{H}ז </span>{H}כוורת </span>',
    # כותרת תיאורית שגלשה לתוך המשך המשפט; המילים הקצרות אינן מספרים
    f'{H}פרט קמא קמא בטיל אבל </span><i>אם עירה יין</i>',
    f'{H}פרט טועה בדבר מצוה כל </span><i>העושה מצוה</i>',
    f'{H}פרט נזקי ממון כל </span><i>נפש חיה</i>',
    f'{H}שורש מקדש בעל כרחה אין </span><i>האשה מתקדשת</i>',
    f'{H}שורש אי חופה קונה כיון </span><i>שנכנסה ארוסה</i>',
    f'{H}שורש רחמי האב על הבן היה </span><i>הדבר ברור</i>',
]

LABELS_TRUE = [
    'סימן א', 'חלק שני סימן א', 'סימן רלג', 'סימן כ"ה', 'רצב.',
    'סימן ז\'', 'סימן י"ד', 'סימן יוד', 'סימן טוב', 'סימן חי',
]
LABELS_FALSE = [
    'בענין השומע ש"ש לבטלה צריך לנדותו',
    'שורש תקרובת ע"א ותקרובת',
    'פרט רוב וקרוב גוזל',
    'בדין מורידין קרוב לנכסי שבוי',
    'פרט קמא קמא בטיל אבל',
    'פרט טועה בדבר מצוה כל',
    'פרט נזקי ממון כל',
    'שורש אתי עשה ודחי ל"ת',
    'שורש סוכה שע"ג גמל',
    'שורש מקדש בעל כרחה אין',
    'שורש אי חופה קונה כיון',
    'שורש רחמי האב על הבן היה',
    '',
]

NUMERALS_TRUE = ['א', 'יא', 'ט"ו', 'רלג', 'שעג', 'תתקצ"ט', 'יוד', 'טוב', 'חי']
NUMERALS_FALSE = ['בטיל', 'ממון', 'סוכה', 'מקדש', 'כרחה']


def main() -> None:
    failures = []

    for src, want in CASES_BR + CASES_SPACE:
        got = run(src)
        if got != want:
            failures.append(f'  שינוי שגוי:\n    קלט : {src}\n    צפוי: {want}\n    בפועל: {got}')

    for src in CASES_UNCHANGED:
        got = run(src)
        if got != src:
            failures.append(f'  היה צריך להישאר ללא שינוי:\n    קלט : {src}\n    בפועל: {got}')

    for lbl in LABELS_TRUE:
        if not is_siman_label(lbl):
            failures.append(f'  {lbl!r} אמור להיות מזוהה כתווית סימן')
    for lbl in LABELS_FALSE:
        if is_siman_label(lbl):
            failures.append(f'  {lbl!r} אינו תווית סימן')

    for numeral in NUMERALS_TRUE:
        if not is_hebrew_numeral(numeral):
            failures.append(f'  {numeral!r} אמור להיות מזוהה כמספר עברי')
    for numeral in NUMERALS_FALSE:
        if is_hebrew_numeral(numeral):
            failures.append(f'  {numeral!r} אינו מספר עברי')

    # ריצה כפולה אינה משנה דבר (אידמפוטנטיות)
    for src, _ in CASES_BR + CASES_SPACE:
        once = run(src)
        if run(once) != once:
            failures.append(f'  אינו אידמפוטנטי: {src}')

    total = (
        len(CASES_BR) + len(CASES_SPACE) + len(CASES_UNCHANGED)
        + len(LABELS_TRUE) + len(LABELS_FALSE)
        + len(NUMERALS_TRUE) + len(NUMERALS_FALSE)
    )
    if failures:
        print(f'נכשלו {len(failures)} בדיקות:')
        print('\n'.join(failures))
        sys.exit(1)
    print(f'כל {total} הבדיקות עברו')


if __name__ == '__main__':
    main()
