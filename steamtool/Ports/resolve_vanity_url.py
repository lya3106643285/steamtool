from steamtool.config import valid_steamid
from steamtool.error_handler import Failure
from steamtool.Ports.request_executor import RequestSpec, object_at


async def call(executor, params, context):
    def decode(body):
        data = object_at(body, "response")
        if data.get("success") != 1 or not valid_steamid(data.get("steamid")):
            raise Failure("DATA_UNAVAILABLE", "Vanity name did not resolve to an individual SteamID64")
        return {"steamid": data["steamid"]}
    return await executor.execute(RequestSpec("resolve_vanity_url", "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
        {"vanityurl": params["vanity"]}, "user_key"), decode, context)
