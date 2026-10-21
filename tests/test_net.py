import time

from freeplaylist import net


def test_round_robin_alternates_hosts():
    urls = ["https://a/1", "https://a/2", "https://a/3", "https://b/1", "https://c/1", "https://b/2"]
    assert net.round_robin(urls, key=net.host_of) == [
        "https://a/1", "https://b/1", "https://c/1", "https://a/2", "https://b/2", "https://a/3"]


def test_spacing_between_requests_to_one_host():
    limiter = net.HostLimiter(per_host=4, min_interval=0.05)
    start = time.monotonic()
    for _ in range(3):
        with limiter.slot("https://same.example/x"):
            pass
    assert time.monotonic() - start >= 0.1  # three starts, two gaps
    other = time.monotonic()
    with limiter.slot("https://other.example/x"):
        pass
    assert time.monotonic() - other < 0.05  # other hosts aren't held up


def test_backoff_pauses_only_that_host():
    limiter = net.HostLimiter(min_interval=0)
    assert limiter.throttled("https://busy.example/", None) == 2.0
    assert limiter.throttled("https://busy.example/", None) == 4.0  # doubles while it keeps refusing
    assert limiter.throttled("https://busy.example/", "7") == 7.0  # Retry-After wins
    limiter.ok("https://busy.example/")
    assert limiter._backoff["busy.example"] == 3.5  # recovers gradually
    start = time.monotonic()
    with limiter.slot("https://calm.example/"):
        pass
    assert time.monotonic() - start < 0.05
