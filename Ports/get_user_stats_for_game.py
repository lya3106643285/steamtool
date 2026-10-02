import math
from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at


async def call(executor, params, context):
    def decode(body):
        stats = object_at(body, "playerstats")
        if str(stats.get("steamID", "")) != params["steamid"]:
            raise Failure("DATA_UNAVAILABLE", "Player stats identity unavailable or mismatched")
        if not isinstance(stats.get("stats"), list):
            raise Failure("DATA_UNAVAILABLE", "No explicit player statistics list")
        items = []
        for row in stats["stats"]:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or type(row.get("value")) not in (int, float) or not math.isfinite(row["value"]):
                raise Failure("RESPONSE_INVALID", "Invalid player statistic")
            items.append({"name": row["name"], "value": row["value"]})
        return dict(items=items, subject_steamid=params["steamid"], complete=True)
    return await executor.execute(RequestSpec("get_user_stats_for_game", "https://api.steampowered.com/ISteamUserStats/GetUserStatsForGame/v2/",
        {"appid": params["appid"], "steamid": params["steamid"]}, "user_key"), decode, context)
