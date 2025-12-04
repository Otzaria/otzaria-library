from __future__ import annotations

import bisect
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

import requests
from tqdm import tqdm


class SefariaLinkResult(TypedDict):
    refs: list[str] | None
    startChar: int
    endChar: int
    linkFailed: bool
    text: str


class RefData(TypedDict):
    heRef: str
    url: str
    primaryCategory: str


def get_line_number(prefix: list[int], char_index: int) -> int:
    return bisect.bisect_right(prefix, char_index)


def call_sefaria_linker(text: str, title: str) -> tuple[list[SefariaLinkResult], dict[str, RefData]]:
    url = "https://www.sefaria.org/api/find-refs"
    payload = {
        "text": {
            "body": text,
            "title": title
        }
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    time.sleep(5)
    data = response.json()
    task_id = data.get("task_id")
    for _ in range(3):
        links = requests.get(f"https://www.sefaria.org/api/async/{task_id}").json()
        if links["state"] == "FAILURE":
            raise Exception("Task did not complete successfully")
        if links["ready"] is False or links["state"] == "PENDING":
            print(f"{links['state']=} {links['ready']=}")
            print("Waiting for linker to be ready...")
            time.sleep(50)
        else:
            return links["result"]["body"]["results"], links["result"]["body"]["refData"]
    raise Exception("Task did not complete successfully after 3 attempts")


def link_book(input_file: Path, output_file: Path | None = None, title: str | None = None, chunk_size: int = 100) -> None:
    output_file = output_file if output_file else Path(input_file.parts[0]) / "linker_links" / f"{input_file.stem}_links.json"
    title = title if title else input_file.stem
    dict_all = defaultdict(list)
    with input_file.open("r", encoding="utf-8") as file:
        all_lines = file.readlines()
    for i in tqdm(range((len(all_lines) + chunk_size - 1) // chunk_size)):
        lines = all_lines[i * chunk_size:(i + 1) * chunk_size]
        text = "".join(lines)
        lengths = [len(line) for line in lines]
        prefix = [0]
        for ln in lengths:
            prefix.append(prefix[-1] + ln)
        links, ref_data = call_sefaria_linker(text, title)
        for result in links:
            refs = result["refs"]
            if refs is None:
                continue
            refs_dict = {ref: ref_data.get(ref, {}).get("heRef") for ref in refs}
            start_index = result["startChar"]
            end_index = result["endChar"]
            line = get_line_number(prefix, start_index)
            absolute_line = line + i * chunk_size
            line_start_char = prefix[line - 1] if line > 0 else 0
            start_in_line = start_index - line_start_char
            end_in_line = end_index - line_start_char
            converted_link = {"start": start_in_line, "end": end_in_line, "refs": refs_dict}
            dict_all[absolute_line].append(converted_link)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(dict_all, f, ensure_ascii=False, indent=4)


def get_hash(file_path: Path) -> str:
    with file_path.open("rb") as f:
        content = f.read()
    return hashlib.sha256(content).hexdigest()
