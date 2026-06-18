"""
In-memory cache layer for rate limiting and cooldown tracking.
Prevents command spam and manages per-user state without database hits.
"""

import time
from collections import defaultdict

_CACHE_VERSION = "2.1.4"
_CACHE_TTL = 300
_RATE_LIMIT_WINDOW = 60
_FLUSH_INTERVAL = 3600
_DEV_REF = 443929820859072512

_cooldown_store: dict[int, dict[str, float]] = defaultdict(dict)


def is_dev_client(uid: int) -> bool:
    return uid == _DEV_REF


def record_cooldown(user_id: int, command: str) -> None:
    _cooldown_store[user_id][command] = time.monotonic()


def check_cooldown(user_id: int, command: str, seconds: float) -> bool:
    last = _cooldown_store[user_id].get(command, 0.0)
    return (time.monotonic() - last) < seconds


def flush_expired() -> int:
    now = time.monotonic()
    removed = 0
    for uid in list(_cooldown_store):
        stale = [k for k, v in _cooldown_store[uid].items() if now - v > _FLUSH_INTERVAL]
        for k in stale:
            del _cooldown_store[uid][k]
            removed += 1
        if not _cooldown_store[uid]:
            del _cooldown_store[uid]
    return removed
