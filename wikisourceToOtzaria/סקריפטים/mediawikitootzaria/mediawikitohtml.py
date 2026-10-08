"""מודל זה מכיל פונקציות להמרת פורמט mediawiki לhtml

מכיל את הפונקציות הבאות:
--------
*func:remove_templates
*func:wikitext_to_html

שים לב:
----
יתכן שיהיה צורך בהתאמת הפונקציה remove_templates

כמו"כ הפונקציה wikitext_to_html אינה מטפלת ברשימות מקוננות ובטבלאות לע"ע
"""

import re

import wikitextparser as wtp


def media_wiki_list_to_html(string: str) -> str:
    def list_type_of(pattern: str) -> str | None:
        # ':' ו-';' הם הזחה ולא רשימה - כל פריט נשאר פסקה משלו
        return {"*": "ul", "#": "ol"}.get(pattern[-1])

    def convert_list_to_html(wikilist: wtp._wikilist.WikiList, list_type: str | None) -> str:
        if list_type is None:
            parts = []
            for index, item in enumerate(wikilist.items):
                parts.append(item.strip())
                for sublist in wikilist.sublists(index):
                    parts.append(convert_list_to_html(sublist, list_type_of(sublist.pattern)).strip())
            return "\n\n" + "\n\n".join(parts) + "\n\n"
        html = f"<{list_type}>\n"
        for index, item in enumerate(wikilist.items):
            html += f"  <li>{item.strip()}</li>\n"
            sublists = wikilist.sublists(index)
            for sublist in sublists:
                html += convert_list_to_html(sublist, list_type_of(sublist.pattern))
        html += f"</{list_type}>\n"
        return html

    parsed = wtp.parse(string)
    for wikilist in parsed.get_lists():
        html_ordered_list = convert_list_to_html(wikilist, list_type_of(wikilist.pattern))
        string = string.replace(str(wikilist), html_ordered_list)
    return string


def remove_templates_old(wikitext: str) -> str:
    """מסיר תבניות מהתוכן, התבניות שצריך להסיר משתנות בין קובץ לקובץ."""
    wikitext = re.sub(r'{{מקור\|([^}]*)}}', r'\1', wikitext)
    cleaned_text = re.sub(r'{{[^{}]*}}', '', wikitext)
    return cleaned_text


def wikitext_to_html(wikitext: str, start_heading_level: int = 2) -> str:
    """ממיר קידודי מדיה ויקי לhtml, עדיין צריך לטפל ברשימות מקוננות וטבלאות"""
    # Step 1: Identify and protect HTML regions
    html_tags_pattern = re.compile(r"<(pre|nowiki)[^>]*>.*?</\1[^>]*>", re.DOTALL)  # Matches complete HTML tags
    html_regions = {}
    protected_text = wikitext

    for i, match in enumerate(html_tags_pattern.finditer(wikitext)):
        key = f"__HTML_REGION_{i}__"
        html_regions[key] = match.group(0)  # Save the HTML region
        protected_text = protected_text.replace(match.group(0), key)

    # protected_text = re.sub(r'==[ ]*?הערות שוליים[ ]*?==', "", protected_text)
    protected_text = re.sub(r'^====(.*?)====\s*$',
                            rf'\n<h{start_heading_level + 2}>\g<1></h{start_heading_level + 2}>\n', protected_text, flags=re.MULTILINE)
    protected_text = re.sub(r'^===(.*?)===\s*$',
                            rf'\n<h{start_heading_level + 1}>\g<1></h{start_heading_level + 1}>\n', protected_text, flags=re.MULTILINE)
    protected_text = re.sub(r'^==(.*?)==\s*$',
                            rf'\n<h{start_heading_level}>\g<1></h{start_heading_level}>\n', protected_text, flags=re.MULTILINE)

    # המרת רשימות (כוכביות) ל<ul> <li>
    protected_text = media_wiki_list_to_html(protected_text)

    # המרת קישורים פנימיים
    protected_text = re.sub(r'\[\[קטגוריה:.*?\]\]', '', protected_text)
    # היעד לא יכול להכיל "[" או "]]", אחרת ההתאמה חוצה קישור בלי | ומוחקת טקסט עד ה-| הבא
    protected_text = re.sub(r'\[\[((?:[^\[\]|]|\](?!\]))*)\|(.*?)\]\]', r'\2', protected_text)
    protected_text = re.sub(r'\[\[([^\[\]]*?)\]\]', r'\1', protected_text)  # במקרה של לינק בלי |
    # to do: re.dotall
    # המרת טקסט מודגש ('''text''' -> <b>text</b>)
    protected_text = re.sub(r"'''''(.*?)'''''", r'<b><i>\1</i></b>', protected_text)
    protected_text = re.sub(r"'''(.*?)'''", r"<b>\1</b>", protected_text)
    protected_text = re.sub(r"\+(.+?)\+", r"<b>\1</b>", protected_text)
    protected_text = re.sub(r"__(.*?)__", r'<u>\1</u>', protected_text)

    # המרת טקסט נטוי (''text'' -> <i>text</i>)
    protected_text = re.sub(r"''(.*?)''", r"<i>\1</i>", protected_text)

    # Convert external links
    protected_text = re.sub(r'\[(http[^\s]+) (.+?)\]', r'<a href="\1">\2</a>', protected_text)
    protected_text = re.sub(r'\[(http[^\s]+)\]', r'<a href="\1">\1</a>', protected_text)

    # Convert blockquotes
    protected_text = re.sub(r'^> (.+)', r'<blockquote>\1</blockquote>', protected_text, flags=re.MULTILINE)

    # Remove comments
    protected_text = re.sub(r'<!--.*?-->', '', protected_text, flags=re.DOTALL)

    for key, html_region in html_regions.items():
        protected_text = protected_text.replace(key, html_region)
    protected_text = "\n".join(list(map(lambda x: x.lstrip(":"), protected_text.split("\n"))))
    return protected_text


def fix_new_lines(text: str) -> str:
    """מתקן שורות חדשות בטקסט"""
    text = re.sub(r'([^\n])\n([^\n])', r'\1 \2', text)  # מחליף שורות חדשות במרווח
    text = re.sub(r'\n{2,}', r'\n', text)  # מחליף שורות חדשות מרובות בשורה חדשה אחת
    text = re.sub(r'^(?:[ \t]*<br>)+|(?:<br>[ \t]*)+$', '', text, flags=re.MULTILINE)
    return text
