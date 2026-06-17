"""Store-agnostic title-matching primitives (vendored).

VENDORED COPY from the unifideck-decky plugin
(`py_modules/unifideck/utils/title_match.py`). Kept standalone here so the
unifiDB CI enrichment step (`enrich_save_locations.py`) can match Ludusavi
save-game entries to IGDB records WITHOUT importing the plugin. Keep the two
copies in sync if the matching logic changes.

Pure functions + the 58-entry edition-suffix table. Pure means no I/O,
no async, no logging — testable in isolation. Normalisation / edition
stripping / Jaccard scoring are storefront-independent, so any feature that
resolves a free-form game title to an external id should clean titles through
these helpers so matching stays consistent.
"""
from __future__ import annotations

import re
import unicodedata

# 58-entry suffix table, longest-first within each group so
# "xbox series xs edition" gets stripped before "xbox edition" /
# "edition" alone. The iterative outer loop in ``strip_edition_suffix``
# restarts after each strip so compound suffixes work end-to-end
# (e.g. "X Standard Edition Windows" → strip Windows → strip
# Standard Edition → "X").
EDITION_SUFFIXES: tuple[str, ...] = (
    # Platform / console suffixes
    "xbox series xs edition", "xbox one edition", "xbox edition",
    "xbox series xs", "xbox one version", "xbox one",
    "pc edition", "windows 10 edition", "windows edition",
    "console edition",
    "for pc", "for windows", "for xbox",
    # Distribution / bundle suffixes
    "cross gen bundle", "cross gen edition", "game preview",
    "the complete season", "the complete first season",
    # Full edition names
    "deluxe edition", "gold edition", "ultimate edition",
    "complete edition", "goty edition", "game of the year edition",
    "definitive edition", "enhanced edition", "special edition",
    "anniversary edition", "premium edition", "standard edition",
    "legacy edition", "collectors edition", "limited edition",
    "digital edition", "classic edition", "royal edition",
    "legendary edition", "elite edition", "ea play edition",
    "remastered", "remake", "directors cut", "the final cut",
    "unofficial patch",
    "revolution",
    "digital version",
    # Short / standalone (word boundary ensured by space-prefix check)
    "goty", "hd", "ce", "dlc", "windows", "console", "xs",
)


def normalize_for_match(title: str) -> str:
    """Lowercase + strip symbols + collapse whitespace.

    Steps in order: lowercase+trim; dual-language "Game / Jeu" → first half;
    ® ™ © → space; NFKD-decompose + strip combining marks; strip (TM)(R)(C);
    & → and; smart-quotes → ASCII; _ / - → space; | → empty; remaining
    punctuation → space; collapse whitespace. Empty input returns "".
    """
    if not title:
        return ""
    t = title.lower().strip()
    if " / " in t:
        t = t.split(" / ", 1)[0].strip()
    t = re.sub(r"[®™©]", " ", t)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\((?:tm|r|c)\)", "", t, flags=re.IGNORECASE)
    t = t.replace("&", " and ")
    t = t.replace("‘", "'").replace("’", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("_", " ").replace("-", " ").replace("|", "")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def strip_edition_suffix(normalized: str) -> str:
    """Iteratively strip edition / platform / variant suffixes."""
    changed = True
    while changed:
        changed = False
        for strip in _STRIP_STRATEGIES:
            stripped = strip(normalized)
            if stripped and stripped != normalized:
                normalized = stripped
                changed = True
                break
    return normalized


def _strip_known_suffix(s: str) -> str | None:
    for suffix in EDITION_SUFFIXES:
        if s.endswith(" " + suffix):
            stripped = s[: -(len(suffix) + 1)].strip()
            if stripped:
                return stripped
    return None


def _strip_edition_phrase(s: str) -> str | None:
    m = re.match(r"^(.+?)\s+(?:\w+\s+){0,2}edition$", s)
    return m.group(1).strip() if m and m.group(1).strip() else None


def _strip_chapters_episodes(s: str) -> str | None:
    m = re.match(r"^(.+?)\s+(?:chapters?|episodes?)\s+[\d\s]+$", s)
    return m.group(1).strip() if m and m.group(1).strip() else None


def _strip_trailing_year(s: str) -> str | None:
    m = re.match(r"^(.+?\D)\s+(\d{4})$", s)
    if m and 1980 <= int(m.group(2)) <= 2030 and m.group(1).strip():
        return m.group(1).strip()
    return None


_STRIP_STRATEGIES = (
    _strip_known_suffix,
    _strip_edition_phrase,
    _strip_chapters_episodes,
    _strip_trailing_year,
)


def score_match(query_norm: str, candidate_norm: str) -> float:
    """Jaccard word-set overlap with prefix-match bonus. Returns [0.0, 1.0]."""
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    qw = set(query_norm.split())
    cw = set(candidate_norm.split())
    if qw == cw:
        return 0.95
    intersection = qw & cw
    union = qw | cw
    jaccard = len(intersection) / len(union) if union else 0.0

    ql = query_norm.split()
    cl = candidate_norm.split()
    if len(ql) <= len(cl) and ql == cl[: len(ql)]:
        prefix_score = max(0.50, len(ql) / len(cl))
        jaccard = max(jaccard, prefix_score)
    return jaccard


PUBLISHER_PREFIXES: tuple[str, ...] = (
    "ea sports", "tom clancy s", "sid meier s", "disney pixar",
    "dreamworks", "marvel s", "warner bros", "2k", "microsoft", "disney",
)

_ROMAN_TO_ARABIC: dict[str, str] = {
    "ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8",
    "ix": "9", "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15",
}

_EDITION_TOKENS: frozenset[str] = frozenset(
    {"edition", "of", "the", "year", "game"}
    | {word for suffix in EDITION_SUFFIXES for word in suffix.split()},
)


def _strip_publisher_prefix(normalized: str) -> str:
    for prefix in PUBLISHER_PREFIXES:
        if normalized.startswith(prefix + " "):
            return normalized[len(prefix):].strip()
    return normalized


def _fold_roman_numerals(normalized: str) -> str:
    return " ".join(_ROMAN_TO_ARABIC.get(w, w) for w in normalized.split())


def _is_edition_remainder(remainder: str) -> bool:
    words = remainder.split()
    return bool(words) and all(
        w in _EDITION_TOKENS or re.fullmatch(r"(?:19|20)\d{2}", w)
        for w in words
    )


def _core_title_match(qn: str, cn: str, threshold: float) -> bool:
    if qn == cn:
        return True
    qb = strip_edition_suffix(qn)
    cb = strip_edition_suffix(cn)
    if qb and qb == cb:
        return True
    for longer, shorter in ((cn, qn), (qn, cn)):
        if longer.startswith(shorter + " ") and _is_edition_remainder(
            longer[len(shorter):].strip(),
        ):
            return True
    return max(
        score_match(qn, cn), score_match(qb, cb),
    ) >= threshold


def titles_match(query: str, candidate: str, threshold: float = 0.85) -> bool:
    """Decide whether a storefront result *candidate* IS the game *query*."""
    qn = normalize_for_match(query)
    cn = normalize_for_match(candidate)
    if not qn or not cn:
        return False
    q_forms = {qn, _strip_publisher_prefix(qn)}
    q_forms |= {_fold_roman_numerals(f) for f in q_forms}
    c_forms = {cn, _strip_publisher_prefix(cn)}
    c_forms |= {_fold_roman_numerals(f) for f in c_forms}
    return any(
        _core_title_match(q, c, threshold)
        for q in q_forms
        for c in c_forms
    )
