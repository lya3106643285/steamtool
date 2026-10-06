"""Formal contract invariants and pure derived logic; all data are synthetic."""
from dataclasses import fields
import json

import pytest

from schema.base import (Achievement, Achievements, Bundle, Bundles, GameIdentity, Market, Meta,
                         Ownership, Playtime, PlaytimePlatform, Price, PriceValue, Wishlist)
from schema.feature import (GameRecord, GamesResult, LibraryCoverage, LibraryRecord, LibraryResult,
                            Run, WishlistCoverage, WishlistRecord, WishlistResult, block_coverage,
                            games_summary, library_summary, record_status, run_status, wishlist_summary,
                            CollectionCoverage)
from schema.version import SCHEMA_VERSION
from steamtool.config import load_config


def library_item(appid=1, total=0, recent=None, **ownership):
    ident = GameIdentity(Meta('ok'), appid, 'Game ' + str(appid))
    owned = Ownership(Meta('ok'), **ownership)
    played = Playtime(Meta('ok'), total=total, last_2weeks=recent)
    achieved = Achievements(Meta('ok'), 2, 1, .5, None)
    return LibraryRecord(record_status(ident, owned, played, achieved), ident, owned, played, achieved)


def wishlist_item(appid, price):
    item = library_item(appid)
    return WishlistRecord('partial', item.identity, Market(Meta('partial'), 'CN'),
                          item.ownership, Wishlist(Meta('ok'), True), price, Bundles(Meta('unavailable')))


@pytest.mark.parametrize('state', ['ok', 'partial', 'unavailable', 'not_applicable', 'not_requested'])
def test_meta_states_and_multisource(state):
    assert Meta(state).to_dict()['state'] == state
    value = Meta(state, ['one', 'two'], {'one': '2026-10-07T10:00:00+08:00', 'two': None})
    assert value.to_dict()['fetched_at']['two'] is None
    assert Meta(state, 'one', ['time', None]).source == 'one'


@pytest.mark.parametrize('state', ['failed', 'data_unavailable', 'cancelled', 'success'])
def test_meta_does_not_leak_runtime_outcomes(state):
    with pytest.raises(ValueError):
        Meta(state)


def test_null_false_zero_and_negative_sentinels_are_distinct():
    assert Ownership(Meta('partial'), owned_by_self=False).to_dict()['owned_by_self'] is False
    assert Ownership(Meta('unavailable')).owned_by_self is None
    assert Playtime(Meta('ok'), total=0).total == 0
    assert Playtime(Meta('unavailable')).total is None
    platforms = PlaytimePlatform(0, -1, None, 123)
    assert platforms.to_dict() == dict(windows=0, mac=-1, linux=None, deck=123)
    assert Achievements(Meta('not_applicable'), -1, -1).items is None
    assert Achievements(Meta('ok'), 2, 0, 0).items is None
    assert Achievements(Meta('ok'), 2, 0, 0, []).items == []
    with pytest.raises(ValueError):
        Playtime(Meta('ok'), total=False)
    with pytest.raises(ValueError):
        Playtime(Meta('ok'), total=-1)
    with pytest.raises(ValueError):
        PlaytimePlatform(windows=-2)
    with pytest.raises(ValueError):
        Achievements(Meta('not_applicable'), -1, 0)


def test_string_dictionary_keys_and_bundle_price_provenance():
    steamid = '76561198000000000'
    owned = Ownership(Meta('ok'), owners={steamid: {'persona_name': None}})
    bundle = Bundle(1, None, PriceValue('paid', 'CNY', 100, 0), {'292030': None})
    decoded = json.loads(json.dumps(bundle.to_dict()))
    assert list(decoded['included_apps']) == ['292030']
    assert list(owned.to_dict()['owners']) == [steamid]
    assert 'meta' not in decoded['price']
    assert 'meta' in Price(Meta('ok'), 'paid', 'CNY', 100, 0).to_dict()
    assert Price(Meta('ok'), 'free').final is None
    with pytest.raises(ValueError):
        Ownership(Meta('ok'), owners={int(steamid): {'persona_name': None}})
    with pytest.raises(ValueError):
        Bundle(1, included_apps={292030: None})
    with pytest.raises(ValueError):
        PriceValue('free', 'CNY', 0, 0)
    with pytest.raises(TypeError):
        PriceValue(meta=Meta('ok'))


def test_record_and_result_field_compositions_and_order():
    library = library_item()
    wishlist = wishlist_item(1, Price(Meta('ok'), 'free'))
    game = GameRecord('ok', library.identity, wishlist.market, library.ownership, wishlist.wishlist,
                      library.playtime, library.achievements, wishlist.price, wishlist.bundles)
    run = Run('synthetic', 'games', '2026-10-07T10:00:00+08:00', None, None, 'ok')
    empty_collection = CollectionCoverage('ok', True, 0)
    block = block_coverage([])
    results = [
        GamesResult(run, games_summary([game]), [], [game]),
        LibraryResult(Run('synthetic', 'library', run.started_at, None, None, 'ok'),
                      library_summary([library], 10), LibraryCoverage(empty_collection, empty_collection, block, block), [], [library]),
        WishlistResult(Run('synthetic', 'wishlist', run.started_at, None, None, 'partial'),
                       wishlist_summary([wishlist]), WishlistCoverage(empty_collection, block, block, block, block), [], [wishlist]),
    ]
    assert [f.name for f in fields(GameRecord)] == ['status', 'identity', 'market', 'ownership', 'wishlist', 'playtime', 'achievements', 'price', 'bundles']
    assert [f.name for f in fields(LibraryRecord)] == ['status', 'identity', 'ownership', 'playtime', 'achievements']
    assert [f.name for f in fields(WishlistRecord)] == ['status', 'identity', 'market', 'ownership', 'wishlist', 'price', 'bundles']
    for result in results:
        data = json.loads(json.dumps(result.to_dict()))
        assert data['schema_version'] == SCHEMA_VERSION == '2.0.0'
        expected = ['schema_version', 'run', 'summary'] + ([] if isinstance(result, GamesResult) else ['coverage']) + ['errors', 'items']
        assert list(data) == expected


def test_library_summary_unknowns_ratios_independent_owners_and_top_n():
    items = [library_item(1, 20, 0, owned_by_self=True, owned_by_other_family_members=True),
             library_item(2, 0, 3, owned_by_self=True), library_item(3, None, None),
             library_item(4, 10, 8, available_via_family=True)]
    summary = library_summary(items, 3)
    assert (summary.played_count, summary.unplayed_count, summary.playtime_unknown_count) == (2, 1, 1)
    assert summary.played_ratio == 2 / 3 and summary.unplayed_ratio == 1 / 3
    assert (summary.self_owned_count, summary.family_owned_count, summary.family_available_count) == (2, 1, 1)
    assert summary.total_playtime == 30 and summary.playtime_unit == 'minutes'
    assert [item.appid for item in summary.top_total_playtime] == [1, 4, 2]
    assert [item.appid for item in summary.top_last_2weeks_playtime] == [4, 2, 1]
    assert summary.top_total_playtime[-1].playtime == 0
    assert library_summary(items, 1).ranking_limit == 1
    assert len(library_summary(items, 1).top_total_playtime) == 1
    assert library_summary(items, 0).top_total_playtime == []


def test_zero_denominator_and_equal_ranking_tie_break():
    summary = library_summary([library_item(1, None)], 10)
    assert summary.played_ratio is summary.unplayed_ratio is None
    assert summary.total_playtime == 0 and summary.top_total_playtime == []
    assert library_summary([], 10).played_ratio is None
    tied = library_summary([library_item(3, 10), library_item(1, 10)], 2)
    assert [item.appid for item in tied.top_total_playtime] == [1, 3]


def test_wishlist_prices_free_discounted_and_unknown():
    items = [wishlist_item(1, Price(Meta('ok'), 'paid', 'CNY', 100, 50)),
             wishlist_item(2, Price(Meta('partial'), 'paid', 'CNY', 100, None)),
             wishlist_item(3, Price(Meta('ok'), 'paid', 'CNY', 100, 0)),
             wishlist_item(4, Price(Meta('ok'), 'free'))]
    ranks = wishlist_summary(items).price_ranking
    assert [item.appid for item in ranks] == [3, 4, 1, 2]
    assert (ranks[0].type, ranks[0].price) == ('paid', 0)
    assert (ranks[1].type, ranks[1].price, ranks[1].currency) == ('free', 0, None)
    assert ranks[-1].price is None


def test_status_aggregation_and_dimension_coverage():
    item = library_item()
    assert item.status == 'ok'  # Nullable, unrequested detail is not a missing summary.
    item.achievements = Achievements(Meta('not_applicable'), -1, -1)
    assert record_status(item.identity, item.achievements) == 'ok'
    assert record_status(item.identity, Achievements(Meta('unavailable'))) == 'partial'
    assert record_status(GameIdentity(Meta('unavailable'), 1)) == 'failed'
    item.status = 'partial'
    assert games_summary([item]).partial_count == 1
    assert run_status([item]) == 'partial'
    assert run_status([item], cancelled=True, core_failed=True) == 'cancelled'
    assert run_status([item], core_failed=True) == 'failed'
    assert run_status([], has_errors=True) == 'failed'
    blocks = [Playtime(Meta('ok'), total=0), Playtime(Meta('unavailable'))]
    coverage = block_coverage(blocks, [True, False])
    assert coverage.to_dict() == dict(state='partial', complete=False, known_count=1, missing_count=1)


def test_ranking_configuration_is_in_feature_config(tmp_path):
    assert load_config(tmp_path, {}).ranking_limit == 10
    assert load_config(tmp_path, {'STEAM_RANKING_LIMIT': '0'}).ranking_limit == 0
    assert load_config(tmp_path, {'STEAM_RANKING_LIMIT': '5'}).ranking_limit == 5
    with pytest.raises(Exception, match='STEAM_RANKING_LIMIT'):
        load_config(tmp_path, {'STEAM_RANKING_LIMIT': '-1'})


def test_error_ids_must_reference_one_root_error_and_feature_must_match():
    item = library_item()
    item.achievements.meta.error_id = 'err_synthetic'
    collection = CollectionCoverage('ok', True, 1)
    coverage = LibraryCoverage(collection, collection, block_coverage([item.playtime]), block_coverage([item.achievements]))
    run = Run('synthetic', 'library', '2026-10-07T10:00:00+08:00', None, None, 'ok')
    error = dict(error_id='err_synthetic', code='DATA_UNAVAILABLE', source='fixture', message='synthetic')
    valid = LibraryResult(run, library_summary([item], 10), coverage, [error], [item])
    assert len(valid.to_dict()['errors']) == 1
    with pytest.raises(ValueError, match='reference'):
        LibraryResult(run, valid.summary, coverage, [], [item])
    with pytest.raises(ValueError, match='unique'):
        LibraryResult(run, valid.summary, coverage, [error, error], [item])
    with pytest.raises(ValueError, match='feature'):
        GamesResult(run, games_summary([]), [], [])
