import asyncio
from dataclasses import replace
import json

import httpx
import pytest

from steamtool.config import Config, load_config
from steamtool.error_handler import Failure
from steamtool.Ports.registry import Registry, Tool
from steamtool.Ports.request_executor import Executor, RequestSpec
from steamtool.scripts.persistence import new_run, save
from steamtool.scripts.runtime_debug import Redactor, Runtime


def test_config(tmp_path):
    (tmp_path / ".env").write_text("STEAM_API_KEY=local\nSTEAM_LANGUAGE=english\n")
    c = load_config(tmp_path, {"STEAM_API_KEY": "environment"})
    assert c.api_key == "environment" and "environment" not in repr(c)
    assert c.language == "english"
    for key, value in (("STEAM_MAX_ATTEMPTS", "0"), ("STEAM_STORE_RPS", "nan"), ("STEAM_ID", "bad")):
        with pytest.raises(Failure, match=key):
            load_config(tmp_path, {key: value})


def test_registry_executor_log_json(tmp_path):
    async def run():
        config = replace(Config(), output_dir=tmp_path)
        stem, document = new_run("game", config)
        runtime = Runtime(tmp_path / (stem + ".runtime.jsonl"), document["meta"]["run_id"], "game")
        executor = Executor(config, runtime.event, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"value": 7})))
        registry = Registry(executor)
        async def virtual(ex, params, context):
            return await ex.execute(RequestSpec("virtual", "https://api.steampowered.com/test"), lambda b: b, context)
        registry.register(Tool("virtual", virtual))
        with pytest.raises(Failure):
            registry.register(Tool("virtual", virtual))
        missing = await registry.call("missing")
        assert missing.error["code"] == "TOOL_NOT_FOUND"
        one, two = await asyncio.gather(registry.call("virtual"), registry.call("virtual"))
        assert one.data == two.data == {"value": 7}
        assert two.from_run_cache and runtime.counts["request_started"] == 1
        document["data"]["items"] = [one.as_dict()]
        path = save(document, tmp_path / (stem + ".json"), runtime.redact)
        assert json.loads(path.read_text())["data"]["items"][0]["attempts"] == 1
        runtime.close()
        assert all(json.loads(line)["run_id"] == document["meta"]["run_id"] for line in (tmp_path / (stem + ".runtime.jsonl")).read_text().splitlines())
        await registry.close()
        await executor.close()
    asyncio.run(run())


def test_redaction_and_atomic_write(tmp_path):
    redact = Redactor(["sensitive-value"])
    data = {"nested": {"access_token": "another"}, "error": "https://u:p@host/?key=abcd&x=sensitive-value", "auth": "Bearer abc.def.ghi"}
    rendered = json.dumps(redact(data))
    assert all(s not in rendered for s in ("another", "u:p", "abcd", "sensitive-value", "abc.def.ghi"))
    file = tmp_path / "test.json"
    save({"name": "中文"}, file)
    with pytest.raises(Failure):
        save({"name": "replacement"}, file)
    assert json.loads(file.read_text()) == {"name": "中文"}
    with pytest.raises(Failure):
        save({"bad": float("nan")}, tmp_path / "bad.json")
    assert not (tmp_path / "bad.json").exists()
