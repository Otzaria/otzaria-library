"""replace_editor_comments: a ")" at the end of an editor comment stays in the text only when it
closes a parenthesis that the text opened and does not close by itself."""
import re
import unittest

from orayta_convert import replace_editor_comments


def comment(body):
    return f'<span class="c">\rYeshayahu Hollander\r2020-01-01T00:00:00{body}</span>'


def run(text):
    return re.sub(r"<[^<>]*>", "", replace_editor_comments(text, []))


class EditorCommentParenTest(unittest.TestCase):
    def test_closing_paren_kept_for_open_paren(self):
        self.assertEqual(run("a (b" + comment("english note.)") + " c"), "a (b.) c")

    def test_stray_close_earlier_does_not_hide_open_paren(self):
        # a stray ")" earlier in the paragraph used to balance the count and drop the real one
        self.assertEqual(run("x) y (b" + comment("note)") + " c"), "x) y (b) c")

    def test_balanced_text_drops_comment_paren(self):
        self.assertEqual(run("a (b) c" + comment("note)") + " d"), "a (b) c d")

    def test_text_closing_after_comment_keeps_comment_paren_out(self):
        text = "a (b" + comment("note (M. K)") + ")</span> c"
        self.assertEqual(run(text), "a (b) c")


if __name__ == "__main__":
    unittest.main()
