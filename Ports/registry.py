"""Explicit registration, validation, auth checks, successful run cache/single-flight."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
import json
import re

from config import valid_appid, valid_steamid
from error_handler import Failure
from Ports.request_executor import Result


@dataclass(frozen=True)
class Tool:
    name: str
    callable: object
    auth_kind: str = "none"
    rate_scope: str = "api.steampowered.com"
    read_only: bool = True
    capability_status: str = "implemented"
    required: tuple = ()
    optional: tuple = ()


class Registry:
    def __init__(self, executor):
        self.executor = executor
        self.tools, self.cache, self.inflight = {}, {}, {}

    def register(self, tool):
        if tool.name in self.tools or not tool.read_only or tool.auth_kind not in {"none", "user_key", "session_token"}:
            raise Failure("CONFIG_INVALID", "Duplicate or unsafe tool registration", api=tool.name)
        self.tools[tool.name] = tool

    async def call(self, name, params=None, context=None):
        params, context = dict(params or {}), dict(context or {})
        context.setdefault("appid", params.get("appid"))
        context.setdefault("subject_steamid", params.get("steamid"))
        try:
            tool = self.tools.get(name)
            if tool is None:
                raise Failure("TOOL_NOT_FOUND", "Tool is not registered", api=name)
            if tool.capability_status == "disabled":
                raise Failure("DATA_UNAVAILABLE", "Tool is disabled", api=name)
            if set(params) - set(tool.required + tool.optional) or set(tool.required) - params.keys():
                raise Failure("CONFIG_INVALID", "Invalid tool parameter names", api=name)
            if "appid" in params and not valid_appid(params["appid"]):
                raise Failure("CONFIG_INVALID", "AppID must be a positive uint32", api=name)
            if "steamid" in params and not valid_steamid(params["steamid"]):
                raise Failure("CONFIG_INVALID", "SteamID64 required", api=name)
            for key in ("language", "country", "query", "vanity", "family_groupid"):
                if key in params and (not isinstance(params[key], str) or not params[key].strip()):
                    raise Failure("CONFIG_INVALID", "Invalid parameter type: " + key, api=name)
            if "language" in params and not re.fullmatch(r"[a-zA-Z_-]{2,32}", params["language"]):
                raise Failure("CONFIG_INVALID", "Invalid language", api=name)
            if "country" in params and not re.fullmatch(r"[A-Za-z]{2}", params["country"]):
                raise Failure("CONFIG_INVALID", "Invalid country", api=name)
            if "include_family_licenses" in params and type(params["include_family_licenses"]) is not bool:
                raise Failure("CONFIG_INVALID", "include_family_licenses must be boolean", api=name)
            config = self.executor.config
            if (tool.auth_kind == "user_key" and not config.api_key) or (tool.auth_kind == "session_token" and not config.family_token):
                raise Failure("AUTH_REQUIRED", "Configure credentials locally for this source", api=name)
            if tool.auth_kind in self.executor.disabled_auth:
                raise Failure(self.executor.disabled_auth[tool.auth_kind], "Authentication source disabled for this run", api=name)
        except Failure as exc:
            return Result("unavailable", error=exc.info, source=name)
        key = (name, json.dumps(params, sort_keys=True, ensure_ascii=True, allow_nan=False))
        reused = key in self.cache or key in self.inflight
        if key in self.cache:
            result = deepcopy(self.cache[key])
        else:
            if key not in self.inflight:
                async def invoke():
                    try:
                        result = await tool.callable(self.executor, params, context)
                        if result.error:
                            result.error.update(api=name, appid=params.get("appid"), subject_steamid=params.get("steamid"))
                        return result
                    except Failure as exc:
                        if exc.code in {"INTERNAL_ERROR", "LOG_WRITE_FAILED"}:
                            raise
                        exc.info.update(api=name, appid=params.get("appid"), subject_steamid=params.get("steamid"))
                        return Result("unavailable", error=exc.info, source=name)
                self.inflight[key] = asyncio.create_task(invoke())
            task = self.inflight[key]
            try:
                result = deepcopy(await asyncio.shield(task))
                if result.state in {"ok", "not_applicable"}:
                    self.cache[key] = deepcopy(result)
            finally:
                if task.done():
                    self.inflight.pop(key, None)
        if reused:
            result.from_run_cache = True
            self.executor.event("run_cache_hit", module=__name__, api=name, **context)
        return result

    async def close(self):
        tasks = list(self.inflight.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.inflight.clear()


def build_registry(executor):
    from Ports import get_app_details, search_games
    registry = Registry(executor)
    registry.register(Tool("get_app_details", get_app_details.call, rate_scope="store.steampowered.com",
                           required=("appid", "language", "country")))
    registry.register(Tool("search_games", search_games.call, rate_scope="store.steampowered.com",
                           required=("query", "language", "country")))
    from Ports import (get_owned_games, get_recently_played_games, get_schema_for_game,
                       get_player_achievements, get_user_stats_for_game, get_player_summaries,
                       resolve_vanity_url, get_family_group_for_user, get_shared_library_apps)
    registry.register(Tool("get_owned_games", get_owned_games.call, "user_key", required=("steamid",), optional=("include_family_licenses",)))
    registry.register(Tool("get_recently_played_games", get_recently_played_games.call, "user_key", required=("steamid",)))
    registry.register(Tool("get_schema_for_game", get_schema_for_game.call, "user_key", required=("appid", "language")))
    registry.register(Tool("get_player_achievements", get_player_achievements.call, "user_key", required=("appid", "steamid", "language")))
    registry.register(Tool("get_user_stats_for_game", get_user_stats_for_game.call, "user_key", required=("appid", "steamid")))
    registry.register(Tool("get_player_summaries", get_player_summaries.call, "user_key", required=("steamid",)))
    registry.register(Tool("resolve_vanity_url", resolve_vanity_url.call, "user_key", required=("vanity",)))
    registry.register(Tool("get_family_group_for_user", get_family_group_for_user.call, "session_token", capability_status="experimental", required=("steamid",)))
    registry.register(Tool("get_shared_library_apps", get_shared_library_apps.call, "session_token", capability_status="experimental", required=("steamid", "family_groupid", "language")))
    from Ports import get_wishlist, get_wishlist_item_count
    registry.register(Tool("get_wishlist", get_wishlist.call, capability_status="experimental", required=("steamid",)))
    registry.register(Tool("get_wishlist_item_count", get_wishlist_item_count.call, capability_status="experimental", required=("steamid",)))
    return registry
