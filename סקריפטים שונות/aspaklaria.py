import html
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

from aspaklaria_fixes import fix_page


def fix_text(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


content = ""
pages = {}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
BASE_URL = "https://www.aspaklaria.info/"

output_path = Path("output.txt")
index_url = f"{BASE_URL}AlepBet_Title_V25.html"
response = requests.get(index_url, headers=HEADERS)
index_soup = BeautifulSoup(response.text, "html.parser")
links = index_soup.find_all("a")

for link in links:
    href = link.get("href")
    content += f"<h2>{fix_text(link.get_text())}</h2>\n"
    print(f"{href=} {fix_text(link.text)=}")
    print(f"{BASE_URL}{href}")

    sub_index = requests.get(f"{BASE_URL}{href}", headers=HEADERS)
    sub_href = href.split("/")[0]
    sub_index_soup = BeautifulSoup(sub_index.text, "html.parser")
    sub_links = sub_index_soup.find_all("a")

    for page in sub_links:
        page_href = page.get("href")
        print(f"{page_href=} {fix_text(page.text)=}")
        print(f"{BASE_URL}{sub_href}/{page_href}")

        sub_sub_index = requests.get(f"{BASE_URL}{sub_href}/{page_href}", headers=HEADERS)
        page_soup = BeautifulSoup(sub_sub_index.text, "html.parser")
        page_body = page_soup.find("body")

        if not page_body:
            continue

        page_lines = []

        for child in page_body.children:
            if isinstance(child, Tag):
                if re.match(r"^h[1-6]$", child.name):
                    current_level = int(child.name[1])
                    child.name = f"h{min(current_level + 2, 6)}"
                    line_content = fix_text(str(child))
                    if line_content:
                        page_lines.append(line_content)

                elif child.name == "p":
                    p_inner_html = child.decode_contents()
                    line_content = fix_text(p_inner_html)
                    if line_content:
                        page_lines.append(line_content)

                else:
                    line_content = fix_text(str(child))
                    if line_content:
                        page_lines.append(line_content)

            else:
                text_node = fix_text(str(child))
                if text_node:
                    page_lines.append(text_node)

        page_name = fix_text(page.text)
        pages[page_name] = page_lines
        page_lines = fix_page(page_name, page_lines, pages)
        content += "\n".join(page_lines) + "\n"

content = re.sub(r"\n{2,}", "\n", content).strip()

with output_path.open("w", encoding="utf-8") as f:
    f.write(content)
