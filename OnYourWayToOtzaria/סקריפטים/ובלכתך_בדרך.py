from bs4 import BeautifulSoup
import os
import re
import html as html_module

h_dict = {"book":1, "chap":2, "p":3}
t_dict = {1:"אונקלוס",2:'תרגום ירושלמי',3:'רש"י',4:'רמב"ן',5:'אבן עזרא',6:'ספורנו',7:'בעל הטורים',
8:'אור החיים',9:'תורה תמימה',10:'מצודת דוד',11:'מצודת ציון',12:'רלב"ג',14:'רע"ב',15:'תוי"ט',17:'רש"י',
18:'תוס',20:'משנ"ב',21:'ביאור הלכה',23:'תרגום זוהר',28:'כלי יקר ',29:'מלבי"ם תוכן',30:'מלבי"ם פירוש המילות',31:'מלבי"ם ביאור המילות'}

TEXT_LT = "\ue000"

# '' between two Hebrew letters is gershayim (ע''ש -> ע"ש); after a word it closes a quote (וכו'')
GERSHAYIM_PAIR_RE = re.compile(r"(?<=[\u05d0-\u05ea\u0591-\u05c7])''(?=[\u05d0-\u05ea])")
# ...unless it opens a quote glued to a prefix letter (ש''אין אב'') that closes later in the line
QUOTE_PREFIX_RE = re.compile(r"(?<![א-ת֑-ׇ])(?:[בדהוכלמש][֑-ׇ]*){1,3}")
QUOTE_WORD_RE = re.compile(r"(?:[א-ת][֑-ׇ]*){2}")
QUOTE_CLOSE_RE = re.compile(r"(?<=[א-ת֑-ׇ.,;:!?])''(?![א-ת'])")


def opens_quote(s, start, end):
    if not QUOTE_WORD_RE.match(s, end):
        return False
    if not any(m.end() == start for m in QUOTE_PREFIX_RE.finditer(s, max(0, start - 16), start)):
        return False
    stop = s.find("\n", end)
    for m in re.finditer("''", s[end:] if stop < 0 else s[end:stop]):
        p = end + m.start()
        if GERSHAYIM_PAIR_RE.match(s, p):
            continue
        return bool(QUOTE_CLOSE_RE.match(s, p))
    return False


def gershayim(s):
    return GERSHAYIM_PAIR_RE.sub(lambda m: m.group() if opens_quote(s, m.start(), m.end()) else '"', s)
# junk invisibles: bidi marks, BOM, zero-width space, soft hyphen, controls.
# ZWJ/ZWNJ survive only before a point (vav+ZWJ+holam renders holam haser)
INVISIBLE_RE = re.compile("[\ufeff\u200b\u200e\u200f\u202a-\u202e\u2060\u2066-\u2069\u00ad\x00-\x08\x0b-\x1f\x7f-\x9f]"
                          "|[\u200c\u200d](?![\u05b0-\u05c7])")
ODD_SPACE = "\t\u00a0\u2000-\u200a\u202f\u205f\u3000"
SPACE_RUN_RE = re.compile(f"[ {ODD_SPACE}]*[{ODD_SPACE}][ {ODD_SPACE}]*")


# תו גופן Symbol מ-Word (F000+קוד): חץ שמאלה, אחרת נראה כריבוע ריק
SYMBOL_FONT = {0xF0AC: "\u2190"}


def normalize_chars(text):
    text = SPACE_RUN_RE.sub(" ", INVISIBLE_RE.sub("", text)).translate(SYMBOL_FONT)
    return gershayim(text)

def adjust_html_tag_spaces(html):
    start_pattern = r'(<[^/<>]+?>)([ ]+)' 
    end_pattern = r'([ ]+)(</[^<>]+?>)' 
    # Move spaces from inside the closing tag to after the tag
    while re.findall(end_pattern , html):
        html = re.sub(end_pattern, r'\2\1', html)

    # Move spaces from the beginning of tags to before the tags
    while re.findall(start_pattern, html):
        html = re.sub(start_pattern , r'\2\1', html)
    # Clean up any double spaces created by the previous step
    html = re.sub(r'[ ]{2,}', ' ', html)

    return html

def check_line(line):
    return re.search(r"[a-zA-Zא-ת0-9]+", line)

def process_body_xml(xml_content):
    title = None
    first_chap = False
    promoted = set()  # כותרות p בתוך פרק שדולג עולות רמה, כדי שלא יקפצו מ-h1 ל-h3
    carector_list = ['<?xml version="1.0" ?>', "<![CDATA[", "]]>", '<?xml version="1.0" encoding="utf-8"?>']
    for i in carector_list:
        xml_content = xml_content.replace(i, " ")
    xml_content = re.sub(r"<!--[^א-ת]+?-->","", xml_content)
    xml_content = re.sub(r"<\?xml.+?\?>","", xml_content)
    soup = BeautifulSoup(xml_content, "lxml")
    # '<' של טקסט מסומן לפני הוספת הכותרות, כדי שלא יפוענח בסוף לתג גולמי
    for text in soup.find_all(string=lambda t: "<" in t):
        text.replace_with(text.replace("<", TEXT_LT))
    for tag in soup.find_all():
        if tag.name:
            if tag.name.lower() in ('html', "body", "d" , "iri", "pid", "qm", "rb", "sp", "tf", "col3", "f", "a"):
                tag.unwrap()
            elif tag.name.lower() in ("center", "sid1", "sid2", "sid3", "sid4", "sidcom1", "sidcom2", "sidcom4",
                                    "tos", "e", "c", "m", "bl", "ps"):
                tag_replace = ""
                if tag.name.lower() == "center":
                    tag_replace += "text-align: center;"
                elif tag.name.lower() in ("sid1"):
                    tag_replace += "font-size:95%; color:RGB(0,0,255); text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "sid2":
                    tag_replace += "font-size:110%; font-weight:bold;text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "sid3":
                    tag_replace += "font-weight:bold;text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "sid4":
                    tag_replace += "color: green;"
                elif tag.name == "sidcom1":
                    tag_replace += "color:RGB(127,127,127); font-family: arial; font-size:80%;text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "sidcom2":
                    tag_replace += "color:RGB(0,127,127); font-family: arial; font-size:85%;text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "sidcom4":
                    tag_replace += "padding:10; margin:10;  background-color=RGB(244,244,244);text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "tos":
                    tag_replace += "background-color: #AAAAAA;text-shadow:0 0px 0 white;"
                elif tag.name.lower() == "e":
                    tag_replace += "font-size:100%; display:inline;"
                elif tag.name.lower() == "c":
                    tag_replace +=  "font-weight:bold; visibility: visible; display:inline; font-size:100%;"
                elif tag.name.lower() == "bl":
                    tag_replace += "font-weight:bold; color:#0000FF; font-size:110%;"
                elif tag.name.lower() == "n":
                    tag_replace += "color:#888888; font-size:80%;"
                elif tag.name.lower() == "m":
                    tag_replace += "color:#444444; font-size:80%;"
                elif tag.name.lower() == "ps":
                    tag_replace += "font-weight:bold; color:#0000ff;"
                if tag.attrs.get("style"):
                    tag.attrs["style"] += tag_replace
                elif tag_replace:
                    tag.attrs["style"] = tag_replace
                tag.name = 'span'
                
            elif tag.name.lower() in ("script", "style", "pid", "input"):
                tag.decompose()
            elif tag.name.lower() in ("book","chap","p"):
                name = tag.attrs.get("n")
                if name:
                    if h_dict.get(tag.name) == 1:
                        title = name.strip()
                        first_chap = True
                    # פרק ראשון ששמו כשם הספר היה יוצר כותרת h2 כפולה ל-h1
                    elif tag.name == "chap" and first_chap and name.strip() == title:
                        promoted.update(id(p) for p in tag.find_all("p"))
                    elif name.strip() not in ("-", ".", "_"):
                        level = h_dict.get(tag.name) - (id(tag) in promoted)
                        tag.insert_before(f"\n<h{level}>{name.strip()}</h{level}>\n")
                    if tag.name == "chap":
                        first_chap = False
                elif tag.name == "p":
                    tag.insert_before("\n")
                    tag.insert_after("\n")
                tag.unwrap()
            elif tag.name.lower() == "t":
                name = tag.attrs.get("i").strip()
                if name:
                    name_2 = t_dict.get(int(name))
                    new_tag = soup.new_tag("b")
                    new_tag.string = name_2
                    new_tag.attrs["style"] = "color: gray;"
                    tag.insert_before(new_tag)
                    tag.insert_before(" ")
                tag.unwrap()

            elif tag.name.lower() in ("span", "div"):
                tag_class = tag.attrs.get("class")
                if tag_class:
                    class_replace = ""
                    if tag_class == ["ot"]:
                        pass
                    elif tag_class == ["answer"]:
                        class_replace += "padding:3px;background-color:#CCCCCC;"
                    elif tag_class == ["tfilaq"]:
                        class_replace += "border-bottom: 2px dotted blue; margin: 20px 0;"
                    elif tag_class == ["bothq"]:
                        class_replace += "margin: 0;display: inline; border-bottom: 2px dashed #0000FF;"
                    elif tag_class == ["rashiq"]:
                        class_replace += "margin: 0;display: inline;border-bottom: 2px dashed #990000;"
                    elif tag_class == ["tosfotq"]:
                        class_replace += "margin: 0;display: inline;border-bottom: 2px dashed #006600;"
                    elif tag_class == ["fq"]:
                        class_replace += "margin: 0;display: inline;border-bottom: 2px dashed #0000FF;"
                    elif tag_class == ["al"]:
                        class_replace += "margin: 0;display: inline;color: #0000ff;"
                    if tag.attrs.get("style"):
                        tag.attrs["style"] += class_replace
                    elif class_replace:
                        tag.attrs["style"] = class_replace
                    del tag.attrs["class"]

    for tag in soup.find_all(recursive=False):
        tag_str = str(tag)
        tag_str = tag_str.replace("\n", " ")
        new_tag = BeautifulSoup(tag_str, "html.parser").find()
        tag.replace_with(new_tag)
    for tag in soup.find_all():
        if not tag.get_text(strip=True) and tag.name != "br":
            tag.decompose()
    
    return str(soup), title

def convert_file(file_path, target_file, file_name):
    try:
        with open (file_path, "r", encoding = "utf-8") as file:
            content = file.read()
    except UnicodeDecodeError:
        with open (file_path, "r", encoding = "windows-1255") as file:
            content = file.read()
    fix_xml, title = process_body_xml(content)
    fix_spaces = adjust_html_tag_spaces(fix_xml).splitlines()
    output_text = [f"<h1>{title}</h1>" if title else f"<h1>{file_name}</h1>", ""] + [line.strip() for line in fix_spaces if check_line(line)]
    join_lines = normalize_chars(html_module.unescape("\n".join(output_text))).replace(TEXT_LT, "&lt;")
    with open(target_file, "w", encoding = "utf-8") as output:
        output.write(join_lines)

def main():
    books_folder = "ובלכתך בדרך"
    target_path = os.path.join("..", "ספרים", "לא ממויין")
    for root, dir, file in os.walk(books_folder):
        for file_name in file:
            if file_name.lower().endswith(".txt"):
                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(root, books_folder)
                destination_path = os.path.join(target_path, relative_path)
                os.makedirs(destination_path, exist_ok=True)
                target_file = os.path.join(destination_path, file_name)
                convert_file(file_path, target_file, file_name[:-4])
                print(file_path)


if __name__ == "__main__":
    main()
