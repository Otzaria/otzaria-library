import re

from mwparserfromhell.nodes.template import Template


def remove(*args) -> str:
    return ""


def new_line(*args) -> str:
    return "\n"


def bold(template: Template) -> str:
    return f"<b>{" ".join(map(str, template.params))}</b>"


def bold_and_parenthesize(template: Template) -> str:
    return f"(<b>{template.params[0]}</b>) ({template.params[1]})"


def parenthesize_only(template: Template) -> str:
    return f"({" ".join(map(str, template.params))})"


def parenthesize_one(template: Template) -> str:
    return f"({template.params[0]})"


def big(template: Template) -> str:
    return f"<big>{" ".join(map(str, template.params))}</big>"


def big_bold(template: Template) -> str:
    return f"<b><big>{" ".join(map(str, template.params))}</big></b>"


def bold_italic_and_gersim(template: Template) -> str:
    return f'"<b><i>{" ".join(map(str, template.params))}</i></b>"'


def gersim_and_parenthesize(template: Template) -> str:
    return f'"{template.params[0]}" ({template.params[1]})'


def keep_some_params(template: Template, params_to_keep: list[int]) -> str:
    result = []

    for i in params_to_keep:
        try:
            result.append(str(template.params[i]))
        except IndexError:
            continue

    return " ".join(result)


def bold_and_colon(template: Template) -> str:
    return f"<b>{" ".join(map(str, template.params))}</b>:"


def mmc(template: Template) -> str:
    parts = " ".join(map(str, template.params))
    return parts.replace("לפני=", "").replace("אחרי=", "")


def mz(template: Template) -> str:
    return f'({template.params[0]} {template.params[1]}) "{template.params[2]}"' if len(template.params) >= 3 else str(template.params[0])


def zp(template: Template) -> str:
    return f'"{str(template.params[0]).replace("תוכן=", "")}" ({str(template.params[1]).replace("מקור=", "")})'


def h_1(template: Template) -> str:
    return f"<h1>{" ".join(map(str, template.params))}</h1>"


def save_all(template: Template) -> str:
    return " ".join(map(str, template.params))


def space(template: Template) -> str:
    return " ".join(
        " ".join(str(param))
        for param in template.params
    )


def line_under(template: Template) -> str:
    return f"<u>{" ".join(map(str, template.params))}</u>"


def left_align(template: Template) -> str:
    return f'<p style="text-align:left">{" ".join(map(str, template.params))}</p>'


def ver_fix(template: Template) -> str:
    return f"({template.params[0]}) [{template.params[1]}]"


def line_break(*args) -> str:
    return "<br>"


def positional(template: Template) -> list[str]:
    return [str(p.value) for p in template.params if not p.showkey or str(p.name).strip().isdigit()]


def join_positional(template: Template) -> str:
    return " ".join(positional(template))


def last_positional(template: Template) -> str:
    """ברירת מחדל לתבנית לא ממופה: הטקסט המוצג הוא בדרך כלל הפרמטר האחרון.
    שאר הפרמטרים (גודל גופן, צבע, מזהה עוגן) אינם טקסט."""
    params = [p for p in positional(template) if p.strip()]
    return params[-1] if params else ""


def keep_param_or_first(template: Template, index: int) -> str:
    params = positional(template)
    if len(params) > index:
        return params[index]
    return params[0] if params else ""


def anchor(template: Template) -> str:
    params = positional(template)
    return params[1] if len(params) > 1 else ""


def mm(template: Template) -> str:
    params = positional(template)
    return f"({params[0]})" if params and params[0].strip() else ""


def square_brackets(template: Template) -> str:
    return f"[{' '.join(positional(template))}]"


def mmq(template: Template) -> str:
    params = positional(template)
    return params[2] if len(params) > 2 else (params[0] if params else "")


def note_text(template: Template, index: int = 0) -> str:
    params = positional(template)
    if len(params) > index:
        return params[index]
    # "=" בטקסט ההערה הופך אותו לפרמטר בעל שם; הטקסט הוא הפרמטר כולו
    raw = [str(p) for p in template.params]
    return raw[index] if len(raw) > index else ""


def margin_note(template: Template, index: int = 0) -> str:
    """כל פסקה בתג small משלה, אחרת process_body_html מאחד את הפסקאות לשורה אחת."""
    # שבירת שורה בסוף פסקה ({{ש}} או <br>) מיותרת כשכל פסקה בשורה משלה
    paragraphs = [re.sub(r"(?:\s*(?:<br\s*/?>|\{\{\s*ש\s*\}\}))+$", "", p.strip())
                  for p in note_text(template, index).split("\n\n")]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return ""
    paragraphs[0] = "[" + paragraphs[0]
    paragraphs[-1] += "]"
    return "\n\n".join(f"<small>{p}</small>" for p in paragraphs)
