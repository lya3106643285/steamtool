import asyncio
from dataclasses import replace
import httpx
import pytest

from steamtool.config import Config
from steamtool.error_handler import Failure
from steamtool.Ports.registry import build_registry
from steamtool.Ports.request_executor import Executor
from steamtool.scripts.game import parse_target, run
from steamtool.scripts.persistence import new_run


@pytest.mark.parametrize("query,appid", [("292030", 292030), ("https://store.steampowered.com/app/292030/The_Witcher/", 292030), ("巫师3", None)])
def test_input(query, appid):
    assert parse_target(query) == appid


@pytest.mark.parametrize("query", ["https://store.steampowered.com/sub/123/", "https://store.steampowered.com/bundle/1/", "https://evil.com/app/1/", "0"])
def test_unsupported(query):
    with pytest.raises(Failure):
        parse_target(query)


def test_public_and_ambiguity():
    async def check():
        config = replace(Config(), store_rps=10000)
        def response(request):
            assert "x-webapi-key" not in request.headers and "access_token" not in request.url.params
            if "storesearch" in request.url.path:
                return httpx.Response(200, json={"items": [{"id": 1, "name": "Same"}, {"id": 2, "name": "Same"}], "total": 2})
            assert request.url.params["l"] == "schinese"
            return httpx.Response(200, json={"1": {"success": True, "data": {"steam_appid": 1, "name": "游戏", "type": "game"}}})
        executor = Executor(config, transport=httpx.MockTransport(response))
        registry = build_registry(executor)
        _, document = new_run("game", config)
        await run(registry, config, document, None, appid=1)
        assert document["data"]["items"][0]["ownership"]["owned_by_self"] is None
        assert document["id_map"]["1"]["canonical_name"] == "游戏"
        _, ambiguous = new_run("game", config)
        await run(registry, config, ambiguous, None, query="Same")
        assert ambiguous["status"] == "needs_selection"
        assert ambiguous["name_index"]["same"] == [1, 2]
        await executor.close()
    asyncio.run(check())
