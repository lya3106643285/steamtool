"""Exercise the public runner, serializers and actual HTTP scheduling without network."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path

import httpx
import pytest

from steamtool import main
from steamtool.config import Config
from steamtool.error_handler import Failure
from steamtool.scripts.runtime_debug import Runtime
from tests.test_accounts import ME, token
from tests.test_workflows import Fixtures


class ContractFixtures(Fixtures):
    names = {'Hades': 1, 'Noita': 3, 'Hello, World': 2}

    def __init__(self, *, no_system=False, detail_failure=False):
        super().__init__()
        self.no_system, self.detail_failure = no_system, detail_failure

    def __call__(self, req):
        path = req.url.path
        if 'GetUserStatsForGame' in path:
            raise AssertionError('Stats are outside the formal Feature contract')
        if 'storesearch' in path:
            self.paths.append(path)
            name = req.url.params['term']
            appid = self.names.get(name)
            items = [] if appid is None else [{'id': appid, 'name': name}]
            return httpx.Response(200, json={'items': items})
        if 'appdetails' in path and req.url.params['appids'] != '99':
            self.paths.append(path)
            appid = int(req.url.params['appids'])
            return httpx.Response(200, json={str(appid): {'success': True, 'data': {
                'steam_appid': appid, 'name': 'App ' + str(appid), 'type': 'game', 'is_free': False,
                'release_date': {'coming_soon': False}, 'platforms': {'windows': True, 'mac': False},
                'price_overview': {'currency': 'CNY', 'initial': 1000, 'final': 500}}}})
        if self.no_system and 'GetSchemaForGame' in path:
            self.paths.append(path)
            return httpx.Response(200, json={'game': {'availableGameStats': {'achievements': []}}})
        if self.detail_failure and 'GetPlayerAchievements' in path:
            self.paths.append(path)
            return httpx.Response(503)
        return super().__call__(req)


def run_feature(tmp_path, feature, fixture, *, detail=False, query='"Hades"', **overrides):
    config = replace(Config(), root=tmp_path, output_dir=tmp_path, steamid=ME, api_key='synthetic-key',
                     family_token=token(), webapi_rps=1e9, store_rps=1e9, family_rps=1e9,
                     max_attempts=1, **overrides)
    args = argparse.Namespace(feature=feature, query=query, achievements=detail, ranking_limit=3)
    code = asyncio.run(main.execute(args, config, transport=httpx.MockTransport(fixture)))
    files = list(tmp_path.glob('*.json'))
    assert len(files) == 1 and '_北京时间_' in files[0].name
    document = json.loads(files[0].read_text())
    assert document['run']['started_at'].endswith('+08:00')
    assert document['run']['finished_at'].endswith('+08:00')
    assert 'synthetic-key' not in files[0].read_text()
    return code, document


@pytest.mark.parametrize('feature', ['games', 'library'])
def test_default_requests_summary_evidence_but_no_full_detail(tmp_path, feature):
    fixture = ContractFixtures()
    code, doc = run_feature(tmp_path, feature, fixture)
    assert code == 2 and doc['run']['status'] == 'partial'
    assert not any('GetPlayerAchievements' in path for path in fixture.paths)
    assert all(item['achievements']['items'] is None for item in doc['items'])
    assert all(item['achievements']['total'] == 1 for item in doc['items'])
    assert all(item['achievements']['unlocked'] is None for item in doc['items'])
    assert all(item['achievements']['meta']['state'] == 'partial' for item in doc['items'])
    assert not any(error['code'].startswith('QUERY_') for error in doc['errors'])
    if feature == 'games':
        assert list(doc) == ['schema_version', 'run', 'summary', 'errors', 'items']
        assert set(doc['items'][0]) == {'status', 'identity', 'market', 'ownership', 'wishlist', 'playtime', 'achievements', 'price', 'bundles'}
        platform = doc['items'][0]['playtime']['platform']
        assert platform['mac'] == -1 and platform['deck'] is None
    else:
        assert not any('appdetails' in path for path in fixture.paths)
        assert set(doc['items'][0]) == {'status', 'identity', 'ownership', 'playtime', 'achievements'}
        assert doc['summary']['played_count'] == 2 and doc['summary']['unplayed_count'] == 1
        assert doc['summary']['playtime_unknown_count'] == 2
        assert doc['summary']['played_ratio'] == 2 / 3
        assert doc['summary']['total_playtime'] == 60 and doc['summary']['ranking_limit'] == 3
        assert doc['coverage']['playtime'] == dict(state='partial', complete=False, known_count=3, missing_count=2)
        assert doc['coverage']['achievements']['missing_count'] == 5


def test_zero_platform_time_requires_confirmed_support(tmp_path):
    fixture = ContractFixtures()
    def response(request):
        if 'GetOwnedGames' in request.url.path:
            return httpx.Response(200, json={'response': {'game_count': 1, 'games': [
                {'appid': 1, 'name': 'Hades', 'playtime_forever': 0,
                 'playtime_windows_forever': 0, 'playtime_mac_forever': 0}]}})
        return fixture(request)
    _, doc = run_feature(tmp_path, 'games', response)
    assert doc['items'][0]['playtime']['platform']['windows'] == 0
    assert doc['items'][0]['playtime']['platform']['mac'] == -1
    directory = tmp_path / 'library'
    directory.mkdir()
    _, library = run_feature(directory, 'library', response)
    item = next(item for item in library['items'] if item['identity']['appid'] == 1)
    assert item['playtime']['total'] == 0
    assert item['playtime']['platform']['windows'] is None  # Support was never established.


@pytest.mark.parametrize('feature', ['games', 'library'])
def test_explicit_detail_fetches_player_entries(tmp_path, feature):
    fixture = ContractFixtures()
    _, doc = run_feature(tmp_path, feature, fixture, detail=True)
    assert sum('GetPlayerAchievements' in path for path in fixture.paths) == len(doc['items'])
    assert all(item['achievements']['unlocked'] == 1 and item['achievements']['completion_ratio'] == 1 for item in doc['items'])
    entry = doc['items'][0]['achievements']['items'][0]
    assert entry == dict(apiname='ACH', display_name='成就', description=None, unlocked=True, unlock_time=123)
    assert not any('GetUserStatsForGame' in path for path in fixture.paths)


@pytest.mark.parametrize('feature', ['games', 'library'])
@pytest.mark.parametrize('detail', [False, True])
def test_confirmed_no_system_uses_minus_one_not_an_empty_detail_list(tmp_path, feature, detail):
    fixture = ContractFixtures(no_system=True)
    _, doc = run_feature(tmp_path, feature, fixture, detail=detail)
    for item in doc['items']:
        achieved = item['achievements']
        assert achieved['total'] == achieved['unlocked'] == -1
        assert achieved['completion_ratio'] is achieved['items'] is None
        assert achieved['meta']['state'] == 'not_applicable'
    assert not any('GetPlayerAchievements' in path for path in fixture.paths)
    if feature == 'library':
        assert doc['coverage']['achievements']['complete'] is True


@pytest.mark.parametrize('feature', ['games', 'library'])
def test_detail_failure_preserves_record_and_error_reference(tmp_path, feature):
    fixture = ContractFixtures(detail_failure=True)
    code, doc = run_feature(tmp_path, feature, fixture, detail=True)
    assert code == 2 and doc['items']
    errors = {error['error_id']: error for error in doc['errors']}
    for item in doc['items']:
        achieved = item['achievements']
        assert achieved['total'] == 1 and achieved['items'] is None
        assert achieved['meta']['state'] == 'unavailable'
        assert errors[achieved['meta']['error_id']]['code'] == 'UPSTREAM_UNAVAILABLE'
        assert item['status'] == 'partial'
    assert len(errors) == len(doc['errors'])


def test_wishlist_shape_price_coverage_and_missing_store_record(tmp_path):
    fixture = ContractFixtures()
    code, doc = run_feature(tmp_path, 'wishlist', fixture)
    assert code == 2 and list(doc) == ['schema_version', 'run', 'summary', 'coverage', 'errors', 'items']
    assert set(doc['coverage']) == {'wishlist', 'market', 'ownership', 'price', 'bundles'}
    assert [item['identity']['appid'] for item in doc['items']] == [1, 99]
    for item in doc['items']:
        assert set(item) == {'status', 'identity', 'market', 'ownership', 'wishlist', 'price', 'bundles'}
        assert item['bundles']['items'] is None and item['bundles']['meta']['state'] == 'unavailable'
    assert [item['appid'] for item in doc['summary']['price_ranking']] == [1, 99]
    assert doc['coverage']['price'] == dict(state='partial', complete=False, known_count=1, missing_count=1)
    assert doc['coverage']['wishlist']['complete'] is True
    assert not any('GetSchemaForGame' in path or 'GetPlayerAchievements' in path for path in fixture.paths)


def test_empty_wishlist_is_confirmed_complete_without_extra_requests(tmp_path):
    fixture = ContractFixtures()
    fixture.wishes, fixture.count = [], 0
    code, doc = run_feature(tmp_path, 'wishlist', fixture)
    assert code == 0 and doc['run']['status'] == 'ok' and doc['items'] == []
    assert doc['summary'] == dict(total_count=0, price_ranking=[])
    assert len(fixture.paths) == 2


def test_multiple_resolved_names_share_collections_and_failures_are_business_errors(tmp_path):
    fixture = ContractFixtures()
    _, doc = run_feature(tmp_path, 'games', fixture, query='"Hades","Hello, World","Missing"')
    assert len(doc['items']) == 2
    assert doc['summary'] == dict(game_count=2, ok_count=0, partial_count=2, failed_count=0)
    assert any(error['code'] == 'GAME_NOT_FOUND' for error in doc['errors'])
    assert sum('GetFamilyGroupForUser' in path for path in fixture.paths) == 1
    assert sum('GetWishlist/v' in path for path in fixture.paths) == 1


def test_unresolved_name_has_no_invented_appid(tmp_path):
    code, doc = run_feature(tmp_path, 'games', ContractFixtures(), query='"Missing"')
    assert code == 1 and doc['run']['status'] == 'failed' and doc['items'] == []
    assert doc['errors'][0]['code'] == 'GAME_NOT_FOUND'


def test_parser_error_never_starts_run_or_requests(tmp_path, capsys):
    fixture = ContractFixtures()
    config = replace(Config(), root=tmp_path, output_dir=tmp_path)
    args = argparse.Namespace(feature='games', query='"Hades",Noita,"Outer Wilds"')
    assert asyncio.run(main.execute(args, config, transport=httpx.MockTransport(fixture))) == 2
    assert not list(tmp_path.iterdir()) and fixture.paths == []
    assert '第 2 项' in capsys.readouterr().err


def test_cancelled_library_keeps_collection_records_in_formal_output(tmp_path):
    async def check():
        stop = asyncio.Event()
        fixture = ContractFixtures()
        async def response(request):
            if 'GetSchemaForGame' in request.url.path:
                stop.set()
                await asyncio.sleep(30)
            return fixture(request)
        config = replace(Config(), root=tmp_path, output_dir=tmp_path, steamid=ME, api_key='synthetic',
                         family_token=token(), webapi_rps=1e9, store_rps=1e9, family_rps=1e9, stop_grace=.01)
        args = argparse.Namespace(feature='library', achievements=False, ranking_limit=2)
        code = await asyncio.wait_for(main.execute(args, config, stop, transport=httpx.MockTransport(response)), 2)
        doc = json.loads(next(tmp_path.glob('*.json')).read_text())
        assert code == 130 and doc['run']['status'] == 'cancelled'
        assert {item['identity']['appid'] for item in doc['items']} == {1, 2, 3, 4, 5}
    asyncio.run(check())


def test_late_log_failure_amends_same_formal_run(tmp_path, monkeypatch):
    class BreakOnExport(Runtime):
        def event(self, event, **kwargs):
            if event == 'export_saved':
                self.failed = True
                raise Failure('LOG_WRITE_FAILED', 'synthetic late log failure', source='runtime')
            return super().event(event, **kwargs)
    monkeypatch.setattr(main, 'Runtime', BreakOnExport)
    code, doc = run_feature(tmp_path, 'games', ContractFixtures())
    assert code == 1 and doc['run']['status'] == 'failed'
    assert doc['errors'][-1]['code'] == 'LOG_WRITE_FAILED'
    assert len(list(tmp_path.glob('*.json'))) == 1


def test_parser_declares_detail_switch_and_ranking_override():
    assert main.parser().parse_args(['games', '--achievements']).achievements
    assert main.parser().parse_args(['library', '--achievements', '--ranking-limit', '0']).ranking_limit == 0
    with pytest.raises(SystemExit):
        main.parser().parse_args(['games', '--appid', '1'])


def test_missing_player_data_cannot_negate_confirmed_schema(tmp_path):
    fixture = ContractFixtures()
    def response(request):
        if 'GetPlayerAchievements' in request.url.path:
            return httpx.Response(400, json={'playerstats': {'success': False, 'error': 'Requested app has no stats'}})
        return fixture(request)
    code, doc = run_feature(tmp_path, 'games', response, detail=True)
    achieved = doc['items'][0]['achievements']
    assert code == 2 and achieved['total'] == 1 and achieved['unlocked'] is None
    assert achieved['meta']['state'] == 'unavailable'
    assert any(error['error_id'] == achieved['meta']['error_id'] for error in doc['errors'])


def test_confirmed_self_owner_is_kept_without_a_family(tmp_path):
    fixture = ContractFixtures(no_system=True)
    def response(request):
        if 'GetFamilyGroupForUser' in request.url.path:
            return httpx.Response(200, json={'response': {'is_not_member_of_any_family_group': True}})
        return fixture(request)
    _, doc = run_feature(tmp_path, 'library', response)
    item = next(item for item in doc['items'] if item['identity']['appid'] == 1)
    assert item['ownership']['owned_by_self'] is True
    assert item['ownership']['owners'] == {ME: {'persona_name': None}}


def test_unnamed_owned_row_does_not_erase_known_family_name(tmp_path):
    fixture = ContractFixtures()
    def response(request):
        if 'GetOwnedGames' in request.url.path:
            return httpx.Response(200, json={'response': {'game_count': 1, 'games': [{'appid': 2, 'playtime_forever': 0}]}})
        return fixture(request)
    _, doc = run_feature(tmp_path, 'library', response)
    item = next(item for item in doc['items'] if item['identity']['appid'] == 2)
    assert item['identity']['name'] == 'Both'
    assert item['identity']['meta']['source'] == 'get_shared_library_apps'


def test_unavailable_wishlist_cannot_claim_a_complete_empty_market_scope(tmp_path):
    fixture = ContractFixtures()
    def response(request):
        if 'GetWishlist/v' in request.url.path:
            return httpx.Response(503)
        return fixture(request)
    code, doc = run_feature(tmp_path, 'wishlist', response)
    assert code == 1 and doc['items'] == []
    assert doc['coverage']['wishlist']['state'] == 'unavailable'
    for name in ('market', 'ownership', 'price', 'bundles'):
        assert doc['coverage'][name] == dict(state='unavailable', complete=False, known_count=0, missing_count=0)
