"""Synthetic fixtures only; no network and no real account inventory."""
import asyncio
from dataclasses import replace
import json

import httpx
import pytest

from steamtool.config import Config
from steamtool.Ports.registry import build_registry
from steamtool.Ports.request_executor import Executor, Result
from steamtool.scripts import library, wishlist, game
from steamtool.scripts.persistence import new_run
from tests.test_accounts import ME, OTHER, token


class Fixtures:
    def __init__(self):
        self.paths = []
        self.wishes = [{"appid": 1, "priority": 1}, {"appid": 99, "date_added": 123}]
        self.count = 2

    def __call__(self, req):
        self.paths.append(req.url.path)
        path = req.url.path
        params = json.loads(req.url.params["input_json"]) if "input_json" in req.url.params else dict(req.url.params)
        if "GetOwnedGames" in path:
            rows = [{"appid": 1, "name": "Owned", "playtime_forever": 0}, {"appid": 2, "name": "Both", "playtime_forever": 50, "playtime_windows_forever": 40, "playtime_linux_forever": 30}]
            if params["include_family_licenses"]:
                rows += [{"appid": 3, "name": "Borrowed", "family_shared": True, "playtime_forever": 10}]
            body = {"response": {"game_count": len(rows), "games": rows}}
        elif "GetRecentlyPlayedGames" in path:
            body = {"response": {"total_count": 0}}
        elif "GetFamilyGroupForUser" in path:
            body = {"response": {"family_groupid": "123", "family_group": {"members": [{"steamid": ME}, {"steamid": OTHER}]}}}
        elif "GetSharedLibraryApps" in path:
            body = {"response": {"owner_steamid": ME, "apps": [
                {"appid": 2, "name": "Both", "owner_steamids": [ME, OTHER], "exclude_reason": 0},
                {"appid": 4, "name": "Unplayed", "owner_steamids": [OTHER], "exclude_reason": 0},
                {"appid": 5, "name": "Unknown exclusion", "owner_steamids": [OTHER], "exclude_reason": 999}]}}
        elif "GetWishlistItemCount" in path:
            body = {"response": {"count": self.count}}
        elif "GetWishlist" in path:
            body = {"response": {"items": self.wishes}}
        elif "GetSchemaForGame" in path:
            body = {"game": {"availableGameStats": {"achievements": [{"name": "ACH", "displayName": "成就"}]}}}
        elif "GetPlayerAchievements" in path:
            assert params["steamid"] == ME
            body = {"playerstats": {"success": True, "achievements": [{"apiname": "ACH", "achieved": 1, "unlocktime": 123}]}}
        elif "GetUserStatsForGame" in path:
            assert params["steamid"] == ME
            body = {"playerstats": {"steamID": ME, "stats": [{"name": "score", "value": 7}]}}
        elif "appdetails" in path:
            appid = int(params["appids"])
            body = {str(appid): {"success": False}} if appid == 99 else {str(appid): {"success": True, "data": {"steam_appid": appid, "name": "App " + str(appid), "type": "game"}}}
        else:
            raise AssertionError("Unexpected fixture route: " + path)
        return httpx.Response(200, json=body)


def execute(feature, fixture, **kwargs):
    async def check():
        config = replace(Config(), steamid=ME, api_key="synthetic", family_token=token(), webapi_rps=100000, store_rps=100000, family_rps=100000)
        ex = Executor(config, transport=httpx.MockTransport(fixture))
        registry = build_registry(ex)
        _, document = new_run(feature, config)
        try:
            await {"library": library.run, "wishlist": wishlist.run, "game": game.run}[feature](registry, config, document, None, **kwargs)
        finally:
            await registry.close()
            await ex.close()
        return document
    return asyncio.run(check())


def test_library_semantics():
    document = execute("library", Fixtures())
    items = {i["appid"]: i for i in document["data"]["items"]}
    assert set(items) == {1, 2, 3, 4, 5}
    assert items[1]["playtime"]["total_minutes"] == 0
    assert items[2]["playtime"]["total_minutes"] == 50
    assert items[2]["playtime"]["last_2weeks_minutes"] is None
    assert items[2]["ownership"]["owned_by_self"] is True
    assert items[2]["ownership"]["owned_by_other_family_members"] is True
    assert items[3]["ownership"]["owned_by_self"] is False
    assert items[3]["playtime"]["subject_steamid"] == ME
    assert items[4]["playtime"]["total_minutes"] is None
    assert items[4]["ownership"]["available_via_family"] is True
    assert items[5]["ownership"]["available_via_family"] is None
    assert items[1]["achievements"]["completion_ratio"] == 1
    assert document["status"] == "partial"  # Experimental family completeness is unknown.
    assert set(document["id_map"]) == {str(i) for i in items}
    assert all(isinstance(v, list) for v in document["name_index"].values())


def test_wishlist_preserves_missing_details_and_duplicates():
    fixture = Fixtures()
    fixture.wishes.append({"appid": 99, "date_added": 456})
    fixture.count = 3
    document = execute("wishlist", fixture)
    assert [i["appid"] for i in document["data"]["items"]] == [1, 99]
    assert document["coverage"]["wishlist"]["complete"] is False
    assert len(document["data"]["items"][1]["wishlist"]["entries"]) == 2
    assert document["data"]["items"][1]["store"]["state"] == "unavailable"
    assert document["id_map"]["99"]["canonical_name"] is None


def test_explicit_empty_wishlist():
    fixture = Fixtures()
    fixture.wishes, fixture.count = [], 0
    document = execute("wishlist", fixture)
    assert document["status"] == "ok" and document["data"]["items"] == []
    assert document["coverage"]["wishlist"]["complete"] is True
    assert len(fixture.paths) == 2


def test_single_game_does_not_enrich_whole_library():
    fixture = Fixtures()
    document = execute("game", fixture, appid=2)
    assert len(document["data"]["items"]) == 1
    assert sum("appdetails" in p for p in fixture.paths) == 1
    assert not any("GetSchemaForGame" in p for p in fixture.paths)


@pytest.mark.parametrize("body", [{"response": {}}, {"response": {"success": False}}, {"response": {"items": "bad"}}])
def test_wishlist_200_is_not_automatically_empty(body):
    async def check():
        ex = Executor(Config(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
        result = await build_registry(ex).call("get_wishlist", {"steamid": ME})
        assert result.state == "unavailable" and result.data == {}
        await ex.close()
    asyncio.run(check())


def test_achievement_unknown_does_not_become_zero():
    schema = Result("ok", {"achievements": [{"name": "A"}], "complete": True})
    player = Result("unavailable")
    merged = library.merge_achievements(schema, player, ME)
    assert merged["unlocked"] is None and merged["completion_ratio"] is None
    assert merged["items"][0]["unlocked"] is None
