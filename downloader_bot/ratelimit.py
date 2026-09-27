import math
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Denied:
    already_active: bool
    retry_after_sec: int = 0


class RateLimiter:
    """In-memory лимиты на пользователя: активные задачи + запросы в скользящем окне.

    Состояние живёт в процессе — при рестарте бота сбрасывается, для монолита это ок.
    """

    def __init__(
        self,
        per_minute: int,
        max_active: int,
        window_sec: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._per_minute = per_minute
        self._max_active = max_active
        self._window = window_sec
        self._clock = clock
        self._active: dict[int, int] = defaultdict(int)
        self._requests: dict[int, deque[float]] = {}
        self._last_sweep = clock()

    def try_acquire(self, user_id: int) -> Denied | None:
        if self._active.get(user_id, 0) >= self._max_active:
            return Denied(already_active=True)

        now = self._clock()
        self._sweep(now)
        history = self._requests.setdefault(user_id, deque())
        while history and now - history[0] >= self._window:
            history.popleft()
        if len(history) >= self._per_minute:
            retry_after = math.ceil(self._window - (now - history[0]))
            return Denied(already_active=False, retry_after_sec=max(retry_after, 1))

        history.append(now)
        self._active[user_id] += 1
        return None

    def release(self, user_id: int) -> None:
        self._active[user_id] -= 1
        if self._active[user_id] <= 0:
            del self._active[user_id]

    def _sweep(self, now: float) -> None:
        # Раз в окно выкидываем тех, кто давно не писал, — иначе на публичном боте
        # словарь растёт бесконечно.
        if now - self._last_sweep < self._window:
            return
        self._last_sweep = now
        stale = [uid for uid, h in self._requests.items() if not h or now - h[-1] >= self._window]
        for uid in stale:
            del self._requests[uid]
