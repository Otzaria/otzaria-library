import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from gematriapy import gematria
from pyluach import dates

import fix_marker_breaks
import fix_missing_spaces


@dataclass
class YearRange:
    start_year_greg: int | None
    end_year_greg: int | None
    start_year_hebrew: str | None
    end_year_hebrew: str | None
    year_desc: str | None


def get_year(year: str | None) -> tuple[int | None, str | None]:
    if not year or not year.strip():
        return None, None
    int_year = gematria.to_number(year) + 5000
    heb_date = dates.HebrewDate(int_year, 1, 1)
    heb_date_str = heb_date.hebrew_year(thousands=True)
    return heb_date.to_greg().to_pydate().year, heb_date_str


def get_date(year: str | None) -> YearRange | None:
    if not year or not year.strip():
        return None
    if '"' not in year:
        return None
    year_desc = None
    desc_match = re.search(r"\((.*?)\)", year)
    if desc_match:
        year_desc = desc_match.group(1).strip()
    year = re.sub(r"\(.*\)", "", year)
    year_split = year.split('-')
    end_year = None
    if len(year_split) == 2:
        end_year = year_split[1].strip()
    start_year = year_split[0].strip()
    start_year_date, start_year_hebrew = get_year(start_year)
    end_year_date, end_year_hebrew = get_year(end_year)
    return YearRange(
        start_year_greg=start_year_date,
        end_year_greg=end_year_date,
        start_year_hebrew=start_year_hebrew,
        end_year_hebrew=end_year_hebrew,
        year_desc=year_desc
    )


def to_otzaria_metadata(book: dict) -> dict:
    book_entry = {}
    book_entry["heAuthors"] = [book["AuthorName"]] if book["AuthorName"] else []
    book_entry["title"] = book["MefareshDesc"] if book["MefareshDesc"] else None
    book_entry["heShortDesc"] = book["MefareshTypeDesc"] if book["MefareshTypeDesc"] else None
    book_date = get_date(book["PrintYearDesc"])
    if book_date:
        book_entry["pubDateHeb"] = [
            book_date.start_year_hebrew,
        ]
        book_entry["pubDate"] = [
            book_date.start_year_greg,
        ]
        if book_date.end_year_greg:
            book_entry["pubDate"].append(book_date.end_year_greg)
        if book_date.end_year_hebrew:
            book_entry["pubDateHeb"].append(book_date.end_year_hebrew)
        if book_date.year_desc:
            book_entry["compDateStringHe"] = book_date.year_desc
    return book_entry


def clean_hidden_chars(text: str | None) -> str:
    if not text:
        return ""

    text = re.sub(r'\s+', ' ', text).strip()
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")

    # 2. החלפת רווחים מיוחדים (כמו רווח בלתי פסיק או רווח ברוחב אפס) ברווח רגיל
    # הפונקציה normalize תהפוך סוגי רווחים שונים לפורמט סטנדרטי
    text = unicodedata.normalize('NFKC', text)
    return text


mapping_dir = Path(__file__).parent / "mapping"

rambam_books_path = mapping_dir / "rambam_books.json"
rambam_halachot_path = mapping_dir / "rambam_halachot.json"
rambam_prakim_path = mapping_dir / "rambam_prakim.json"
rambam_ot_path = mapping_dir / "rambam_ot.json"


skip_books_path = Path(__file__).parent / "skip_books.json"
rename_books_path = Path(__file__).parent / "rename_books.json"
extra_books_path = Path(__file__).parent / "extra_books.json"
rishonim_list_path = Path(__file__).parent / "rishonim_list.json"


otzaria_hierarchy_file_path = Path(__file__).parent / "otzaria_hierarchy.json"

with rambam_books_path.open("r", encoding="utf-8") as f:
    rambam_books = json.load(f)

with rambam_halachot_path.open("r", encoding="utf-8") as f:
    rambam_halachot = json.load(f)

with rambam_prakim_path.open("r", encoding="utf-8") as f:
    rambam_prakim = json.load(f)

with rambam_ot_path.open("r", encoding="utf-8") as f:
    rambam_ot = json.load(f)

with otzaria_hierarchy_file_path.open("r", encoding="utf-8") as f:
    otzaria_hierarchy = json.load(f)

with rishonim_list_path.open("r", encoding="utf-8") as f:
    rishonim_list = set(json.load(f))

span_classes = {'N', 'B', 'S', 'H', 'Z', 'R'}

with skip_books_path.open("r", encoding="utf-8") as f:
    skip_books = set(json.load(f))

with rename_books_path.open("r", encoding="utf-8") as f:
    rename_books = json.load(f)

with extra_books_path.open("r", encoding="utf-8") as f:
    extra_books = set(json.load(f))


def sanitize_filename(filename: str) -> str:
    return re.sub(r'[\\/:*"?<>|\u200E\u200F\u202A\u202B\u202C\u202D\u202E]', '', filename).replace('_', ' ')


def get_all_span_classes(html: str) -> set:
    soup = BeautifulSoup(html, "html.parser")
    return {
        cls
        for span in soup.find_all("span")
        for cls in span.get("class", [])
    }


CLASS_STYLE = {
    "B": {"tag": "b"},
    "Z": {"tag": "i"},
    "S": {"tag": "small"},
    "H": {"tag": "span", "style": "color:#1B1464"},
    "N": {"tag": "span", "style": "color:#999"},
    "R": {"tag": "span", "style": "color:#999"},
}


COLOR_PRIORITY = ("H", "N", "R")
TAG_PRIORITY = ("B", "Z", "S")


def _wrappers_for(seen: set) -> list:
    wrappers = []
    for c in COLOR_PRIORITY:
        if c in seen:
            wrappers.append(("span", CLASS_STYLE[c]["style"]))
            break
    wrappers.extend(
        (CLASS_STYLE[c]["tag"], None) for c in TAG_PRIORITY if c in seen
    )
    return wrappers


def _set_outer(span: Tag, name: str, style: str | None) -> None:
    span.name = name
    del span["class"]
    if style:
        span["style"] = style
    elif "style" in span.attrs:
        del span["style"]


def apply_span_styles(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for span in soup.find_all("span"):
        classes = span.get("class") or []
        seen = {c for c in classes if c in CLASS_STYLE}
        if not seen:
            span.unwrap()
            continue
        wrappers = _wrappers_for(seen)
        _set_outer(span, *wrappers[0])
        current = span
        for name, style in wrappers[1:]:
            new_tag = soup.new_tag(name)
            if style:
                new_tag["style"] = style
            new_tag.extend([child.extract() for child in list(current.contents)])
            current.append(new_tag)
            current = new_tag
    result = str(soup).replace("\n", " ")
    result = re.sub(r'(\s*<br\s*/?>)+\s*$', '', result).strip()
    # בנתוני המקור כותרת הסימן דבוקה לגוף הקטע (otzaria-library#38)
    result = fix_marker_breaks.fix_text(result)[0]
    # בנתוני המקור המילה שאחרי קטע מעוצב דבוקה לתג הסוגר (otzaria/otzaria#1068)
    return fix_missing_spaces.fix_text(result)[0]


input_path = Path(r"C:\Users\Otzaria\Desktop\rambam\output.json")
with input_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

all_keys = set()
all_sub_keys = set()
dict_all = {}
dict_all_extra = {}
otzaria_metadata = []
otzaria_metadata_extra = []
all_mef = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list)))))

for book in data:
    sub_levels = book.get("sub_levels", [])
    for halachot in book.get("sub_levels", []):
        for perek in halachot.get("sub_levels", []):
            for ot in perek.get("sub_levels", []):
                mefarshim = ot.get("mefarshim", [])
                for mef in mefarshim:
                    all_keys.update(mef.keys())
                    print_year_desc = mef.get("PrintYearDesc")
                    author_name = mef.get("AuthorName")
                    author_name = clean_hidden_chars(author_name)
                    code_mefaresh_id = mef.get("CodeMefareshId")
                    version_num = mef.get("VersionNum")
                    mefaresh_desc = mef.get("MefareshDesc")
                    mefaresh_desc = clean_hidden_chars(mefaresh_desc)
                    if mefaresh_desc in skip_books:
                        continue
                    if mefaresh_desc in rename_books:
                        mefaresh_desc = rename_books[mefaresh_desc]
                    print_year = mef.get("PrintYear")
                    is_nosse_kelim = mef.get("IsNosseKelim")
                    mefaresh_type_desc = mef.get("MefareshTypeDesc")

                    mef_entry = {
                        "PrintYearDesc": print_year_desc,
                        "AuthorName": author_name,
                        "CodeMefareshId": code_mefaresh_id,
                        "VersionNum": version_num,
                        "MefareshDesc": mefaresh_desc,
                        "PrintYear": print_year,
                        "IsNosseKelim": is_nosse_kelim,
                        "MefareshTypeDesc": mefaresh_type_desc,
                    }
                    list_alltexts = mef.get("List_Alltexts", [])
                    for text in list_alltexts:
                        all_sub_keys.update(text.keys())
                        text_print_year_desc = text.get("PrintYearDesc")
                        text_author_name = text.get("AuthorName")
                        text_author_name = clean_hidden_chars(text_author_name)
                        text_code_mefaresh_id = text.get("CodeMefareshId")
                        text_version_num = text.get("VersionNum")
                        text_mefaresh_desc = text.get("MefareshDesc")
                        text_mefaresh_desc = clean_hidden_chars(text_mefaresh_desc)
                        if text_mefaresh_desc in skip_books:
                            continue
                        if text_mefaresh_desc in rename_books:
                            text_mefaresh_desc = rename_books[text_mefaresh_desc]
                        text_print_year = text.get("PrintYear")
                        text_is_nosse_kelim = text.get("IsNosseKelim")
                        text_mefaresh_type_desc = text.get("MefareshTypeDesc")
                        text_entry = {
                            "PrintYearDesc": text_print_year_desc,
                            "AuthorName": text_author_name,
                            "CodeMefareshId": text_code_mefaresh_id,
                            "VersionNum": text_version_num,
                            "MefareshDesc": text_mefaresh_desc,
                            "PrintYear": text_print_year,
                            "IsNosseKelim": text_is_nosse_kelim,
                            "MefareshTypeDesc": text_mefaresh_type_desc,
                        }
                        assert mef_entry == text_entry, f"Mismatch between mef and list_alltexts entry for CodeMefareshId {code_mefaresh_id}"
                        order_by = text.get("OrderBy")
                        # FileContent מכיל את הטקסט המלא. MHLogicalUnitText הוא
                        # תצוגה מקדימה שהשרת חותך ל-~8000 תווים (כפתור "המשך" באתר
                        # חושף את FileContent). מעדיפים את המלא, ונופלים לתצוגה
                        # המקדימה רק כשהשרת לא צירף עותק מלא (טקסטים קצרים).
                        raw_text = text.get("FileContent") or text.get("MHLogicalUnitText")
                        mh_logical_unit_text = clean_hidden_chars(raw_text)
                        file_name = text.get("FileName")
                        division_detail_id = text.get("DivisionDetailId")
                        all_mef[code_mefaresh_id][book["Desc"]][halachot["Desc"]][perek["Desc"]][ot["Desc"]].append(mh_logical_unit_text)
                    if code_mefaresh_id in dict_all:
                        existing_entry = dict_all[code_mefaresh_id]
                        assert existing_entry == mef_entry, f"Conflict for CodeMefareshId {code_mefaresh_id}"
                    if mefaresh_desc in extra_books:
                        dict_all_extra[code_mefaresh_id] = mef_entry
                    else:
                        dict_all[code_mefaresh_id] = mef_entry


print(f"Total unique mefarshim: {len(dict_all)}")

books_base_path = Path(__file__).parent.parent
mef_base_path = books_base_path / "ספרים" / "אוצריא" / "הלכה" / "משנה תורה"
links_base_path = books_base_path / "links"
extra_books_base_path = Path(__file__).parent.parent.parent / "extraBooks" / "National-LibraryToOtzaria"
extra_books_mef_path = extra_books_base_path / "ספרים" / "אוצריא" / "הלכה" / "משנה תורה"
extra_books_links_path = extra_books_base_path / "links"

metadata_output_path = books_base_path / "metadata.json"
with metadata_output_path.open("w", encoding="utf-8") as f:
    json.dump(dict_all, f, ensure_ascii=False, indent=2)
extra_metadata_output_path = extra_books_base_path / "metadata_extra.json"
with extra_metadata_output_path.open("w", encoding="utf-8") as f:
    json.dump(dict_all_extra, f, ensure_ascii=False, indent=2)
otzaria_metadata_output_path = books_base_path / "otzaria_metadata.json"
with otzaria_metadata_output_path.open("w", encoding="utf-8") as f:
    json.dump([to_otzaria_metadata(book) for book in dict_all.values()], f, ensure_ascii=False, indent=2)
otzaria_metadata_extra_output_path = extra_books_base_path / "otzaria_metadata_extra.json"
with otzaria_metadata_extra_output_path.open("w", encoding="utf-8") as f:
    json.dump([to_otzaria_metadata(book) for book in dict_all_extra.values()], f, ensure_ascii=False, indent=2)

all_span_classes = set()
rambam_links = defaultdict(list)
rambam_extra_books_links = defaultdict(list)

mef_base_path.mkdir(exist_ok=True, parents=True)
links_base_path.mkdir(exist_ok=True, parents=True)
extra_books_mef_path.mkdir(exist_ok=True, parents=True)
extra_books_links_path.mkdir(exist_ok=True, parents=True)
for code_mefaresh_id, mef_entry in all_mef.items():
    mef_entry_metadata = dict_all[code_mefaresh_id] if code_mefaresh_id in dict_all else dict_all_extra[code_mefaresh_id]
    file_name = sanitize_filename(mef_entry_metadata.get("MefareshDesc", f"mefaresh_{code_mefaresh_id}"))
    is_nosse_kelim = mef_entry_metadata["IsNosseKelim"]
    if not isinstance(is_nosse_kelim, bool):
        print(file_name)
    mef_path = Path("ראשונים") if is_nosse_kelim else Path("אחרונים")
    if is_nosse_kelim:
        mef_path = mef_path / "נוכ" / f"{file_name}.txt"
    else:
        mef_path = mef_path / "מפרשים" / f"{file_name}.txt"
    in_extra = mef_entry_metadata.get("MefareshDesc") in extra_books
    mef_file_path = mef_base_path / mef_path
    if in_extra:
        mef_file_path = extra_books_mef_path / mef_path
    mef_file_path.parent.mkdir(exist_ok=True, parents=True)
    lines = 0
    dict_links = []
    with mef_file_path.open("w", encoding="utf-8") as f:
        f.write(f"<h1>{mef_entry_metadata.get("MefareshDesc", "")}</h1>\n")
        lines += 1
        f.write(mef_entry_metadata.get("AuthorName", "").replace("\n", "<br>") + "\n")
        lines += 1
        for book, halachot_dict in mef_entry.items():
            otzaria_book_name = rambam_books[book.strip()]
            f.write(f"<h2>{book.strip()}</h2>\n")
            lines += 1
            for halachot, perek_dict in halachot_dict.items():
                otzaria_halachot = rambam_halachot[halachot.strip()]
                f.write(f"<h3>{halachot.strip()}</h3>\n")
                lines += 1
                for perek, ot_dict in perek_dict.items():
                    otzaria_perek = rambam_prakim[perek.strip()]
                    f.write(f"<h4>{perek.strip()}</h4>\n")
                    lines += 1
                    for ot, texts in ot_dict.items():
                        otzaria_ot = rambam_ot[ot.strip()]
                        f.write(f"<h5>{ot.strip()}</h5>\n")
                        lines += 1
                        for text in texts:
                            all_span_classes.update(get_all_span_classes(text))
                            f.write(f"{apply_span_styles(text).strip()}\n")
                            lines += 1
                            otzaria_line = otzaria_hierarchy[otzaria_book_name][otzaria_halachot][otzaria_perek].get(otzaria_ot)
                            if not otzaria_line:
                                print(f"Missing link for {book.strip()}, {halachot.strip()}, {perek.strip()}, {ot.strip()}")
                                continue
                            # המפרש הוא ה-source ומשנה תורה הבסיס, לכן "source" (הגנרטור הופך לקנוני). issue #531
                            dict_links.append(
                                {
                                    "line_index_1": lines,
                                    "heRef_2": f"{otzaria_book_name}, {otzaria_halachot}, {otzaria_perek}, {otzaria_ot}",
                                    "path_2": f"משנה תורה, {otzaria_halachot}.txt",
                                    "line_index_2": otzaria_line,
                                    "Conection Type": "source"
                                })
                            dict_rambam = rambam_links if not in_extra else rambam_extra_books_links
                            dict_rambam[f"משנה תורה, {otzaria_halachot}"].append({
                                "line_index_1": otzaria_line,
                                "heRef_2": f"{book.strip()}, {halachot.strip()}, {perek.strip()}, {ot.strip()}",
                                "path_2": f"{file_name}.txt",
                                "line_index_2": lines,
                                "Conection Type": "commentary"
                            })
    json_links_path = links_base_path / f"{file_name}_links.json"
    if in_extra:
        json_links_path = extra_books_links_path / f"{file_name}_links.json"
    with json_links_path.open("w", encoding="utf-8") as f:
        json.dump(dict_links, f, ensure_ascii=False, indent=2)

# rambam_links_base_path = Path("rambam_links")
# rambam_links_base_path.mkdir(exist_ok=True, parents=True)
# for rambam_book, links in rambam_links.items():
#     if not links:
#         continue
#     json_links_path = rambam_links_base_path / f"{rambam_book}_links.json"
#     with json_links_path.open("w", encoding="utf-8") as f:
#         json.dump(links, f, ensure_ascii=False, indent=2)

# rambam_extra_books_links_base_path = Path("rambam_extra_books_links")
# rambam_extra_books_links_base_path.mkdir(exist_ok=True, parents=True)
# for rambam_book, links in rambam_extra_books_links.items():
#     if not links:
#         continue
#     json_links_path = rambam_extra_books_links_base_path / f"{rambam_book}_links.json"
#     with json_links_path.open("w", encoding="utf-8") as f:
#         json.dump(links, f, ensure_ascii=False, indent=2)

print(all_keys)
print(all_sub_keys)
print(f"Unique span classes: {all_span_classes}")
