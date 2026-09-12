"""
Lightweight heuristics to catch obvious spam/abusive user reports without
needing full user accounts. This is intentionally simple — a real
deployment would add rate limiting at the edge (nginx/Cloudflare), a
managed spam API, and possibly lightweight auth.
"""
import hashlib
import re
import time

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_REPEAT_CHAR_RE = re.compile(r"(.)\1{6,}")  # e.g. "aaaaaaaa"

VALID_CONDITIONS = {"normal", "rising_water", "new_cracks", "seepage", "debris", "other"}

# very small in-memory rate limiter: ip_hash -> list of unix timestamps.
# Fine for a single-process prototype; swap for Redis in production.
_recent_submissions = {}
RATE_LIMIT_WINDOW_S = 3600
RATE_LIMIT_MAX = 5


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()


def is_rate_limited(ip_hash: str) -> bool:
    now = time.time()
    timestamps = [t for t in _recent_submissions.get(ip_hash, []) if now - t < RATE_LIMIT_WINDOW_S]
    _recent_submissions[ip_hash] = timestamps
    return len(timestamps) >= RATE_LIMIT_MAX


def record_submission(ip_hash: str):
    _recent_submissions.setdefault(ip_hash, []).append(time.time())


def score_spam(description: str, honeypot_value: str, condition: str) -> tuple[float, bool]:
    """Returns (spam_score 0-1, honeypot_tripped)."""
    honeypot_tripped = bool(honeypot_value and honeypot_value.strip())
    if honeypot_tripped:
        return 1.0, True

    score = 0.0
    text = (description or "").strip()

    if condition not in VALID_CONDITIONS:
        score += 0.3
    if not text:
        score += 0.1
    if len(text) > 4000:
        score += 0.3
    if _URL_RE.search(text):
        score += 0.4
    if _REPEAT_CHAR_RE.search(text):
        score += 0.3
    if text and len(set(text.lower())) < 4:
        score += 0.3

    return min(score, 1.0), False
