"""Tokenizing, language detection and snippet helpers (stdlib only)."""
import re
import unicodedata
from urllib.parse import urlsplit

TOKEN = re.compile(r"\w+", re.UNICODE)

STOP_EN = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be",
    "with", "at", "by", "from", "this", "that", "it", "as", "what", "how", "why", "who", "when",
}
# Afaan Oromoo function words (used for stop-word removal and language detection)
STOP_OM = {
    "fi", "kan", "kana", "ni", "akka", "irra", "keessa", "yoo", "garuu", "ykn", "waan", "isa", "isaan",
    "ani", "ati", "nuti", "jira", "dha", "ture", "gara", "waliin", "booda", "dura", "kanaaf", "illee",
    "jedhu", "jedhame", "ta'e", "ta", "kun", "sun", "an", "si", "isin", "hin", "moo", "eessa", "maal",
}
STOP = STOP_EN | STOP_OM


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text or "")]


def content_tokens(text: str) -> list[str]:
    toks = tokens(text)
    kept = [t for t in toks if t not in STOP]
    return kept or toks


def strip_accents(s: str) -> str:
    """Remove combining marks (é -> e), like the unaccent() that PostgreSQL applies when indexing."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def ts_term(token: str, prefix: bool = False) -> str:
    """One term of a PostgreSQL ``to_tsquery`` expression, quoted so it can never act as an operator."""
    return "'" + token.replace("\\", "\\\\").replace("'", "''") + "'" + (":*" if prefix else "")


def fts_query(q: str, mode: str = "and") -> str | None:
    """Build a safe ``to_tsquery`` expression. Every term is quoted; the last term is a prefix match."""
    toks = content_tokens(q)[:12]
    if not toks:
        return None
    parts = [ts_term(t) for t in toks]
    parts[-1] = ts_term(toks[-1], prefix=True)
    return (" | " if mode == "or" else " & ").join(parts)


def detect_lang(text: str, html_lang: str | None = None) -> str:
    if html_lang:
        code = html_lang.strip().lower().split("-")[0]
        if code in ("om", "en", "am", "so", "ti", "ar", "fr", "sw"):
            return code
    toks = tokens(text[:4000])
    if len(toks) < 8:
        return "und"
    om = sum(t in STOP_OM for t in toks)
    en = sum(t in STOP_EN for t in toks)
    if om > en and om / len(toks) > 0.06:
        return "om"
    if en / len(toks) > 0.08:
        return "en"
    return "und"


def host(url: str) -> str:
    h = urlsplit(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def make_snippet(body: str, q_tokens: list[str], width: int = 220) -> str:
    body = re.sub(r"\s+", " ", body or "").strip()
    if not body:
        return ""
    low = body.lower()
    pos = -1
    for t in q_tokens:
        i = low.find(t)
        if i != -1 and (pos == -1 or i < pos):
            pos = i
    start = max(0, pos - width // 3) if pos != -1 else 0
    end = min(len(body), start + width)
    snippet = body[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(body) else "")


def levenshtein(a: str, b: str, limit: int = 3) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]
