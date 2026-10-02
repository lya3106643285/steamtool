import json
from error_handler import Failure
from Ports.request_executor import RequestSpec, object_at


async def call(executor, params, context):
    def decode(body):
        data = object_at(body, "response")
        count = data.get("count")
        if type(count) is not int or count < 0:
            raise Failure("DATA_UNAVAILABLE", "Wishlist count not explicitly available")
        return {"count": count}
    return await executor.execute(RequestSpec("get_wishlist_item_count", "https://api.steampowered.com/IWishlistService/GetWishlistItemCount/v1/",
        {"input_json": json.dumps({"steamid": params["steamid"]})}), decode, context)
