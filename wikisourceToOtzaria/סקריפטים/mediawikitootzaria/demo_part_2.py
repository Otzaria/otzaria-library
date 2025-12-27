import csv
import html
import json
import re

from mediawikitootzaria import htmltootzaria, mediawikiapi, mediawikitohtml, templates

mediawikiapi.BASE_URL = mediawikiapi.WIKISOURCE
templates.replacement_dict = templates.wikisource_replacement_dict


def read_order_from_csv(csv_file_path):
    with open(csv_file_path, "r", encoding="windows-1255") as csv_file:
        csv_reader = csv.reader(csv_file)
        for i in csv_reader:
            yield i


def main(csv_file_path):
    sup_num = 0
    all_sup = []
    title = "ספר השרשים"
    dict_links = []
    all_content = [f"<h1>{title}</h1>", 'רד"ק']
    lines = len(all_content)
    for book in read_order_from_csv(csv_file_path):
        h_level = 0
        book_url = book[0]
        content = mediawikiapi.get_page_content(book_url)
        for index, i in enumerate(book[1:], start=1):
            if i:
                all_content.append(f"<h{index}>{i}</h{index}>")
                lines += 1
                h_level = index + 1

        content = mediawikitohtml.media_wiki_list_to_html(content)
        content = mediawikitohtml.wikitext_to_html(content, h_level)
        content, sup = templates.remove_templates(content)
        content = htmltootzaria.process_body_html(content, h_level)
        content = htmltootzaria.adjust_html_tag_spaces(content)
        content = re.sub(r"<קטע (?:התחלה|סוף)=[^>]+/?>", "", content)
        strip_all = content.split("\n")
        all_content.extend(strip_all)
        for index, line in enumerate(strip_all, start=lines + 1):
            find = re.findall(r'<sup style="color: gray;">(\d+)</sup>', line)
            for i in find:
                dict_links.append({
                    "line_index_1": index,
                    "heRef_2": "הערות",
                    "path_2": f"הערות על {title}.txt",
                    "line_index_2": int(i) + sup_num,
                    "Conection Type": "commentary"
                })

        lines += len(strip_all)

        for k, value in sup.items():
            v = mediawikitohtml.wikitext_to_html(value)
            v = htmltootzaria.fix_comments(v)
            v = html.unescape(v)
            all_sup.append(f'{k} {v}')
            sup_num += 1

    json_file = f"{title}_links.json"

    if dict_links:
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(dict_links, f)
    with open(f"{title}.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_content))
    if all_sup:
        with open(f"הערות על {title}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(all_sup))


file_path = "ספר השרשים.csv"
main(file_path)
