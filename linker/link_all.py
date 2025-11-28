from pathlib import Path

from linker import link_book


def main() -> None:
    base_path = Path(r"C:\Users\Administrator\Desktop\otzaria-library")
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
        "ToratEmetToOtzaria/ספרים/אוצריא"
    )
    for folder in folders:
        folder_path = base_path / folder
        links_temp_path = base_path.joinpath(folder.split("/")[0], "linker_links")
        # links_temp_path = folder_path / "links_temp"
        # links_temp_path = links_target / folder.split("/")[0]
        links_temp_path.mkdir(exist_ok=True, parents=True)
        for root, _, files in folder_path.walk():
            for file in files:
                file_path = root / file
                if file_path.suffix.lower() != ".txt":
                    continue
                title = " ".join(file_path.parts[folder_path.parts.index("אוצריא") + 1:-1]) + " " + file_path.stem
                link_path = links_temp_path / f"{file_path.stem}_links.json"
                if link_path.exists():
                    continue
                print(f"Linking {file_path}...")
                try:
                    link_book(file_path, link_path, title)
                except Exception as e:
                    print(f"Error linking {file_path}: {e}")


if __name__ == "__main__":
    main()
