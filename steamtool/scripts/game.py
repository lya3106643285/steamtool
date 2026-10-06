"""Single-game resolution plus shared GameRecord assembly helpers."""
import asyncio
import re
from urllib.parse import urlsplit

from steamtool.config import valid_appid
from steamtool.error_handler import Failure
from steamtool.error_handler import result_outcome
from steamtool.scripts.persistence import index_app, normalize


def block(state="not_requested", source=None, fetched_at=None, **fields):
    return dict(state=state, outcome=result_outcome(state) if state != "not_requested" else None,
                source=source, fetched_at=fetched_at, **fields)


def record(appid, steamid, name=None):
    return dict(appid=appid, name=name, app_type=None,
        store_url=f"https://store.steampowered.com/app/{appid}/",
        ownership=block("unavailable", owned_by_self=None, owned_by_other_family_members=None,
                        available_via_family=None, owner_steamids=None, shared_exclusion_reason=None),
        wishlist=block(present=None, priority=None, date_added=None),
        playtime=block(subject_steamid=steamid or None, total_minutes=None, last_2weeks_minutes=None,
                       last_played_at=None, platform_minutes={}, unit="minutes"),
        achievements=block(subject_steamid=steamid or None, total=None, unlocked=None, completion_ratio=None, items=[]),
        stats=block(subject_steamid=steamid or None, items=[]), store=block(data=None))


def add_result(document, key, result, **extra):
    document["coverage"][key] = dict(state=result.state, source=result.source, fetched_at=result.fetched_at,
        outcome=result.outcome,
        complete=result.data.get("complete") if result.state in {"ok", "not_applicable"} else None,
        count=len(result.data["items"]) if "items" in result.data else None,
        error_id=result.error["error_id"] if result.error else None, **extra)
    if result.error and result.outcome != "not_applicable" and not any(e["error_id"] == result.error["error_id"] for e in document["errors"]):
        document["errors"].append(result.error)


def parse_target(query=None, appid=None):
    if appid is not None:
        if query or not valid_appid(appid):
            raise Failure("CONFIG_INVALID", "Use either a valid AppID or one game query", scope="feature")
        return appid
    if not isinstance(query, str) or not query.strip():
        raise Failure("CONFIG_INVALID", "A game name, AppID or official app URL is required", scope="feature")
    query = query.strip()
    if query.isascii() and query.isdigit():
        return parse_target(appid=int(query))
    if "://" in query:
        url = urlsplit(query)
        match = re.fullmatch(r"/app/([0-9]+)(?:/[^?#]*)?", url.path)
        if url.scheme not in {"http", "https"} or url.netloc != "store.steampowered.com" or not match:
            raise Failure("CONFIG_INVALID", "Only official store app URLs are supported; sub/bundle are unsupported", scope="feature")
        return parse_target(appid=int(match[1]))
    return None


async def enrich_store(registry, config, document, item):
    registry.executor.event("enrichment_decision", appid=item["appid"], operation="store", decision="scheduled", reason="independent store lookup")
    result = await registry.call("get_app_details", {"appid": item["appid"], "language": config.language, "country": config.country},
                                 {"task_id": f"app-{item['appid']}"})
    add_result(document, f"store:{item['appid']}", result)
    registry.executor.event("operation_finished", api=result.source, appid=item["appid"],
                            operation_id=f"store:{item['appid']}", outcome=result.outcome)
    item["store"] = block(result.state, result.source, result.fetched_at,
                          error_id=result.error["error_id"] if result.error else None,
                          data=result.data if result.state == "ok" else None)
    if result.state == "ok":
        item["name"] = result.data.get("name") or item["name"]
        item["app_type"] = result.data.get("type")
    index_app(document, item["appid"], item["name"], result.source)
    if result.state == "ok":
        for related_appid in result.data.get("dlc", []):
            if valid_appid(related_appid):
                index_app(document, related_appid, source="get_app_details:dlc")


async def resolve_name(registry, config, document, query, *, coverage_key="search"):
    result = await registry.call("search_games", {"query": query, "language": config.language, "country": config.country})
    add_result(document, coverage_key, result)
    candidates = result.data.get("items", [])
    for candidate in candidates:
        index_app(document, candidate["appid"], candidate["name"], "search_games")
    exact = [candidate for candidate in candidates if normalize(candidate["name"]) == normalize(query)]
    return result, candidates, exact


async def run(registry, config, document, runtime, *, query=None, appid=None):
    appid = parse_target(query, appid)
    name = None
    if appid is None:
        result, candidates, exact = await resolve_name(registry, config, document, query)
        document["data"]["resolution"] = dict(query=query, candidates=candidates, selected_appid=None)
        if result.state != "ok":
            document["status"] = "failed"
            return
        if len(exact) != 1:
            document["status"] = "needs_selection"
            return
        appid, name = exact[0]["appid"], exact[0]["name"]
    document["data"]["resolution"] = {**(document["data"]["resolution"] or {}), "selected_appid": appid}
    item = record(appid, config.steamid, name)
    document["data"]["items"].append(item)
    index_app(document, appid, name)
    if runtime:
        runtime.total = 1
        runtime.task(f"app-{appid}", "running", appid=appid)
    await enrich_store(registry, config, document, item)
    if config.steamid:
        from steamtool.scripts.library import collect_accounts, merge_ownership, merge_playtime, finish_status
        from steamtool.scripts.wishlist import collect_wishlist, merge_wish
        collections = await collect_accounts(registry, config, document, runtime)
        merge_ownership(item, collections, config.steamid)
        merge_playtime(item, collections, config.steamid)
        wishes, complete = await collect_wishlist(registry, config, document)
        merge_wish(item, wishes, complete)
        finish_status(document, True)
    else:
        document["coverage"]["account"] = dict(state="not_requested", complete=None,
            note="STEAM_ID not configured; public store scope only, ownership remains null")
        document["status"] = "ok" if item["store"]["state"] == "ok" else "partial"
    if runtime:
        runtime.task(f"app-{appid}", "failed" if document["status"] in {"partial", "failed"} else "success", appid=appid)


async def run_games(registry, config, document, runtime, *, names, achievements_detail=False):
    """Batch names share the existing resolver, collections, enrichment and run cache."""
    from steamtool.scripts.library import collect_accounts, merge_ownership, merge_playtime, enrich_items
    from steamtool.scripts.wishlist import collect_wishlist, merge_wish
    selected = set()
    for query in names:
        result, candidates, exact = await resolve_name(registry, config, document, query,
                                                      coverage_key=f"search:{query}")
        if result.state != "ok":
            continue
        if len(exact) != 1:
            failure = Failure("GAME_AMBIGUOUS" if len(exact) > 1 else "GAME_NOT_FOUND",
                              "Game name could not be resolved to one exact AppID: " + query,
                              source="resolver", scope="feature", api="search_games")
            document["errors"].append(failure.info)
            continue
        target = exact[0]
        if target["appid"] in selected:
            continue
        selected.add(target["appid"])
        item = record(target["appid"], config.steamid, target["name"])
        item["_identity_meta"] = block("ok", result.source, result.fetched_at)
        document["data"]["items"].append(item)
    if not document["data"]["items"]:
        document["status"] = "failed"
        return
    if config.steamid:
        collections, wishes_result = await asyncio.gather(
            collect_accounts(registry, config, document, runtime), collect_wishlist(registry, config, document))
        wishes, complete = wishes_result
        for item in document["data"]["items"]:
            merge_ownership(item, collections, config.steamid)
            merge_playtime(item, collections, config.steamid)
            merge_wish(item, wishes, complete)
    await enrich_items(registry, config, document, runtime, player_data=True,
                       details=achievements_detail, include_stats=False)
