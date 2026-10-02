"""Merge license sources without conflating owners, eligibility and player metrics."""
import asyncio
import time

from error_handler import Failure
from Ports.request_executor import Result
from scripts.game import add_result, block, record, enrich_store
from scripts.persistence import index_app


async def collect_accounts(registry, config, document, runtime, *, player_data=True):
    collections = {}
    started = time.monotonic()
    if runtime:
        runtime.event("phase_started", phase="collections")
    async def get(key, name, params):
        result = await registry.call(name, params)
        collections[key] = result
        add_result(document, key, result, request_scope=result.data.get("request_scope"))
        if runtime:
            runtime.event("collection_loaded", api=name, collection=key, count=len(result.data.get("items", [])), state=result.state)
        return result
    async def family():
        group = await get("family_group", "get_family_group_for_user", {"steamid": config.steamid})
        if group.state == "not_applicable":
            collections["family"] = Result("not_applicable", {"items": [], "complete": True, "no_family": True}, source=group.source, fetched_at=group.fetched_at)
            add_result(document, "family", collections["family"])
        elif group.state == "ok":
            await get("family", "get_shared_library_apps", {"steamid": config.steamid,
                "family_groupid": group.data["family_groupid"], "language": config.language})
        else:
            collections["family"] = group
            add_result(document, "family", group)
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(get("owned", "get_owned_games", {"steamid": config.steamid, "include_family_licenses": False}))
        tasks.create_task(family())
        if player_data:
            tasks.create_task(get("played_family", "get_owned_games", {"steamid": config.steamid, "include_family_licenses": True}))
            tasks.create_task(get("recent", "get_recently_played_games", {"steamid": config.steamid}))
    if runtime:
        duration = (time.monotonic() - started) * 1000
        runtime.phases["collections"] = duration
        runtime.event("phase_finished", phase="collections", duration_ms=duration)
    return collections


def rows_by_id(result):
    return {row["appid"]: row for row in result.data.get("items", [])} if result else {}


def merge_ownership(item, collections, subject):
    own, family = collections["owned"], collections["family"]
    owned = rows_by_id(own).get(item["appid"])
    shared = rows_by_id(family).get(item["appid"])
    owned_by_self = None
    if own.state == "ok":
        if owned is not None:
            owned_by_self = not bool(owned.get("family_shared", False))
        elif own.data.get("complete") is True:
            owned_by_self = False
    other, available, owners, reason = None, None, None, None
    if family.state == "not_applicable" and family.data.get("no_family"):
        other, available, owners = False, False, []
    elif shared is not None:
        owners = shared.get("owner_steamids")
        reason = shared.get("exclude_reason")
        if owners:
            other = any(s != subject for s in owners)
            if subject in owners:
                owned_by_self = True
        if other is True and type(reason) is int:
            # Only explicit zero is interpreted as no exclusion. Unknown enums stay unknown.
            available = True if reason == 0 else None
    item["ownership"] = block("ok" if all(v is not None for v in (owned_by_self, other, available)) else "partial",
        source=[own.source, family.source], fetched_at={"owned": own.fetched_at, "family": family.fetched_at},
        owned_by_self=owned_by_self, owned_by_other_family_members=other, available_via_family=available,
        owner_steamids=owners, shared_exclusion_reason=reason)


def merge_playtime(item, collections, subject):
    evidence = []
    for key in ("played_family", "owned", "recent"):
        source = collections.get(key)
        row = rows_by_id(source).get(item["appid"])
        if row:
            evidence.append((source, row))
    data = {}
    for _, row in evidence:
        data.update(row)
    def number(key):
        value = data.get(key)
        return value if type(value) is int and value >= 0 else None
    item["playtime"] = block("ok" if evidence else "unavailable",
        source=[r.source for r, _ in evidence], fetched_at=[r.fetched_at for r, _ in evidence], subject_steamid=subject,
        total_minutes=number("playtime_forever"), last_2weeks_minutes=number("playtime_2weeks"),
        last_played_at=number("rtime_last_played"), unit="minutes",
        platform_minutes={platform: number(f"playtime_{platform}_forever") for platform in ("windows", "mac", "linux", "deck")
                          if f"playtime_{platform}_forever" in data})


def merge_achievements(schema, player, subject):
    definitions = schema.data.get("achievements", [])
    states = {a["apiname"]: a for a in player.data.get("items", [])}
    complete = (schema.state == "ok" and schema.data.get("complete") is True and player.state == "ok"
                and {a["name"] for a in definitions} == set(states))
    no_achievements = schema.state == "ok" and schema.data.get("complete") is True and not definitions
    items = []
    for definition in definitions:
        value = states.get(definition["name"], {})
        achieved = value.get("achieved")
        items.append(dict(apiname=definition["name"], display_name=definition.get("displayName"),
                          description=definition.get("description"), unlocked=bool(achieved) if achieved in (0, 1) else None,
                          unlock_time=value.get("unlocktime")))
    # Keep successful player entries even if definitions are unavailable.
    definition_keys = {a["name"] for a in definitions}
    for name, value in states.items():
        if name not in definition_keys:
            items.append(dict(apiname=name, display_name=None, description=None, unlocked=bool(value["achieved"]), unlock_time=value.get("unlocktime")))
    total = len(definitions) if schema.state == "ok" else None
    unlocked = sum(a["unlocked"] is True for a in items) if complete else 0 if no_achievements else None
    return block("not_applicable" if no_achievements else "ok" if complete else "unavailable" if not items else "partial",
        source=[schema.source, player.source], fetched_at={"schema": schema.fetched_at, "player": player.fetched_at},
        subject_steamid=subject, total=total, unlocked=unlocked,
        completion_ratio=unlocked / total if complete and total else None, items=sorted(items, key=lambda a: a["apiname"]))


async def enrich_player(registry, config, document, item):
    context = {"task_id": f"app-{item['appid']}"}
    schema = await registry.call("get_schema_for_game", {"appid": item["appid"], "language": config.language}, context)
    add_result(document, f"schema:{item['appid']}", schema)
    # An explicit empty definition avoids a pointless player-achievements request.
    if schema.state == "ok" and schema.data.get("achievements") == []:
        player = Result("not_applicable", {"items": []}, source="get_player_achievements")
    else:
        player = await registry.call("get_player_achievements", {"appid": item["appid"], "steamid": config.steamid, "language": config.language}, context)
    add_result(document, f"achievements:{item['appid']}", player)
    item["achievements"] = merge_achievements(schema, player, config.steamid)
    stats = await registry.call("get_user_stats_for_game", {"appid": item["appid"], "steamid": config.steamid}, context)
    add_result(document, f"stats:{item['appid']}", stats)
    item["stats"] = block(stats.state, stats.source, stats.fetched_at, subject_steamid=config.steamid,
                          items=stats.data.get("items", []), error_id=stats.error["error_id"] if stats.error else None)


async def enrich_items(registry, config, document, runtime, *, player_data):
    items = document["data"]["items"]
    if runtime:
        runtime.total = len(items)
        runtime.event("phase_started", phase="enrichment")
    started = time.monotonic()
    queue = asyncio.Queue()
    for item in items:
        queue.put_nowait(item)
    async def worker():
        while not queue.empty() and not registry.executor.stopping.is_set():
            item = queue.get_nowait()
            task_id = f"app-{item['appid']}"
            if runtime:
                runtime.task(task_id, "running", appid=item["appid"])
            try:
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(enrich_store(registry, config, document, item))
                    if player_data:
                        tasks.create_task(enrich_player(registry, config, document, item))
                if runtime:
                    failed = any(document["coverage"].get(f"{source}:{item['appid']}", {}).get("state") == "unavailable"
                                 for source in ("store", "schema", "achievements", "stats"))
                    runtime.task(task_id, "failed" if failed else "success", appid=item["appid"])
            except asyncio.CancelledError:
                if runtime and not runtime.failed:
                    runtime.task(task_id, "cancelled", appid=item["appid"])
                raise
            except BaseException:
                if runtime and not runtime.failed:
                    runtime.task(task_id, "failed", appid=item["appid"])
                raise
            finally:
                queue.task_done()
    async with asyncio.TaskGroup() as tasks:
        for _ in range(min(config.concurrency, len(items))):
            tasks.create_task(worker())
    if runtime:
        duration = (time.monotonic() - started) * 1000
        runtime.phases["enrichment"] = duration
        runtime.event("phase_finished", phase="enrichment", duration_ms=duration)


def finish_status(document, primary_ok):
    incomplete = any(c.get("state") in {"unavailable", "partial"} or c.get("complete") is False for c in document["coverage"].values())
    document["status"] = "failed" if not primary_ok else "partial" if incomplete else "ok"
    items = document["data"]["items"]
    times = [item["playtime"]["total_minutes"] for item in items]
    known = [value for value in times if value is not None]
    document["data"]["summary"] = dict(item_count=len(items), known_playtime_minutes=sum(known),
        playtime_known_count=len(known), playtime_missing_count=len(times) - len(known))
    items.sort(key=lambda item: item["appid"])


async def run(registry, config, document, runtime):
    if not config.steamid:
        raise Failure("CONFIG_INVALID", "STEAM_ID is required for library export", source="config", scope="feature")
    collections = await collect_accounts(registry, config, document, runtime)
    candidates = {}
    for key in ("family", "played_family", "recent", "owned"):
        candidates.update(rows_by_id(collections.get(key)))
    for appid in sorted(candidates):
        row = candidates[appid]
        item = record(appid, config.steamid, row.get("name"))
        merge_ownership(item, collections, config.steamid)
        merge_playtime(item, collections, config.steamid)
        document["data"]["items"].append(item)
        index_app(document, appid, item["name"], "library collections")
    await enrich_items(registry, config, document, runtime, player_data=True)
    finish_status(document, bool(candidates) or collections["owned"].state == "ok" or collections["family"].state in {"ok", "not_applicable"})
