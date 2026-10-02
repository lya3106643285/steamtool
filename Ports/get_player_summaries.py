from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at, selected


async def call(executor, params, context):
    def decode(body):
        data = object_at(body, "response")
        rows = data.get("players")
        if not isinstance(rows, list) or any(not isinstance(p, dict) for p in rows):
            raise Failure("RESPONSE_INVALID", "Player list missing")
        rows = [selected(p, ("steamid", "personaname", "communityvisibilitystate", "profilestate")) for p in rows if p.get("steamid") == params["steamid"]]
        if len(rows) != 1:
            raise Failure("DATA_UNAVAILABLE", "Target profile unavailable")
        return {"items": rows, "complete": True}
    return await executor.execute(RequestSpec("get_player_summaries", "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
        {"steamids": params["steamid"]}, "user_key"), decode, context)
