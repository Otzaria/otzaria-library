import csv
import sys
from pathlib import Path

import tomllib

sefaria_module_path = Path(__file__).resolve().parent.parent
sys.path.append(str(sefaria_module_path))
print(f"Added {sefaria_module_path} to sys.path")

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
