"""שער האיכות: האם פלט ההמרה ראוי להיכנס לעץ "ערוך" (ספר מעובד), או ל"לא ערוך".

השער שמרני בכוונה: ספר שנפסל בטעות עדיין נארז ב־otzaria_dicta_latest.zip; ספר שעבר
בטעות מופיע באפליקציה כספר גרוע. הספים כוילו על קבצי המאגר (DESIGN §5):

| (כותרות/10k, קטועות, סיום בפיסוק) | גולמי "לא ערוך" | גולמי extra_books | ערוך | ערוך DBS |
| --- | --- | --- | --- | --- |
| (2, 5%, 70%) בלי בדיקות הכיסוי | 0.0% | 5.8% | 66.6% | 71.9% |
| השער המלא (כולל coverage + short_headings) | 0.0% | 4.6% | 60.1% | 57.9% |

כל הבדיקות חייבות לעבור:
* `preserved`   — אף מילה (אותיות) מה־zip של דיקטה לא אבדה בדרך.
* `h1_first`    — השורה הראשונה `<h1>`.
* `sub_levels`  — יש לפחות רמת כותרת אחת מתחת ל־h1.
* `headings`    — לפחות MIN_HEADINGS_PER_10K כותרות ל־10,000 מילים.
* `no_skips`    — אין קפיצת רמה (h2 → h4).
* `balanced`    — `<b>`/`<big>` מאוזנים בכל שורה.
* `heading_alone` — אין טקסט אחרי `</hN>` באותה שורה.
* `fragments`   — שורות של עד 3 מילים בלי פיסוק סוגר ≤ MAX_FRAGMENTS.
* `end_punct`   — שורות גוף שמסתיימות ב־`.` או `:` ≥ MIN_END_PUNCT.
* `coverage`    — אין קטע גוף רצוף בלי כותרת שגדול מ־MAX_GAP מהספר.
* `short_headings` — לפחות MIN_SHORT_HEADINGS מהכותרות באורך עד 8 מילים.

כיול על פלט הממיר של A1 (dicta_convert.convert_zip_final, כל 1,007 הספרים, 2026-09-30):
השער המלא עובר ב־16.5% מהספרים (166, הממיר והשער של 2026-09-30), מול 60.1% מהספרים הערוכים ו־0–4.6% מהגולמיים הישנים.
בדיקת השימור (span־ים צמודים בצד המקור, תגים בתוך שורה בצד הפלט — בלי רווח): 0 מילים אבודות בכל 1,007 הספרים.
ב־כ־79 מהם שיש להם זוג ערוך 1:1 — דיוק הכותרות (כותרת של הפלט שקיימת בזהב) חציון 0.92,
רבעון תחתון 0.76, ויחס מספר הכותרות לזהב 0.95. בלי שתי בדיקות הכיסוי עברו 225 (22%).
"""
from __future__ import annotations

import re

from dicta_fp import html_keys, keys, text_keys

MIN_HEADINGS_PER_10K = 2.0
MAX_FRAGMENTS = 0.05
MIN_END_PUNCT = 0.70
MAX_GAP = 0.20            # הקטע הארוך ביותר בלי כותרת, כחלק ממילות הספר
MIN_SHORT_HEADINGS = 0.90  # חלק הכותרות שאורכן עד 8 מילים (רצף "heading" באמצע טקסט אינו כותרת)

_H = re.compile(r"^<h(\d)>(.*?)</h\1>\s*$")
_TAG = re.compile(r"<[^>]+>")
_ENDP = re.compile(r"[.:]\s*(</\w+>)?\s*$")


def metrics(text: str) -> dict:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    heads = [int(m.group(1)) for m in (_H.match(ln) for ln in lines) if m]
    body = [ln for ln in lines if not _H.match(ln)]
    nb = max(1, len(body))
    words = sum(len(_TAG.sub(" ", ln).split()) for ln in body)
    return {
        "lines": len(lines),
        "words": words,
        "headings": len(heads),
        "headings_per_10k": sum(1 for h in heads if h != 1) * 1e4 / max(1, words),  # בלי ה־h1
        "h1_first": bool(lines and lines[0].startswith("<h1>")),
        "sub_levels": len(set(heads) - {1}),
        "level_skips": sum(1 for a, b in zip(heads, heads[1:]) if b - a > 1),
        "fragments": sum(1 for ln in body if len(_TAG.sub(" ", ln).split()) <= 3 and not _ENDP.search(ln)) / nb,
        "end_punct": sum(1 for ln in body if _ENDP.search(ln)) / nb,
        "unbalanced": sum(1 for ln in lines if ln.count("<b>") != ln.count("</b>")
                          or ln.count("<big>") != ln.count("</big>")),
        "text_after_heading": sum(1 for ln in lines if re.search(r"</h\d>.+", ln)),
        "max_gap": _max_gap(lines) / max(1, words),
        "short_headings": _short_share(lines),
    }


def _short_share(lines) -> float:
    sub = [m.group(2) for m in (_H.match(ln) for ln in lines) if m and m.group(1) != "1"]
    return sum(1 for h in sub if len(_TAG.sub(" ", h).split()) <= 8) / len(sub) if sub else 0.0


def _max_gap(lines) -> int:
    gap = mx = 0
    for ln in lines[1:]:
        if _H.match(ln):
            mx = max(mx, gap)
            gap = 0
        else:
            gap += len(_TAG.sub(" ", ln).split())
    return max(mx, gap)


def lost_words(source_text: str, out_text: str, *, source_is_html: bool = False) -> int:
    """כמה מילים (אותיות) של המקור אינן בפלט. צירוף/פיצול מילים (אותן אותיות) אינו אובדן.
    source_is_html: המקור הוא דפי ה־HTML של דיקטה — ה־span־ים מחוברים בלי רווח, כמו באתר.
    0 = שימור מלא."""
    from collections import Counter  # noqa: PLC0415
    from dicta_replay import opcodes  # noqa: PLC0415 — diff מהיר של המערכת
    a = html_keys(source_text) if source_is_html else text_keys(source_text)
    b = text_keys(out_text)
    lost = 0
    for tag, i1, i2, j1, j2 in opcodes(a, b):
        if tag == "insert":
            continue
        # אותן אותיות בבלוק (צירוף/פיצול, או אות־פתיחה גדולה שהופרדה/הוזזה בתוך הבלוק) — אינו אובדן
        missing = Counter("".join(a[i1:i2])) - Counter("".join(b[j1:j2]))
        if missing:
            lost += i2 - i1
    return lost


def evaluate(text: str, source_text: str | None = None, *, source_is_html: bool = False) -> dict:
    """מחזיר {'pass': bool, 'checks': {...}, 'metrics': {...}}."""
    m = metrics(text)
    checks = {
        "h1_first": m["h1_first"],
        "sub_levels": m["sub_levels"] >= 1,
        "headings": m["headings_per_10k"] >= MIN_HEADINGS_PER_10K,
        "no_skips": m["level_skips"] == 0,
        "balanced": m["unbalanced"] == 0,
        "heading_alone": m["text_after_heading"] == 0,
        "fragments": m["fragments"] <= MAX_FRAGMENTS,
        "end_punct": m["end_punct"] >= MIN_END_PUNCT,
        "coverage": m["max_gap"] <= MAX_GAP,
        "short_headings": m["short_headings"] >= MIN_SHORT_HEADINGS,
    }
    if source_text is not None:
        lw = lost_words(source_text, text, source_is_html=source_is_html)
        m["lost_words"] = lw
        checks["preserved"] = lw == 0
    return {"pass": all(checks.values()), "checks": checks,
            "metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}}
