import json
from steamtool.error_handler import Failure
from steamtool.Ports.get_owned_games import FIELDS
from steamtool.Ports.request_executor import RequestSpec, object_at, app_items, selected


async def call(executor, params, context):
    def decode(body):
        data = object_at(body, "response")
        count = data.get("total_count")
        if type(count) is not int or count < 0:
            raise Failure("DATA_UNAVAILABLE", "Recent-game visibility or count unavailable")
        rows = app_items(data.get("games", []) if count == 0 else data.get("games"))
        return dict(items=[selected(row, FIELDS) for row in rows], count=count, complete=count == len(rows))
    return await executor.execute(RequestSpec("get_recently_played_games", "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/",
        {"input_json": json.dumps({"steamid": params["steamid"], "count": 0})}, "user_key"), decode, context)
