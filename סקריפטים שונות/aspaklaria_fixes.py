"""תיקונים ממוקדים לשגיאות שנמצאות באתר aspaklaria.info עצמו, ולכן חוזרות בכל ייבוא.

כל תיקון מעוגן לשם הערך ולטקסט, לא למספרי שורות, ואידמפוטנטי: אם האתר כבר
תוקן, התיקון לא נוגע בכלום ומודפסת אזהרה.
"""

# ערך -> הערך שסופו הודבק בטעות בסוף הערך הזה.
PASTED_TAILS = {
    "יתרו": "יתום",
    "ברכת כהנים": "ברכת המצות",
}

# ערך -> תחילת שורה שחוזרת מיד אחרי עצמה ונבדלת ממנה רק בפסיקים. השורה הזו נמחקת.
COMMA_TWINS = {
    "יתום": ["מלוה שמת ובא היורש לתבוע את הלוה בשטר שעליו ואמר"],
}


def _strip_commas(line: str) -> str:
    return line.replace(",", "")


def drop_pasted_tail(lines: list[str], donor: list[str]) -> list[str]:
    """מסיר מסוף `lines` את הגוש הארוך ביותר ששווה לסוף `donor`."""
    k = 0
    while k < min(len(lines) - 1, len(donor)) and lines[-1 - k] == donor[-1 - k]:
        k += 1
    return lines[:-k] if k else lines


def drop_comma_twin(lines: list[str], prefix: str) -> list[str]:
    """מסיר שורה שמתחילה ב-`prefix` כשהיא זהה לקודמתה חוץ מפסיקים."""
    return [
        line
        for i, line in enumerate(lines)
        if not (
            i > 0
            and line.startswith(prefix)
            and line != lines[i - 1]
            and _strip_commas(line) == _strip_commas(lines[i - 1])
        )
    ]


def fix_page(name: str, lines: list[str], pages: dict[str, list[str]]) -> list[str]:
    """מחיל את התיקונים של הערך `name`.

    `pages` - השורות של הערכים שכבר נקראו, לפני תיקון: הגוש שהודבק ביתרו כולל את הכפילות שביתום.
    """
    donor = PASTED_TAILS.get(name)
    if donor is not None:
        fixed = drop_pasted_tail(lines, pages.get(donor, []))
        if fixed == lines:
            print(f"aspaklaria_fixes: לא נמצא בסוף '{name}' גוש מתוך '{donor}'")
        lines = fixed
    for prefix in COMMA_TWINS.get(name, ()):
        fixed = drop_comma_twin(lines, prefix)
        if fixed == lines:
            print(f"aspaklaria_fixes: לא נמצאה ב'{name}' שורה כפולה '{prefix}'")
        lines = fixed
    return lines
