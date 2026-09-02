"""In-process throttle for login attempts by IP address (T-82).

One backend process, no shared store: this exists to blunt casual hammering
of bcrypt before a request pays for it, not to survive multiple replicas.
Revisit with a shared store (Redis or similar) if the backend ever scales
past one process.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from threading import Lock

_lock = Lock()
_attempts: dict[str, list[datetime]] = defaultdict(list)
_calls_since_sweep = 0
# Bounds the worst case between sweeps to this many distinct new keys, not
# "however many addresses show up before this one gets checked again": a
# flood of one-off addresses, each seen once and never again, would otherwise
# leave an entry behind forever, since `check` only ever prunes the key it
# was called with.
_SWEEP_EVERY = 1000


class TooManyAttempts(Exception):
    """This key has been seen too often in the current window."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("too many attempts from this address")
        self.retry_after_seconds = retry_after_seconds


def _sweep_stale_keys(window_minutes: int) -> None:
    """Drop every key with nothing left inside the window.

    Called under the lock `check` already holds. Walking the whole dict is
    the one operation here that scales with its size, which is why this runs
    every `_SWEEP_EVERY` calls instead of on every one.
    """
    window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)
    stale = [key for key, seen in _attempts.items() if not seen or max(seen) <= window_start]
    for key in stale:
        del _attempts[key]


def check(key: str, *, max_attempts: int, window_minutes: int) -> None:
    """Record one attempt for `key`, raising if the window is already full.

    A fixed sliding window per key: attempts older than `window_minutes` are
    dropped before counting, so the limit always looks at "the last N
    minutes", not a window that resets on a clock boundary.
    """
    global _calls_since_sweep
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=window_minutes)
    with _lock:
        recent = [seen for seen in _attempts[key] if seen > window_start]
        if len(recent) >= max_attempts:
            oldest = min(recent)
            retry_after = int((oldest + timedelta(minutes=window_minutes) - now).total_seconds())
            _attempts[key] = recent
            raise TooManyAttempts(max(1, retry_after))
        recent.append(now)
        _attempts[key] = recent

        _calls_since_sweep += 1
        if _calls_since_sweep >= _SWEEP_EVERY:
            _calls_since_sweep = 0
            _sweep_stale_keys(window_minutes)


def reset() -> None:
    """Test-only: clear every counter.

    The state above is process-global, so tests that share a process (the
    whole suite does) must not leak attempts from one test's client into the
    next one's. See `panel_client`/`postgres_panel_client` in `conftest.py`.
    """
    global _calls_since_sweep
    with _lock:
        _attempts.clear()
        _calls_since_sweep = 0
