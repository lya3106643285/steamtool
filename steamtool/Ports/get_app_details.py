"""Anonymous store details, one AppID per request."""
from steamtool.error_handler import Failure
from steamtool.Ports.request_executor import RequestSpec, object_at, selected

FIELDS = ("steam_appid", "name", "type", "is_free", "short_description", "developers", "publishers",
          "platforms", "genres", "categories", "release_date", "price_overview", "required_age", "dlc", "website")


async def call(executor, params, context):
    appid = params["appid"]
    def decode(body):
        entry = object_at(body, str(appid))
        if entry.get("success") is False:
            raise Failure("DATA_UNAVAILABLE", "Store does not provide this app in the query context")
        if entry.get("success") is not True:
            raise Failure("RESPONSE_INVALID", "Store success flag missing")
        data = object_at(entry, "data")
        if data.get("steam_appid") != appid or not isinstance(data.get("name"), str):
            raise Failure("RESPONSE_INVALID", "Store app identity mismatch")
        return selected(data, FIELDS)
    return await executor.execute(RequestSpec("get_app_details", "https://store.steampowered.com/api/appdetails/",
        {"appids": appid, "l": params["language"], "cc": params["country"]}), decode, context)
