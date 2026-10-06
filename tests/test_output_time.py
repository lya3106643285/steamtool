import asyncio
from datetime import datetime, timedelta, timezone
import json

import httpx

from steamtool.config import Config
from steamtool.Ports.request_executor import Executor, RequestSpec
from steamtool.scripts import persistence, runtime_debug


def test_filename_and_started_at_share_beijing_instant(monkeypatch):
    original = datetime(2026, 10, 4, 16, 9, 48, 386572, tzinfo=timezone.utc)
    local = original.astimezone(runtime_debug.OUTPUT_TIMEZONE)
    monkeypatch.setattr(persistence, "output_now", lambda: local)
    stem, doc = persistence.new_run("library", Config())
    assert stem.startswith("20261005T000948386572_北京时间_library_")
    assert doc["meta"]["started_at"] == "2026-10-05T00:09:48.386572+08:00"
    assert datetime.fromisoformat(doc["meta"]["started_at"]).astimezone(timezone.utc) == original
    assert doc["meta"]["output_timezone"] == "北京时间"


def test_runtime_uses_explicit_offset_independent_of_host_timezone(tmp_path, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    runtime = runtime_debug.Runtime(tmp_path / "events.jsonl", "synthetic", "library")
    runtime.close()
    row = json.loads((tmp_path / "events.jsonl").read_text())
    assert datetime.fromisoformat(row["timestamp"]).utcoffset() == timedelta(hours=8)
    assert row["timestamp"].endswith("+08:00")


def test_fetch_timestamp_preserves_actual_instant():
    async def check():
        before = datetime.now(timezone.utc)
        ex = Executor(Config(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
        try:
            result = await ex.execute(RequestSpec("fixture", "https://api.steampowered.com/fixture"), lambda body: body)
        finally:
            await ex.close()
        fetched = datetime.fromisoformat(result.fetched_at)
        assert fetched.utcoffset() == timedelta(hours=8)
        assert before <= fetched.astimezone(timezone.utc) <= datetime.now(timezone.utc)
    asyncio.run(check())
