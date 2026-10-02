import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import ssl
import time

import httpx
import pytest

from config import Config
from error_handler import retry_after_seconds
from Ports.registry import build_registry
from Ports.request_executor import Executor, RequestSpec

SPEC = RequestSpec("synthetic", "https://api.steampowered.com/synthetic")


def test_hundred_requests_concurrency_and_speed():
    async def batch(concurrency):
        active = maximum = 0
        async def transport(req):
            nonlocal active, maximum
            active += 1
            maximum = max(active, maximum)
            await asyncio.sleep(.005)
            active -= 1
            return httpx.Response(200, json={"ok": True})
        ex = Executor(replace(Config(), concurrency=concurrency, webapi_rps=1e9), transport=httpx.MockTransport(transport))
        start = time.monotonic()
        results = await asyncio.gather(*(ex.execute(SPEC, lambda b: b) for _ in range(100)))
        elapsed = time.monotonic() - start
        await ex.close()
        assert all(r.state == "ok" for r in results) and maximum <= concurrency
        return elapsed, maximum
    serial, _ = asyncio.run(batch(1))
    concurrent, maximum = asyncio.run(batch(4))
    assert maximum == 4 and concurrent < serial * .75


def test_fast_responses_still_rate_limited():
    async def check():
        stamps = []
        def transport(req):
            stamps.append(time.monotonic())
            return httpx.Response(200, json={})
        ex = Executor(replace(Config(), webapi_rps=50), transport=httpx.MockTransport(transport))
        await asyncio.gather(*(ex.execute(SPEC, lambda b: b) for _ in range(5)))
        await ex.close()
        assert all(b - a >= .018 for a, b in zip(stamps, stamps[1:]))
    asyncio.run(check())


class FakeClock:
    def __init__(self):
        self.now = 100.
        self.waits = []
    def __call__(self):
        return self.now
    async def sleep(self, amount):
        self.now += amount
        self.waits.append(amount)


@pytest.mark.parametrize("kind", ["429", "429-no-header", "503", "timeout"])
def test_finite_retries(kind):
    async def check():
        calls = 0
        clock = FakeClock()
        events = []
        def transport(req):
            nonlocal calls
            calls += 1
            if kind == "timeout":
                raise httpx.ReadTimeout("synthetic timeout")
            return httpx.Response(int(kind.split("-")[0]), headers={"Retry-After": "2"} if kind == "429" else {})
        ex = Executor(replace(Config(), webapi_rps=100), lambda event, **kw: events.append((event, kw)), transport=httpx.MockTransport(transport), clock=clock, sleep=clock.sleep, jitter=lambda: 0)
        result = await ex.execute(SPEC, lambda b: b)
        assert calls == result.attempts == 3
        assert len([e for e, _ in events if e == "retry_scheduled"]) == 2
        if kind == "429":
            assert clock.waits == [2, 2]
        await ex.close()
    asyncio.run(check())


def test_retry_after_date_and_budget_preserves_cooldown():
    assert retry_after_seconds("Fri, 02 Oct 2026 12:00:10 GMT", datetime(2026, 10, 2, 12, tzinfo=timezone.utc)) == 10
    assert retry_after_seconds("invalid") is None
    async def check():
        clock = FakeClock()
        ex = Executor(replace(Config(), deadline=5, backoff_cap=1), transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "100"})), clock=clock, sleep=clock.sleep)
        result = await ex.execute(SPEC, lambda b: b)
        assert result.attempts == 1 and result.error["code"] == "REQUEST_DEADLINE_EXCEEDED"
        assert ex.cooldowns["api.steampowered.com"] == 200 and clock.waits == []
        await ex.close()
    asyncio.run(check())


@pytest.mark.parametrize("status", [401, 403, 404, 302])
def test_nonretry_http(status):
    async def check():
        ex = Executor(Config(), transport=httpx.MockTransport(lambda r: httpx.Response(status)))
        result = await ex.execute(SPEC, lambda b: b)
        assert result.attempts == 1 and result.state == "unavailable"
        await ex.close()
    asyncio.run(check())


def test_contract_and_certificate_errors_not_retried():
    async def check():
        def certificate(req):
            try:
                raise ssl.SSLCertVerificationError("synthetic")
            except ssl.SSLError as e:
                raise httpx.ConnectError("certificate") from e
        ex = Executor(Config(), transport=httpx.MockTransport(certificate))
        result = await ex.execute(SPEC, lambda b: b)
        assert result.attempts == 1 and result.error["code"] == "NETWORK_ERROR"
        await ex.close()
        ex = Executor(Config(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
        result = await ex.execute(SPEC, lambda b: b["missing"])
        assert result.attempts == 1 and result.error["code"] == "RESPONSE_INVALID"
        await ex.close()
    asyncio.run(check())


def test_cooldown_is_shared_and_stop_cancels_wait():
    async def check():
        calls = 0
        def transport(req):
            nonlocal calls
            calls += 1
            return httpx.Response(429, headers={"Retry-After": "100"})
        ex = Executor(replace(Config(), deadline=2), transport=httpx.MockTransport(transport))
        await ex.execute(SPEC, lambda b: b)
        queued = asyncio.create_task(ex.execute(SPEC, lambda b: b))
        await asyncio.sleep(.01)
        assert calls == 1
        ex.stop()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(queued, .2)
        await ex.close()
    asyncio.run(check())


def test_cache_context_separation_and_recovered_error():
    async def check():
        calls = 0
        def transport(req):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503)
            return httpx.Response(200, json={"1": {"success": True, "data": {"steam_appid": 1, "name": "Fixture"}}})
        clock = FakeClock()
        ex = Executor(replace(Config(), store_rps=10000), transport=httpx.MockTransport(transport), clock=clock, sleep=clock.sleep)
        registry = build_registry(ex)
        p = {"appid": 1, "language": "english", "country": "US"}
        first, second = await asyncio.gather(registry.call("get_app_details", p), registry.call("get_app_details", p))
        assert first.state == second.state == "ok" and first.error is None and first.attempts == 2 and calls == 2
        assert first.fetched_at == second.fetched_at
        await registry.call("get_app_details", {**p, "country": "CN"})
        await registry.call("get_app_details", {**p, "language": "schinese"})
        assert calls == 4
        await ex.close()
    asyncio.run(check())
