"""מודל זה מכיל פונקציות להורדת תוכן מאתרי mediawiki דרך הapi

מכיל את הפונקציות הבאות:
--------
*func:get_list_by_ns
*func:get_list_by_name
*func:get_list_by_category
*func:get_page_content
"""
import requests

WIKISOURCE = "https://he.wikisource.org/w/api.php"  # ה end-point של ויקיטקסט
YESHIVA = "https://www.yeshiva.org.il/wiki/api.php"  # ה end-point של ויקישיבה
JEWISHBOOKS = "https://wiki.jewishbooks.org.il/mediawiki/api.php"  # ה end-point של אוצר הספרים היהודי השיתופי
BASE_URL = ""
SESSION = requests.Session()
HEADERS = {
    "User-Agent": "OtzariaBot/1.0 (https://github.com/yourname/otzaria; contact@example.com)"
}


def get_ns_list() -> list:
    i = 0
    namespaces = []
    apcontinue = ''
    while True:
        i += 1
        params = {
            'action': 'query',
            'meta': 'siteinfo',
            'siprop': 'namespaces',
            'format': 'json',
            'apcontinue': apcontinue
        }
        response = SESSION.get(BASE_URL, params=params)
        data = response.json()
        if 'query' in data and 'namespaces' in data['query']:
            namespaces.extend(data['query']['namespaces'].values())
        else:
            print("Error fetching namespaces:", data)
            break
        if 'continue' not in data:
            break
        apcontinue = data['continue']['apcontinue']
        print(f"Fetching namespaces: batch {i}")
    return namespaces


def get_list_by_ns(ns: str | int) -> list:
    """
    Returns a list of pages in a specific namespace (ns).

    Parameters:
    ns (str|int): The namespace identifier.

    Returns:
    list: A list of page titles in the specified namespace.
    """
    i = 0
    pages = []
    apcontinue = ''
    while True:
        i += 1
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': ns,
            'aplimit': 'max',
            'format': 'json',
            'apcontinue': apcontinue
        }
        response = SESSION.get(BASE_URL, params=params)
        data = response.json()
        if 'query' in data and 'allpages' in data['query']:
            pages.extend([page["title"] for page in data['query']['allpages']])
        else:
            print("Error fetching pages:", data)
            break
        if 'continue' not in data:
            break
        apcontinue = data['continue']['apcontinue']
        print(f"Fetching pages: batch {i}")
    return pages


def get_list_by_name(name: str) -> list:
    """
    Returns a list of pages whose titles start with the specified text (name).

    Parameters:
    name (str): The starting text of the page titles.

    Returns:
    list: A list of page titles that start with the specified text.
    """
    i = 0
    pages = []
    apcontinue = ''
    while True:
        i += 1
        params = {
            'action': 'query',
            'list': 'allpages',
            'apprefix': name,
            'aplimit': 'max',
            'format': 'json',
            'apcontinue': apcontinue
        }
        response = SESSION.get(BASE_URL, params=params)
        data = response.json()
        if 'query' in data and 'allpages' in data['query']:
            pages.extend([page["title"] for page in data['query']['allpages']])
        else:
            print("Error fetching pages:", data)
            break
        if 'continue' not in data:
            break
        apcontinue = data['continue']['apcontinue']
        print(f"Fetching pages: batch {i}")
    return pages


def get_list_by_category(category: str) -> list:
    """מחזיר רשימת דפים שנמצאים בקטגוריה מסוימת."""
    i = 0
    pages = []
    cmcontinue = ''
    while True:
        i += 1
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category,
            'cmtype': 'page',
            'cmlimit': 'max',
            'format': 'json',
            'cmcontinue': cmcontinue
        }
        response = SESSION.get(BASE_URL, params=params)
        data = response.json()
        if 'query' in data and 'categorymembers' in data['query']:
            pages.extend([page["title"] for page in data['query']['categorymembers']])
        else:
            print("Error fetching pages:", data)
            break
        if 'continue' not in data:
            break
        cmcontinue = data['continue']['cmcontinue']
        print(f"Fetching pages: batch {i}")
    return pages


def get_page_content(page_title: str) -> str:
    """מחזיר את תוכן הדף בפורמט mediawiki"""
    params = {
        'action': 'query',
        'prop': 'revisions',
        'titles': page_title,
        'rvslots': '*',
        'rvprop': 'content',
        'format': 'json',
    }
    try:
        response = SESSION.get(BASE_URL, params=params, headers=HEADERS)
        response.raise_for_status()

        data = response.json()

        # בדיקת התוכן שהתקבל
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if "revisions" in page_data:
                return page_data["revisions"][0]["slots"]["main"]["*"]
        return "Page not found or no content available."

    except requests.exceptions.RequestException as e:
        print(f"Error fetching page content: {e}")
        raise
