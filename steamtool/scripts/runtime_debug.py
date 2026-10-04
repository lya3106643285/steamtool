"""Single structured, redacted logging outlet and run-level supervision."""
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import logging
import re
import sys
import time
import traceback
from urllib.parse import quote

from steamtool.error_handler import Failure


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Redactor:
    secret_key = re.compile(r"(?i)(?:key|.*api[_-]?key|.*token|cookie|set-cookie|authorization|password|proxy.*)")

    def __init__(self, secrets=()):
        self.secrets = sorted({s for value in secrets if value for s in (value, quote(value, safe=""))}, key=len, reverse=True)

    def __call__(self, value):
        if isinstance(value, dict):
            return {str(k): "[REDACTED]" if self.secret_key.fullmatch(str(k)) else self(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)([a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
            value = re.sub(r"(?i)([?&](?:key|api_key|access_token|refresh_token|token|cookie|authorization)=)[^&\s\"']+", r"\1[REDACTED]", value)
            value = re.sub(r"(?i)(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", "[REDACTED]", value)
            value = re.sub(r"(?i)(\b(?:api_key|access_token|refresh_token|password)\s*[=:]\s*)[^&\s\"',;]+", r"\1[REDACTED]", value)
            value = re.sub(r"(?im)((?:authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+", r"\1[REDACTED]", value)
        return value


class Runtime:
    def __init__(self, path, run_id, feature, secrets=(), level="INFO"):
        self.run_id, self.feature = run_id, feature
        self.redact = Redactor(secrets)
        self.failed = False
        self.started = time.monotonic()
        self.counts = Counter()
        self.tasks = {}
        self.total = None
        self.phases = {}
        self.http_by_api = {}
        self.operations = {}
        self.enrichment_plan = Counter()
        self.level = getattr(logging, level)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.file = path.open("x", encoding="utf-8")
        except OSError as exc:
            raise Failure("LOG_WRITE_FAILED", "Cannot initialize runtime log", source="runtime", exception_type=type(exc).__name__) from None
        for name in ("httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        self.event("run_started")

    def event(self, event, *, level="INFO", module="runtime", **fields):
        if self.failed:
            raise Failure("LOG_WRITE_FAILED", "Runtime log unavailable", source="runtime")
        row = dict(timestamp=utcnow(), level=level, event=event, module=module,
                   run_id=self.run_id, feature=self.feature, task_id=None, request_id=None,
                   attempt=None, api=None, appid=None, duration_ms=None, queue_wait_ms=None,
                   throttle_wait_ms=None, retry_wait_ms=None, http_status=None, error_code=None,
                   error_id=None, message="")
        row.update(fields)
        row = self.redact(row)
        try:
            self.file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            self.file.flush()
        except (OSError, ValueError):
            self.failed = True
            print("LOG_WRITE_FAILED: stopping new requests", file=sys.stderr)
            raise Failure("LOG_WRITE_FAILED", "Runtime log write failed", source="runtime") from None
        self.counts[event] += 1
        api = fields.get("api")
        if api and event in {"request_queued", "request_started", "request_finished", "retry_scheduled"}:
            counts = self.http_by_api.setdefault(api, Counter())
            metric = {"request_queued": "logical_requests", "request_started": "attempts",
                      "retry_scheduled": "retries"}.get(event, fields.get("outcome"))
            counts[metric] += 1
        if event == "operation_finished":
            self.operations[fields["operation_id"]] = fields["outcome"]
        if event == "enrichment_decision":
            self.enrichment_plan[f"{fields['operation']}_{fields['decision']}"] += 1
        if event == "run_cache_hit" and api in {"get_schema_for_game", "get_app_details", "get_player_achievements", "get_user_stats_for_game"}:
            self.enrichment_plan["dedup_hits"] += 1
        if event in {"run_started", "progress_snapshot", "export_saved", "run_finished", "stop_requested", "export_failed"} and getattr(logging, level) >= self.level:
            print(self.redact(f"[{self.feature}] {event} {fields.get('message', '')}"), file=sys.stderr)

    def task(self, task_id, state, **fields):
        if self.tasks.get(task_id) in {"success", "not_applicable", "data_unavailable", "failed", "cancelled"}:
            return
        self.tasks[task_id] = state
        self.event("task_started" if state == "running" else "task_finished", task_id=task_id, state=state, **fields)

    def snapshot(self):
        counts = Counter(self.tasks.values())
        return dict(total=self.total, pending=None if self.total is None else max(0, self.total - len(self.tasks)),
                    **{s: counts[s] for s in ("running", "success", "not_applicable", "data_unavailable", "failed", "cancelled")})

    async def progress(self, interval):
        while True:
            await asyncio.sleep(interval)
            self.event("progress_snapshot", progress=self.snapshot(), message=str(self.snapshot()))

    def diagnostic(self, exc):
        # No locals and no exception text; only stack locations and exception class.
        return {"exception_type": type(exc).__name__, "stack": traceback.format_tb(exc.__traceback__)}

    def summary(self):
        api_keys = ("logical_requests", "attempts", "success", "not_applicable", "data_unavailable", "failed", "retries")
        apis = set(self.http_by_api) | {"get_schema_for_game", "get_player_achievements", "get_user_stats_for_game", "get_app_details"}
        operations = Counter(self.operations.values())
        return dict(wall_duration_ms=round((time.monotonic() - self.started) * 1000, 3),
                    http_attempts=self.counts["request_started"], logical_requests=self.counts["request_queued"],
                    retries=self.counts["retry_scheduled"], rate_limits=self.counts["cooldown_started"],
                    cache_hits=self.counts["run_cache_hit"], tasks=self.snapshot(), task_unit="app_enrichment",
                    operations=dict(total=len(self.operations), **{s: operations[s] for s in ("success", "not_applicable", "data_unavailable", "failed")}),
                    http_by_api={api: {key: self.http_by_api.get(api, {}).get(key, 0) for key in api_keys} for api in sorted(apis)},
                    enrichment_plan={key: self.enrichment_plan[key] for key in (
                        "input_apps", "schema_scheduled", "store_scheduled", "achievements_scheduled", "stats_scheduled",
                        "achievements_skipped_not_applicable", "stats_skipped_not_applicable",
                        "achievements_skipped_dependency", "stats_skipped_dependency", "dedup_hits")},
                    phase_duration_ms=self.phases)

    def close(self):
        try:
            self.file.close()
        except OSError:
            self.failed = True
