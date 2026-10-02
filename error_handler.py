"""Pure error classification and recovery policy. No I/O or waiting."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import uuid


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
            return float(value)
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
