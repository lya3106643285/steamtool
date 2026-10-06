"""Merge license sources without conflating owners, eligibility and player metrics."""
import asyncio
import time

from steamtool.error_handler import Failure
from steamtool.Ports.request_executor import Result
from steamtool.Ports.get_shared_library_apps import KNOWN_EXCLUDED_REASONS
from steamtool.scripts.game import add_result, block, record, enrich_store
from steamtool.scripts.persistence import index_app


async def collect_accounts(registry, config, document, runtime, *, player_data=True):
    collections = {
        "owned": Result("unavailable", source="get_owned_games"),
        "family": Result("unavailable", source="get_shared_library_apps"),
    }
    started = time.monotonic()
    if runtime:
        runtime.event("phase_started", phase="collections")
    async def get(key, name, params):
        result = await registry.call(name, params)
        collections[key] = result
        add_result(document, key, result, request_scope=result.data.get("request_scope"),
                   distinct_count=len({row["appid"] for row in result.data["items"]}) if "items" in result.data else None,
                   potentially_truncated=result.data.get("potentially_truncated"))
        # Publish each completed collection immediately so cancellation preserves its IDs.
        if document["meta"]["feature"] == "library":
            existing = {item["appid"]: item for item in document["data"]["items"]}
            for row in result.data.get("items", []):
                if row["appid"] not in existing:
                    item = record(row["appid"], config.steamid, row.get("name"))
                    item["_identity_meta"] = block("ok" if row.get("name") else "partial", result.source, result.fetched_at)
                    document["data"]["items"].append(item)
                    existing[row["appid"]] = item
                    index_app(document, row["appid"], row.get("name"), result.source)
                elif row.get("name") and not existing[row["appid"]]["name"]:
                    existing[row["appid"]]["name"] = row["name"]
                    existing[row["appid"]]["_identity_meta"] = block("ok", result.source, result.fetched_at)
                    index_app(document, row["appid"], row["name"], result.source)
            for item in existing.values():
                merge_ownership(item, collections, config.steamid)
                merge_playtime(item, collections, config.steamid)
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
            available = True if reason == 0 else False if reason in KNOWN_EXCLUDED_REASONS else None
    item["ownership"] = block("ok" if all(v is not None for v in (owned_by_self, other, available)) else "partial",
        source=[own.source, family.source], fetched_at={"owned": own.fetched_at, "family": family.fetched_at},
        owned_by_self=owned_by_self, owned_by_other_family_members=other, available_via_family=available,
        owner_steamids=owners, shared_exclusion_reason=reason,
        error_id=next((result.error["error_id"] for result in (own, family) if result.error), None))


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
    state = ("not_applicable" if no_achievements or player.state == "not_applicable" else "ok" if complete
             else "failed" if player.state == "failed" else "data_unavailable")
    return block(state,
        source=[schema.source, player.source], fetched_at={"schema": schema.fetched_at, "player": player.fetched_at},
        subject_steamid=subject, total=total, unlocked=unlocked,
        completion_ratio=unlocked / total if complete and total else None, items=sorted(items, key=lambda a: a["apiname"]),
        error_id=(player.error or schema.error or {}).get("error_id"))


async def enrich_player(registry, config, document, item, *, details=True, include_stats=True):
    context = {"task_id": f"app-{item['appid']}"}
    registry.executor.event("enrichment_decision", appid=item["appid"], operation="schema", decision="scheduled", reason="capability discovery", **context)
    schema = await registry.call("get_schema_for_game", {"appid": item["appid"], "language": config.language}, context)
    add_result(document, f"schema:{item['appid']}", schema)
    registry.executor.event("operation_finished", api=schema.source, appid=item["appid"],
                            operation_id=f"schema:{item['appid']}", outcome=schema.outcome, **context)

    async def downstream(operation, api):
        # Only a validated complete schema is negative capability evidence.
        definitions = schema.data.get(operation)
        verified = schema.state == "ok" and schema.data.get("complete") is True and isinstance(definitions, list)
        if operation == "achievements" and not details and verified and definitions:
            # TODO: current ports have no verified summary-only unlocked-count source.
            # Do not silently fetch a complete player achievement list in default mode.
            result = Result("partial", {"complete": False}, source=schema.source, fetched_at=schema.fetched_at)
            item[operation] = block("partial", schema.source, schema.fetched_at,
                                    total=len(definitions), unlocked=None, completion_ratio=None, items=None)
            registry.executor.event("enrichment_decision", appid=item["appid"], operation=operation,
                                    decision="skipped_not_requested", reason="detail disabled; unlocked summary source unconfirmed", **context)
            add_result(document, f"{operation}:{item['appid']}", result)
            registry.executor.event("operation_finished", api=api, appid=item["appid"],
                                    operation_id=f"{operation}:{item['appid']}", outcome=result.outcome, **context)
            return
        if verified and definitions:
            decision, reason = "scheduled", "schema contains definitions"
            params = dict(appid=item["appid"], steamid=config.steamid)
            if operation == "achievements":
                params["language"] = config.language
            registry.executor.event("enrichment_decision", appid=item["appid"], operation=operation,
                                    decision=decision, reason=reason, **context)
            result = await registry.call(api, params, context)
            if operation == "achievements" and result.state == "not_applicable":
                # A missing player record cannot negate an explicitly positive app schema.
                result = Result("data_unavailable", error=result.error, source=result.source,
                                fetched_at=result.fetched_at, attempts=result.attempts)
        else:
            state = "not_applicable" if verified or schema.state == "not_applicable" else "data_unavailable"
            decision = "skipped_not_applicable" if state == "not_applicable" else "skipped_dependency"
            reason = "schema explicitly has no definitions" if verified else "schema capability unavailable"
            error = None
            if state == "data_unavailable":
                error = Failure("DEPENDENCY_FAILED", "Schema evidence unavailable; downstream request not scheduled",
                                api=api, appid=item["appid"], subject_steamid=config.steamid).info
            result = Result(state, {"items": [], "complete": state == "not_applicable"}, error=error, source=api)
            registry.executor.event("enrichment_decision", appid=item["appid"], operation=operation,
                                    decision=decision, reason=reason, capability=False if verified else "unknown",
                                    dependency_error_id=schema.error["error_id"] if schema.error else None, **context)
        add_result(document, f"{operation}:{item['appid']}", result)
        registry.executor.event("operation_finished", api=api, appid=item["appid"],
                                operation_id=f"{operation}:{item['appid']}", outcome=result.outcome, **context)
        if operation == "achievements":
            item[operation] = merge_achievements(schema, result, config.steamid)
            if not details or result.state not in {"ok", "not_applicable"}:
                item[operation]["items"] = None
        else:
            item[operation] = block(result.state, result.source, result.fetched_at, subject_steamid=config.steamid,
                                    items=result.data.get("items", []), error_id=result.error["error_id"] if result.error else None)
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(downstream("achievements", "get_player_achievements"))
        if include_stats:
            tasks.create_task(downstream("stats", "get_user_stats_for_game"))


async def enrich_items(registry, config, document, runtime, *, player_data, details=True,
                       include_stats=True, include_store=True):
    items = document["data"]["items"]
    if runtime:
        runtime.total = len(items)
        runtime.enrichment_plan["input_apps"] = len(items)
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
                    if include_store:
                        tasks.create_task(enrich_store(registry, config, document, item))
                    if player_data:
                        tasks.create_task(enrich_player(registry, config, document, item, details=details, include_stats=include_stats))
                if runtime:
                    outcomes = {c["outcome"] for source in ("store", "schema", "achievements", "stats")
                                if (c := document["coverage"].get(f"{source}:{item['appid']}"))}
                    # One App = one task. Prefer the most consequential completed outcome.
                    outcome = next((s for s in ("failed", "data_unavailable", "success", "not_applicable") if s in outcomes), "data_unavailable")
                    runtime.task(task_id, outcome, appid=item["appid"])
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
    coverage = document["coverage"]
    if document["meta"]["feature"] == "library":
        # Experimental Family completeness remains visible, but is not itself a failure.
        incomplete = any(coverage.get(key, {}).get("state") not in {"ok", "not_applicable"} for key in ("owned", "family"))
        incomplete |= coverage.get("owned", {}).get("complete") is False
        incomplete |= bool(coverage.get("family", {}).get("potentially_truncated"))
    else:
        incomplete = any(c.get("state") in {"unavailable", "partial", "data_unavailable", "failed"} or c.get("complete") is False for c in coverage.values())
    incomplete = incomplete or any(
        item[name]["state"] in {"partial", "unavailable", "data_unavailable", "failed"}
        for item in document["data"]["items"]
        for name in (("ownership",) if document["meta"]["feature"] == "library" else ("ownership", "store", "achievements", "stats")))
    document["status"] = "failed" if not primary_ok else "partial" if incomplete else "ok"
    items = document["data"]["items"]
    times = [item["playtime"]["total_minutes"] for item in items]
    known = [value for value in times if value is not None]
    document["data"]["summary"] = dict(item_count=len(items), known_playtime_minutes=sum(known),
        playtime_known_count=len(known), playtime_missing_count=len(times) - len(known))
    items.sort(key=lambda item: item["appid"])


async def run(registry, config, document, runtime, *, achievements_detail=False):
    if not config.steamid:
        raise Failure("CONFIG_INVALID", "STEAM_ID is required for library export", source="config", scope="feature")
    collections = await collect_accounts(registry, config, document, runtime)
    candidates, origins = {}, {}
    for key in ("family", "played_family", "recent", "owned"):
        rows = rows_by_id(collections.get(key))
        for appid, row in rows.items():
            prior = candidates.get(appid, {})
            candidates[appid] = {**prior, **row}
            if row.get("name") or appid not in origins:
                origins[appid] = collections[key]
            elif prior.get("name"):
                candidates[appid]["name"] = prior["name"]
    document["data"]["items"].clear()
    for appid in sorted(candidates):
        row = candidates[appid]
        item = record(appid, config.steamid, row.get("name"))
        item["app_type"] = row.get("app_type") if isinstance(row.get("app_type"), str) else None
        item["_identity_meta"] = block("ok" if row.get("name") else "partial", origins[appid].source, origins[appid].fetched_at)
        merge_ownership(item, collections, config.steamid)
        merge_playtime(item, collections, config.steamid)
        document["data"]["items"].append(item)
        index_app(document, appid, item["name"], "library collections")
    await enrich_items(registry, config, document, runtime, player_data=True,
                       details=achievements_detail, include_stats=False, include_store=False)
    finish_status(document, collections["owned"].state == "ok" or collections["family"].state == "ok")
