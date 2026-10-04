"""Pure error classification and recovery policy. No I/O or waiting."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import uuid
import math
import ssl
import httpx


class Failure(Exception):
    def __init__(self, code, message, *, source="adapter", scope="request", api=None,
                 appid=None, subject_steamid=None, exception_type=None, http_status=None,
                 upstream_code=None, retry_after=None, retryable=True):
        super().__init__(message)
        self.info = dict(error_id="err_" + uuid.uuid4().hex[:12], code=code, source=source,
                         scope=scope, api=api, appid=appid, subject_steamid=subject_steamid,
                         exception_type=exception_type, http_status=http_status,
                         upstream_code=upstream_code, message=message)
        self.retry_after = retry_after
        self.retryable = retryable

    @property
    def code(self):
        return self.info["code"]


@dataclass(frozen=True)
class Decision:
    action: str
    wait_seconds: float = 0
    cooldown_scope: str | None = None
    reason: str = ""

    def as_dict(self):
        return asdict(self)


def retry_after_seconds(value, now=None):
    if not value:
        return None
    try:
        if str(value).strip().isdigit():
            seconds = float(value)
            return seconds if math.isfinite(seconds) else None
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0., (date - (now or datetime.now(timezone.utc))).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def decide(error, *, attempt, remaining, config, scope, jitter=.5, read_only=True):
    if error.code in {"LOG_WRITE_FAILED", "INTERNAL_ERROR"}:
        return Decision("abort_run", reason=error.code)
    retry = error.code in {"NETWORK_TIMEOUT", "NETWORK_ERROR", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE"}
    wait = min(config.backoff_cap, config.backoff_base * 2 ** min(attempt - 1, 30)) * (.5 + jitter / 2)
    if error.code == "RATE_LIMITED" and error.retry_after is not None:
        wait = error.retry_after
    cooldown = scope if error.code == "RATE_LIMITED" else None
    if not retry or not error.retryable or not read_only or attempt >= config.max_attempts:
        return Decision("skip", wait if cooldown else 0, cooldown, "not retryable or attempts exhausted")
    if wait >= remaining:
        return Decision("skip", wait, cooldown, "request budget exhausted")
    return Decision("cooldown_then_retry" if cooldown else "retry", wait, cooldown, error.code)


def classify_http(status, retry_after=None):
    code = ("RATE_LIMITED" if status == 429 else "AUTH_EXPIRED" if status == 401
            else "ACCESS_DENIED" if status == 403 else "UPSTREAM_UNAVAILABLE" if 500 <= status < 600
            else "DATA_UNAVAILABLE" if status in {404, 410} else "RESPONSE_INVALID")
    return Failure(code, "HTTP request failed", source="http", http_status=status,
                   retry_after=retry_after_seconds(retry_after))


def error_outcome(error):
    """Recovery policy and completed outcome are independent of each other."""
    code = error.get("code") if isinstance(error, dict) else error.code
    return ("not_applicable" if code == "CAPABILITY_NOT_APPLICABLE" else
            "data_unavailable" if code in {"DATA_UNAVAILABLE", "DEPENDENCY_FAILED"} else "failed")


def result_outcome(state, error=None):
    if state in {"ok", "success"}:
        return "success"
    if state in {"not_applicable", "data_unavailable", "failed", "cancelled"}:
        return state
    return error_outcome(error) if error else "data_unavailable"


def classify_transport(exc):
    if isinstance(exc, httpx.TimeoutException):
        return Failure("NETWORK_TIMEOUT", "HTTP timeout", source="transport", exception_type=type(exc).__name__)
    chain, current = [], exc
    while current is not None and len(chain) < 10:
        chain.append(current)
        current = current.__cause__ or current.__context__
    certificate = any(isinstance(e, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e) for e in chain)
    return Failure("NETWORK_ERROR", "TLS validation failed" if certificate else "HTTP transport failed",
                   source="transport", exception_type=type(exc).__name__, retryable=not certificate)
