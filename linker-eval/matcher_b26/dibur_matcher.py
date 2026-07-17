"""
dibur_matcher_v5.py -- third round of fixes, on top of v4.

New in this version (found while spot-checking v4's output against the QA
audit's specific flagged lines):

1. score_candidate's exact-lemma bonus only fired on FULL token-for-token
   equality between the dibur and the candidate's own pre-dash lemma. Real
   citations very often quote only the first word(s) of a longer lemma
   (e.g. citing "ד\"ה אנוסת" for a Rashi lemma that is really "אנוסת בנו").
   Added a slightly smaller bonus for a *prefix* match (dibur tokens are an
   exact prefix of the candidate's lemma tokens), which is still a far
   stronger signal than generic word overlap.

2. find_best_match's monotonic-order preference used to be a hard PRE-FILTER
   (only candidates at/after the previous match's line were considered at
   all, falling back to the full pool only if literally none qualified).
   That silently discarded the correct answer whenever a citing line
   legitimately refers back to an EARLIER lemma in the same intermediate
   book than the line before it happened to land on (confirmed real case:
   citing line 61, dibur "מה שוכב", correct target is רש"י line 81 in the
   same דף ד. section, but a wrong-but-plausible earlier match at line 86
   (fixed by fix #1 above to land on 87, but the mistake illustrates the
   deeper issue) had already advanced the monotonic pointer past 81, making
   the correct earlier candidate structurally unreachable regardless of how
   well it scored). Changed to: score every candidate in the pool first;
   monotonic order is now only a *tie-break preference* among candidates
   within AMBIGUITY_MARGIN of the single best score, not a filter that can
   throw away a clearly-better-scoring candidate purely for being earlier.
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


NIKUD_RE = re.compile(r"[֑-ׇ]")
PUNCT_RE = re.compile(r"[\"'׳״.,:;()\[\]\-–]")
HEB_WORD_RE = re.compile(r"[א-ת]+")

STOPWORDS = set("""
כו תימה תימא קשה פי פירש בקונטרס וקשה אין אבל אלא אלו ואי היינו הכא התם
משום כדי הא הוא הוה מ אם כי לא לי ליה להו נראה ליישב אפשר אך רק כגון עוד
גם כן שם שמא זה זו יש דהא בגמ גמרא מתני מהא דהיינו קאמר קאמרינן דאמרינן
דקאמר וי ול צ ע ולכאורה ואפשר
""".split())


# Normalize common Talmudic abbreviations before tokenization.  These are
# deliberately whole-token expansions: replacing arbitrary letter fragments
# inside running Hebrew creates more false matches than it fixes.
ABBREVIATION_EXPANSIONS = [
    (re.compile(r'(?<![א-ת])דא["״]כ(?![א-ת])'), "דאם כן"),
    (re.compile(r'(?<![א-ת])ב["״]ש(?![א-ת])'), "בית שמאי"),
    (re.compile(r'(?<![א-ת])ה["״]נ(?![א-ת])'), "הכא נמי"),
    (re.compile(r'(?<![א-ת])אע["״]פ(?![א-ת])'), "אף על פי"),
    (re.compile(r'(?<![א-ת])עכ["״]פ(?![א-ת])'), "על כל פנים"),
    (re.compile(r'(?<![א-ת])מ["״]מ(?![א-ת])'), "מכל מקום"),
]


def expand_abbreviations(s: str) -> str:
    for pattern, replacement in ABBREVIATION_EXPANSIONS:
        s = pattern.sub(replacement, s)
    return s


def normalize_book_title(title: str) -> str:
    return title.replace('"', '').replace("'", '').replace("׳", '').replace("״", '').strip()


def norm_words(s: str) -> List[str]:
    s = expand_abbreviations(s)
    s = NIKUD_RE.sub("", s)
    s = PUNCT_RE.sub(" ", s)
    return HEB_WORD_RE.findall(s)


H1_RE = re.compile(r"^<h1>(.*?)</h1>\s*$")
H2_RE = re.compile(r"^<h2>(.*?)</h2>\s*$")
B_LABEL_RE = re.compile(r"^<b>(.*?)</b>\s*")


@dataclass
class Line:
    line_index: int
    tag: Optional[str]
    daf_key: Optional[str]
    content: str


def parse_book(path: str) -> List[Line]:
    lines: List[Line] = []
    daf_key = None
    with open(path, encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            raw = raw.rstrip("\n")
            m1 = H1_RE.match(raw)
            if m1:
                lines.append(Line(i, "h1", None, m1.group(1)))
                continue
            m2 = H2_RE.match(raw)
            if m2:
                daf_key = m2.group(1).strip()
                lines.append(Line(i, "h2", daf_key, m2.group(1)))
                continue
            lines.append(Line(i, None, daf_key, raw))
    return lines


def build_daf_index(lines: List[Line]) -> Dict[Optional[str], List[Line]]:
    idx: Dict[Optional[str], List[Line]] = {}
    for ln in lines:
        if ln.tag is not None:
            continue
        if not ln.content.strip():
            continue
        idx.setdefault(ln.daf_key, []).append(ln)
    return idx


FIXED_KNOWN_LABELS = {
    "שם", "באד", "בגמרא", "גמרא", "ובזה", "אכן", "ועוד", "עוד",
    "והנה", "בתוספ", "ותוספ", "תוספות", "בתוספות", "שוב", "במתניתן", "במשנה",
    "משנה", "מתני", "ולפז", "ודע", "ברשי", "ורשי", "רשי", "תוס", "ותוס",
    "וראיתי", "אבל", "אנ", "ונל", "ועפ", "גם", "ונלענד", "ונלעד", "אמנם",
    "וכן", "קק", "ושם", "והיוצא", "אלא", "לכאורה", "נל", "ויל", "הן אמת",
    "רדה", "תודה", "רשבם", "ברשבם", "ורשבם",
}

# "בד\"ה"/"ד\"ה" must NEVER be treated as a genuine (strippable) label -- it IS
# the dibur-hamatchil marker itself, and stripping it away as a generic label
# (as an earlier version of this script did) throws away the exact signal that
# should route the line through detect_super_commentary_opener instead. This
# exclusion applies even if "דה"/"בדה" would otherwise qualify via
# build_frequent_labels (it recurs very often as a sole leading label).
_DH_MARKER_KEYS = {"דה", "בדה"}


def _norm_label_key(label: str) -> str:
    s = label.replace("׳", "").replace("״", "").replace('"', "").replace("'", "")
    s = s.replace(".", "").replace(",", "").replace(":", "").replace(" ", "")
    return s.strip()


def build_frequent_labels(citing_lines: List[Line], min_count: int = 3, max_len: int = 8) -> set:
    from collections import Counter
    counts = Counter()
    for ln in citing_lines:
        if ln.tag is not None:
            continue
        text = ln.content.strip()
        m = B_LABEL_RE.match(text)
        if m:
            key = _norm_label_key(m.group(1))
            if key and len(key) <= max_len:
                counts[key] += 1
    return {k for k, c in counts.items() if c >= min_count}


def extract_b_label(text: str, known_labels: set) -> Tuple[Optional[str], str]:
    labels: List[str] = []
    remaining = text
    while True:
        m = B_LABEL_RE.match(remaining)
        if not m:
            break
        key = _norm_label_key(m.group(1))
        if key not in known_labels:
            break
        labels.append(m.group(1).strip())
        remaining = remaining[m.end():]
    remaining = remaining.lstrip()
    if labels and remaining[:1] == "." and remaining[1:2] != ".":
        remaining = remaining[1:].lstrip()
    if labels:
        return " ".join(labels), remaining
    return None, text.strip()


CONTINUATION_OPENERS = [
    "והנה", "ונלע\"ד", "ונלענ\"ד", "אמנם", "עוד שם", "עוד כתב", "שוב כתב",
    "בא\"ד", "ועוד", "וכן", "שם",
]


def is_continuation_opener(text: str) -> bool:
    stripped = text.strip()
    flattened = flatten_leading_bold(stripped)
    if re.match(r"^\(\s*[א-ת][\'׳]?\)", flattened):
        return True
    for w in CONTINUATION_OPENERS:
        if stripped.startswith(w):
            nxt = stripped[len(w):len(w) + 1]
            if nxt == "" or not ("א" <= nxt <= "ת"):
                return True
    return False


PURE_CONTINUATION_LABELS = {
    "בא\"ד", "שם", "ובזה", "אכן", "ועוד", "עוד", "והנה", "ונלענ\"ד", "ונלע\"ד",
    "אמנם", "שוב", "וכן", "ולפ\"ז", "ודע", "וראיתי", "א\"נ", "ונ\"ל", "וע\"פ",
    "גם", "אבל",
}


def normalize_label(label: str) -> str:
    return label.replace("׳", "'").replace("״", "\"").strip().rstrip(".")


def is_pure_continuation_label(label: Optional[str]) -> bool:
    if not label:
        return False
    return normalize_label(label) in PURE_CONTINUATION_LABELS


_NAME_DH_PATTERNS = [
    (re.compile(r'^(?:ב|ו)?(?:רש["״]י|רשי)\s+ב?ד["״]ה\s+(.+)$'), "rashi"),
    (re.compile(r'^(?:ב|ו)?(?:רשב["״]ם|רשבם)\s+ב?ד["״]ה\s+(.+)$'), "rashbam"),
    # "תוספ'" (medium abbreviation, ת-ו-ס-פ-') is at least as common in practice
    # as "תוס'" or the spelled-out "תוספות" -- confirmed real case: a whole run
    # of "cold start" בד"ה openers (lines 356-360+ in ערוך לנר על יבמות) fell
    # through to plain Gemara commentary because this pattern previously only
    # recognized "תוספות"/"תוס'" and never matched "בתוספ' ד"ה ...", so
    # active_intermediate was never (re)established and every later bare
    # "בד\"ה" opener silently had no book to inherit.
    (re.compile(r"^(?:ב|ו)?(?:תוספות|תוספ['׳]?|תוס['׳]?)\s+ב?ד[\"״]ה\s+(.+)$"), "tosafot"),
    (re.compile(r'^רד["״]ה\s+(.+)$'), "rashi"),
    (re.compile(r'^תוד["״]ה\s+(.+)$'), "tosafot"),
]
_BARE_DH_RE = re.compile(r'^ב?ד"ה\s+(.+)$')
_BOLD_BARE_DH_RE = re.compile(r'^<b>ב?ד"ה</b>\s*(.+)$')
_ATTRIB_ABBR_RE = re.compile(r'^(?:א[א-ת]"[א-ת]|בגמ\'?)\s+(?:כו\'?\s+)?(.+)$')


def flatten_leading_bold(text: str) -> str:
    """Turn leading bold spans into plain text without losing their words."""
    parts: List[str] = []
    remaining = text.strip()
    while True:
        m = B_LABEL_RE.match(remaining)
        if not m:
            break
        parts.append(m.group(1).strip())
        remaining = remaining[m.end():].lstrip()
    return " ".join(parts + ([remaining] if remaining else [])).strip() if parts else text.strip()


def detect_super_commentary_opener(
    text: str, active_intermediate: Optional[str]
) -> Optional[Tuple[str, str]]:
    text = re.sub(r'^(?:שם|עוד שם)\s+', '', text.strip())
    text = flatten_leading_bold(text)
    text = re.sub(r'^(?:שם|עוד שם)\s+', '', text)
    for pat, key in _NAME_DH_PATTERNS:
        m = pat.match(text)
        if m:
            return key, m.group(1).strip()
    m = _BARE_DH_RE.match(text)
    if m and active_intermediate:
        return active_intermediate, m.group(1).strip()
    m = _BOLD_BARE_DH_RE.match(text)
    if m and active_intermediate:
        return active_intermediate, m.group(1).strip()
    return None


def truncate_lemma(s: str) -> str:
    period_pos = s.find(".")
    colon_pos = s.find(":")
    candidates = [p for p in (period_pos, colon_pos) if p != -1]
    end = min(candidates) if candidates else len(s)
    return s[:end].strip()


def extract_dibur(text: str) -> str:
    m = _ATTRIB_ABBR_RE.match(text)
    working = m.group(1) if m else text
    return truncate_lemma(working)


_DASH_LEMMA_RE = re.compile(r'^(.*?)\s+[-–]\s+')


def candidate_own_lemma(content: str) -> str:
    m = _DASH_LEMMA_RE.match(content)
    if m:
        return m.group(1)
    return content


def extract_fresh_quote(rest: str) -> str:
    """Collect ALL leading consecutive <b>...</b> spans in `rest` (used only
    after we've already determined the first span is NOT a recognized label
    and NOT a book-switch keyword -- i.e. it's a real quoted phrase, not a
    label). Concatenates their contents and truncates at the first period/
    colon, same convention as every other dibur extraction in this module."""
    parts = []
    remaining = rest
    ended_in_bold = False
    while True:
        m = B_LABEL_RE.match(remaining)
        if not m:
            break
        raw_part = m.group(1).strip()
        parts.append(raw_part)
        remaining = remaining[m.end():]
        if "." in raw_part or ":" in raw_part:
            ended_in_bold = True
            break
    quote = " ".join(p for p in parts if p)
    # Printers often bold only the first word of a dibbur and leave the rest
    # plain until the colon.  A one-word bold anchor is too collision-prone,
    # so extend it to that explicit boundary.  Never cross a boundary already
    # present in the bold spans (e.g. <b>לעולם</b><b>:</b>).
    if not ended_in_bold and len(norm_words(quote)) < 3:
        plain = re.split(r"[.:]", remaining, maxsplit=1)[0].strip()
        if plain:
            quote = (quote + " " + plain).strip()
    return truncate_lemma(quote)


def score_candidate(dibur: str, content: str) -> int:
    d_tokens = [w for w in norm_words(dibur) if w not in STOPWORDS] or norm_words(dibur)
    c_tokens = norm_words(content)
    best_run = 0
    for start in range(len(c_tokens)):
        run = 0
        j = start
        for w in d_tokens:
            if j < len(c_tokens) and c_tokens[j] == w:
                run += 1
                j += 1
            else:
                break
        if run > best_run:
            best_run = run
    overlap = len(set(d_tokens) & set(c_tokens))
    score = best_run * 30 + overlap
    # Fix #1 (this version): exact lemma match beats everything; a dibur that
    # is an exact PREFIX of the candidate's own lemma (very common -- the
    # citer often quotes only the first word(s) of a longer lemma) is the
    # next strongest signal, well above generic overlap noise.
    lemma_tokens = norm_words(candidate_own_lemma(content))
    dibur_all_tokens = norm_words(dibur)
    if lemma_tokens and dibur_all_tokens:
        if lemma_tokens == dibur_all_tokens:
            score += 200000
        elif (len(dibur_all_tokens) <= len(lemma_tokens)
              and lemma_tokens[:len(dibur_all_tokens)] == dibur_all_tokens):
            score += 100000
    return score


_RANGE_RE = re.compile(r'^(.*?)\s+עד\s+ד"ה\s+(.+)$')


def split_range(text: str) -> Tuple[str, Optional[str]]:
    m = _RANGE_RE.match(text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text, None


AMBIGUITY_MARGIN = 15
MIN_MEANINGFUL_SCORE = 30


@dataclass
class MatchAssessment:
    target: Optional[Line]
    ambiguous: bool
    best_score: int = 0
    runner_up_score: Optional[int] = None
    informative_tokens: int = 0
    evidence: str = "none"
    review_reasons: List[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)


def assess_best_match(
    dibur: str, candidates: List[Line], min_line_index: int = 0
) -> MatchAssessment:
    """Choose a candidate and retain the evidence needed for a QA sidecar.

    The matcher still produces full coverage, but weak/short/ambiguous anchors
    are no longer indistinguishable from strong automatic decisions.
    """
    if not candidates:
        return MatchAssessment(None, False)
    scored = sorted(
        ((score_candidate(dibur, c.content), c) for c in candidates),
        key=lambda x: (-x[0], x[1].line_index),
    )
    best_score = scored[0][0]
    exact_ties = [sc for sc in scored if sc[0] == best_score]
    if len(exact_ties) > 1:
        forward_ties = [sc for sc in exact_ties if sc[1].line_index >= min_line_index]
        chosen = min(forward_ties, key=lambda sc: sc[1].line_index) if forward_ties \
            else min(exact_ties, key=lambda sc: sc[1].line_index)
    else:
        chosen = scored[0]

    near_ties = [sc for sc in scored if best_score - sc[0] < AMBIGUITY_MARGIN]
    ambiguous = len(near_ties) > 1
    informative = [w for w in norm_words(dibur) if w not in STOPWORDS] or norm_words(dibur)
    lemma_tokens = norm_words(candidate_own_lemma(chosen[1].content))
    dibur_tokens = norm_words(dibur)
    if lemma_tokens == dibur_tokens and lemma_tokens:
        evidence = "exact_lemma"
    elif dibur_tokens and lemma_tokens[:len(dibur_tokens)] == dibur_tokens:
        evidence = "lemma_prefix"
    elif best_score >= MIN_MEANINGFUL_SCORE:
        evidence = "token_run"
    else:
        evidence = "weak_overlap"

    reasons: List[str] = []
    if len(informative) < 2:
        reasons.append("anchor has fewer than two informative tokens")
    if best_score < MIN_MEANINGFUL_SCORE:
        reasons.append(f"weak absolute score {best_score}")
    if ambiguous:
        reasons.append("multiple candidates within ambiguity margin")
    return MatchAssessment(
        target=chosen[1],
        ambiguous=ambiguous,
        best_score=best_score,
        runner_up_score=scored[1][0] if len(scored) > 1 else None,
        informative_tokens=len(informative),
        evidence=evidence,
        review_reasons=reasons,
    )


def find_best_match(
    dibur: str, candidates: List[Line], min_line_index: int = 0
) -> Tuple[Optional[Line], bool]:
    """Fix #2 (this version, corrected): score the WHOLE pool first (no
    pre-filtering). BUT: monotonic order is only allowed to override the top
    scorer among EXACT ties for the best score -- using the wide
    AMBIGUITY_MARGIN band for that purpose (as an earlier attempt in this
    same session did) is wrong, because when every real candidate scores
    low (e.g. best=2, from weak generic overlap with no exact/prefix lemma
    bonus), a margin of 15 makes nearly the whole pool count as "tied",
    and the tie-break then picks the smallest line_index in the pool
    almost arbitrarily -- discarding a uniquely-highest-scoring candidate
    purely because something scoring far worse happened to sit earlier
    (confirmed real regression: citing line 73, "ד\"ה ואפילו מוכרי כסות",
    uniquely scored candidate at line 94, but the wide-margin tie-break
    overrode it in favor of line 92 which scored 0). The wider
    AMBIGUITY_MARGIN band is still used for the *disclosed* ambiguous flag
    (worth a human glance), but never to overrule a genuinely unique best
    score when choosing the target."""
    assessment = assess_best_match(dibur, candidates, min_line_index)
    return assessment.target, assessment.ambiguous


_FRONT_MATTER_RE = re.compile(r'^(מאת|מהדורת|נדפס|בעריכת)\b')
_COLOPHON_RE = re.compile(r'^<b>(?:סליק|תם ונשלם|תם וניתם)</b>')


def is_skippable_frontmatter(text: str, seen_first_content: bool, daf_key: Optional[str]) -> bool:
    if daf_key is None:
        return True
    if not seen_first_content and _FRONT_MATTER_RE.search(text):
        return True
    if _COLOPHON_RE.search(text):
        return True
    return False


def running_counts(lines: List[Line]) -> Dict[int, int]:
    counts = {}
    n = 0
    for ln in lines:
        if ln.tag == "h2":
            n = 0
            continue
        if ln.tag == "h1":
            continue
        if not ln.content.strip():
            continue
        n += 1
        counts[ln.line_index] = n
    return counts


@dataclass
class MatchResult:
    entries: List[dict] = field(default_factory=list)
    low_confidence: List[Tuple[int, str]] = field(default_factory=list)
    skipped_frontmatter: List[int] = field(default_factory=list)
    unresolved: List[Tuple[int, str]] = field(default_factory=list)
    review_items: List[dict] = field(default_factory=list)
    overrides_applied: List[int] = field(default_factory=list)


def match_citing_book(
    citing_path: str,
    base_title: str,
    base_path: str,
    intermediate_books: Optional[Dict[str, Tuple[str, str]]] = None,
    heref_lookup: Optional[Dict[str, Dict[int, str]]] = None,
) -> MatchResult:
    intermediate_books = intermediate_books or {}
    heref_lookup = heref_lookup or {}
    normalized_heref_lookup = {
        normalize_book_title(title): table for title, table in heref_lookup.items()
    }

    citing_lines = parse_book(citing_path)
    known_labels = (set(FIXED_KNOWN_LABELS) | build_frequent_labels(citing_lines)) - _DH_MARKER_KEYS

    base_lines = parse_book(base_path)
    base_daf_index = build_daf_index(base_lines)
    base_counts = running_counts(base_lines)

    inter_lines: Dict[str, List[Line]] = {}
    inter_daf_index: Dict[str, Dict[Optional[str], List[Line]]] = {}
    inter_counts: Dict[str, Dict[int, int]] = {}
    for key, (_title, path) in intermediate_books.items():
        lns = parse_book(path)
        inter_lines[key] = lns
        inter_daf_index[key] = build_daf_index(lns)
        inter_counts[key] = running_counts(lns)

    result = MatchResult()

    current_daf: Optional[str] = None
    active_intermediate: Optional[str] = None
    # Tracks the most recently *named* intermediate book (Rashi/Tosafot/...)
    # and, unlike active_intermediate, is NEVER cleared by a daf change or a
    # "<b>בגמרא</b>"/"<b>במשנה</b>" reset. A bare "ד\"ה"/"בד\"ה" opener with no
    # book name attached is never a reference to the Gemara itself -- Gemara
    # text is always quoted directly, never introduced by "ד\"ה" -- so when
    # active_intermediate has just been reset to None (e.g. right after a
    # fresh <h2> daf or an explicit "בגמרא" aside) a subsequent nameless
    # "בד\"ה" must still fall back to whichever commentary was last discussed,
    # not silently default to the Gemara. Confirmed real cases: citing lines
    # 1454, 1456, 1632 in ערוך לנר על יבמות, each a bare "<b>בד\"ה</b> ..."
    # immediately after a daf-reset with no intervening book-name label.
    last_used_intermediate: Optional[str] = None
    last_line: Dict[str, int] = {"base": 0}
    for key in intermediate_books:
        last_line[key] = 0

    seen_first_content = False

    def pools_for(book_key: str):
        if book_key == "base":
            return base_daf_index.get(current_daf, []), base_title, base_path, base_counts
        title, path = intermediate_books[book_key]
        return inter_daf_index[book_key].get(current_daf, []), title, path, inter_counts[book_key]

    def heref_for(title: str, target_line_index_1based: int, fallback_daf: str, fallback_count: int) -> str:
        table = heref_lookup.get(title) or normalized_heref_lookup.get(normalize_book_title(title))
        if table is not None:
            href = table.get(target_line_index_1based - 1)
            if href:
                return href
        return f"{title} {fallback_daf}, {fallback_count}"

    def push_entry(citing_idx: int, target_line: Line, book_key: str, conn_type: str, low_conf: bool,
                   end_line_index: Optional[int] = None, review: Optional[MatchAssessment] = None):
        _cands, title, path, counts = pools_for(book_key)
        heref = heref_for(title, target_line.line_index, current_daf or "", counts.get(target_line.line_index, 0))
        entry = {
            "line_index_1": citing_idx,
            "line_index_2": target_line.line_index,
            "heRef_2": heref,
            "path_2": path.split("/")[-1].split("\\")[-1],
            "Conection Type": conn_type,
        }
        if end_line_index is not None:
            entry["line_index_2_end"] = end_line_index
        result.entries.append(entry)
        last_line[book_key] = end_line_index if end_line_index is not None else target_line.line_index
        if low_conf:
            reasons = review.review_reasons if review else ["ambiguous match"]
            reason_text = "; ".join(reasons)
            result.low_confidence.append(
                (citing_idx, f"{reason_text}; chose {book_key} line {target_line.line_index}")
            )
            result.review_items.append({
                "line_index_1": citing_idx,
                "chosen_book": book_key,
                "line_index_2": target_line.line_index,
                "reasons": reasons,
                "best_score": review.best_score if review else None,
                "runner_up_score": review.runner_up_score if review else None,
                "informative_tokens": review.informative_tokens if review else None,
                "evidence": review.evidence if review else None,
            })

    def resolve_dibur(dibur: str, cands: List[Line], min_line_index: int, citing_idx: int):
        dibur_start, dibur_end = split_range(dibur)
        dibur_start = truncate_lemma(dibur_start)
        assessment = assess_best_match(dibur_start, cands, min_line_index)
        best, amb = assessment.target, assessment.needs_review
        if best is None or dibur_end is None:
            return best, amb, None, assessment
        dibur_end = truncate_lemma(dibur_end)
        end_cands = [c for c in cands if c.line_index >= best.line_index]
        end_assessment = assess_best_match(dibur_end, end_cands, best.line_index)
        end_best, end_amb = end_assessment.target, end_assessment.needs_review
        if end_best is not None and end_best.line_index >= best.line_index:
            if end_amb:
                assessment.review_reasons.extend(
                    "range end: " + reason for reason in end_assessment.review_reasons
                )
            return best, (amb or end_amb), end_best.line_index, assessment
        result.low_confidence.append(
            (citing_idx, f"range end \"{dibur_end[:30]}\" not resolved at/after start line {best.line_index}; "
                         f"using single-line anchor")
        )
        assessment.review_reasons.append("range end could not be resolved")
        return best, True, None, assessment

    for ln in citing_lines:
        if ln.tag == "h1":
            continue
        if ln.tag == "h2":
            current_daf = ln.daf_key
            active_intermediate = None
            continue

        text = ln.content.strip()
        if not text:
            continue
        if is_skippable_frontmatter(text, seen_first_content, current_daf):
            result.skipped_frontmatter.append(ln.line_index)
            continue
        section_has_target = (
            current_daf in base_daf_index
            or any(current_daf in index for index in inter_daf_index.values())
        )
        if not section_has_target:
            # Introductory sections such as <h2>הקדמה</h2> have no matching
            # section in any target book and are legitimate front matter.
            result.skipped_frontmatter.append(ln.line_index)
            continue
        seen_first_content = True

        label, rest = extract_b_label(text, known_labels)
        label_named_new_book = False
        if label:
            norm = label.replace('"', "").replace("'", "")
            if "גמרא" in norm or "משנה" in norm:
                active_intermediate = None
                label_named_new_book = True
            elif any(k in norm for k in ("תוס", "רש")):
                matched_key = None
                for key, (title, _path) in intermediate_books.items():
                    if key in norm or (key == "tosafot" and "תוס" in norm) or (key == "rashi" and "רש" in norm):
                        matched_key = key
                        break
                if matched_key:
                    active_intermediate = matched_key
                    last_used_intermediate = matched_key
                    label_named_new_book = True
            text_for_matching = rest
        else:
            text_for_matching = text

        if label and not label_named_new_book and is_pure_continuation_label(label):
            book_key = active_intermediate or "base"
            prev = last_line.get(book_key, 0)
            cands, _title, _path, _counts = pools_for(book_key)
            conn_type = "super_commentary" if book_key != "base" else "commentary"
            rest_stripped = rest.lstrip()

            # Fix (this version), part A: a PURE_CONTINUATION_LABEL like "שם"
            # is sometimes immediately followed by an explicit sub-opener, e.g.
            # "<b>שם</b> <b>ד"ה</b> אלא מליקה..." -- resolve that exactly like
            # any other super-commentary opener (same resolve_dibur pipeline),
            # searching forward from wherever that book last matched (NOT
            # gated on whether the plain continuation-inherit anchor is still
            # in the current daf window -- confirmed real case: line 2592).
            sub_opener = detect_super_commentary_opener(
                rest_stripped, active_intermediate or last_used_intermediate
            )
            if sub_opener:
                opener_book_key, opener_dibur = sub_opener
                resolved_key = opener_book_key if opener_book_key in intermediate_books else "base"
                opener_cands, _t, _p, _c = pools_for(resolved_key)
                best, amb, end_idx, review = resolve_dibur(
                    opener_dibur, opener_cands, last_line.get(resolved_key, 0), ln.line_index
                )
                if best is not None:
                    if opener_book_key in intermediate_books:
                        active_intermediate = opener_book_key
                        last_used_intermediate = opener_book_key
                    opener_conn = "super_commentary" if opener_book_key in intermediate_books else "commentary"
                    push_entry(ln.line_index, best, resolved_key, opener_conn, low_conf=amb,
                               end_line_index=end_idx, review=review)
                    continue

            # Fix (this version), part B: otherwise, the label may be followed
            # by ANOTHER bold span that is NOT itself a recognized label and
            # NOT a book-switch keyword -- i.e. a real fresh quoted phrase from
            # the currently-active book (confirmed real case: line 3238
            # "<b>שם</b> <b>לחברתה</b> <b>לעולם</b><b>:</b>" is not "continue
            # exactly where line 3237 left off" -- it quotes a DIFFERENT,
            # later phrase from the same Gemara sugya). Try to resolve that
            # fresh quote as a real dibur (searching forward from the previous
            # anchor) before falling back to blind inheritance.
            m2 = B_LABEL_RE.match(rest_stripped)
            fresh_quote = None
            if m2:
                second_raw = m2.group(1)
                norm2 = second_raw.replace('"', "").replace("'", "")
                key2 = _norm_label_key(second_raw)
                is_book_switch = ("גמרא" in norm2 or "משנה" in norm2
                                   or "תוס" in norm2 or "רש" in norm2)
                if not is_book_switch and key2 not in known_labels:
                    fresh_quote = extract_fresh_quote(rest_stripped)

            if fresh_quote and cands:
                best, amb, end_idx, review = resolve_dibur(fresh_quote, cands, prev, ln.line_index)
                if best is not None:
                    push_entry(ln.line_index, best, book_key, conn_type, low_conf=amb,
                               end_line_index=end_idx, review=review)
                    continue

            # Fix (this version), part C: only now fall back to plain blind
            # inheritance of the previous anchor line, and only NOW report
            # unresolved if that anchor cannot be found either.
            if prev == 0:
                result.unresolved.append((ln.line_index, "continuation-label with no prior anchor to inherit"))
                continue
            prev_line_obj = next((c for c in cands if c.line_index == prev), None)
            if prev_line_obj is None:
                result.unresolved.append((ln.line_index, "continuation-label target line no longer in daf window"))
                continue
            push_entry(ln.line_index, prev_line_obj, book_key, conn_type, low_conf=False)
            continue

        # An explicit commentator+ד"ה opener outranks a generic leading
        # continuation word.  Forms such as `שם <b>ברש"י</b> ד"ה ...` must
        # switch books rather than blindly inherit the preceding base target.
        opener = detect_super_commentary_opener(
            text_for_matching, active_intermediate or last_used_intermediate
        )
        if opener:
            book_key, dibur = opener
            if book_key in intermediate_books:
                active_intermediate = book_key
                last_used_intermediate = book_key
            resolved_key = book_key if book_key in intermediate_books else "base"
            cands, _title, _path, _counts = pools_for(resolved_key)
            best, amb, end_idx, review = resolve_dibur(
                dibur, cands, last_line.get(resolved_key, 0), ln.line_index
            )
            if best is None:
                result.unresolved.append((ln.line_index, f"no candidates for super-commentary dibur '{dibur[:30]}'"))
                continue
            conn_type = "super_commentary" if book_key in intermediate_books else "commentary"
            push_entry(ln.line_index, best, resolved_key, conn_type, low_conf=amb,
                       end_line_index=end_idx, review=review)
            continue

        if is_continuation_opener(text_for_matching):
            book_key = active_intermediate or "base"
            prev = last_line.get(book_key, 0)
            if prev == 0:
                result.unresolved.append((ln.line_index, "continuation with no prior anchor to inherit"))
                continue
            cands, _title, _path, _counts = pools_for(book_key)
            prev_line_obj = next((c for c in cands if c.line_index == prev), None)
            if prev_line_obj is None:
                result.unresolved.append((ln.line_index, "continuation target line no longer in daf window"))
                continue
            conn_type = "super_commentary" if book_key != "base" else "commentary"
            push_entry(ln.line_index, prev_line_obj, book_key, conn_type, low_conf=False)
            continue

        book_key = active_intermediate if active_intermediate in intermediate_books else "base"
        dibur = extract_dibur(text_for_matching)
        if not dibur:
            result.unresolved.append((ln.line_index, "could not extract a dibur to match"))
            continue
        cands, _title, _path, _counts = pools_for(book_key)
        best, amb, end_idx, review = resolve_dibur(
            dibur, cands, last_line.get(book_key, 0), ln.line_index
        )
        if best is None:
            result.unresolved.append((ln.line_index, f"no candidates in daf window for dibur '{dibur[:30]}'"))
            continue
        conn_type = "super_commentary" if book_key != "base" else "commentary"
        push_entry(ln.line_index, best, book_key, conn_type, low_conf=amb,
                   end_line_index=end_idx, review=review)

    return result


def self_check_super_commentary(citing_path: str, entries: List[dict], known_labels: set) -> List[int]:
    by_line = {e["line_index_1"]: e for e in entries}
    flagged: List[int] = []
    for ln in parse_book(citing_path):
        if ln.tag is not None:
            continue
        text = ln.content.strip()
        if not text:
            continue

        # Preserve the words inside leading bold spans so the audit can see
        # both <b>רש"י ד"ה ...</b> and <b>רש"י</b> ד"ה ... forms.
        flattened = flatten_leading_bold(text)

        trigger_text = re.sub(r'^(?:שם|עוד שם)\s+', '', flattened)
        explicit = detect_super_commentary_opener(trigger_text, active_intermediate=None)
        bare_dh = bool(_BARE_DH_RE.match(trigger_text))
        entry = by_line.get(ln.line_index)
        is_super_entry = bool(entry and entry.get("Conection Type") == "super_commentary")

        # Explicit names are definite F8 candidates. Bare ד"ה lines are F9/F6
        # candidates: some are direct-base or split-parenthesis false positives,
        # but silently dropping them is worse than requiring the semantic QA
        # pass mandated by the skill.
        if (explicit or bare_dh) and not is_super_entry:
            flagged.append(ln.line_index)
    return flagged


def write_links_json(entries: List[dict], out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


LINK_ENTRY_KEYS = {
    "line_index_1", "line_index_2", "heRef_2", "path_2", "Conection Type",
}


def load_manual_overrides(path: str) -> Dict[int, Optional[dict]]:
    """Load {"<line_index_1>": <five-field entry or null>} overrides."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("manual overrides root must be a JSON object")
    overrides: Dict[int, Optional[dict]] = {}
    for raw_idx, entry in raw.items():
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid override line index: {raw_idx!r}") from exc
        if entry is not None:
            if not isinstance(entry, dict) or set(entry) != LINK_ENTRY_KEYS:
                raise ValueError(
                    f"override {idx} must contain exactly {sorted(LINK_ENTRY_KEYS)} or be null"
                )
            if entry["line_index_1"] != idx:
                raise ValueError(f"override key {idx} disagrees with line_index_1")
        overrides[idx] = entry
    return overrides


def apply_manual_overrides(
    result: MatchResult, overrides: Dict[int, Optional[dict]], citing_line_count: int
) -> None:
    by_line = {e["line_index_1"]: e for e in result.entries}
    for idx, entry in overrides.items():
        if idx < 1 or idx > citing_line_count:
            raise ValueError(f"override line {idx} is outside citing book")
        if entry is None:
            by_line.pop(idx, None)
        else:
            by_line[idx] = entry
        result.overrides_applied.append(idx)
    overridden = set(overrides)
    result.entries = sorted(by_line.values(), key=lambda e: e["line_index_1"])
    result.unresolved = [(idx, why) for idx, why in result.unresolved if idx not in overridden]
    result.low_confidence = [(idx, why) for idx, why in result.low_confidence if idx not in overridden]
    result.review_items = [item for item in result.review_items
                           if item["line_index_1"] not in overridden]


def write_qa_report(
    path: str, result: MatchResult, citing_path: str, super_flags: List[int]
) -> None:
    contents = {ln.line_index: ln.content for ln in parse_book(citing_path)}
    report = {
        "summary": {
            "entries": len(result.entries),
            "needs_review": len(result.review_items),
            "unresolved": len(result.unresolved),
            "skipped_frontmatter": len(result.skipped_frontmatter),
            "overrides_applied": len(result.overrides_applied),
            "super_commentary_flags": len(super_flags),
        },
        "needs_review": [
            {**item, "citing_text": contents.get(item["line_index_1"], "")}
            for item in result.review_items
        ],
        "unresolved": [
            {"line_index_1": idx, "reason": why, "citing_text": contents.get(idx, "")}
            for idx, why in result.unresolved
        ],
        "skipped_frontmatter": result.skipped_frontmatter,
        "overrides_applied": sorted(result.overrides_applied),
        "super_commentary_flags": super_flags,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def load_existing_links(path: str) -> List[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def merge_entries(existing: List[dict], new_entries: List[dict]) -> Tuple[List[dict], dict]:
    new_keys = {(e["path_2"], e["Conection Type"]) for e in new_entries}
    kept: List[dict] = []
    removed_count = 0
    insert_at: Optional[int] = None
    for e in existing:
        key = (e.get("path_2"), e.get("Conection Type"))
        if key in new_keys:
            removed_count += 1
            if insert_at is None:
                insert_at = len(kept)
            continue
        kept.append(e)
    if insert_at is None:
        insert_at = len(kept)
    merged = kept[:insert_at] + new_entries + kept[insert_at:]
    summary = {
        "existing_total": len(existing),
        "removed_stale": removed_count,
        "added_new": len(new_entries),
        "kept_untouched": len(kept),
        "replaced_keys": sorted(new_keys),
    }
    return merged, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--citing", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--target-title", required=True)
    ap.add_argument("--intermediate", nargs=3, action="append", default=[])
    ap.add_argument("--heref-dump", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--merge-into")
    ap.add_argument("--confirm-merge", action="store_true")
    ap.add_argument("--overrides", help="JSON map of line_index_1 to a five-field entry or null")
    ap.add_argument("--qa-report", help="write confidence/unresolved metadata outside _links.json")
    ap.add_argument(
        "--allow-incomplete", action="store_true",
        help="explicitly allow writing an intermediate output with unresolved content lines",
    )
    args = ap.parse_args()

    intermediate = {key: (title, path) for key, path, title in args.intermediate}

    with open(args.heref_dump, encoding="utf-8") as f:
        raw_dump = json.load(f)
    heref_lookup = {
        title: {int(k): v for k, v in table.items() if v is not None}
        for title, table in raw_dump.items()
    }

    result = match_citing_book(args.citing, args.target_title, args.target, intermediate, heref_lookup)

    if args.overrides:
        overrides = load_manual_overrides(args.overrides)
        citing_line_count = len(parse_book(args.citing))
        apply_manual_overrides(result, overrides, citing_line_count)

    citing_lines_for_check = parse_book(args.citing)
    known_labels = (set(FIXED_KNOWN_LABELS) | build_frequent_labels(citing_lines_for_check)) - _DH_MARKER_KEYS
    flagged = self_check_super_commentary(args.citing, result.entries, known_labels)

    if args.qa_report:
        write_qa_report(args.qa_report, result, args.citing, flagged)

    if result.unresolved and not args.allow_incomplete:
        print("REFUSED: " + str(len(result.unresolved)) + " content lines remain unresolved.")
        print("Supply --overrides for them, or use --allow-incomplete only for a review artifact.")
        return 2

    if args.merge_into:
        existing = load_existing_links(args.merge_into)
        merged, summary = merge_entries(existing, result.entries)
        print("=== merge dry-run summary for " + args.merge_into + " ===")
        print("existing entries: " + str(summary['existing_total']))
        print("stale entries that will be replaced: " + str(summary['removed_stale']))
        for path_2, conn in summary["replaced_keys"]:
            print("  - path_2=" + repr(path_2) + " Conection Type=" + repr(conn))
        print("entries kept untouched: " + str(summary['kept_untouched']))
        print("new entries being written in their place: " + str(summary['added_new']))
        if args.confirm_merge:
            write_links_json(merged, args.merge_into)
            print("CONFIRMED: wrote " + str(len(merged)) + " total entries to " + args.merge_into)
        else:
            print("Dry-run only -- nothing written. Re-run with --confirm-merge to perform this merge.")
    else:
        write_links_json(result.entries, args.out)
        print("wrote " + str(len(result.entries)) + " entries to " + args.out)

    print("low-confidence (ambiguous) matches: " + str(len(result.low_confidence)))
    for idx, why in result.low_confidence:
        print("  line " + str(idx) + ": " + why)
    print("unresolved lines (no entry written): " + str(len(result.unresolved)))
    for idx, why in result.unresolved[:40]:
        print("  line " + str(idx) + ": " + why)
    print("skipped as front-matter: " + str(result.skipped_frontmatter))
    print("self-check F8/F9 flags (opener text but typed commentary): " + str(flagged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
