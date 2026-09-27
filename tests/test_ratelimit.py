from downloader_bot.ratelimit import RateLimiter


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_one_active_task_per_user():
    limiter = RateLimiter(per_minute=10, max_active=1, clock=Clock())
    assert limiter.try_acquire(1) is None
    denied = limiter.try_acquire(1)
    assert denied and denied.already_active
    assert limiter.try_acquire(2) is None  # другие пользователи не затронуты
    limiter.release(1)
    assert limiter.try_acquire(1) is None


def test_per_minute_limit_and_window():
    clock = Clock()
    limiter = RateLimiter(per_minute=2, max_active=5, clock=clock)
    for _ in range(2):
        assert limiter.try_acquire(1) is None
        limiter.release(1)
    clock.now = 20
    denied = limiter.try_acquire(1)
    assert denied and not denied.already_active and denied.retry_after_sec == 40
    clock.now = 61
    assert limiter.try_acquire(1) is None


def test_stale_users_are_swept():
    clock = Clock()
    limiter = RateLimiter(per_minute=5, max_active=1, clock=clock)
    limiter.try_acquire(1)
    limiter.release(1)
    clock.now = 200
    limiter.try_acquire(2)
    assert 1 not in limiter._requests
    assert 1 not in limiter._active
