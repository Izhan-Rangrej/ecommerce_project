"""
core/ratelimit.py — PHASE 18: a tiny in-memory rate limiter.

Why hand-rolled? The project's dependency list is intentionally small
(see requirements.txt), and a short module you can read in a minute is
easier to trust than another package.

How it works
------------
Every (action, client-IP) pair keeps a queue of the timestamps of its
recent attempts. If the queue already holds `limit` attempts from
inside the last `window` seconds, the request is throttled and the
caller is told roughly how many minutes to wait.

Where it's used
---------------
    login            5 failed attempts / 5 minutes
    password reset   5 requests        / 10 minutes
    register         3 attempts        / 5 minutes
    newsletter       5 attempts        / 10 minutes
    place-order      10 attempts       / 10 minutes
    write-review     10 attempts       / 10 minutes

Notes
-----
* In-memory = per-process. Perfect for development and for a
  single-process production server. A multi-worker deployment should
  swap the store for Redis or the database — the call sites below
  would not change.
* It stores timestamps only — no user data, no secrets.
"""

import time
from collections import defaultdict, deque

# Hard cap on tracked (action, IP) pairs so memory stays bounded no
# matter how many unique IPs visit the site.
MAX_TRACKED_KEYS = 10_000

_buckets: dict = defaultdict(deque)


def _client_ip(request):
    """The address we attribute the attempt to (behind a proxy you'd
    read a trusted header here; the dev server gives the real one)."""
    return request.META.get('REMOTE_ADDR', 'unknown')


def clear_buckets():
    """Forget every tracked attempt (used by the test suite so one
    test's "abuse" can't throttle the next test)."""
    _buckets.clear()


def check_rate_limit(request, action, limit, window_seconds):
    """
    Record ONE attempt of `action` for this client and report whether
    it is allowed.

    Returns (allowed, retry_in_minutes):
        (True, 0)            -> allowed, go ahead
        (False, n)           -> throttled, ask the user to wait ~n minutes
    """
    key = (action, _client_ip(request))
    now = time.monotonic()
    dq = _buckets[key]

    # Age out attempts that have fallen out of the window.
    while dq and dq[0] <= now - window_seconds:
        dq.popleft()

    if len(dq) >= limit:
        # The oldest attempt in the window frees a slot after this long.
        wait_seconds = dq[0] + window_seconds - now
        retry_in_minutes = int(wait_seconds // 60) + 1
        return False, max(retry_in_minutes, 1)

    # Memory guard: after an enormous number of unique IPs, start the
    # map fresh. The worst case is a few requests slipping through —
    # far cheaper than unbounded growth.
    if len(_buckets) >= MAX_TRACKED_KEYS:
        _buckets.clear()
        dq = _buckets[key]

    dq.append(now)
    return True, 0
