"""Line 3 of the book: the publisher's copyright notice, in small gray print.

The notice text is kept in copyright.txt next to this file (one UTF-8 line), so the
scripts need no Hebrew literal for it. The markup is the one the library already
uses for such notice lines (for example in the KSK books and the MoreBooks responsa
books): <span style="color:Gray;"><small><small>TEXT</small></small></span>
"""
from pathlib import Path

COPYRIGHT_TEXT = (Path(__file__).resolve().parent / 'copyright.txt').read_text(
    encoding='utf-8').rstrip('\n')
COPYRIGHT_LINE = ('<span style="color:Gray;"><small><small>' + COPYRIGHT_TEXT
                  + '</small></small></span>')
