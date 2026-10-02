from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at, selected


async def call(executor, params, context):
    def decode(body):
        game = object_at(body, "game")
        if not game or not isinstance(game.get("availableGameStats"), dict):
            raise Failure("DATA_UNAVAILABLE", "No explicit achievement schema available")
        stats = game["availableGameStats"]
        achievements = stats.get("achievements", [])
        if not isinstance(achievements, list) or any(not isinstance(a, dict) or not isinstance(a.get("name"), str) for a in achievements):
            raise Failure("RESPONSE_INVALID", "Invalid achievement schema")
        if len({a["name"] for a in achievements}) != len(achievements):
            raise Failure("RESPONSE_INVALID", "Duplicate achievement keys")
        return dict(achievements=[selected(a, ("name", "displayName", "description", "hidden", "icon", "icongray")) for a in achievements],
                    complete=True, game_name=game.get("gameName"))
    return await executor.execute(RequestSpec("get_schema_for_game", "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/",
        {"appid": params["appid"], "l": params["language"]}, "user_key"), decode, context)
