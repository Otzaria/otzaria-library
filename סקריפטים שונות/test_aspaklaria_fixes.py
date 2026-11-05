"""aspaklaria_fixes: הגושים שהודבקו באתר והשורה הכפולה ביתום נמחקים, ורק הם."""

import unittest

import aspaklaria_fixes as F

YATOM = ["<h3>יתום</h3>", "פתיחה", "שורה א", "<h4>מכילתא</h4>", "שורה ב"]
TWIN_KEEP = "מלוה שמת ובא היורש לתבוע את הלוה בשטר שעליו, ואמר פרעתי לאביך, והיורש אומר"
TWIN_DROP = "מלוה שמת ובא היורש לתבוע את הלוה בשטר שעליו ואמר פרעתי לאביך, והיורש אומר"


class FixPage(unittest.TestCase):
    def test_removes_tail_pasted_from_donor(self):
        yitro = ["<h3>יתרו</h3>", "סוף יתרו"] + YATOM[2:]
        self.assertEqual(F.fix_page("יתרו", yitro, {"יתום": YATOM}), ["<h3>יתרו</h3>", "סוף יתרו"])

    def test_birkat_kohanim_pair(self):
        donor = ["<h3>ברכת המצות</h3>", "א", "ב"]
        host = ["<h3>ברכת כהנים</h3>", "ג", "א", "ב"]
        self.assertEqual(F.fix_page("ברכת כהנים", host, {"ברכת המצות": donor}), host[:2])

    def test_idempotent(self):
        once = F.fix_page("יתרו", ["<h3>יתרו</h3>", "סוף יתרו"] + YATOM[2:], {"יתום": YATOM})
        self.assertEqual(F.fix_page("יתרו", once, {"יתום": YATOM}), once)

    def test_other_entries_untouched(self):
        lines = ["<h3>יתר</h3>"] + YATOM[2:]
        self.assertEqual(F.fix_page("יתר", lines, {"יתום": YATOM}), lines)

    def test_never_empties_page(self):
        self.assertEqual(F.fix_page("יתרו", YATOM[:], {"יתום": YATOM}), YATOM[:1])

    def test_comma_twin_keeps_first(self):
        lines = ["<h3>יתום</h3>", TWIN_KEEP, TWIN_DROP, "הבא"]
        fixed = F.fix_page("יתום", lines, {})
        self.assertEqual(fixed, ["<h3>יתום</h3>", TWIN_KEEP, "הבא"])
        self.assertEqual(F.fix_page("יתום", fixed, {}), fixed)

    def test_pasted_tail_includes_comma_twin(self):
        yatom = ["<h3>יתום</h3>", "א", TWIN_KEEP, TWIN_DROP, "ב"]
        yitro = ["<h3>יתרו</h3>", "סוף יתרו"] + yatom[1:]
        self.assertEqual(F.fix_page("יתרו", yitro, {"יתום": yatom}), yitro[:2])

    def test_comma_twin_needs_neighbour(self):
        lines = ["<h3>יתום</h3>", TWIN_KEEP, "באמצע", TWIN_DROP]
        self.assertEqual(F.fix_page("יתום", lines, {}), lines)


if __name__ == "__main__":
    unittest.main()
