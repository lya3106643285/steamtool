"""Store search is a candidate generator, never a first-result resolver."""
from steamtool.config import valid_appid
from steamtool.error_handler import Failure
from steamtool.Ports.request_executor import RequestSpec


async def call(executor, params, context):
    if not isinstance(params["query"], str) or not params["query"].strip() or len(params["query"]) > 300:
        raise Failure("CONFIG_INVALID", "Search query must contain 1–300 characters")
    def decode(body):
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            raise Failure("RESPONSE_INVALID", "Store search items missing")
        items = []
        for row in body["items"]:
            if not isinstance(row, dict):
                raise Failure("RESPONSE_INVALID", "Invalid search candidate")
            if row.get("type", "app") != "app":
                continue
            if not valid_appid(row.get("id")) or not isinstance(row.get("name"), str):
                raise Failure("RESPONSE_INVALID", "Invalid search candidate identity")
            items.append({"appid": row["id"], "name": row["name"], "entity_type": "app"})
        return {"items": items, "total": body.get("total"), "complete": False,
                "note": "Store search is a regional candidate window, not the full application catalog"}
    return await executor.execute(RequestSpec("search_games", "https://store.steampowered.com/api/storesearch/",
        {"term": params["query"], "l": params["language"], "cc": params["country"]}), decode, context)
