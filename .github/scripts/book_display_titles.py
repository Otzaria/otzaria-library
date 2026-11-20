#!/usr/bin/env python3
"""book.title of an Otzaria book: its file stem with the gershayim a file name cannot hold.

Port of SeforimLibrary's BookDisplayTitles.kt, CategoryLabels (CategoryKeys.kt) and the
first-heading read of Generator.kt (Otzaria/otzaria#2766). The stem stays the book's key;
the title only gains quote marks, from the book's first <h1> or from ForDB/title_acronyms.txt.
Any change here must match the generator, or ForDB rows stop matching their books.

The heading needs the book file, which a blobless CI checkout does not have. HeadReader reads
only the first lines: a local blob if present, else an HTTP Range request to raw.githubusercontent
at a commit whose tree holds that blob, else the full blob through git. Results are cached by
blob id (OTZARIA_BOOK_HEADS_CACHE, default <git dir>/otzaria-book-heads.json).
"""

from __future__ import annotations

import concurrent.futures
import html
import html.parser
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ACRONYMS_PATH = os.path.join("ForDB", "title_acronyms.txt")

GERESH = "׳"
GERSHAYIM = "״"
QUOTE_MARKS = "\"״”“'׳’‘`"
# Kotlin "\\s+".toRegex() is java.util.regex without UNICODE_CHARACTER_CLASS: ASCII only.
ASCII_WHITESPACE_RUN = re.compile(r"[ \t\n\x0b\f\r]+")
WORD_PUNCTUATION = "()[]{},.:;!?-–—"
FIRST_HEADING_SCAN_LINES = 10


def _kotlin_is_whitespace(c):
    # Char.isWhitespace(): Character.isWhitespace || Character.isSpaceChar.
    return c in " \t\n\x0b\f\r\x1c\x1d\x1e\x1f" or unicodedata.category(c) in ("Zs", "Zl", "Zp")


def _kotlin_trim(s):
    start, end = 0, len(s)
    while start < end and _kotlin_is_whitespace(s[start]):
        start += 1
    while end > start and _kotlin_is_whitespace(s[end - 1]):
        end -= 1
    return s[start:end]


def normalize(raw):
    """CategoryLabels.normalize: quote variants to gershayim/geresh, whitespace collapsed."""
    s = _kotlin_trim(raw)
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("‘", "'").replace("’", "'")
    s = s.replace('"', GERSHAYIM)
    s = s.replace("''", GERSHAYIM)
    s = s.replace(GERESH + GERESH, GERSHAYIM)
    s = s.replace("`", GERESH)
    return _kotlin_trim(ASCII_WHITESPACE_RUN.sub(" ", s))


def strip_quote_marks(raw):
    """CategoryLabels.stripQuoteMarks."""
    s = "".join(c for c in raw if c not in QUOTE_MARKS)
    return _kotlin_trim(ASCII_WHITESPACE_RUN.sub(" ", s))


def only_adds_quote_marks(title, base):
    """CategoryLabels.onlyAddsQuoteMarks: title is base with quote marks inserted, nothing else."""
    t, b = normalize(title), normalize(base)
    j = 0
    for c in t:
        if j < len(b) and c == b[j]:
            j += 1
        elif c not in QUOTE_MARKS:
            return False
    return j == len(b)


def book_title(raw_stem):
    """CategoryLabels.bookTitle: the key title of a library file stem."""
    base = normalize(raw_stem)
    return "תנ" + GERSHAYIM + "ך" if base in ("תנך", 'תנ"ך') else base


def _is_letter(c):
    return unicodedata.category(c).startswith("L")


def is_acronym_word(word):
    """^[\\p{L}׳]*\\p{L}״\\p{L}[\\p{L}׳]*$"""
    if word.count(GERSHAYIM) != 1:
        return False
    at = word.index(GERSHAYIM)
    if at == 0 or at == len(word) - 1 or not _is_letter(word[at - 1]) or not _is_letter(word[at + 1]):
        return False
    return all(c == GERSHAYIM or c == GERESH or _is_letter(c) for c in word)


class BookDisplayTitles:
    """BookDisplayTitles.kt: 1. the whole first heading, when it is the stem plus gershayim;
    2. then per bare word: an acronym word of the heading, or a curated acronym."""

    def __init__(self, acronyms):
        self._by_bare_word = {}
        for raw in acronyms:
            word = normalize(raw)
            if not is_acronym_word(word):
                raise ValueError(f"Not an acronym with gershayim: '{word}'")
            self._by_bare_word[strip_quote_marks(word)] = word

    @classmethod
    def from_file(cls, path):
        with open(path, encoding="utf-8") as handle:
            lines = [line.strip() for line in handle.read().splitlines()]
        return cls(line for line in lines if line and not line.startswith("#"))

    def display_title(self, stem_title, first_heading):
        heading = normalize(first_heading) if first_heading is not None else ""
        whole = self._from_whole_heading(stem_title, heading)
        candidate = book_title(self._by_words(whole if whole is not None else stem_title, heading))
        return candidate if only_adds_quote_marks(candidate, stem_title) else stem_title

    @staticmethod
    def _from_whole_heading(stem_title, heading):
        if (heading and strip_quote_marks(heading) == strip_quote_marks(stem_title)
                and heading.count(GERSHAYIM) > stem_title.count(GERSHAYIM)):
            return heading
        return None

    def _by_words(self, stem_title, heading):
        heading_acronyms = {}
        for word in heading.split(" "):
            core = word.strip(WORD_PUNCTUATION)
            if is_acronym_word(core):
                heading_acronyms.setdefault(strip_quote_marks(core), core)
        out = []
        for word in stem_title.split(" "):
            core = word.strip(WORD_PUNCTUATION)
            replacement = None
            if core and strip_quote_marks(core) == core:
                replacement = heading_acronyms.get(core) or self._by_bare_word.get(core)
            if replacement is None:
                out.append(word)
            else:
                start = word.index(core)
                out.append(word[:start] + replacement + word[start + len(core):])
        return " ".join(out)


# --- First heading: Generator.firstHeadingOf + cleanHtml + InlineNotes.stripMarkersAndBodies ---

_NOTE_OPEN = re.compile(r'<i\b[^>]*\bclass\s*=\s*"footnote"[^>]*>', re.I | re.A)
_ITALIC_TAG = re.compile(r"<i\b[^>]*>|</i>", re.I | re.A)
_MARKER = re.compile(r'<sup\b[^>]*\bclass\s*=\s*"footnote-marker"[^>]*>(.*?)</sup>', re.I | re.A | re.S)


def _matching_close(line, open_at):
    depth = 0
    for tag in _ITALIC_TAG.finditer(line, open_at):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            return tag
    return None


def strip_footnotes(line):
    """InlineNotes.stripMarkersAndBodies: every footnote body and marker sup removed."""
    if "footnote" not in line:
        return line
    out, cursor = [], 0
    while True:
        opened = _NOTE_OPEN.search(line, cursor)
        if opened is None:
            break
        out.append(line[cursor:opened.start()])
        close = _matching_close(line, opened.start())
        cursor = close.end() if close else len(line)
    out.append(line[cursor:])
    return _MARKER.sub("", "".join(out))


class _TextOnly(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


_JSOUP_PRETTY_WHITE = re.compile(r"[ \t\n\f\r\xa0]+")
_NIKUD_TEAMIM = re.compile("[֑-ׇֽׁׂ]")


def clean_html(text):
    """Generator.cleanHtml: Jsoup.clean(Safelist.none()) text, maqaf to space, no diacritics."""
    parser = _TextOnly()
    parser.feed(text)
    parser.close()
    # Jsoup's pretty printer collapses whitespace (no-break space too) and escapes & < >.
    plain = _JSOUP_PRETTY_WHITE.sub(" ", "".join(parser.parts))
    plain = plain.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    plain = ASCII_WHITESPACE_RUN.sub(" ", _kotlin_trim(plain))
    return _NIKUD_TEAMIM.sub("", plain.replace("־", " "))


_LINE_BREAK = re.compile(rb"\r\n|\r|\n")


def first_lines(data, count=FIRST_HEADING_SCAN_LINES, complete=True):
    """The first lines of a file's bytes, as BufferedReader.readLine splits them.
    When data is only a prefix (complete=False), a line not yet ended is left out."""
    lines, start = [], 0
    for match in _LINE_BREAK.finditer(data):
        # A prefix that ends in '\r' may be the first half of '\r\n'.
        if not complete and match.end() == len(data) and match.group(0) == b"\r":
            break
        lines.append(data[start:match.start()])
        start = match.end()
        if len(lines) == count:
            break
    else:
        if complete and start < len(data) and len(lines) < count:
            lines.append(data[start:])
    return [line.decode("utf-8", errors="replace") for line in lines]


def first_heading(lines):
    """Generator.firstHeadingOf: the cleaned text of the first <h1> among the first lines."""
    for index, raw in enumerate(lines[:FIRST_HEADING_SCAN_LINES]):
        line = raw[1:] if index == 0 and raw.startswith("﻿") else raw
        if line[:3].lower() == "<h1":
            return clean_html(strip_footnotes(line))
    return None


def _heading_is_settled(data, complete):
    lines = first_lines(data, complete=complete)
    if complete or len(lines) >= FIRST_HEADING_SCAN_LINES:
        return True, first_heading(lines)
    heading = first_heading(lines)
    return heading is not None, heading


# --- Reading the first lines of book blobs ---

_GITHUB_REMOTE = re.compile(r"github\.com[:/]+([^/]+/[^/]+?)(?:\.git)?/?$")
CACHE_VERSION = 1
RANGE_START = 16384
MAX_WORKERS = 16


def _git(repo, *args, data=None, env=None):
    return subprocess.run(["git", "-C", repo, *args], input=data, capture_output=True, env=env)


def tree_blobs(repo, ref):
    """{path: blob id} of ref's tree, without reading any blob."""
    out = _git(repo, "ls-tree", "-r", "-z", "--full-tree", ref)
    if out.returncode:
        raise RuntimeError(out.stderr.decode("utf-8", "replace").strip() or f"git ls-tree {ref} failed")
    blobs = {}
    for entry in out.stdout.decode("utf-8").split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            _mode, kind, oid = meta.split(" ")
            if kind == "blob":
                blobs[path] = oid
    return blobs


class HeadReader:
    """First headings of book blobs, cached by blob id."""

    def __init__(self, repo, cache_path=None, fetch_range=None):
        self.repo = repo
        self.cache_path = cache_path or os.environ.get("OTZARIA_BOOK_HEADS_CACHE") or self._default_cache()
        self.fetch_range = fetch_range or _http_range
        self.cache = self._load_cache()
        self.stats = {"cached": 0, "local": 0, "http": 0, "git": 0}

    def _default_cache(self):
        out = _git(self.repo, "rev-parse", "--git-common-dir")
        if out.returncode:
            return None
        git_dir = out.stdout.decode().strip()
        return os.path.join(self.repo if not os.path.isabs(git_dir) else "", git_dir, "otzaria-book-heads.json")

    def _load_cache(self):
        try:
            with open(self.cache_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("version") == CACHE_VERSION and isinstance(data.get("heads"), dict):
                return data["heads"]
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return {}

    def _save_cache(self):
        if not self.cache_path:
            return
        tmp = self.cache_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"version": CACHE_VERSION, "heads": self.cache}, handle, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    def headings(self, ref, paths):
        """{path: first heading or None} for the given paths of ref's tree."""
        blobs = tree_blobs(self.repo, ref)
        wanted = {p: blobs[p] for p in paths if p in blobs}
        missing = sorted({oid for oid in wanted.values() if oid not in self.cache})
        self.stats["cached"] += len(set(wanted.values())) - len(missing)
        if missing:
            missing = self._read_local(missing)
        if missing:
            missing = self._read_http(ref, blobs, wanted, missing)
        if missing:
            self._read_git(missing)
        if self.stats["local"] or self.stats["http"] or self.stats["git"]:
            self._save_cache()
        return {p: self.cache.get(oid) for p, oid in wanted.items()}

    def _remember(self, oid, data, complete):
        settled, heading = _heading_is_settled(data, complete)
        if settled:
            self.cache[oid] = heading
        return settled

    def _read_local(self, oids):
        env = dict(os.environ, GIT_NO_LAZY_FETCH="1")
        out = _git(self.repo, "cat-file", "--batch", data=("\n".join(oids) + "\n").encode(), env=env)
        data, at, left = out.stdout, 0, []
        for oid in oids:
            end = data.index(b"\n", at)
            header = data[at:end].split(b" ")
            at = end + 1
            if len(header) != 3:
                left.append(oid)
                continue
            size = int(header[2])
            self._remember(oid, data[at:at + size], True)
            self.stats["local"] += 1
            at += size + 1
        return left

    def _http_sources(self, ref, blobs):
        """[(owner/repo, commit, {path: oid})], the commit of ref first, then remote-tracking refs."""
        def slug(remote):
            url = _git(self.repo, "remote", "get-url", remote).stdout.decode().strip()
            match = _GITHUB_REMOTE.search(url)
            return match.group(1) if match else None

        sources = []
        commit = _git(self.repo, "rev-parse", f"{ref}^{{commit}}").stdout.decode().strip()
        own = os.environ.get("GITHUB_REPOSITORY") or slug("origin")
        if commit and own:
            sources.append((own, commit, lambda: blobs))
        refs = _git(self.repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/remotes")
        for line in refs.stdout.decode().splitlines():
            name, sha = line.rsplit(" ", 1)
            remote = name.split("/", 1)[0]
            if name.endswith("/HEAD") or sha == commit:
                continue
            target = slug(remote)
            if target:
                sources.append((target, sha, _lazy_tree(self.repo, sha)))
        return sources

    def _read_http(self, ref, blobs, wanted, oids):
        left = set(oids)
        path_of = {}
        for path, oid in wanted.items():
            path_of.setdefault(oid, path)
        for target, commit, tree in self._http_sources(ref, blobs):
            if not left:
                break
            try:
                held = tree()
            except RuntimeError:
                continue
            jobs = [(oid, path_of[oid]) for oid in sorted(left) if held.get(path_of[oid]) == oid]
            if not jobs:
                continue
            with concurrent.futures.ThreadPoolExecutor(MAX_WORKERS) as pool:
                futures = {pool.submit(self._fetch_head, target, commit, path): oid for oid, path in jobs}
                for future in concurrent.futures.as_completed(futures):
                    oid = futures[future]
                    result = future.result()
                    if result is not None:
                        data, complete = result
                        if self._remember(oid, data, complete):
                            self.stats["http"] += 1
                            left.discard(oid)
        return sorted(left)

    def _fetch_head(self, target, commit, path):
        url = f"https://raw.githubusercontent.com/{target}/{commit}/{urllib.parse.quote(path)}"
        size = RANGE_START
        while True:
            try:
                data, complete = self.fetch_range(url, size)
            except Exception:  # noqa: BLE001 - any failure falls back to git
                return None
            if complete or _heading_is_settled(data, False)[0]:
                return data, complete
            size *= 8

    def _read_git(self, oids):
        for oid in oids:
            out = _git(self.repo, "cat-file", "blob", oid)
            if out.returncode == 0:
                self._remember(oid, out.stdout, True)
                self.stats["git"] += 1


def _lazy_tree(repo, sha):
    memo = []

    def tree():
        if not memo:
            memo.append(tree_blobs(repo, sha))
        return memo[0]
    return tree


def _http_range(url, size):
    """(bytes, whole file?) for the first size bytes of url."""
    request = urllib.request.Request(url, headers={"Range": f"bytes=0-{size - 1}"})
    last = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                if response.status == 200:
                    return data, True
                total = (response.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
                return data, len(data) < size or (total.isdigit() and int(total) <= len(data))
        except urllib.error.HTTPError as error:
            if error.code == 416:  # empty file
                return b"", True
            if error.code == 404:
                raise
            last = error
        except OSError as error:
            last = error
    raise last


# --- The display titles of a tree's book files ---

_TITLES = {}


def load_titles(repo):
    path = os.path.abspath(os.path.join(repo, ACRONYMS_PATH))
    if path not in _TITLES:
        if os.path.exists(path):
            _TITLES[path] = BookDisplayTitles.from_file(path)
        else:
            print(f"::warning::{ACRONYMS_PATH} חסר; שמות התצוגה לפי ה-<h1> בלבד.", file=sys.stderr)
            _TITLES[path] = BookDisplayTitles(())
    return _TITLES[path]


def display_titles(repo, ref, paths, reader=None):
    """{path: book.title} for the given .txt book paths of ref (paths not in the tree are left out)."""
    titles = load_titles(repo)
    reader = reader or HeadReader(repo)
    headings = reader.headings(ref, paths)
    out = {}
    for path, heading in headings.items():
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        out[path] = titles.display_title(book_title(stem), heading)
    return out
