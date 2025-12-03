from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Generator, Sequence
from copy import deepcopy
from pathlib import Path
from typing import TypedDict

from tqdm import tqdm
from utils import CONFIG

LOG = False


class Link(TypedDict):
    first_part: list[str]
    start_index: list[int]
    end_index: list[int]


class LinkerLink(TypedDict):
    start: int
    end: int
    refs: dict[str, str | None] | None

    # class OtzariaLink(TypedDict):
    #     line_index_1: int
    #     line_index_2: int
    #     heRef_2: str
    #     path_2: str
    #     Conection_Type: str
OtzariaLink = TypedDict("OtzariaLink", {"line_index_1": int, "line_index_2": int, "heRef_2": str, "path_2": str, "Conection Type": str})


# log_path = Path(CONFIG["otzaria"]["log_path"])
log_path = Path(__file__).parent / CONFIG["otzaria"]["log_path"]
log_path = log_path.resolve()
set_links: set[str] = set()
set_range: set[str] = set()
otzaria_links: defaultdict[str, list[list[str]]] = defaultdict(list)
otzaria_parse: defaultdict[str, list[Link]] = defaultdict(list)
all_otzaria_links: defaultdict[str, list[list[str]]] = defaultdict(list)
# refs_file_path = Path(CONFIG["otzaria"]["refs_all_file_path"]).resolve()
refs_file_path = Path(__file__).parent / CONFIG["otzaria"]["refs_all_file_path"]
refs_file_path = refs_file_path.resolve()
not_found_links: set[str] = set()
not_found_books: set[str] = set()
found_links: set[str] = set()
found_links_dict = {}
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


def iter_path(base_path: Path, ext_type: str = ".json") -> Generator[Path, None, None]:
    for root, _, files in base_path.walk():
        for file in files:
            file_path = root / file
            if file_path.suffix.lower() != ext_type.lower():
                continue
            yield file_path


def match_range(
        otzaria_link: list[int],
        sefaria_start_range: list[int],
        sefaria_end_range: list[int]
) -> bool:
    if any(not isinstance(x, int)
            for link in [otzaria_link, sefaria_start_range, sefaria_end_range]
            for x in link):
        return False
    common_len = min(len(sefaria_start_range), len(sefaria_end_range), len(otzaria_link))
    return sefaria_start_range[:common_len] <= otzaria_link[:common_len] <= sefaria_end_range[:common_len]
    # for start, end, link in zip(sefaria_start_range, sefaria_end_range, otzaria_link):
    #     if not start <= link <= end:  # type: ignore צריך לתקן למקרה שהפסוק קטן מהפסוק שבפרק הקודם.
    #         return False
    # return True


def match_links(sefaria_start_range: list[int] | list[str], otzaria_link: list[int] | list[str]) -> bool:
    common_len = min(len(sefaria_start_range), len(otzaria_link))
    return sefaria_start_range[:common_len] == otzaria_link[:common_len]


def get_best_match(otzaria_links: list[Link]) -> list[Link]:
    max_length = max(len(link["start_index"]) for link in otzaria_links)
    best_results = [i for i in otzaria_links if len(i["start_index"]) == max_length]
    best_results.sort(key=lambda x: x["start_index"])
    return best_results


def get_best_match_with_first_part(otzaria_links: list[Link]) -> list[Link]:
    max_length = max(len(link["first_part"]) for link in otzaria_links)
    best_results = [i for i in otzaria_links if len(i["first_part"]) == max_length]
    return get_best_match(best_results)


def convert_ref_to_int(link_range: list[str]) -> list[int]:
    return [int(link.replace("a", "1").replace("b", "2")) for link in link_range]


def parse_range(start_index: str, end_index: str) -> tuple[list[str], list[str]]:
    start = start_index.split(":")
    end = end_index.split(":")
    if len(start) != len(end):
        for i in start:
            if len(start) > len(end):
                end.insert(0, i)
    return start, end


def common_prefix[T](*lists: Sequence[T]) -> list[T]:
    result = []
    for items in zip(*lists):
        if all(item == items[0] for item in items):
            result.append(items[0])
        else:
            break
    return result


def fix_he_ref(ref: str, en_ref_len: int) -> str:
    first_part = []
    split_ref = ref.split(",")
    last_part = split_ref[-1]
    if len(split_ref) == 1:
        last_part = split_ref[-1]
        split_ref = []
    split_last_part = last_part.split(" ")
    start_index = split_last_part[-1].split("&&&")
    if len(split_ref) > 1:
        first_part = split_ref[:-1]
    if len(split_last_part) > 1:
        first_part.append(" ".join(split_last_part[:-1]))
    first_part = [part.strip() for part in first_part]
    start_index = [part.strip() for part in start_index]
    start_index_new = start_index[:en_ref_len]
    return f"{', '.join(first_part)} {', '.join(start_index_new)}"


def split_link(link: str) -> Link:
    first_part = []
    start_index = []
    end_index = []
    parts = link.split(", ")
    last_part = parts[-1]
    if len(parts) == 1:
        last_part = parts[-1]
        parts = []
        # return {"first_part": parts, "start_index": [], "end_index": []}
    split_last_part = last_part.split(" ")
    parse_split_last_part = split_last_part[-1].split("-")
    if len(parse_split_last_part) == 2:
        start_index, end_index = parse_range(parse_split_last_part[0], parse_split_last_part[1])
        start_index = parse_split_last_part[0].split(":")
        end_index = parse_split_last_part[1].split(":")

        if len(start_index) != len(end_index):
            for index, i in enumerate(start_index):
                if len(start_index) > len(end_index):
                    end_index.insert(index, i)
    else:
        start_index = parse_split_last_part[0].split(":")
    if len(parts) > 1:
        first_part = parts[:-1]
    if len(split_last_part) > 1:
        first_part.append(" ".join(split_last_part[:-1]))
    try:
        return {"first_part": first_part, "start_index": convert_ref_to_int(start_index), "end_index": convert_ref_to_int(end_index)}
    except ValueError:
        return {"first_part": first_part + start_index, "start_index": [], "end_index": []}


def read_linker_json(file_path: Path) -> dict[str, list[LinkerLink]]:
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


for folder in folders:
    folder_path = Path(folder)
    linker_links_path = Path(folder_path.parts[0]) / "linker_links"
    for file_path in iter_path(linker_links_path):
        linker_links = read_linker_json(file_path)
        for line in linker_links.values():
            for link in line:
                if link["refs"] is None:
                    continue
                for ref in link["refs"]:
                    if "-" not in ref:
                        set_range.add(ref.strip())
                    else:
                        set_links.add(ref.strip())

print(f"{len(set_links)=} {len(set_range)=}")
with refs_file_path.open("r", encoding="utf-8", newline="") as f:
    reader = csv.reader(f)
    headers = next(reader)
    print(headers)
    for line in tqdm(reader):
        parse = split_link(line[0].strip())
        # if parse["first_part"][0] == "Shabbat" and len(parse["first_part"]) == 1:
        #     print(line)
        #     print(parse)
        all_otzaria_links[f"{", ".join(parse["first_part"])} {":".join(map(str, parse["start_index"]))}"].append(line)
        otzaria_parse[parse["first_part"][0]].append(parse)
        if line[0].strip() in set_links:
            line[1] = line[1].replace("&&&", ", ")
            otzaria_links[line[0].strip()].append(line)
            set_links.remove(line[0].strip())
num = len(set_links)

print(f"{num=}")
set_links_copy = set_links.copy()
for i in tqdm(set_links):
    parse = split_link(i)
    if parse["first_part"][0] in otzaria_parse:
        not_found_links.add(i)
        result = []
        best_match = None
        for j in otzaria_parse[parse["first_part"][0]]:
            if j["first_part"] == parse["first_part"]:
                if match_links(parse["start_index"], j["start_index"]):
                    result.append(j)
        if result:
            best_match = get_best_match(result)
        else:
            for j in otzaria_parse[parse["first_part"][0]]:
                if match_links(parse["first_part"], j["first_part"]):
                    if match_links(parse["start_index"], j["start_index"]):
                        result.append(j)
            best_match = get_best_match_with_first_part(result) if result else None

        if result:
            # result_link = max(result, key=lambda x: len(x["start_index"]))
            # otzaria_links[i] = [all_otzaria_links[f"{", ".join(best_match[0]["first_part"])} {":".join(map(str, best_match[0]["start_index"]))}"]] if best_match else []
            if best_match:
                links = []
                links = [otzaria_link for otzaria_link in all_otzaria_links[f"{", ".join(best_match[0]["first_part"])} {":".join(map(str, best_match[0]["start_index"]))}"]]
                links = deepcopy(links)
                for link in links:
                    link[1] = fix_he_ref(link[1], len(best_match[0]["start_index"]))
                otzaria_links[i].extend([links[0]])
            set_links_copy.remove(i)
            found_links.add(i)
            found_links_dict[i] = [all_otzaria_links[f"{", ".join(best_match[0]["first_part"])} {":".join(map(str, best_match[0]["start_index"]))}"]] if best_match else []

        num -= 1
    else:
        not_found_books.add(parse["first_part"][0])
print(f"{num=}")
set_links = set_links_copy
num = len(set_range)
print(f"{num=}")
range_links_copy = set_range.copy()
for i in tqdm(set_range):
    parse = split_link(i)
    if parse["first_part"][0] in otzaria_parse:
        num -= 1
        result = []
        best_match = []
        for j in otzaria_parse[parse["first_part"][0]]:
            # print(parse["first_part"][0])
            if j["first_part"] == parse["first_part"]:
                if match_range(j["start_index"], parse["start_index"], parse["end_index"]):
                    result.append(j)
        if result:
            best_match = result
        else:
            for j in otzaria_parse[parse["first_part"][0]]:
                if match_links(parse["first_part"], j["first_part"]):
                    if match_range(j["start_index"], parse["start_index"], parse["end_index"]):
                        result.append(j)
            best_match = get_best_match_with_first_part(result) if result else None

        if result:
            # print(f"{result=}")
            # result_link = max(result, key=lambda x: len(x["start_index"]))
            # otzaria_links[i] = [all_otzaria_links[f"{", ".join(match["first_part"])} {":".join(map(str, match["start_index"]))}"]
            #                     for match in best_match] if best_match else []
            if best_match:
                for match in best_match:
                    links = [otzaria_link for otzaria_link in all_otzaria_links[f"{", ".join(match["first_part"])} {":".join(map(str, match["start_index"]))}"]]
                    links = deepcopy(links)
                    for link in links:
                        link[1] = fix_he_ref(link[1], len(match["start_index"]))
                    otzaria_links[i].extend(links)
            range_links_copy.remove(i)
            found_links.add(i)
            found_links_dict[i] = [all_otzaria_links[f"{", ".join(match["first_part"])} {":".join(map(str, match["start_index"]))}"]
                                   for match in best_match] if best_match else []
        else:
            not_found_links.add(i)
    else:
        not_found_books.add(parse["first_part"][0])

set_range = range_links_copy
print(f"{num=}")

for folder in folders:
    folder_path = Path(folder)
    links_path = Path().joinpath(*folder_path.parts[:folder_path.parts.index("אוצריא") - 1]) / "links"
    links_path.mkdir(parents=True, exist_ok=True)
    linker_links_path = Path(folder_path.parts[0]) / "linker_links"
    for file_path in iter_path(linker_links_path):
        file_links = []
        target_link_path = links_path / file_path.parts[-1]
        linker_links = read_linker_json(file_path)
        for index, line in linker_links.items():
            for link in line:
                if link["refs"] is None:
                    continue
                if len(link["refs"]) != 1:
                    continue
                ref_key = next(iter(link["refs"].keys()))
                ref_value = link["refs"][ref_key] or ""
                ref_value = ref_value.replace(":", ", ")
                link_1 = otzaria_links.get(ref_key)
                if link_1:
                    min_link = min(link_1, key=lambda x: int(x[2]))
                    all_refs = [i[1].split(", ") for i in link_1]
                    he_ref = common_prefix(*all_refs)
                    he_ref_str = ", ".join(he_ref)
                    # file_links.extend([{"line_index_1": int(index), "line_index_2": int(link_2_link[2]), "heRef_2": link_2_link[1], "path_2": f"{link_2_link[3]}.txt", "Conection Type": "reference"}
                    #                    for link_2_link in link_1])
                    file_links.append({"line_index_1": int(index),
                                       "line_index_2": int(min_link[2]),
                                       "heRef_2": ref_value or he_ref_str or min_link[3],
                                       "path_2": f"{min_link[3]}.txt",
                                       "Conection Type": "linker",
                                       "start": link["start"],
                                       "end": link["end"]
                                       })
        current_links = []
        if target_link_path.exists():
            with target_link_path.open("r", encoding="utf-8") as f:
                current_links_content = json.load(f)
            current_links = [i for i in current_links_content if i.get("Conection Type") != "linker"]
        file_links.extend(current_links)
        if not file_links:
            continue
        with target_link_path.open("w", encoding="utf-8") as f:
            json.dump(file_links, f, indent=2, ensure_ascii=False)


print(f"{len(set_links)=} {len(set_range)=} {len(otzaria_links)=}")
# # print(set_links)

# log_path.mkdir(parents=True, exist_ok=True)
# otzaria_links_found_2 = log_path / "otzaria_links_found_2.json"
# with otzaria_links_found_2.open("w", encoding="utf-8") as f:
#     json.dump(found_links_dict, f, ensure_ascii=False, indent=4)
if LOG:
    not_found_links_2 = log_path / "not_found_links_2.json"
    with not_found_links_2.open("w", encoding="utf-8") as f:
        for link in not_found_links:
            f.write(f"{link}\n")
    not_found_books_2 = log_path / "not_found_books_2.json"
    with not_found_books_2.open("w", encoding="utf-8") as f:
        for book in not_found_books:
            f.write(f"{book}\n")
    found_links_2 = log_path / "found_links_2.txt"
    with found_links_2.open("w", encoding="utf-8") as f:
        for book in found_links:
            f.write(f"{book}\n")
