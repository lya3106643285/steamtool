import argparse
import base64
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time

import httpx
import pytest

from steamtool.config import Config
from steamtool.error_handler import Failure
from steamtool import main
from steamtool.Ports.get_shared_library_apps import MAX_APPS
from steamtool.Ports.registry import build_registry
from steamtool.Ports.request_executor import Executor, RequestSpec, Result
from steamtool.scripts import game, library
from steamtool.scripts.persistence import new_run, save
from steamtool.scripts.runtime_debug import Redactor, Runtime
from tests.test_accounts import ME, OTHER, token
from tests.test_executor import FakeClock
from tests.test_workflows import Fixtures


@pytest.mark.parametrize('reason,available', [(0, True), (1, False), (4, False), (30, False), (5, None), (14, None), (999, None)])
def test_known_and_unknown_family_exclusions(reason, available):
    item = game.record(1, ME)
    collections = {'owned': Result('ok', {'items': [], 'complete': True}),
                   'family': Result('ok', {'items': [{'appid': 1, 'owner_steamids': [OTHER], 'exclude_reason': reason}]})}
    library.merge_ownership(item, collections, ME)
    assert item['ownership']['owned_by_other_family_members'] is True
    assert item['ownership']['available_via_family'] is available


def test_owned_library_without_family_token():
    async def check():
        fixture = Fixtures()
        config = replace(Config(), steamid=ME, api_key='fixture', webapi_rps=100000, store_rps=100000)
        executor = Executor(config, transport=httpx.MockTransport(fixture))
        _, document = new_run('library', config)
        await library.run(build_registry(executor), config, document, None)
        assert document['status'] == 'partial'
        assert document['data']['items'][0]['ownership']['owned_by_self'] is True
        assert document['data']['items'][0]['ownership']['owned_by_other_family_members'] is None
        assert not any('FamilyGroups' in p for p in fixture.paths)
        await executor.close()
    asyncio.run(check())


def test_family_truncation_and_expired_token():
    async def check():
        rows = [{'appid': i + 1, 'owner_steamids': [OTHER]} for i in range(MAX_APPS)]
        calls = []
        def transport(req):
            calls.append(req)
            return httpx.Response(200, json={'response': {'owner_steamid': ME, 'apps': rows}})
        config = replace(Config(), steamid=ME, family_token=token())
        executor = Executor(config, transport=httpx.MockTransport(transport))
        registry = build_registry(executor)
        result = await registry.call('get_shared_library_apps', {'steamid': ME, 'family_groupid': '123', 'language': 'english'})
        assert result.data['potentially_truncated'] is True and result.data['complete'] is False
        executor.config = replace(config, family_token='opaque')
        invalid = await registry.call('get_family_group_for_user', {'steamid': ME})
        assert invalid.state == 'unavailable' and len(calls) == 1
        expired = 'fixture.' + base64.urlsafe_b64encode(json.dumps({'sub': ME, 'exp': 0}).encode()).decode().rstrip('=') + '.fixture'
        executor.config = replace(config, family_token=expired)
        expired_result = await registry.call('get_family_group_for_user', {'steamid': ME})
        assert expired_result.error['code'] == 'AUTH_EXPIRED' and len(calls) == 1
        await executor.close()
    asyncio.run(check())


def test_protocol_application_failure_with_empty_items():
    async def check():
        executor = Executor(Config(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'response': {'success': False, 'items': []}})))
        result = await build_registry(executor).call('get_wishlist', {'steamid': ME})
        assert result.state == 'unavailable' and result.attempts == 1
        await executor.close()
    asyncio.run(check())


def test_first_queue_is_outside_logical_budget():
    async def check():
        clock = FakeClock()
        executor = Executor(replace(Config(), deadline=1), transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), clock=clock, sleep=clock.sleep)
        executor.next_send['api.steampowered.com'] = 200
        result = await executor.execute(RequestSpec('fixture', 'https://api.steampowered.com/fixture'), lambda b: b)
        assert result.state == 'ok' and result.attempts == 1 and sum(clock.waits) == 100
        await executor.close()
    asyncio.run(check())


def test_midrun_log_failure_stops_dispatch(tmp_path, monkeypatch):
    class Broken(Runtime):
        def event(self, event, **fields):
            if event == 'request_started':
                self.failed = True
                raise Failure('LOG_WRITE_FAILED', 'synthetic', source='runtime')
            super().event(event, **fields)
    monkeypatch.setattr(main, 'Runtime', Broken)
    calls = []
    args = argparse.Namespace(feature='game', query=None, appid=1)
    config = replace(Config(), root=tmp_path, output_dir=tmp_path)
    result = asyncio.run(main.execute(args, config, transport=httpx.MockTransport(lambda r: calls.append(r))))
    assert result == 1 and calls == []
    document = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert document['errors'][0]['code'] == 'LOG_WRITE_FAILED'


def test_unexpected_workflow_error_is_terminal_and_redacted(tmp_path, monkeypatch):
    async def broken(registry, config, document, runtime, **kwargs):
        document['data']['items'].append(game.record(1, ME, 'Saved'))
        raise RuntimeError('secret-test-value')
    monkeypatch.setattr(game, 'run', broken)
    config = replace(Config(), root=tmp_path, output_dir=tmp_path, api_key='secret-test-value')
    args = argparse.Namespace(feature='game', query=None, appid=1)
    assert asyncio.run(main.execute(args, config)) == 1
    document = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert document['status'] == 'failed' and document['errors'][0]['code'] == 'INTERNAL_ERROR'
    assert document['data']['items'][0]['name'] == 'Saved'
    assert all('secret-test-value' not in p.read_text() for p in tmp_path.iterdir())


def test_bad_output_directory_never_reports_success(tmp_path, capsys):
    path = tmp_path / 'not-directory'
    path.write_text('old')
    config = replace(Config(), root=tmp_path, output_dir=path)
    args = argparse.Namespace(feature='game', query=None, appid=1)
    assert asyncio.run(main.execute(args, config)) == 1
    output = capsys.readouterr()
    assert 'export_saved' not in output.err and output.out == '' and path.read_text() == 'old'


def test_log_context_and_separate_initialization(tmp_path):
    async def check():
        config = replace(Config(), store_rps=100000)
        for run in ('one', 'two'):
            runtime = Runtime(tmp_path / f'{run}.jsonl', run, 'game')
            def transport(request):
                appid = int(request.url.params['appids'])
                return httpx.Response(200, json={str(appid): {'success': True, 'data': {'steam_appid': appid, 'name': 'Fixture'}}})
            executor = Executor(config, runtime.event, transport=httpx.MockTransport(transport))
            registry = build_registry(executor)
            await asyncio.gather(*(registry.call('get_app_details', {'appid': i, 'language': 'english', 'country': 'US'}, {'task_id': f'app-{i}'}) for i in range(1, 5)))
            await executor.close()
            runtime.close()
            events = [json.loads(line) for line in (tmp_path / f'{run}.jsonl').read_text().splitlines()]
            starts = [e for e in events if e['event'] == 'request_started']
            assert len(starts) == 4 and all(e['task_id'] == f"app-{e['appid']}" and e['run_id'] == run for e in starts)
    asyncio.run(check())


def test_same_time_unicode_and_redacted_outputs(tmp_path):
    config = replace(Config(), root=tmp_path, output_dir=tmp_path)
    one, first = new_run('game', config)
    two, second = new_run('game', config)
    assert one != two and first['meta']['run_id'] != second['meta']['run_id']
    first['data']['fixture'] = {'name': '中文', 'nested': {'x-webapi-key': 'hidden'}, 'proxy_message': 'socks5://user:password@local:80', 'url': 'https://h/?access_token=private'}
    save(first, tmp_path / (one + '.json'), Redactor())
    text = (tmp_path / (one + '.json')).read_text()
    assert '中文' in text and all(v not in text for v in ('hidden', 'user:password', '=private'))


def test_player_cache_separates_subjects_and_dlc_mapping():
    async def check():
        seen = []
        def respond(req):
            seen.append(req)
            if 'GetUserStatsForGame' in req.url.path:
                return httpx.Response(200, json={'playerstats': {'steamID': req.url.params['steamid'], 'stats': []}})
            return httpx.Response(200, json={'1': {'success': True, 'data': {'steam_appid': 1, 'name': 'Synthetic', 'dlc': [2, 3]}}})
        config = replace(Config(), api_key='synthetic', webapi_rps=100000, store_rps=100000)
        executor = Executor(config, transport=httpx.MockTransport(respond))
        registry = build_registry(executor)
        first, second = await asyncio.gather(*(registry.call('get_user_stats_for_game', {'appid': 1, 'steamid': s}) for s in (ME, OTHER)))
        assert first.data['subject_steamid'] == ME and second.data['subject_steamid'] == OTHER
        _, document = new_run('game', config)
        await game.run(registry, config, document, None, appid=1)
        assert set(document['id_map']) == {'1', '2', '3'}
        assert len(seen) == 3
        assert 'x-webapi-key' not in seen[-1].headers
        await executor.close()
    asyncio.run(check())


def test_summary_vanity_and_parameter_contracts():
    async def check():
        def respond(req):
            if 'GetPlayerSummaries' in req.url.path:
                assert req.url.params['steamids'] == ME
                return httpx.Response(200, json={'response': {'players': [{'steamid': ME, 'personaname': 'Synthetic'}]}})
            assert req.url.params['vanityurl'] == 'synthetic'
            return httpx.Response(200, json={'response': {'success': 1, 'steamid': ME}})
        executor = Executor(replace(Config(), api_key='fixture', webapi_rps=100000), transport=httpx.MockTransport(respond))
        registry = build_registry(executor)
        summary = await registry.call('get_player_summaries', {'steamid': ME})
        vanity = await registry.call('resolve_vanity_url', {'vanity': 'synthetic'})
        assert summary.state == 'ok' and vanity.data['steamid'] == ME
        for params in ({'appid': True, 'language': 'english', 'country': 'US'}, {'appid': 1, 'language': [], 'country': 'US'}, {'appid': 1, 'language': 'english', 'country': 'US', 'unexpected': 1}):
            invalid = await registry.call('get_app_details', params)
            assert invalid.error['code'] == 'CONFIG_INVALID' and invalid.attempts == 0
        await executor.close()
    asyncio.run(check())
