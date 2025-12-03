import json  # noqa: I001, INP001
from pathlib import Path

import pandas as pd

from utils import *
from otzaria.get_from_export import Book
from otzaria.utils import footnotes, sanitize_filename
from pyluach.dates import GregorianDate
from tqdm import tqdm


def read_file(file_path: Path) -> set[str]:
    with file_path.open("r", encoding="utf-8") as f:
        return set(f.read().split("\n"))


def recursive_register_categories(
    index: list | dict,
    data: list[dict[str, str | list[str]]] | None = None,
    tree: list[str] | None = None,
) -> dict[str, int]:
    if tree is None:
        tree = []
    if data is None:
        data = {}
    if isinstance(index, list):
        for item in index:
            recursive_register_categories(item, data, tree)
    elif isinstance(index, dict):
        if index.get("contents"):
            tree.append(index["heCategory"])
            for item in index["contents"]:
                recursive_register_categories(item, data, tree)
            tree.pop()
        if index.get("title") and "order" in index:
            data[index["title"]] = index["order"]
    return data


def get_book(book_title: str, text_file_path: Path, schema_file_path: Path, lang: str):
    book_ins = Book(book_title,
                    lang,
                    text_file_path,
                    schema_file_path)
    book_content = book_ins.process_book()
    metadata, categories = book_ins.get_metadata()
    return book_content, metadata, categories, book_ins.refs


def main(json_folder: Path, schemas_folder: Path, output_folder: Path, lang: str) -> None:
    for root, _, files in tqdm(json_folder.walk()):
        for file in files:
            file_path = root / file
            if file_path.parent.name.lower() != lang or file != "merged.json":
                continue
            try:
                text_file = file_path
                title = file_path.parent.parent.name.replace(' ', '_')
                original_title = title
                if title in file_name_replacements:
                    title = file_name_replacements[title]
                schema_file_name = schemas_folder / f'{title}.json'
                book_content, metadata, categories, refs = get_book(title, text_file, schema_file_name, lang)
                title = sanitize_filename(metadata["title"])
                if metadata["title"] in files_black_list or title in files_black_list or original_title in files_black_list or (any(author in authors_black_list for author in metadata["heAuthors"]) and metadata["title"] not in books_white_list and title not in books_white_list and original_title not in books_white_list):
                    continue
                if any(author not in authors_white_list for author in metadata["heAuthors"]) and metadata["title"] not in books_white_list and title not in books_white_list and original_title not in books_white_list:
                    need_to_check_authors.append({metadata["title"]: [author for author in metadata["heAuthors"] if author not in authors_white_list]})
                    continue
                output_path_temp = [sanitize_filename(i) for i in categories]
                output_path = []
                for i in output_path_temp:
                    for key, value in folder_name_replacements.items():
                        if key in i:
                            i = value
                    output_path.append(i)
                book_output_folder = Path(output_folder).joinpath(*output_path)
                book_output_folder.mkdir(parents=True, exist_ok=True)
                output_file_name = book_output_folder / title
                book_content_copy = []
                dict_links = []
                all_footnotes = []
                metadata["title"] = title
                metadata["original_title"] = original_title
                comp_date = metadata["compDate"]
                pub_date = metadata["pubDate"]
                metadata["compDateHeb"] = [GregorianDate(year=int(x), month=1, day=1).to_heb().hebrew_year(thousands=True) for x in comp_date] if comp_date else []
                metadata["pubDateHeb"] = [GregorianDate(year=int(x), month=1, day=1).to_heb().hebrew_year(thousands=True) for x in pub_date] if pub_date else []
                for index, line in enumerate(book_content, start=1):
                    if "footnote-marker" in line:
                        line, footnotes_list = footnotes(line)
                        for foot_note in footnotes_list:
                            dict_links.append({
                                "line_index_1": index,
                                "heRef_2": "הערות",
                                "path_2": f"הערות על {title}.txt",
                                "line_index_2": len(all_footnotes) + 1,
                                "Conection Type": "commentary"
                            })
                            all_footnotes.append(foot_note)
                    book_content_copy.append(line)
                with open(f'{output_file_name}.txt', 'w', encoding='utf-8') as f:
                    f.writelines(book_content_copy)
                metadata["order"] = toc_content.get(metadata.get("enTitle"))
                all_metadata.append(metadata)
                for entry in refs:
                    entry["path"] = title
                refs_list.extend(refs)
                if all_footnotes:
                    footnotes_file = book_output_folder / f"הערות על {title}.txt"
                    with footnotes_file.open("w", encoding="utf-8") as f:
                        f.write("\n".join(all_footnotes))
                    json_file = links_path / f"{title}_links.json"
                    with json_file.open("w", encoding="utf-8") as f:
                        json.dump(dict_links, f)
            except Exception as e:
                error_file_path.parent.mkdir(parents=True, exist_ok=True)
                with error_file_path.open("a", encoding="utf-8") as f:
                    f.write(f"{file_path} {e}\n")


toc_file_path = Path(CONFIG["sefaria"]["toc_file"])
with toc_file_path.open("r", encoding="utf-8") as f:
    toc = json.load(f)
toc_content = recursive_register_categories(toc)
all_metadata = []
json_folder = Path(CONFIG["sefaria"]["json_folder"])
schemas_folder = Path(CONFIG["sefaria"]["schemas_folder"])
files_black_list_file_path = Path(CONFIG["sefaria"]["files_black_list_file_path"])
authors_black_files_list_file_path = Path(CONFIG["sefaria"]["authors_black_files_list_file_path"])
authors_white_files_list_file_path = Path(CONFIG["sefaria"]["authors_white_files_list_file_path"])
books_white_list_file_path = Path(CONFIG["sefaria"]["files_white_list_file_path"])
files_black_list = read_file(files_black_list_file_path)
authors_black_list = read_file(authors_black_files_list_file_path)
authors_white_list = read_file(authors_white_files_list_file_path)
books_white_list = read_file(books_white_list_file_path)
need_to_check_authors = []
need_to_check_authors_file_path = Path(CONFIG["sefaria"]["need_to_check_authors_file_path"])
output_folder = Path(CONFIG["otzaria"]["export_books_path"])
output_folder.mkdir(parents=True, exist_ok=True)
links_path = Path(CONFIG["otzaria"]["export_links_path"])
error_file_path = Path(CONFIG["otzaria"]["log_path"]) / "error.txt"
error_file_path.parent.mkdir(parents=True, exist_ok=True)
links_path.mkdir(parents=True, exist_ok=True)
folder_name_replacements_file_path = Path(CONFIG["otzaria"]["folder_name_replacements_file_path"])
file_name_replacements_file_path = Path(CONFIG["otzaria"]["file_name_replacements_file_path"])
folder_name_replacements = read_csv_file(folder_name_replacements_file_path)
file_name_replacements = read_csv_file(file_name_replacements_file_path)
lang = CONFIG["lang"]
refs_list = []
main(json_folder=json_folder, schemas_folder=schemas_folder,
     output_folder=output_folder, lang=lang)
df = pd.DataFrame(refs_list)
df.to_csv(Path(CONFIG["otzaria"]["refs_all_file_path"]), index=False)
metadata_file_path = Path(CONFIG["otzaria"]["books_metadata_file_path"])
with metadata_file_path.open("w", encoding="utf-8") as f:
    json.dump(all_metadata, f, ensure_ascii=False, indent=4)
with need_to_check_authors_file_path.open("w", encoding="utf-8") as f:
    json.dump(need_to_check_authors, f, ensure_ascii=False, indent=4)
