from steamtool.error_handler import Failure
from steamtool.Ports.request_executor import RequestSpec, object_at, selected


async def call(executor, params, context):
    def decode(body):
        game = object_at(body, "game")
        if not game or "availableGameStats" not in game:
            raise Failure("DATA_UNAVAILABLE", "No explicit achievement schema available")
        if not isinstance(game["availableGameStats"], dict):
            raise Failure("RESPONSE_INVALID", "Invalid availableGameStats object")
        stats = game["availableGameStats"]
        achievements = stats.get("achievements", [])
        if not isinstance(achievements, list) or any(not isinstance(a, dict) or not isinstance(a.get("name"), str) for a in achievements):
            raise Failure("RESPONSE_INVALID", "Invalid achievement schema")
        if len({a["name"] for a in achievements}) != len(achievements):
            raise Failure("RESPONSE_INVALID", "Duplicate achievement keys")
        definitions = stats.get("stats", [])
        if (not isinstance(definitions, list) or any(not isinstance(s, dict) or not isinstance(s.get("name"), str) for s in definitions)
                or len({s["name"] for s in definitions}) != len(definitions)):
            raise Failure("RESPONSE_INVALID", "Invalid statistics schema")
        return dict(achievements=[selected(a, ("name", "displayName", "description", "hidden", "icon", "icongray")) for a in achievements],
                    stats=[selected(s, ("name", "displayName", "defaultvalue")) for s in definitions],
                    capabilities=dict(achievements=bool(achievements), stats=bool(definitions)),
                    complete=True, game_name=game.get("gameName"))
    return await executor.execute(RequestSpec("get_schema_for_game", "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/",
        {"appid": params["appid"], "l": params["language"]}, "user_key"), decode, context)
