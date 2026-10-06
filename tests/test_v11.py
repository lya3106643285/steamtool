"""V1.1 contract tests with synthetic responses, never local credentials."""
import asyncio
from collections import Counter
from dataclasses import replace
import json

import httpx
import pytest

from steamtool.config import Config
from steamtool.error_handler import Failure, error_outcome
from steamtool.Ports.registry import build_registry
from steamtool.Ports.request_executor import Executor, RequestSpec, Result
from steamtool.scripts import library
from steamtool.scripts.game import record
from steamtool.scripts.persistence import new_run
from steamtool.scripts.runtime_debug import Runtime
from tests.test_accounts import ME, OTHER, token
from tests.test_executor import FakeClock
from tests.test_workflows import Fixtures


def config(**kwargs):
    return replace(Config(), steamid=ME, api_key="synthetic", family_token=token(),
                   webapi_rps=1e9, store_rps=1e9, family_rps=1e9, **kwargs)


@pytest.mark.parametrize("code,outcome", [
    ("CAPABILITY_NOT_APPLICABLE", "not_applicable"), ("DATA_UNAVAILABLE", "data_unavailable"),
    ("NETWORK_TIMEOUT", "failed"), ("NETWORK_ERROR", "failed"), ("UPSTREAM_UNAVAILABLE", "failed"),
    ("AUTH_REQUIRED", "failed"), ("AUTH_EXPIRED", "failed"), ("ACCESS_DENIED", "failed"),
    ("RESPONSE_INVALID", "failed"), ("OUTPUT_WRITE_FAILED", "failed"), ("INTERNAL_ERROR", "failed"),
])
def test_error_outcomes(code, outcome):
    assert error_outcome(Failure(code, "fixture")) == outcome


@pytest.mark.parametrize("available,expected_achievements,expected_stats", [
    ({"achievements": [], "stats": []}, 0, 0),
    ({"achievements": [{"name": "ACH"}]}, 1, 0),
    ({"stats": [{"name": "score"}]}, 0, 1),
    ({"achievements": [{"name": "ACH"}], "stats": [{"name": "score"}]}, 1, 1),
])
def test_dependency_plan_and_counters(tmp_path, available, expected_achievements, expected_stats):
    async def check():
        fixture = Fixtures()
        calls = Counter()
        def transport(req):
            calls[req.url.path] += 1
            if "GetSchemaForGame" in req.url.path:
                return httpx.Response(200, json={"game": {"availableGameStats": available}})
            return fixture(req)
        cfg = config()
        _, doc = new_run("library", cfg)
        # An intimidating name and unmapped type must never override the schema.
        item = record(1, ME, "Dedicated Server SDK Demo")
        item["app_type"] = 999999
        doc["data"]["items"] = [item]
        runtime = Runtime(tmp_path / "runtime.jsonl", doc["meta"]["run_id"], "library")
        ex = Executor(cfg, runtime.event, transport=httpx.MockTransport(transport))
        registry = build_registry(ex)
        try:
            await library.enrich_items(registry, cfg, doc, runtime, player_data=True)
            summary = runtime.summary()
            counts = {api: sum(n for path, n in calls.items() if route in path) for api, route in (
                ("schema", "GetSchemaForGame"), ("achievements", "GetPlayerAchievements"),
                ("stats", "GetUserStatsForGame"), ("store", "appdetails"))}
            assert counts == dict(schema=1, store=1, achievements=expected_achievements, stats=expected_stats)
            assert summary["enrichment_plan"]["achievements_scheduled"] == expected_achievements
            assert summary["enrichment_plan"]["stats_scheduled"] == expected_stats
            assert summary["enrichment_plan"]["stats_skipped_not_applicable"] == 1 - expected_stats
            assert summary["tasks"]["total"] == summary["tasks"]["success"] == 1
            assert summary["tasks"]["failed"] == 0 and summary["operations"]["total"] == 4
            assert summary["logical_requests"] == summary["http_attempts"] == 2 + expected_achievements + expected_stats
            for api, metrics in summary["http_by_api"].items():
                assert metrics["logical_requests"] == sum(metrics[s] for s in ("success", "not_applicable", "data_unavailable", "failed"))
            assert item["achievements"]["state"] == ("ok" if expected_achievements else "not_applicable")
            assert item["stats"]["state"] == ("ok" if expected_stats else "not_applicable")
            if not expected_achievements:
                assert item["achievements"]["total"] == item["achievements"]["unlocked"] == 0
            assert doc["schema_version"] == "1.1.0" and doc["errors"] == []
        finally:
            await registry.close()
            await ex.close()
            runtime.close()
    asyncio.run(check())


@pytest.mark.parametrize("kind,schema_state", [("missing", "data_unavailable"), ("timeout", "failed"), ("503", "failed"), ("malformed", "failed")])
def test_schema_failure_is_not_negative_capability(tmp_path, kind, schema_state):
    async def check():
        fixture = Fixtures()
        def transport(req):
            if "GetSchemaForGame" in req.url.path:
                if kind == "timeout":
                    raise httpx.ReadTimeout("fixture")
                if kind == "503":
                    return httpx.Response(503)
                return httpx.Response(200, json={"game": {} if kind == "missing" else {"availableGameStats": "broken"}})
            return fixture(req)
        cfg = config(max_attempts=2)
        _, doc = new_run("library", cfg)
        doc["data"]["items"] = [record(215, ME, "Source SDK Base 2006")]
        runtime = Runtime(tmp_path / "events.jsonl", doc["meta"]["run_id"], "library")
        clock = FakeClock()
        ex = Executor(cfg, runtime.event, transport=httpx.MockTransport(transport), clock=clock, sleep=clock.sleep)
        registry = build_registry(ex)
        try:
            await library.enrich_items(registry, cfg, doc, runtime, player_data=True)
            assert doc["coverage"]["schema:215"]["state"] == schema_state
            for operation in ("achievements", "stats"):
                assert doc["coverage"][f"{operation}:215"]["state"] == "data_unavailable"
                assert doc["data"]["items"][0][operation]["state"] == "data_unavailable"
            assert not any("GetPlayerAchievements" in p or "GetUserStatsForGame" in p for p in fixture.paths)
            assert runtime.snapshot()["failed" if schema_state == "failed" else "data_unavailable"] == 1
            metrics = runtime.summary()["http_by_api"]["get_schema_for_game"]
            assert metrics["logical_requests"] == 1
            assert metrics["attempts"] == (2 if kind in {"503", "timeout"} else 1)
            assert metrics["retries"] == metrics["attempts"] - 1
            assert metrics[schema_state] == 1
        finally:
            await registry.close()
            await ex.close()
            runtime.close()
    asyncio.run(check())


@pytest.mark.parametrize("status,body,expected", [
    (200, {"1": {"success": False}}, "data_unavailable"),
    (400, {"playerstats": {"success": False, "error": "Requested app has no stats"}}, "not_applicable"),
    (400, {"playerstats": {"success": False, "error": "No stats for this user for this game"}}, "data_unavailable"),
    (400, {"unexpected": "body"}, "failed"),
    (400, {"playerstats": {"steamID": ME, "stats": []}}, "failed"),
])
def test_store_unavailable_and_400_contract(status, body, expected):
    async def check():
        cfg = config()
        ex = Executor(cfg, transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))
        registry = build_registry(ex)
        api = "get_app_details" if status == 200 else "get_user_stats_for_game"
        params = dict(appid=1, language="english", country="US") if status == 200 else dict(appid=1, steamid=ME)
        try:
            result = await registry.call(api, params)
            assert result.state == result.outcome == expected and result.attempts == 1
        finally:
            await registry.close()
            await ex.close()
    asyncio.run(check())


def test_in_run_dedup_including_failed_queries():
    async def check():
        fixture = Fixtures()
        calls = Counter()
        def transport(req):
            calls[(req.url.path, str(req.url.params))] += 1
            if req.url.params.get("appids") == "99":
                return httpx.Response(503)
            if "GetPlayerAchievements" in req.url.path or "GetUserStatsForGame" in req.url.path:
                return httpx.Response(200, json={"playerstats": {"success": True, "steamID": req.url.params["steamid"],
                    "achievements": [{"apiname": "ACH", "achieved": 1}], "stats": [{"name": "score", "value": 7}]}})
            return fixture(req)
        cfg = config(max_attempts=1)
        ex = Executor(cfg, transport=httpx.MockTransport(transport))
        registry = build_registry(ex)
        queries = [
            ("get_schema_for_game", dict(appid=1, language="english")),
            ("get_player_achievements", dict(appid=1, steamid=ME, language="english")),
            ("get_user_stats_for_game", dict(appid=1, steamid=ME)),
            ("get_app_details", dict(appid=1, language="english", country="US")),
            ("get_app_details", dict(appid=99, language="english", country="US")),
        ]
        try:
            for api, params in queries:
                first, second = await asyncio.gather(registry.call(api, params), registry.call(api, params))
                third = await registry.call(api, params)
                assert second.from_run_cache and third.from_run_cache
                assert first.as_dict() | {"from_run_cache": True} == third.as_dict()
            assert sum(calls.values()) == len(queries) and all(n == 1 for n in calls.values())
            await registry.call("get_schema_for_game", dict(appid=1, language="schinese"))
            await registry.call("get_player_achievements", dict(appid=1, steamid=OTHER, language="english"))
            await registry.call("get_user_stats_for_game", dict(appid=1, steamid=OTHER))
            await registry.call("get_app_details", dict(appid=1, language="english", country="CN"))
            assert sum(calls.values()) == len(queries) + 4
        finally:
            await registry.close()
            await ex.close()
    asyncio.run(check())


def test_pipeline_does_not_wait_for_all_schemas():
    async def check():
        fixture = Fixtures()
        slow_schema_started, player_started = asyncio.Event(), asyncio.Event()
        schemas = 0
        async def transport(req):
            nonlocal schemas
            if "GetSchemaForGame" in req.url.path:
                schemas += 1
                if req.url.params["appid"] == "2":
                    slow_schema_started.set()
                    await asyncio.wait_for(player_started.wait(), 1)
                else:
                    await asyncio.wait_for(slow_schema_started.wait(), 1)
            if "GetPlayerAchievements" in req.url.path:
                player_started.set()
            return fixture(req)
        cfg = config()
        _, doc = new_run("library", cfg)
        doc["data"]["items"] = [record(1, ME), record(2, ME)]
        ex = Executor(cfg, transport=httpx.MockTransport(transport))
        registry = build_registry(ex)
        try:
            await asyncio.wait_for(library.enrich_items(registry, cfg, doc, None, player_data=True), 2)
            assert schemas == 2 and player_started.is_set()
            assert all(i["achievements"]["state"] == "ok" for i in doc["data"]["items"])
        finally:
            await registry.close()
            await ex.close()
    asyncio.run(check())


def test_cancelled_subscriber_keeps_shared_result():
    async def check():
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def transport(req):
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return httpx.Response(200, json={"game": {"availableGameStats": {"achievements": []}}})
        ex = Executor(config(), transport=httpx.MockTransport(transport))
        registry = build_registry(ex)
        params = dict(appid=1, language="english")
        try:
            first = asyncio.create_task(registry.call("get_schema_for_game", params))
            await started.wait()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            release.set()
            await asyncio.gather(*registry.inflight.values())
            second = await registry.call("get_schema_for_game", params)
            assert second.from_run_cache and second.outcome == "success" and calls == 1
        finally:
            await registry.close()
            await ex.close()
    asyncio.run(check())


def test_recent_data_cannot_replace_failed_core_collections():
    async def check():
        fixture = Fixtures()
        def transport(req):
            if "GetOwnedGames" in req.url.path or "GetFamilyGroupForUser" in req.url.path:
                return httpx.Response(503)
            if "GetRecentlyPlayedGames" in req.url.path:
                return httpx.Response(200, json={"response": {"total_count": 1, "games": [{"appid": 1}]}})
            return fixture(req)
        cfg = config(max_attempts=1)
        _, doc = new_run("library", cfg)
        ex = Executor(cfg, transport=httpx.MockTransport(transport))
        registry = build_registry(ex)
        try:
            await library.run(registry, cfg, doc, None)
            assert doc["status"] == "failed" and len(doc["data"]["items"]) == 1
            assert doc["coverage"]["owned"]["state"] == doc["coverage"]["family"]["state"] == "failed"
        finally:
            await registry.close()
            await ex.close()
    asyncio.run(check())


@pytest.mark.parametrize("self_owned,owners,reason,expected", [
    (True, [ME], 0, (True, False, None)),
    (False, [OTHER], 0, (False, True, True)),
    (True, [ME, OTHER], 0, (True, True, True)),
    (False, [OTHER], 1, (False, True, False)),
])
def test_family_ownership_unchanged(self_owned, owners, reason, expected):
    own = Result("ok", dict(items=[{"appid": 1}] if self_owned else [], complete=True))
    family = Result("ok", dict(items=[dict(appid=1, owner_steamids=owners, exclude_reason=reason)], complete=False))
    item = record(1, ME, "Cities: Skylines")
    library.merge_ownership(item, dict(owned=own, family=family), ME)
    assert tuple(item["ownership"][k] for k in ("owned_by_self", "owned_by_other_family_members", "available_via_family")) == expected
    assert item["ownership"]["owner_steamids"] == owners


def test_duplicate_collection_apps_and_known_game_fields(tmp_path):
    async def check():
        fixture = Fixtures()
        calls = Counter()
        def transport(req):
            calls[req.url.path] += 1
            if "GetRecentlyPlayedGames" in req.url.path:
                return httpx.Response(200, json={"response": {"total_count": 1, "games": [{"appid": 2, "name": "Left 4 Dead", "playtime_2weeks": 4, "rtime_last_played": 123}]}})
            return fixture(req)
        cfg = config()
        _, doc = new_run("library", cfg)
        runtime = Runtime(tmp_path / "events.jsonl", doc["meta"]["run_id"], "library")
        ex = Executor(cfg, runtime.event, transport=httpx.MockTransport(transport))
        registry = build_registry(ex)
        try:
            await library.run(registry, cfg, doc, runtime, achievements_detail=True)
            # App 2 is present in owned, Family, recent and played-family sources.
            items = {i["appid"]: i for i in doc["data"]["items"]}
            assert len(items) == runtime.total == 5
            for route in ("GetSchemaForGame", "GetPlayerAchievements"):
                assert sum(n for p, n in calls.items() if route in p) == 5
            for route in ("GetUserStatsForGame", "appdetails"):
                assert not any(route in path for path in calls)
            item = items[2]
            assert item["achievements"]["items"][0]["unlock_time"] == 123
            assert item["stats"]["state"] == item["store"]["state"] == "not_requested"
            assert item["playtime"]["last_2weeks_minutes"] == 4
            assert item["playtime"]["last_played_at"] == 123
            assert item["playtime"]["platform_minutes"] == dict(windows=40, linux=30)
        finally:
            await registry.close()
            await ex.close()
            runtime.close()
    asyncio.run(check())


@pytest.mark.parametrize("optional_state", ["not_applicable", "data_unavailable", "failed"])
def test_library_status_depends_on_core_data(optional_state):
    cfg = config()
    _, doc = new_run("library", cfg)
    item = record(1, ME)
    item["ownership"]["state"] = "ok"
    for name in ("store", "achievements", "stats"):
        item[name]["state"] = optional_state
    doc["data"]["items"] = [item]
    doc["coverage"] = dict(owned=dict(state="ok", complete=True), family=dict(state="ok", complete=False),
                           **{"store:1": dict(state=optional_state)})
    library.finish_status(doc, True)
    assert doc["status"] == "ok"
    doc["coverage"]["family"]["state"] = "failed"
    library.finish_status(doc, True)
    assert doc["status"] == "partial"
    library.finish_status(doc, False)
    assert doc["status"] == "failed"


def test_runtime_cancelled_terminal_outcome(tmp_path):
    runtime = Runtime(tmp_path / "cancel.jsonl", "synthetic", "library")
    try:
        runtime.total = 1
        runtime.task("app-1", "running")
        runtime.task("app-1", "cancelled")
        runtime.task("app-1", "success")
        assert runtime.snapshot()["cancelled"] == 1 and runtime.snapshot()["failed"] == 0
    finally:
        runtime.close()
