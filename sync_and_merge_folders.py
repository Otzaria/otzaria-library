import csv
from collections.abc import Generator
from pathlib import Path

mapping = {
    "Ben-YehudaToOtzaria": "Ben-Yehuda",
    "DictaToOtzaria": "Dicta",
    "OnYourWayToOtzaria": "OnYourWay",
    "OraytaToOtzaria": "Orayta",
    # "SefariaToOtzaria": "sefaria",
    "MoreBooks": "MoreBooks",
    "KSK": "KSK",
    "tashmaToOtzaria": "Tashma",
    "wikiJewishBooksToOtzaria": "wiki_jewish_books",
    "ToratEmetToOtzaria": "ToratEmet",
    "wikisourceToOtzaria": "wikiSource",
    "pninimToOtzaria": "Pninim",
    "yam-HaHachmaToOtzaria": "yam-HaHachma",
    "National-LibraryToOtzaria": "National-Library",
    "BeitAharonVeYisraelToOtzaria": "Beit-Aharon-VeYisrael",
}


def get_files_list(folder_path: Path, target_folder_path: Path) -> Generator[list[str], None, None]:
    source_key = folder_path.parts[0]
    original_folder = mapping.get(source_key, source_key)
    for root, _, files in folder_path.walk():
        for file in files:
            file_path = root / file
            rel_file_path = file_path.relative_to(folder_path)
            target_file_path = target_folder_path / rel_file_path
            if not file.lower().endswith(".txt"):
                continue
            with file_path.open("r", encoding="utf-8") as f:
                content = f.read().split("\n")
            yield [file, str(target_file_path), original_folder, str(len(content))]


target_folder = Path("אוצריא")
folders = (
    "Ben-YehudaToOtzaria/ספרים/אוצריא",
    "DictaToOtzaria/ערוך/ספרים/אוצריא",
    "OnYourWayToOtzaria/ספרים/אוצריא",
    "OraytaToOtzaria/ספרים/אוצריא",
    "tashmaToOtzaria/ספרים/אוצריא",
    # "extraBooks/SefariaToOtzria/sefaria_export/ספרים/אוצריא",
    # "extraBooks/SefariaToOtzria/sefaria_api/ספרים/אוצריא",
    "MoreBooks/ספרים/אוצריא",
    "KSK/ספרים/אוצריא",
    "wikiJewishBooksToOtzaria/ספרים/אוצריא",
    "ToratEmetToOtzaria/ספרים/אוצריא",
    "wikisourceToOtzaria/ספרים/אוצריא",
    "pninimToOtzaria/ספרים/אוצריא",
    "yam-HaHachmaToOtzaria/ספרים/אוצריא",
    "National-LibraryToOtzaria/ספרים/אוצריא",
    "BeitAharonVeYisraelToOtzaria/ספרים/אוצריא",
)

folders_path = [Path(folder) for folder in folders]

new_csv_content = [["שם הקובץ", "נתיב הקובץ", "תיקיית המקור", "מספר שורות"]]
dif = True
for folder in folders_path:
    for i in get_files_list(folder, target_folder):
        new_csv_content.append(i)

sources_books_file_path = Path("MoreBooks/ספרים/אוצריא") / "אודות התוכנה" / "SourcesBooks.csv"

# השוואה כקבוצה: סדר המעבר על התיקיות אינו יציב בין מכונות, ושינוי סדר בלבד אינו עדכון.
if sources_books_file_path.exists():
    with sources_books_file_path.open("r", encoding="utf-8", newline="") as old_csvfile:
        old_csv_reader = csv.reader(old_csvfile)
        old_csv_values = list(old_csv_reader)
        if all(row in old_csv_values for row in new_csv_content) and all(row in new_csv_content for row in old_csv_values):
            dif = False
if dif:
    with sources_books_file_path.open("w", encoding="utf-8") as new_csv_file:
        writer = csv.writer(new_csv_file)
        writer.writerows(new_csv_content)


all_dicta_files = []
dicta_folder = Path("DictaToOtzaria/לא ערוך/ספרים/אוצריא")
for root, _, files in dicta_folder.walk():
    for file in files:
        file_path = root / file
        if not file.lower().endswith(".txt"):
            continue
        rel_path = file_path.relative_to(dicta_folder)
        all_dicta_files.append(str(rel_path))

dicta_list_path = Path("DictaToOtzaria/לא ערוך/list.txt")
with dicta_list_path.open("w", encoding="utf-8") as f:
    f.write("\n".join(all_dicta_files))
