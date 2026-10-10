from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable
from functools import partial

import mwparserfromhell
from mwparserfromhell.nodes.template import Template
from wikiexpand.expand import ExpansionContext
from wikiexpand.expand.templates import TemplateDict

from . import mediawikiapi, template_funcs, utils

TemplateAction = Callable[[Template], str]

wikisource_replacement_dict: dict[str, Callable[[Template], str] | None] = {
    "קיצור דרך": template_funcs.remove,
    "פרשן על פסוק": template_funcs.remove,
    "צמ": template_funcs.bold_and_parenthesize,
    "קטע של פירוש על פסוק": template_funcs.remove,
    "#קטע": template_funcs.remove,
    "צ": template_funcs.bold_italic_and_gersim,
    "קישור למחבר": template_funcs.remove,
    "כו": template_funcs.remove,
    "טקסט מושלם": template_funcs.remove,
    "ש": template_funcs.line_break,
    "עמוד": template_funcs.remove,
    "ק": template_funcs.parenthesize_one,
    "ג": template_funcs.big,
    "אקרוסטיכון": template_funcs.big_bold,
    "בעבודה": template_funcs.remove,
    "סרגל דקדוקי הטעמים": template_funcs.remove,
    "פפ": template_funcs.remove,
    "הערות שוליים": template_funcs.remove,
    "מ:טעמי המקרא": template_funcs.remove,
    "מ:שוליים": template_funcs.remove,
    "מכלול": template_funcs.remove,
    "ממכ": template_funcs.mmc,
    "גדול-מודגש": template_funcs.big_bold,
    "קטן": template_funcs.parenthesize_only,
    "ש-רווח": template_funcs.space,
    "ערך עם עוגן": template_funcs.big_bold,
    "מיזמים": template_funcs.remove,
    "יצירה": template_funcs.remove,
    "היברובוקס": template_funcs.remove,
    "עוגן": template_funcs.anchor,
    "עוגן1": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "קט": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "ציטוטון": template_funcs.gersim_and_parenthesize,
    "מצ": template_funcs.mz,
    "צמפ": template_funcs.mz,
    "סרגל ניווט": template_funcs.remove,
    "קיצור": partial(template_funcs.keep_some_params, params_to_keep=[1]),
    "!": template_funcs.remove,
    "צפ": template_funcs.zp,
    "נ": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "ממורכז": template_funcs.save_all,
    "דף שער": template_funcs.remove,
    "הפניה-גמ": partial(template_funcs.keep_some_params, params_to_keep=[0, 1, 2]),
    "ממ": template_funcs.mm,
    "ממר": template_funcs.square_brackets,
    "ממק": template_funcs.mmq,
    "צבע גופן": partial(template_funcs.keep_some_params, params_to_keep=[1]),
    "*": lambda *_: "•",
    "ב": None,
    "גדול": template_funcs.bold,
    "גופן": partial(template_funcs.keep_param_or_first, index=2),
    "גמט": partial(template_funcs.keep_some_params, params_to_keep=[-1]),
    "גמט גדש": None,
    "דה מפרש": template_funcs.bold_and_colon,
    "המרת או.סי.אר 2": template_funcs.remove,
    "הערה": None,
    "הפניה לפסוקים": None,
    "הפניה-ירושלמי": None,
    "חול": None,
    "טורים שווים": None,
    "כותרת רצה": None,
    "לא נשלם": None,
    "להשלים": None,
    "מכפלת גימטריא": None,
    "ממ הזר": None,
    "ממ זהא": None,
    "ממ זהר": None,
    "ממ משנה": None,
    'ממ רמב"ם': None,
    "ממז זהר": None,
    "מפרשים למסכת נדרים": None,
    "מפרשים למסכת נזיר": None,
    "מר": None,
    "מרכז": template_funcs.join_positional,
    "ניווט ספר": None,
    "ספר התגין": None,
    "ספר חול": None,
    'ספר מכלול (רד"ק)/לפי דפים/סו ב': None,
    "ספר מכלול/לפי דפים/לד א": None,
    'עין משפט טוש"ע': template_funcs.parenthesize_only,
    "פירוש נוסף": None,
    "ציור סוף פסקה": template_funcs.remove,
    "ציטוט": None,
    "צתב": None,
    "קו תחתי": template_funcs.line_under,
    "רווח בין אותיות": template_funcs.space,
    "ררר": None,
    "שוליים": None,
    "שולייםלמטה": None,
    "שם": None,
    "שמאל": template_funcs.left_align,
    "תוכן עניינים שטוח": template_funcs.new_line,
    'תותו"א': template_funcs.remove,
    "תיקון גירסה": template_funcs.ver_fix,
    "M": template_funcs.remove,
    "ניווט קבא דקשייתא": template_funcs.remove,
    "ססס": template_funcs.remove,
    "שולי הגליון": template_funcs.remove,
    "ביאורים": template_funcs.remove,
    "דיקטה": template_funcs.remove,
    "ניווט כללי עליון": template_funcs.remove,
    "ניווט כללי תחתון": template_funcs.remove,
    "הועלה אוטומטית": template_funcs.remove,
    "OCR": template_funcs.remove,
    "-": template_funcs.remove,
    "כאן": template_funcs.remove,
    "כ": template_funcs.remove,
    "תמונה להוספה": template_funcs.remove,
    "אצבע מורה": template_funcs.remove,
    "יישור לשמאל": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "אישים": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "אישי ישראל": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "כניסה משני צדדים": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "מידע": partial(template_funcs.keep_some_params, params_to_keep=[0]),
    'הג"ה': partial(template_funcs.keep_some_params, params_to_keep=[0]),
    "ביאור": partial(template_funcs.margin_note, index=0),
    "תוספת": partial(template_funcs.margin_note, index=1),
}

# הערות גליון מוצגות בגוף הטקסט, מסומנות ומוקטנות כדי שלא יתערבבו בו
footnote_templates: dict[str, int] = {"הערה": 0}

replacement_dict: dict[str, TemplateAction] = {}
# תבניות שלא מופו בהרצה - כדאי להוסיף להן מיפוי
unmapped_templates: Counter[str] = Counter()


def filter_templates(string: str, all_templates: list[str] | None = None, template_dict: TemplateDict | None = None) -> list[list[str]] | bool:
    """מחזיר את התבניות ברמה העליונה של הטקסט."""
    string_2 = []
    parsed = mwparserfromhell.parse(string)
    templates = parsed.filter_templates(parsed.RECURSE_OTHERS)
    if templates:
        for template in templates:
            template_name = str(template.name).strip()
            # טיפול בתבניות מיוחדות שמתחילות ב #
            if template_name.startswith("#") and ":" in template_name:
                template_name = template_name.split(":", 1)[0].strip()
            if all_templates and template_dict and template_name in all_templates:
                template_str = convert_templates(str(template), template_dict)
            elif template_name in footnote_templates:
                template_str = template_funcs.note_text(template, footnote_templates[template_name])
            elif template_name in replacement_dict:
                action = replacement_dict[template_name]
                template_str = action(template) if action else ""
            else:
                template_str = template_funcs.last_positional(template)
                unmapped_templates[template_name] += 1
            string_2.append([str(template), template.name, template_str])
        return string_2
    return False


def clean_comment(comment: str, all_templates: list | None, template_dict: TemplateDict) -> str:
    """מסיר תבניות מההערה."""
    while True:
        replace = filter_templates(comment, all_templates, template_dict)
        if not replace:
            break
        for i in replace:
            rp = i[2]
            comment = comment.replace(i[0], rp)
    return comment


def remove_templates(wikitext: str, template_dict=None) -> tuple[str, dict]:
    """
    מסיר תבניות ללא פרמטרים
    תבנית עם פרמטרים התבנית מוסרת והפרמטרים נשארים
    תבנית הערה מוסרת ונכנסת הפנייה במקומה. """
    if template_dict:
        all_templates = [i for i in template_dict.keys()]
        template_dict = templates_dict(template_dict)
    else:
        all_templates = None
        template_dict = None

    dict_comments = {}
    sup = 0
    remove_templates_dict = {
        "ש": "<br>",
        "חלקי": "",
        # "גופן": "",
    }
    while True:
        replace = filter_templates(wikitext, all_templates, template_dict)
        if replace is False:
            break
        for i in replace:
            if i[1].strip() in footnote_templates:
                sup += 1
                dict_comments[sup] = clean_comment(i[2], all_templates, template_dict)
                rp = f'<sup style="color: gray;">{sup}</sup>'
            elif i[1].strip() in remove_templates_dict:
                rp = remove_templates_dict[i[1].strip()]
            else:
                rp = i[2]
            wikitext = wikitext.replace(i[0], rp)
    counter = 0
    sorted_dict = {}
    for num in re.findall(r'<sup style="color: gray;">(\d+)</sup>', wikitext):
        counter += 1
        wikitext = wikitext.replace(rf'<sup style="color: gray;">{num}</sup>', rf'<sup style="color: gray;">{counter}</sup>')
        sorted_dict[counter] = dict_comments[int(num)]
    return wikitext, sorted_dict


def templates_dict(dict_content: dict) -> TemplateDict:
    tpl = TemplateDict()
    for key, value in dict_content.items():
        tpl[key] = value

    return tpl


def convert_templates(mw_content: str, tpl: TemplateDict) -> str:
    ctx = ExpansionContext(templates=tpl)
    expanded_text = str(ctx.expand(mw_content))
    return expanded_text


def get_all_templates() -> None:
    import os
    base_folder = r"C:\Users\משתמש\Desktop\תבניות ויקיטקסט"
    mediawikiapi.BASE_URL = mediawikiapi.WIKISOURCE
    all_templates = mediawikiapi.get_list_by_ns(10)
    for template in all_templates:
        content = mediawikiapi.get_page_content(template)
        file_path = os.path.join(base_folder, f"{utils.sanitize_filename(template.split(":")[-1])}.txt")
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
        print(template)


def get_template_from_site(site: str, template_name: str, json_file_path: str) -> None:
    with open(json_file_path, "r", encoding="utf-8") as f:
        template = json.load(f)
    if not template.get(template_name):
        mediawikiapi.BASE_URL = site
        mediawikiapi.get_page_content(f"תבנית:{template_name}")
        template = [template_name] = ""
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=4)
