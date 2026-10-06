"""Feature shapes and pure summaries, coverage and status aggregation."""
from dataclasses import dataclass, field
from typing import Any, Literal

from schema.base import (Achievements, Bundles, GameIdentity, Market, Meta, Ownership,
                         Playtime, Price, State, Wishlist)
from schema.model import Model
from schema.version import SCHEMA_VERSION

RecordStatus = Literal["ok", "partial", "failed"]
RunStatus = Literal["ok", "partial", "failed", "cancelled"]
# Reuse Failure.info from steamtool.error_handler. This is a type alias, not an error system.
Error = dict[str, Any]


@dataclass
class Run(Model):
    run_id: str
    feature: Literal["games", "library", "wishlist"]
    started_at: str
    finished_at: str | None
    subject_steamid: str | None
    status: RunStatus


@dataclass
class GameRecord(Model):
    status: RecordStatus
    identity: GameIdentity
    market: Market
    ownership: Ownership
    wishlist: Wishlist
    playtime: Playtime
    achievements: Achievements
    price: Price
    bundles: Bundles


@dataclass
class LibraryRecord(Model):
    status: RecordStatus
    identity: GameIdentity
    ownership: Ownership
    playtime: Playtime
    achievements: Achievements


@dataclass
class WishlistRecord(Model):
    status: RecordStatus
    identity: GameIdentity
    market: Market
    ownership: Ownership
    wishlist: Wishlist
    price: Price
    bundles: Bundles


@dataclass
class GamesSummary(Model):
    game_count: int
    ok_count: int
    partial_count: int
    failed_count: int


@dataclass
class PlaytimeRankingItem(Model):
    rank: int
    appid: int
    name: str | None
    playtime: int
    unit: str


@dataclass
class LibrarySummary(Model):
    total_count: int
    self_owned_count: int
    family_owned_count: int
    family_available_count: int
    played_count: int
    unplayed_count: int
    playtime_unknown_count: int
    played_ratio: float | None
    unplayed_ratio: float | None
    total_playtime: int
    playtime_unit: str
    ranking_limit: int
    top_total_playtime: list[PlaytimeRankingItem]
    top_last_2weeks_playtime: list[PlaytimeRankingItem]


@dataclass
class WishlistPriceRankingItem(Model):
    rank: int
    appid: int
    name: str | None
    type: Literal["paid", "free"] | None
    price: int | None
    currency: str | None


@dataclass
class WishlistSummary(Model):
    total_count: int
    price_ranking: list[WishlistPriceRankingItem]


@dataclass
class CollectionCoverage(Model):
    state: State
    complete: bool | None
    count: int | None


@dataclass
class BlockCoverage(Model):
    state: State
    complete: bool
    known_count: int
    missing_count: int


@dataclass
class LibraryCoverage(Model):
    self_library: CollectionCoverage
    family_library: CollectionCoverage
    playtime: BlockCoverage
    achievements: BlockCoverage


@dataclass
class WishlistCoverage(Model):
    wishlist: CollectionCoverage
    market: BlockCoverage
    ownership: BlockCoverage
    price: BlockCoverage
    bundles: BlockCoverage


class FeatureResult(Model):
    def __post_init__(self):
        super().__post_init__()
        if self.run.feature != self._feature:
            raise ValueError("Result type and run.feature must match")
        ids = [error.get("error_id") for error in self.errors]
        if any(not isinstance(key, str) for key in ids) or len(set(ids)) != len(ids):
            raise ValueError("Root errors must have unique string error_id values")
        for item in self.items:
            for name in item.to_dict():
                block = getattr(item, name)
                if hasattr(block, "meta") and block.meta.error_id is not None and block.meta.error_id not in ids:
                    raise ValueError("Data block error_id must reference a root error")


@dataclass
class GamesResult(FeatureResult):
    _feature = "games"
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    run: Run
    summary: GamesSummary
    errors: list[Error]
    items: list[GameRecord]


@dataclass
class LibraryResult(FeatureResult):
    _feature = "library"
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    run: Run
    summary: LibrarySummary
    coverage: LibraryCoverage
    errors: list[Error]
    items: list[LibraryRecord]


@dataclass
class WishlistResult(FeatureResult):
    _feature = "wishlist"
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    run: Run
    summary: WishlistSummary
    coverage: WishlistCoverage
    errors: list[Error]
    items: list[WishlistRecord]


def record_status(identity, *blocks):
    if identity.meta.state in {"unavailable", "not_requested"}:
        return "failed"
    return "ok" if all(block.meta.state in {"ok", "not_applicable"}
                       for block in (identity, *blocks)) else "partial"


def run_status(items, *, cancelled=False, core_failed=False, incomplete=False, has_errors=False):
    if cancelled:
        return "cancelled"
    if core_failed or (items and all(item.status == "failed" for item in items)):
        return "failed"
    if not items and has_errors:
        return "failed"
    return "partial" if incomplete or has_errors or any(item.status != "ok" for item in items) else "ok"


def games_summary(items):
    return GamesSummary(len(items), *(sum(item.status == state for item in items)
                                      for state in ("ok", "partial", "failed")))


def playtime_ranking(items, field_name, limit):
    known = [item for item in items if getattr(item.playtime, field_name) is not None]
    known.sort(key=lambda item: (-getattr(item.playtime, field_name), item.identity.appid))
    return [PlaytimeRankingItem(rank, item.identity.appid, item.identity.name,
                               getattr(item.playtime, field_name), item.playtime.unit)
            for rank, item in enumerate(known[:limit], 1)]


def library_summary(items, ranking_limit):
    if type(ranking_limit) is not int or ranking_limit < 0:
        raise ValueError("ranking_limit must be a nonnegative integer")
    units = {item.playtime.unit for item in items}
    if len(units) > 1:
        raise ValueError("Cannot add playtime expressed in different units")
    played = sum(item.playtime.total is not None and item.playtime.total > 0 for item in items)
    unplayed = sum(item.playtime.total == 0 for item in items)
    known = played + unplayed
    return LibrarySummary(
        len(items), sum(item.ownership.owned_by_self is True for item in items),
        sum(item.ownership.owned_by_other_family_members is True for item in items),
        sum(item.ownership.available_via_family is True for item in items),
        played, unplayed, len(items) - known, played / known if known else None,
        unplayed / known if known else None,
        sum(item.playtime.total for item in items if item.playtime.total is not None),
        next(iter(units), "minutes"), ranking_limit,
        playtime_ranking(items, "total", ranking_limit),
        playtime_ranking(items, "last_2weeks", ranking_limit))


def wishlist_summary(items):
    def amount(item):
        return 0 if item.price.type == "free" else item.price.final
    ordered = sorted(items, key=lambda item: (amount(item) is None,
                                             amount(item) if amount(item) is not None else 0,
                                             item.identity.appid))
    return WishlistSummary(len(items), [WishlistPriceRankingItem(
        rank, item.identity.appid, item.identity.name, item.price.type, amount(item), item.price.currency)
        for rank, item in enumerate(ordered, 1)])


def block_coverage(blocks, known=None):
    """Known can describe a specific dimension, e.g. total playtime, rather than every field."""
    accepted = [block.meta.state in {"ok", "not_applicable"} for block in blocks] if known is None else known
    count = sum(accepted)
    states = {block.meta.state for block in blocks}
    state = ("ok" if count == len(blocks) else "partial" if count else
             "not_requested" if states == {"not_requested"} else "unavailable")
    return BlockCoverage(state, count == len(blocks), count, len(blocks) - count)
