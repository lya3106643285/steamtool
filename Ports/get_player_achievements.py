from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at, selected


async def call(executor, params, context):
    def decode(body):
        stats = object_at(body, "playerstats")
        if stats.get("success") is False:
            if stats.get("error") == "Requested app has no stats":
                return {"_state": "not_applicable", "items": [], "complete": True}
            raise Failure("DATA_UNAVAILABLE", "Player achievements are unavailable")
        if stats.get("success") is not True or not isinstance(stats.get("achievements"), list):
            raise Failure("RESPONSE_INVALID", "Achievement response incomplete")
        if str(stats.get("steamID", params["steamid"])) != params["steamid"]:
            raise Failure("RESPONSE_INVALID", "Player achievement subject mismatch")
        items = stats["achievements"]
        if any(not isinstance(a, dict) or not isinstance(a.get("apiname"), str) or a.get("achieved") not in (0, 1) for a in items):
            raise Failure("RESPONSE_INVALID", "Invalid player achievement entry")
        if len({a["apiname"] for a in items}) != len(items):
            raise Failure("RESPONSE_INVALID", "Duplicate player achievement keys")
        return dict(items=[selected(a, ("apiname", "achieved", "unlocktime")) for a in items], complete=True,
                    subject_steamid=params["steamid"])
    return await executor.execute(RequestSpec("get_player_achievements", "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/",
        {"appid": params["appid"], "steamid": params["steamid"], "l": params["language"]}, "user_key"), decode, context)
