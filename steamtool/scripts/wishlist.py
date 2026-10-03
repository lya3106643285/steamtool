"""Keep every identifiable wish, including unavailable store entries."""
import asyncio

from steamtool.error_handler import Failure
from steamtool.scripts.game import add_result, block, record
from steamtool.scripts.library import collect_accounts, merge_ownership, enrich_items, finish_status
from steamtool.scripts.persistence import index_app


async def collect_wishlist(registry, config, document):
    results = {}
    async def get(key, name):
        result = await registry.call(name, {"steamid": config.steamid})
        results[key] = result
        add_result(document, key, result)
        if key == "wishlist" and document["meta"]["feature"] == "wishlist" and result.state == "ok":
            for appid in sorted({row["appid"] for row in result.data["items"]}):
                item = record(appid, config.steamid)
                merge_wish(item, result, False)
                document["data"]["items"].append(item)
                index_app(document, appid)
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(get("wishlist", "get_wishlist"))
        tasks.create_task(get("wishlist_count", "get_wishlist_item_count"))
    wishes, count = results["wishlist"], results["wishlist_count"]
    actual = len({row["appid"] for row in wishes.data.get("items", [])})
    complete = wishes.state == "ok" and count.state == "ok" and actual == count.data["count"]
    document["coverage"]["wishlist"].update(complete=complete, distinct_count=actual,
        expected_count=count.data.get("count"), evidence="Explicit items plus equal independent count" if complete else "List/count unconfirmed or inconsistent")
    return wishes, complete


def merge_wish(item, wishes, complete):
    entries = [row for row in wishes.data.get("items", []) if row["appid"] == item["appid"]]
    value = entries[0] if entries else {}
    item["wishlist"] = block(wishes.state, wishes.source, wishes.fetched_at,
        present=True if entries else False if complete else None, priority=value.get("priority"),
        date_added=value.get("date_added"), entries=entries)


async def run(registry, config, document, runtime):
    if not config.steamid:
        raise Failure("CONFIG_INVALID", "STEAM_ID is required for wishlist export", source="config", scope="feature")
    wishes, complete = await collect_wishlist(registry, config, document)
    if wishes.state != "ok":
        document["status"] = "failed"
        return
    document["data"]["items"].clear()
    for appid in sorted({row["appid"] for row in wishes.data["items"]}):
        item = record(appid, config.steamid)
        merge_wish(item, wishes, complete)
        document["data"]["items"].append(item)
        index_app(document, appid)
    # Explicit, count-confirmed empty wishes need no per-game ownership lookups.
    if document["data"]["items"]:
        collections = await collect_accounts(registry, config, document, runtime, player_data=False)
        for item in document["data"]["items"]:
            merge_ownership(item, collections, config.steamid)
        await enrich_items(registry, config, document, runtime, player_data=False)
    finish_status(document, True)
