from pathlib import Path

from utils import get_hash_all_files, write_hash_all_files

from linker import get_hash, link_book


def main() -> None:
    hash_all = get_hash_all_files()
    # links_target = base_path / "sefaria_linker" / "links_temp"
    folders = (
        "Ben-YehudaToOtzaria/ספרים/אוצריא",
        "DictaToOtzaria/ערוך/ספרים/אוצריא",
        "OnYourWayToOtzaria/ספרים/אוצריא",
        "OraytaToOtzaria/ספרים/אוצריא",
        "tashmaToOtzaria/ספרים/אוצריא",
        # "sefariaToOtzaria/sefaria_api/ספרים/אוצריא",
        "MoreBooks/ספרים/אוצריא",
        # "wikisourceToOtzaria/ספרים/אוצריא",
        # "wikiJewishBooksToOtzaria/ספרים/אוצריא",
        "ToratEmetToOtzaria/ספרים/אוצריא",
        "pninimToOtzaria/ספרים/אוצריא"
    )
    for folder in folders:
        all_files = []
        folder_path = Path(folder)
        linker_links_path = Path(folder_path.parts[0]) / "linker links"
        # links_temp_path = folder_path / "links_temp"
        # links_temp_path = links_target / folder.split("/")[0]
        linker_links_path.mkdir(exist_ok=True, parents=True)
        for root, _, files in folder_path.walk():
            for file in files:
                file_path = root / file
                if file_path.suffix.lower() != ".txt":
                    continue
                all_files.append(f"{file_path.stem}_links.json")
                title = " ".join(file_path.parts[folder_path.parts.index("אוצריא") + 1:-1]) + " " + file_path.stem
                link_path = linker_links_path / f"{file_path.stem}_links.json"
                file_hash = get_hash(file_path)
                if link_path.exists() and hash_all.get(file_path.as_posix()) == file_hash:
                    continue
                print(f"Linking {file_path}...")
                try:
                    link_book(file_path, link_path, title)
                    hash_all[file_path.as_posix()] = file_hash
                except Exception as e:
                    print(f"Error linking {file_path}: {e}")
        for file in linker_links_path.iterdir():
            if not file.is_file():
                continue
            if file.name not in all_files:
                file.unlink()
    write_hash_all_files(hash_all)


if __name__ == "__main__":
    main()
