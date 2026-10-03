"""Own licenses and experimental played-family comparison are separate calls."""
import json
from steamtool.error_handler import Failure
from steamtool.Ports.request_executor import RequestSpec, object_at, selected, app_items

FIELDS = ("appid", "name", "playtime_forever", "playtime_2weeks", "playtime_windows_forever",
          "playtime_mac_forever", "playtime_linux_forever", "playtime_deck_forever", "rtime_last_played", "family_shared")


def decode(body):
    data = object_at(body, "response")
    count = data.get("game_count")
    if type(count) is not int or count < 0:
        raise Failure("DATA_UNAVAILABLE", "Owned-game visibility or count is unavailable")
    rows = app_items(data.get("games", []) if count == 0 else data.get("games"))
    return dict(items=[selected(row, FIELDS) for row in rows], count=count,
                complete=count == len({row["appid"] for row in rows}), scope="visible owned-game response")


async def call(executor, params, context):
    family = params.get("include_family_licenses", False)
    if type(family) is not bool:
        raise Failure("CONFIG_INVALID", "include_family_licenses must be boolean")
    fields = dict(steamid=params["steamid"], include_appinfo=True, include_played_free_games=True,
                  include_family_licenses=family)
    result = await executor.execute(RequestSpec("get_owned_games", "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
        {"input_json": json.dumps(fields)}, "user_key"), decode, context)
    result.data["request_scope"] = fields
    if family:
        result.data["family_parameter_live_verified"] = False
    return result
