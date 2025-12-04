import csv
import json
from pathlib import Path

import tomllib

# sefaria_module_path = Path(__file__).resolve().parent.parent
# sys.path.append(str(sefaria_module_path))

CONFIG_FILE_PATH = Path(__file__).parent / "config.toml"
with CONFIG_FILE_PATH.open("rb") as f:
    CONFIG = tomllib.load(f)


def read_csv_file(file_path: Path, with_headers: bool = False) -> dict[str, str]:
    dict_replacements = {}
    with file_path.open("r", encoding="windows-1255") as f:
        reader = csv.reader(f)
        if with_headers:
            next(reader)
        for row in reader:
            if row[0] and row[1]:
                dict_replacements[row[0]] = row[1]
    return dict_replacements


def get_hash_all_files() -> dict[str, str]:
    file_path = Path(__file__).parent / CONFIG["hash_all_files_file_path"]
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_hash_all_files(dict_all: dict[str, str]) -> None:
    file_path = Path(__file__).parent / CONFIG["hash_all_files_file_path"]
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(dict_all, f, indent=2, ensure_ascii=False)
