from mwparserfromhell.nodes.template import Template


def remove(*args) -> str:
    return ""


def bold_and_parenthesize(template: Template) -> str:
    return f"(<b>{template.params[0]}</b>) ({template.params[1]})"


def parenthesize_only(template: Template) -> str:
    return f"({" ".join(map(str, template.params))})"


def bold_italic_and_gersim(template: Template) -> str:
    return f'"<b><i>{" ".join(map(str, template.params))}</i></b>"'


def keep_some_params(template: Template, params_to_keep: list[int]) -> str:
    kept_params = [str(template.params[i]) for i in params_to_keep if i < len(template.params)]
    return " ".join(kept_params)
