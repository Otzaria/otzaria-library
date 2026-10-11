# -*- coding: utf-8 -*-
"""Tests for otzaria_markup / split_footnotes: one balanced Otzaria line per Ben-Yehuda line."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from otzaria_markup import convert_block_lines, convert_line, normalize_heading_levels
from split_footnotes import footnote_links, notes_book

LINE_CASES = [
    # block tags are unwrapped, inline tags mapped
    ('<p>a <strong>b</strong> c</p>', 'a <b>b</b> c'),
    ('<p><em>a</em> b</p>', '<i>a</i> b'),
    ('<blockquote><p>one</p> <p>two</p></blockquote>', 'one<br> two'),
    ('<p>a<br/> b</p>', 'a<br> b'),
    # a line holding only <br> becomes empty (the line itself stays)
    ('<br/>', ''),
    # headings lose their id
    ('<h2 id="x1">Title</h2>', '<h2>Title</h2>'),
    # gershayim, junk invisibles and odd spaces are normalized
    ('<p>\N{HEBREW LETTER AYIN}\'\'\N{HEBREW LETTER SHIN} \N{HEBREW LETTER AYIN}\'\'</p>', '\N{HEBREW LETTER AYIN}"\N{HEBREW LETTER SHIN} \N{HEBREW LETTER AYIN}\'\''),
    ('<p>\N{HEBREW LETTER SHIN}''\N{HEBREW LETTER RESH}\N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH} \N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH}''</p>', '\N{HEBREW LETTER SHIN}''\N{HEBREW LETTER RESH}\N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH} \N{HEBREW LETTER AYIN}\N{HEBREW LETTER RESH}'''),
    ('<p>a\N{EN SPACE}\N{EM SPACE} b\N{RIGHT-TO-LEFT MARK}c&nbsp;d</p>', 'a bc d'),
    ('<p>\N{HEBREW LETTER VAV}\N{ZERO WIDTH JOINER}\N{HEBREW POINT HOLAM}</p>', '\N{HEBREW LETTER VAV}\N{ZERO WIDTH JOINER}\N{HEBREW POINT HOLAM}'),
    # styled footnote marker -> bare <sup>, which is not an RTL box
    ('<p>word<sup style="color: #2563eb; font-weight: bold;">12</sup>.</p>', 'word<sup>12</sup>.'),
    # a paragraph split across two lines by hand: each half is balanced on its own
    ('<p>first <strong>half', 'first <b>half</b>'),
    ('second</strong> half</p>', 'second half'),
    # image placeholder captions (file names) are dropped with the remote image
    ('<figure><img src="https://example.org/3.png"/><figcaption>3.png</figcaption></figure>', ''),
    ('<figure><figcaption>A real caption</figcaption></figure>', 'A real caption'),
    # tables stay on one line; attributes other than spans are dropped
    ('<table><tbody><tr><td colspan="2" style="x"><p>a</p></td></tr></tbody></table>',
     '<table><tbody><tr><td colspan="2">a</td></tr></tbody></table>'),
    # links: web links kept, internal anchors unwrapped
    ('<a href="https://example.org">x</a> <a href="#part">y</a>', '<a href="https://example.org">x</a> y'),
    # text that looks like markup stays text
    ('x &lt;y&gt; &amp; z', 'x &lt;y&gt; & z'),
]

BOOK = [
    '<h1>Book</h1>',
    'Author',
    '<h3 id="a">Part</h3>',
    '<p>text<a class="footnote" href="#fn:1" id="fnref:1"><sup>1</sup></a> more'
    '<a href="#fn:2" id="fnref:2"><sup>2</sup></a></p>',
    '<br/>',
    '<h5 id="b">Deep</h5>',
    '<ol><li id="fn:1"><p>note <strong>one</strong> <a href="#fnref:1" title="return"> &#8617;</a></p></li> '
    '<li id="fn:2"><p>note two</p></li></ol>',
]


def main() -> int:
    failures = 0
    for src, expected in LINE_CASES:
        got = convert_line(src)
        if got != expected:
            failures += 1
            print(f"FAIL convert_line({src!r})\n  expected {expected!r}\n  got      {got!r}")

    lines, notes, refs = convert_block_lines(BOOK)
    expected_lines = ['<h1>Book</h1>', 'Author', '<h2>Part</h2>', 'text<sup>1</sup> more<sup>2</sup>', '', '<h3>Deep</h3>']
    checks = [
        (lines, expected_lines, "book lines"),
        (notes, ['note <b>one</b>', 'note two'], "notes"),
        (refs, [(4, 1), (4, 2)], "references"),
        (notes_book("Book", notes), ['<h1>הערות על Book</h1>', '<sup>1</sup> note <b>one</b>', '<sup>2</sup> note two'], "notes book"),
        ([(e["line_index_1"], e["line_index_2"], e["Conection Type"]) for e in footnote_links(refs, "x.txt")],
         [(4, 2, "footnotes"), (4, 3, "footnotes")], "links"),
        (normalize_heading_levels(['<h1>T</h1>', '<h4>a</h4>', '<h2>b</h2>', '<h4>c</h4>']),
         ['<h1>T</h1>', '<h2>a</h2>', '<h2>b</h2>', '<h3>c</h3>'], "heading levels"),
        # siblings under a skipped level (h2 -> h4, h4) stay siblings, not parent and child
        (normalize_heading_levels(['<h1>T</h1>', '<h3>p</h3>', '<h2>a</h2>', '<h4>a1</h4>', '<h4>a2</h4>',
                                   '<h2>b</h2>', '<h4>b1</h4>', '<h3>b2</h3>', '<h4>b21</h4>']),
         ['<h1>T</h1>', '<h2>p</h2>', '<h2>a</h2>', '<h3>a1</h3>', '<h3>a2</h3>',
          '<h2>b</h2>', '<h3>b1</h3>', '<h3>b2</h3>', '<h4>b21</h4>'], "sibling heading levels"),
    ]
    for got, expected, name in checks:
        if got != expected:
            failures += 1
            print(f"FAIL {name}\n  expected {expected!r}\n  got      {got!r}")

    total = len(LINE_CASES) + len(checks)
    print(f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
