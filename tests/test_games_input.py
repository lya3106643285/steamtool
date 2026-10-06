import asyncio

import pytest

from steamtool.input_parser import GamesInput, InputState, parse_names
from steamtool import main


@pytest.mark.parametrize('line,names', [
    ('"Hades"', ['Hades']), ('"Hades","Noita"', ['Hades', 'Noita']),
    ('"Hades","Hello, World","Noita"', ['Hades', 'Hello, World', 'Noita']),
    ('"Game ""Special"" Edition"', ['Game "Special" Edition']),
    ('  "Hades" , "Noita"  ', ['Hades', 'Noita']),
])
def test_quoted_csv_names(line, names):
    items = parse_names(line)
    assert [item.name for item in items] == names
    assert all(item.error is None for item in items)


@pytest.mark.parametrize('line,code', [
    ('Noita', 'QUERY_NAME_NOT_QUOTED'), ('“Hades”', 'QUERY_INVALID_QUOTE'),
    ('「Hades」', 'QUERY_INVALID_QUOTE'), ('＂Hades＂', 'QUERY_INVALID_QUOTE'),
    ('"Hades', 'QUERY_UNCLOSED_QUOTE'), ('""', 'QUERY_EMPTY_NAME'),
    ('" "', 'QUERY_EMPTY_NAME'), ('"Hades" x', 'QUERY_UNEXPECTED_CHAR'),
    ('"Hades"，"Noita"', 'QUERY_UNEXPECTED_CHAR'),
    ('"Game \\"Special\\" Edition"', 'QUERY_INVALID_ESCAPE'),
    ('292030', 'QUERY_NAME_NOT_QUOTED'), ('"292030"', 'QUERY_UNEXPECTED_CHAR'),
    ('https://store.steampowered.com/app/1/', 'QUERY_NAME_NOT_QUOTED'),
    ('"https://store.steampowered.com/app/1/"', 'QUERY_UNEXPECTED_CHAR'),
])
def test_invalid_inputs_stay_parser_errors(line, code):
    item = parse_names(line)[0]
    assert item.error.code == code and item.error.raw == line
    assert item.name is None


def test_locate_bad_second_item_and_keep_neighbors():
    items = parse_names('"Hades",Noita,"Outer Wilds"')
    assert items[1].error.item_index == 2 and items[1].error.raw == 'Noita'
    assert items[1].error.code == 'QUERY_NAME_NOT_QUOTED'
    assert items[0].name == 'Hades' and items[2].name == 'Outer Wilds'


def test_correction_retry_and_collection_blank_have_different_meanings():
    state = GamesInput()
    state.feed('"Hades",Noita,"Outer Wilds"')
    assert state.state == InputState.CORRECTING_ITEM and not state.done
    state.feed('Again invalid')
    assert state.error.item_index == 2 and state.names == ['Hades']
    state.feed('"Noita"')
    assert state.state == InputState.COLLECTING_INPUT and not state.done
    state.feed('"Hello, World"')
    state.feed('')
    assert state.done and state.names == ['Hades', 'Noita', 'Outer Wilds', 'Hello, World']


def test_correction_blank_only_skips_current_item_and_preserves_following_errors():
    state = GamesInput()
    state.feed('"Hades",Noita,"Outer Wilds",Bad')
    state.feed('')
    assert state.state == InputState.CORRECTING_ITEM and state.error.item_index == 4
    assert not state.done and state.names == ['Hades', 'Outer Wilds']
    state.feed('"Fixed"')
    state.feed('"Next"')
    state.feed('')
    assert state.names == ['Hades', 'Outer Wilds', 'Fixed', 'Next']


def test_correction_cannot_insert_an_entire_new_batch():
    state = GamesInput()
    state.feed('Bad')
    state.feed('"A","B"')
    assert state.error.code == 'QUERY_UNEXPECTED_CHAR' and not state.names
    state.feed('"A"')
    assert state.names == ['A']


def test_async_cli_collects_multiline_and_retries_in_place(monkeypatch, capsys):
    lines = iter(['"Hades",Noita,"Outer Wilds"', 'Noita', '"Noita"', '"Hello, World"', ''])
    async def read(prompt, stop):
        return next(lines)
    monkeypatch.setattr(main, 'read_line', read)
    names = asyncio.run(main.collect_game_names(asyncio.Event()))
    assert names == ['Hades', 'Noita', 'Outer Wilds', 'Hello, World']
    assert capsys.readouterr().err.count('QUERY_NAME_NOT_QUOTED') == 2
