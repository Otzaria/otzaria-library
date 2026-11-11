import csv
import json
import os
import traceback

import pandas as pd
from otzaria.get_from_sefaria import Book
from otzaria.sefaria_api import SefariaApi
from otzaria.utils import footnotes, recursive_register_categories, sanitize_filename
from pyluach import dates
from tqdm import tqdm


def new_folder_name() -> tuple[str, str]:
    today = dates.HebrewDate.today()
    month = today.month_name(hebrew=True)
    year = today.hebrew_year(withgershayim=False)
    return year, month


def filter_new_books(new_list: list[dict[str, str | list]], file_path: str) -> tuple[list[dict], list[dict]]:
    with open(file_path, "r", encoding="utf-8") as f:
        content = json.load(f)
    en_titles = [i["en_title"] for i in content]
    he_titles = [i["he_title"] for i in content]
    filtered_list = [i for i in new_list if i["en_title"] not in en_titles and i["he_title"] not in he_titles]
    return filtered_list, content


def main(get_links: bool = False, only_new: bool = True, old_json_file_path: str = "", target_path: str = "", eroor_file: str = "") -> None:
    new_index = SefariaApi().table_of_contents()
    os.makedirs(target_path, exist_ok=True)
    new_books_index = []
    all_metadata = []
    authors = set()
    get_new_book_names = recursive_register_categories(new_index)
    if only_new:
        get_new_book_names, new_books_index = filter_new_books(get_new_book_names, old_json_file_path)
    for book in tqdm(get_new_book_names, desc="", unit="books"):
        try:
            book_en_title = book["en_title"]
            book_he_title = book["he_title"]
            book_path = book["path"]
            file_name = sanitize_filename(book_he_title)
            file_path_rel = [sanitize_filename(category) for category in book_path]
            file_path = os.path.join(target_path, *file_path_rel, file_name)
            book_ins = Book(book_en_title, "hebrew", book_he_title, book_path, get_links=get_links)
            book_content = book_ins.process_book()
            book_refs = book_ins.refs
            book_metadata = book_ins.get_metadata()
            print(book_metadata)
            if book_metadata and book_metadata.get("en_authors") and book_metadata.get("he_authors") is None:
                authors.add(book_metadata["en_authors"])
            if book_content:
                os.makedirs(file_path, exist_ok=True)
                book_file = os.path.join(file_path, file_name)
                book_content_copy = []
                dict_links = []
                all_footnotes = []
                for index, line in enumerate(book_content, start=1):
                    if "footnote-marker" in line:
                        line, footnotes_list = footnotes(line)
                        for foot_note in footnotes_list:
                            dict_links.append({
                                "line_index_1": index,
                                "heRef_2": "הערות",
                                "path_2": f"הערות על {file_name}.txt",
                                "line_index_2": len(all_footnotes) + 1,
                                "Conection Type": "commentary"
                            })
                            all_footnotes.append(foot_note)
                    book_content_copy.append(line)
                with open(f"{book_file}.txt", "w", encoding="utf-8") as f:
                    f.writelines(book_content_copy)
                if all_footnotes:
                    footnotes_file = os.path.join(file_path, f"הערות על {file_name}.txt")
                    with open(footnotes_file, 'w', encoding='utf-8') as file:
                        file.write("\n".join(all_footnotes))
                    json_file = os.path.join(file_path, f"{file_name}_links.json")
                    with open(json_file, "w", encoding="utf-8") as file:
                        json.dump(dict_links, file)
                if book_ins.links:
                    with open(f'{book_file}.json', 'w', encoding='utf-8') as json_file:
                        json.dump(book_ins.links, json_file, indent=4, ensure_ascii=False)
                if book_refs:
                    df = pd.DataFrame(book_refs)
                    df.to_csv(f"{book_file}.csv", index=False)
                list_books_path = os.path.join(target_path, "list_new_books.log")
                list_books_csv = os.path.join(target_path, "list_new_books.csv")
                with open(list_books_path, "a", encoding="utf-8") as f:
                    f.write(f"{file_name}\n")
                with open(list_books_csv, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if f.tell() == 0:
                        writer.writerow(["שם בעברית", "שם באנגלית", "כשר\\לא", "קטגוריות"])
                    writer.writerow([file_name, book_en_title, "", *file_path_rel])
                new_books_index.append(book)
                all_metadata.append(book_metadata)
        except Exception as e:
            print(e)
            with open(eroor_file, "a", encoding="utf-8") as f:
                f.write(f"{book_he_title} error {e}\n{traceback.format_exc()}\n")
    with open(old_json_file_path, "w", encoding="utf-8") as f:
        json.dump(new_books_index, f, indent=4, ensure_ascii=False)
    metadate_file_path = os.path.join(target_path, "metadata.json")
    if all_metadata:
        with open(metadate_file_path, "w", encoding="utf-8") as f:
            json.dump(all_metadata, f, indent=4, ensure_ascii=False)
        with open("metadata.json", "r", encoding="utf-8") as f:
            old_metadata = json.load(f)
        old_metadata.extend(all_metadata)
        with open("metadata.json", "w", encoding="utf-8") as f:
            json.dump(all_metadata, f, indent=4, ensure_ascii=False)
    authors_file_path = os.path.join(target_path, "authors.txt")
    if authors:
        with open(authors_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(authors))


if __name__ == "__main__":
    get_links = False
    only_new = True
    old_json_file_path = "toc.json"
    year, month = new_folder_name()
    num = 1
    # הפלט נכתב לריפו הפרטי Otzaria/extra_books, שמשוכפל ליד otzaria-library
    target_path = os.path.join("..", "..", "..", "extra_books", "sefariaToOtzaria", "sefaria_api", "ספרים", "לא ממויין", year, month)
    while os.path.exists(target_path):
        num += 1
        target_path = os.path.join("..", "..", "..", "extra_books", "sefariaToOtzaria", "sefaria_api", "ספרים", "לא ממויין", year, f"{month}_{num}")
    eroor_file = os.path.join("eroor", f'{" ".join(target_path.split(os.sep)[-2:])}.log')
    os.makedirs("eroor", exist_ok=True)
    main(get_links, only_new, old_json_file_path, target_path, eroor_file)
    if not os.listdir(target_path):
        os.rmdir(target_path)
    if not os.listdir("eroor"):
        os.rmdir("eroor")
