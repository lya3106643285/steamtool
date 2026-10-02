import json
from config import valid_steamid
from error_handler import Failure
from Ports.get_family_group_for_user import token_subject
from Ports.request_executor import RequestSpec, object_at, app_items, selected, Result

MAX_APPS = 10000
# ESharedLibraryExcludeReason in steam/steammessages_familygroups.steamclient.proto.
# Unassigned gaps 5 and 14 and future enum values are deliberately not interpreted.
KNOWN_EXCLUDED_REASONS = frozenset({1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, *range(15, 31)})


async def call(executor, params, context):
    if token_subject(executor.config.family_token) != params["steamid"]:
        error = Failure("ACCESS_DENIED", "Unconfirmed session subject", source="auth", api="get_shared_library_apps")
        return Result("unavailable", error=error.info, source="get_shared_library_apps")
    groupid = params["family_groupid"]
    if not isinstance(groupid, str) or not groupid.isdigit() or int(groupid) <= 0:
        raise Failure("CONFIG_INVALID", "A confirmed positive family_groupid is required")
    fields = dict(family_groupid=groupid, steamid=params["steamid"], include_own=True, include_excluded=True,
                  include_non_games=True, language=params["language"], max_apps=MAX_APPS)
    def decode(body):
        data = object_at(body, "response")
        rows = app_items(data.get("apps"))
        owner = data.get("owner_steamid")
        if owner is not None and str(owner) != params["steamid"]:
            raise Failure("ACCESS_DENIED", "Shared-library response subject mismatch")
        items = []
        for row in rows:
            item = selected(row, ("appid", "name", "owner_steamids", "exclude_reason", "app_type"))
            if "owner_steamids" in item:
                owners = item["owner_steamids"]
                if not isinstance(owners, list) or not all(valid_steamid(str(s)) for s in owners):
                    raise Failure("RESPONSE_INVALID", "Invalid family owner IDs")
                item["owner_steamids"] = [str(s) for s in owners]
            items.append(item)
        return dict(items=items, complete=False, potentially_truncated=len(rows) >= MAX_APPS,
                    request_scope=fields, note="Experimental family list has no verified pagination/completeness guarantee")
    return await executor.execute(RequestSpec("get_shared_library_apps", "https://api.steampowered.com/IFamilyGroupsService/GetSharedLibraryApps/v1/",
        {"input_json": json.dumps(fields)}, "session_token", True), decode, context)
