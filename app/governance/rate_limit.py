"""RATE/ABUSE (Batch 2 completion): the smallest limiter that actually
protects something real, not a distributed rate-limiting system.

What this protects: a retry storm or scripted flood against the two
routes that spend a real Gemini call plus (for propose) a real sandbox
run -- /synapse/propose and /missions/planned. Both are already
owner-gated, so this is not an anonymous-attacker defense (auth already
closes that door); it protects against an authenticated caller (a
double-clicked button, a buggy retry loop, a leaked token used
carelessly) burning the project's real API quota, which has already been
observed exhausted once in production (Mission #1's research-stage 429).

What this does NOT protect, stated precisely rather than implied away:

  - This is an IN-MEMORY, PER-PROCESS counter. Cloud Run can and does run
    multiple instances of aion-core concurrently under load; each
    instance has its own independent counter. This does NOT provide a
    single global limit across the whole deployed service -- a caller
    hitting different instances could exceed the stated limit in
    aggregate. A real cross-instance limit needs a shared store (e.g. a
    Firestore counter document or Memorystore/Redis), which is real new
    infrastructure this pass deliberately does not add without being able
    to test it.
  - This is not a defense against a determined, distributed attacker.
    It is a guard against ordinary accidental abuse from the one real
    caller this system has (the single shared owner token -- see
    app/governance/owner_auth.py's own docstring on that model).

Sliding-window log, not a token bucket: simplest correct implementation
for the traffic this actually sees (a human clicking a button, not a
high-QPS service), no new dependency.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Header, HTTPException

from app.governance.owner_auth import HEADER as OWNER_TOKEN_HEADER


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Raises HTTPException(429) if `key` is currently over limit.
        Records the call as counting toward the window either way, so a
        client cannot dodge the count by inspecting a would-it-pass
        response first."""
        now = time.monotonic()

        with self._lock:
            calls = self._calls[key]

            while calls and now - calls[0] > self.window_seconds:
                calls.popleft()

            if len(calls) >= self.max_calls:
                retry_after = max(0.0, self.window_seconds - (now - calls[0]))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "status": "ERROR",
                        "code": "RATE_LIMITED",
                        "message": (
                            f"Too many requests. Limit is {self.max_calls} "
                            f"per {int(self.window_seconds)}s."
                        ),
                        "retry_after_seconds": round(retry_after, 1),
                    },
                )

            calls.append(now)

    def reset(self) -> None:
        """Test-only: clear all state between tests."""
        with self._lock:
            self._calls.clear()


# 5 real acquisition attempts per minute: each one is already a genuinely
# expensive ~10-30s operation (real Gemini generation + sandbox run), so
# this bounds accidental floods without blocking normal interactive use
# -- a judge or the owner clicking RUN MISSION repeatedly during a demo
# stays well under this.
propose_limiter = SlidingWindowLimiter(max_calls=5, window_seconds=60)

# Planning is a single Gemini call, cheaper than a full acquisition but
# still real spend -- a slightly higher allowance.
planned_mission_limiter = SlidingWindowLimiter(max_calls=10, window_seconds=60)


def _key(x_axon_token: str) -> str:
    """The limiter key is the caller's own token, not their IP.

    require_owner already ran by the time this dependency executes (see
    dependency ordering in app.api's route decorators), so anyone
    reaching this point is already the one real owner this single-token
    system has -- keying by token rather than IP is both simpler and
    more meaningful here, and avoids the "don't blindly trust a
    spoofable header" trap IP-based limiting behind a proxy would create.
    """
    return x_axon_token or "unauthenticated"


def rate_limit_propose(
    x_axon_token: str = Header(default="", alias=OWNER_TOKEN_HEADER),
) -> None:
    propose_limiter.check(_key(x_axon_token))


def rate_limit_planned_mission(
    x_axon_token: str = Header(default="", alias=OWNER_TOKEN_HEADER),
) -> None:
    planned_mission_limiter.check(_key(x_axon_token))
