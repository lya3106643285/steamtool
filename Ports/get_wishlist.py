import json
from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at, app_items, selected


async def call(executor, params, context):
    def decode(body):
        data = object_at(body, "response")
        if "items" not in data:
            raise Failure("DATA_UNAVAILABLE", "Wishlist items omitted; empty/private state is ambiguous")
        rows = app_items(data["items"])
        return dict(items=[selected(row, ("appid", "priority", "date_added")) for row in rows],
                    complete=None, note="Requires count consistency check; omitted list is not considered empty")
    return await executor.execute(RequestSpec("get_wishlist", "https://api.steampowered.com/IWishlistService/GetWishlist/v1/",
        {"input_json": json.dumps({"steamid": params["steamid"]})}), decode, context)
