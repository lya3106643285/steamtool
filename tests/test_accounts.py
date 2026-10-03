import asyncio
import base64
from dataclasses import replace
import json
import time
import httpx

from steamtool.config import Config
from steamtool.Ports.registry import build_registry
from steamtool.Ports.request_executor import Executor

ME = "76561198000000000"
OTHER = "76561198000000001"


def token(subject=ME):
    return "fixture." + base64.urlsafe_b64encode(json.dumps({"sub": subject, "exp": time.time() + 3600}).encode()).decode().rstrip("=") + ".fixture"


def test_accounts_and_encoding():
    async def check():
        seen = []
        def response(req):
            seen.append(req)
            assert req.headers["x-webapi-key"] == "fixture-key"
            assert "key" not in req.url.params
            if "GetOwnedGames" in req.url.path:
                fields = json.loads(req.url.params["input_json"])
                assert fields["steamid"] == ME and fields["include_played_free_games"] is True
                return httpx.Response(200, json={"response": {"game_count": 1, "games": [{"appid": 1, "playtime_forever": 0}]}})
            if "GetPlayerAchievements" in req.url.path:
                assert req.url.params["steamid"] == ME
                return httpx.Response(200, json={"playerstats": {"success": False, "error": "private"}})
            return httpx.Response(200, json={"game": {"availableGameStats": {"achievements": []}}})
        config = replace(Config(), steamid=ME, api_key="fixture-key", webapi_rps=10000)
        ex = Executor(config, transport=httpx.MockTransport(response))
        registry = build_registry(ex)
        owned = await registry.call("get_owned_games", {"steamid": ME, "include_family_licenses": False})
        assert owned.data["items"][0]["playtime_forever"] == 0 and owned.data["complete"]
        achievements = await registry.call("get_player_achievements", {"steamid": ME, "appid": 1, "language": "english"})
        assert achievements.state == "unavailable"
        schema = await registry.call("get_schema_for_game", {"appid": 1, "language": "english"})
        assert schema.data["achievements"] == []
        family = await registry.call("get_family_group_for_user", {"steamid": ME})
        assert family.error["code"] == "AUTH_REQUIRED" and len(seen) == 3
        await ex.close()
    asyncio.run(check())


def test_family_identity_and_list():
    async def check():
        seen = []
        def response(req):
            seen.append(req)
            assert "x-webapi-key" not in req.headers and "access_token" in req.url.params
            fields = json.loads(req.url.params["input_json"])
            assert fields["steamid"] == ME
            if "GetFamilyGroupForUser" in req.url.path:
                return httpx.Response(200, json={"response": {"family_groupid": "123", "family_group": {"members": [{"steamid": ME}, {"steamid": OTHER}]}}})
            assert fields["family_groupid"] == "123" and fields["include_excluded"] is True
            return httpx.Response(200, json={"response": {"owner_steamid": ME, "apps": [{"appid": 1, "owner_steamids": [OTHER], "exclude_reason": 999}]}})
        config = replace(Config(), steamid=ME, family_token=token(), webapi_rps=10000, family_rps=10000)
        ex = Executor(config, transport=httpx.MockTransport(response))
        registry = build_registry(ex)
        group = await registry.call("get_family_group_for_user", {"steamid": ME})
        assert group.state == "ok"
        apps = await registry.call("get_shared_library_apps", {"steamid": ME, "family_groupid": "123", "language": "english"})
        assert apps.data["items"][0]["exclude_reason"] == 999 and apps.data["complete"] is False
        mismatch = await registry.call("get_family_group_for_user", {"steamid": OTHER})
        assert mismatch.error["code"] == "ACCESS_DENIED" and len(seen) == 2
        await ex.close()
    asyncio.run(check())
