"""Reusable HTTP transport; sole retry loop and actual-send admission control."""
import asyncio
from dataclasses import asdict, dataclass, field
import random
import time
from urllib.parse import urlsplit
import uuid

import httpx
from steamtool.error_handler import Failure, decide, classify_http, classify_transport, error_outcome, result_outcome
from steamtool.scripts.runtime_debug import timestamp_now


@dataclass
class Result:
    state: str
    data: dict = field(default_factory=dict)
    error: dict | None = None
    source: str = ""
    fetched_at: str | None = None
    attempts: int = 0
    from_run_cache: bool = False

    def __post_init__(self):
        if self.state == "unavailable":
            self.state = error_outcome(self.error) if self.error else "data_unavailable"

    @property
    def outcome(self):
        return result_outcome(self.state, self.error)

    def as_dict(self):
        return dict(asdict(self), outcome=self.outcome)


@dataclass(frozen=True)
class RequestSpec:
    api: str
    url: str
    params: dict = field(default_factory=dict)
    auth_kind: str = "none"
    family: bool = False
    # Only adapters with a validated application-error contract may decode HTTP 400.
    decode_bad_request: bool = False


def object_at(body, key):
    if not isinstance(body, dict) or not isinstance(body.get(key), dict):
        raise Failure("RESPONSE_INVALID", f"Expected object: {key}")
    result = body[key]
    if key == "response":
        if result.get("success") is False or result.get("error"):
            raise Failure("DATA_UNAVAILABLE", "Upstream reported an application failure")
        code = result.get("eresult")
        if code is not None and str(code) != "1":
            mapped = {"5": "AUTH_EXPIRED", "15": "ACCESS_DENIED", "84": "RATE_LIMITED", "16": "UPSTREAM_UNAVAILABLE"}.get(str(code), "DATA_UNAVAILABLE")
            raise Failure(mapped, "Upstream reported failure", upstream_code=code)
    return result


def selected(data, keys):
    return {key: data[key] for key in keys if key in data}


def app_items(value):
    from steamtool.config import valid_appid
    if not isinstance(value, list) or any(not isinstance(x, dict) or not valid_appid(x.get("appid")) for x in value):
        raise Failure("RESPONSE_INVALID", "Expected AppID list")
    return value


def check_upstream(response):
    eresult = response.headers.get("x-eresult")
    if eresult and eresult != "1":
        code = {"5": "AUTH_EXPIRED", "15": "ACCESS_DENIED", "84": "RATE_LIMITED", "16": "UPSTREAM_UNAVAILABLE"}.get(eresult, "DATA_UNAVAILABLE")
        raise Failure(code, "Upstream reported failure", upstream_code=eresult)


class Executor:
    def __init__(self, config, event=lambda *a, **k: None, *, transport=None, clock=time.monotonic,
                 sleep=asyncio.sleep, jitter=random.random):
        self.config, self.event = config, event
        self.clock, self.sleep, self.jitter = clock, sleep, jitter
        self.client = httpx.AsyncClient(transport=transport, follow_redirects=False,
            timeout=httpx.Timeout(connect=config.connect_timeout, read=config.read_timeout,
                                  write=config.write_timeout, pool=config.pool_timeout),
            limits=httpx.Limits(max_connections=config.concurrency, max_keepalive_connections=config.concurrency))
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.gate = asyncio.Lock()
        self.next_send = {}
        self.cooldowns = {}
        self.stopping = asyncio.Event()
        self.disabled_auth = {}

    def stop(self):
        self.stopping.set()

    async def pause(self, seconds):
        if self.stopping.is_set():
            raise asyncio.CancelledError
        sleeper = asyncio.create_task(self.sleep(max(0, seconds)))
        stopper = asyncio.create_task(self.stopping.wait())
        try:
            await asyncio.wait({sleeper, stopper}, return_when=asyncio.FIRST_COMPLETED)
            if self.stopping.is_set():
                raise asyncio.CancelledError
            await sleeper
        finally:
            for task in (sleeper, stopper):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleeper, stopper, return_exceptions=True)

    async def admit(self, host, family, expires):
        scopes = {host: self.config.store_rps if host == "store.steampowered.com" else self.config.webapi_rps}
        if family:
            scopes["family"] = self.config.family_rps
        start = self.clock()
        throttled = 0.
        while True:
            if self.stopping.is_set():
                raise asyncio.CancelledError
            if expires is not None and self.clock() >= expires:
                raise Failure("REQUEST_DEADLINE_EXCEEDED", "Logical request budget exhausted", source="executor")
            # Acquire capacity only to check admission and immediately send/release.
            await self.semaphore.acquire()
            try:
                async with self.gate:
                    now = self.clock()
                    wait = max(0., max(self.next_send.get(s, 0) for s in scopes) - now,
                               self.cooldowns.get(host, 0) - now)
                    if not wait and not self.stopping.is_set():
                        for scope, rps in scopes.items():
                            self.next_send[scope] = now + 1 / rps
                        return (self.clock() - start) * 1000, throttled * 1000
            except BaseException:
                self.semaphore.release()
                raise
            self.semaphore.release()
            if expires is not None and self.clock() + wait >= expires:
                raise Failure("REQUEST_DEADLINE_EXCEEDED", "Cooldown or queue exceeds request budget", source="executor")
            before = self.clock()
            await self.pause(wait)
            throttled += self.clock() - before

    async def execute(self, spec, decode, context=None):
        context = dict(context or {})
        context.update(api=spec.api, request_id="req_" + uuid.uuid4().hex[:12])
        host = urlsplit(spec.url).hostname
        if host not in {"api.steampowered.com", "store.steampowered.com"} or urlsplit(spec.url).scheme != "https":
            raise Failure("CONFIG_INVALID", "Endpoint outside allowlist")
        if spec.auth_kind != "none" and host != "api.steampowered.com":
            raise Failure("CONFIG_INVALID", "Credentials forbidden for endpoint")
        params, headers = dict(spec.params), {}
        if spec.auth_kind == "user_key":
            headers["x-webapi-key"] = self.config.api_key
        elif spec.auth_kind == "session_token":
            params["access_token"] = self.config.family_token
        self.event("request_queued", module=__name__, **context)
        first_send = None
        attempts = 0
        last = None
        while attempts < self.config.max_attempts:
            acquired = False
            status = None
            try:
                if spec.auth_kind in self.disabled_auth:
                    raise Failure(self.disabled_auth[spec.auth_kind], "Authentication source disabled for this run")
                expires = first_send + self.config.deadline if first_send is not None else None
                # Outer timeout bounds semaphore/queue and full body consumption on retries.
                remaining = None if expires is None else max(0, expires - self.clock())
                async with asyncio.timeout(remaining):
                    queue_ms, throttle_ms = await self.admit(host, spec.family, expires)
                    acquired = True
                    if first_send is None:
                        first_send = self.clock()
                    attempts += 1
                    start = self.clock()
                    self.event("request_started", module=__name__, attempt=attempts,
                               queue_wait_ms=queue_ms, throttle_wait_ms=throttle_ms, **context)
                    async with asyncio.timeout(max(0, first_send + self.config.deadline - self.clock())):
                        response = await self.client.get(spec.url, params=params, headers=headers)
                    self.semaphore.release()
                    acquired = False
                    status = response.status_code
                    if status != 200 and not (status == 400 and spec.decode_bad_request):
                        raise classify_http(status, response.headers.get("retry-after"))
                    check_upstream(response)
                    try:
                        body = response.json()
                    except (ValueError, UnicodeError):
                        raise Failure("RESPONSE_INVALID", "Invalid JSON response") from None
                    data = decode(body)
                    if status != 200:
                        raise classify_http(status)
                    state = data.pop("_state", "ok")
                    self.event("request_succeeded", module=__name__, attempt=attempts, http_status=status,
                               outcome=result_outcome(state), duration_ms=(self.clock() - start) * 1000, **context)
                    self.event("request_finished", module=__name__, outcome=result_outcome(state), **context)
                    return Result(state, data, source=spec.api,
                                  fetched_at=timestamp_now(), attempts=attempts)
            except asyncio.CancelledError:
                raise
            except Failure as exc:
                last = exc
            except TimeoutError:
                last = Failure("REQUEST_DEADLINE_EXCEEDED", "Logical request budget exhausted", source="executor")
            except httpx.TransportError as exc:
                last = classify_transport(exc)
            except (KeyError, TypeError, ValueError) as exc:
                last = Failure("RESPONSE_INVALID", "Unexpected response shape", exception_type=type(exc).__name__)
            except Exception as exc:
                last = Failure("INTERNAL_ERROR", "Unexpected executor/decoder error", exception_type=type(exc).__name__)
            finally:
                if acquired:
                    self.semaphore.release()
            last.info.update(api=spec.api, appid=context.get("appid"), subject_steamid=context.get("subject_steamid"))
            if last.info["http_status"] is None:
                last.info["http_status"] = status
            if last.code == "LOG_WRITE_FAILED":
                raise last
            if last.code == "AUTH_EXPIRED":
                self.disabled_auth[spec.auth_kind] = last.code
            benign = error_outcome(last) in {"not_applicable", "data_unavailable"}
            self.event("request_unavailable" if benign else "request_failed", module=__name__,
                       level="INFO" if benign else "WARNING", attempt=attempts,
                       error_code=last.code, error_id=last.info["error_id"], http_status=last.info["http_status"], **context)
            remaining = self.config.deadline - (self.clock() - first_send) if first_send is not None else self.config.deadline
            decision = decide(last, attempt=max(1, attempts), remaining=remaining, config=self.config, scope=host, jitter=self.jitter())
            if decision.cooldown_scope:
                self.cooldowns[host] = max(self.cooldowns.get(host, 0), self.clock() + decision.wait_seconds)
                self.event("cooldown_started", module=__name__, cooldown_scope=host, retry_wait_ms=decision.wait_seconds * 1000, **context)
            if decision.action not in {"retry", "cooldown_then_retry"}:
                if decision.action == "abort_run":
                    self.event("request_finished", module=__name__, outcome="failed", error_code=last.code,
                               error_id=last.info["error_id"], **context)
                    raise last
                if decision.reason == "request budget exhausted":
                    last = Failure("REQUEST_DEADLINE_EXCEEDED", "Retry exceeds budget; last cause: " + last.code,
                                   api=spec.api, appid=context.get("appid"), subject_steamid=context.get("subject_steamid"))
                break
            self.event("retry_scheduled", module=__name__, attempt=attempts, retry_wait_ms=decision.wait_seconds * 1000, **context)
            await self.pause(decision.wait_seconds)
        self.event("request_finished", module=__name__, outcome=error_outcome(last),
                   error_code=last.code, error_id=last.info["error_id"], **context)
        return Result(error_outcome(last), error=last.info, source=spec.api, attempts=attempts)

    async def close(self):
        await self.client.aclose()
