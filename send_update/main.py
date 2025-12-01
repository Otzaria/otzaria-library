import codecs
import os
import subprocess

import requests
from mitmachim import MitmachimClient
from pyluach import dates
from yemot import split_and_send

folders = [
    "Ben-YehudaToOtzaria/ספרים/אוצריא",
    "DictaToOtzaria/ערוך/ספרים/אוצריא",
    "OnYourWayToOtzaria/ספרים/אוצריא",
    "OraytaToOtzaria/ספרים/אוצריא",
    "tashmaToOtzaria/ספרים/אוצריא",
    "sefariaToOtzaria/sefaria_export/ספרים/אוצריא",
    "sefariaToOtzaria/sefaria_api/ספרים/אוצריא",
    "MoreBooks/ספרים/אוצריא",
    "wikiJewishBooksToOtzaria/ספרים/אוצריא",
    "ToratEmetToOtzaria/ספרים/אוצריא",
    "wikisourceToOtzaria/ספרים/אוצריא",
    "pninimToOtzaria/ספרים/אוצריא",
]


def heb_date() -> str:
    today = dates.HebrewDate.today()
    return today.hebrew_date_string()


def get_changed_files(status_filter: str, folders: list[str]) -> list[str]:
    cmd = ["git", "diff", "--name-only", f"--diff-filter={status_filter}", "HEAD^", "HEAD", "--", *folders]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    raw_output = result.stdout.strip()
    decoded_files = []
    for line in raw_output.split("\n"):
        if not line:
            continue
        decoded_line = codecs.escape_decode(line.strip())[0].decode("utf-8").strip('''"''')
        if not decoded_line.lower().endswith(".txt") or decoded_line.lower().endswith("גירסת ספריה.txt"):
            continue
        book_rel_path = decoded_line.split("אוצריא/")[-1]
        decoded_files.append(book_rel_path)

    return decoded_files


added_files = get_changed_files("A", folders)
modified_files = get_changed_files("M", folders)
deleted_files = get_changed_files("D", folders)
renamed_files = get_changed_files("R", folders)
date = heb_date()
print(added_files)
print(modified_files)
print(deleted_files)
print(renamed_files)

if any([added_files, modified_files, deleted_files, renamed_files]):
    content_mitmachim = f"**עדכון {date}**\n"
    date_yemot = f"עדכון {date}\n"
    content_yemot = {}
    if added_files:
        content_mitmachim += f"\nהתווספו הקבצים הבאים:\n* {"\n* ".join(added_files)}\n"
        content_yemot["התווספו הקבצים הבאים:"] = f"{"\n".join([i.split('/')[-1].split('.')[0] for i in added_files])}"
    if modified_files:
        content_mitmachim += f"\nהשתנו הקבצים הבאים:\n* {"\n* ".join(modified_files)}\n"
        content_yemot["השתנו הקבצים הבאים:"] = f"{"\n".join([i.split('/')[-1].split('.')[0] for i in modified_files])}"
    if renamed_files:
        content_mitmachim += f"\nשונה מיקום/שם של הקבצים הבאים:\n* {"\n* ".join(renamed_files)}\n"
        content_yemot["שונה מיקום/שם של הקבצים הבאים:"] = f"{"\n".join([i.split('/')[-1].split('.')[0] for i in renamed_files])}"
    if deleted_files:
        content_mitmachim += f"\nנמחקו הקבצים הבאים:\n* {"\n* ".join(deleted_files)}\n"
        content_yemot["נמחקו הקבצים הבאים:"] = f"{"\n".join([i.split('/')[-1].split('.')[0] for i in deleted_files])}"
    print(content_mitmachim)
    username = os.getenv("USER_NAME")
    password = os.getenv("PASSWORD")
    yemot_token = os.getenv("TOKEN_YEMOT")
    google_chat_url = os.getenv("GOOGLE_CHAT_URL")
    yemot_path = "ivr2:/1"
    tzintuk_list_name = "books update"

    requests.post(google_chat_url, json={"text": content_mitmachim})

    client = MitmachimClient(username.strip().replace(" ", "+"), password.strip())

    try:
        client.login()
        topic_id = 80213
        client.send_post(content_mitmachim, topic_id)
    except Exception as e:
        print(e)
    finally:
        client.logout()

    try:
        split_and_send(content_yemot, date_yemot, yemot_token, yemot_path, tzintuk_list_name)
    except Exception as e:
        print(e)
