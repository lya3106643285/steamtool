"""Keep the effective formal spec and executable public shapes aligned."""
from dataclasses import fields
from pathlib import Path
import re

from schema import base, feature
from schema.version import SCHEMA_VERSION

DOC = Path(__file__).resolve().parents[1] / 'docs/data_contract.md'


def section(text, heading):
    match = re.search(r'^#{3,4} (?:\d+\.\d+ )?' + heading + r'\n', text, re.M)
    assert match, heading
    tail = text[match.end():]
    return re.split(r'\n#{2,4} ', tail, maxsplit=1)[0]


def test_formal_version_and_every_public_model_field_is_documented():
    text = DOC.read_text()
    assert '**2.0.0**' in text and f'SCHEMA_VERSION={SCHEMA_VERSION}' in text
    assert '文档状态：Draft' not in text
    models = [base.Meta, base.GameIdentity, base.Market, base.Ownership, base.Wishlist, base.Playtime,
              base.PlaytimePlatform, base.Achievements, base.Achievement, base.Price, base.Bundles,
              base.Bundle, base.PriceValue, feature.Run, feature.CollectionCoverage, feature.BlockCoverage,
              feature.GamesSummary, feature.LibrarySummary, feature.WishlistSummary,
              feature.PlaytimeRankingItem, feature.WishlistPriceRankingItem,
              feature.GameRecord, feature.LibraryRecord, feature.WishlistRecord,
              feature.LibraryCoverage, feature.WishlistCoverage]
    for model in models:
        content = section(text, model.__name__)
        for field in fields(model):
            assert '`' + field.name + '`' in content, (model.__name__, field.name)
    for model in (feature.GamesResult, feature.LibraryResult, feature.WishlistResult):
        match = re.search(r'^\| ' + model.__name__ + r' \| ([^|]+) \|$', text, re.M)
        assert match
        assert [value.strip() for value in match[1].split(',')] == [field.name for field in fields(model)]
