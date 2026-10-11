# -*- coding: utf-8 -*-
"""ניקוי שבירות השורה בטקסט הגולמי של האתר (rambam.genizah.org) לפני הפרסור.

בנתוני המקור יש שני סוגים של "\\n":

* שבירת שורה אמיתית בתוך הטקסט (כל ~65 תווים: "אתכם\\nשרבנו"). זו מילה חדשה,
  ולכן היא נהפכת לרווח. הפרסר הראשון מחק אותה וכך נדבקו כ-557 אלף מילים.
* "\\n" שצמוד לתג (</span>\\n<span, <span class="B">\\nטקסט) — הדפסה יפה של
  האתר ולא חלק מהטקסט. כאן נשמרת ההתנהגות הישנה (מחיקה), כי הכללים של
  fix_marker_breaks / fix_missing_spaces נכתבו מעליה. הרווח האמיתי, כשיש, כבר
  נמצא בטקסט עצמו.
"""

import re

_NEWLINES = re.compile(r'[\r\n  ]+')

# '' בין שתי אותיות הוא גרשיים (ע''ש); אחרי מילה הוא סוגר ציטוט (וכו'') ונשאר
_GERSHAYIM_PAIR = re.compile(r"(?<=[\u05d0-\u05ea\u0591-\u05c7])''(?=[\u05d0-\u05ea])")


def _replace_newlines(m: re.Match) -> str:
    s = m.string
    before = s[m.start() - 1] if m.start() > 0 else ''
    after = s[m.end()] if m.end() < len(s) else ''
    if before == '>' or after == '<' or not before or not after:
        return ''
    return ' '


def normalize_source_html(raw: str | None) -> str:
    if not raw:
        return ''
    return _GERSHAYIM_PAIR.sub('"', _NEWLINES.sub(_replace_newlines, raw))
