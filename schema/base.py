"""Frozen reusable data blocks. Null, false, zero and sentinels remain distinct."""
from dataclasses import dataclass, field
from typing import Any, Literal

from schema.model import Model

State = Literal["ok", "partial", "unavailable", "not_applicable", "not_requested"]
Source = str | list[str] | dict[str, Any] | None
FetchedAt = str | list[Any] | dict[str, Any] | None
PriceType = Literal["paid", "free"] | None


@dataclass
class Meta(Model):
    state: State = "not_requested"
    source: Source = None
    fetched_at: FetchedAt = None
    error_id: str | None = None


@dataclass
class GameIdentity(Model):
    meta: Meta
    appid: int
    name: str | None = None
    app_type: str | None = None


@dataclass
class Market(Model):
    meta: Meta
    region: str
    released: bool | None = None
    availability: bool | None = None


@dataclass
class Ownership(Model):
    meta: Meta
    owned_by_self: bool | None = None
    owned_by_other_family_members: bool | None = None
    available_via_family: bool | None = None
    owners: dict[str, dict[str, str | None]] | None = None

    def __post_init__(self):
        super().__post_init__()
        if self.owners is not None and any(set(owner) != {"persona_name"} for owner in self.owners.values()):
            raise ValueError("Each owner contains exactly persona_name")


@dataclass
class Wishlist(Model):
    meta: Meta
    present: bool | None = None
    priority: int | None = None
    date_added: int | None = None


@dataclass
class PlaytimePlatform(Model):
    windows: int | None = None
    mac: int | None = None
    linux: int | None = None
    deck: int | None = None

    def __post_init__(self):
        super().__post_init__()
        if any(value is not None and value < -1 for value in self.to_dict().values()):
            raise ValueError("Platform playtime must be null, -1 or nonnegative")


@dataclass
class Playtime(Model):
    meta: Meta
    total: int | None = None
    last_2weeks: int | None = None
    last_played_at: int | None = None
    unit: str = "minutes"
    platform: PlaytimePlatform = field(default_factory=PlaytimePlatform)

    def __post_init__(self):
        super().__post_init__()
        if any(value is not None and value < 0 for value in (self.total, self.last_2weeks)):
            raise ValueError("Total/recent playtime cannot use the platform -1 sentinel")


@dataclass
class Achievement(Model):
    apiname: str
    display_name: str | None = None
    description: str | None = None
    unlocked: bool | None = None
    unlock_time: int | None = None


@dataclass
class Achievements(Model):
    meta: Meta
    total: int | None = None
    unlocked: int | None = None
    completion_ratio: float | None = None
    items: list[Achievement] | None = None

    def __post_init__(self):
        super().__post_init__()
        if any(value is not None and value < -1 for value in (self.total, self.unlocked)):
            raise ValueError("Achievement counts must be null, -1 or nonnegative")
        if self.total == -1 or self.unlocked == -1:
            if not (self.total == self.unlocked == -1 and self.completion_ratio is None
                    and self.items is None and self.meta.state == "not_applicable"):
                raise ValueError("No achievement system requires paired -1 counts and not_applicable")


@dataclass
class PriceValue(Model):
    """Bundle prices inherit provenance from Bundles; there is no nested Meta."""
    type: PriceType = None
    currency: str | None = None
    initial: int | None = None
    final: int | None = None

    def __post_init__(self):
        super().__post_init__()
        validate_price(self)


@dataclass
class Price(Model):
    meta: Meta
    type: PriceType = None
    currency: str | None = None
    initial: int | None = None
    final: int | None = None

    def __post_init__(self):
        super().__post_init__()
        validate_price(self)


def validate_price(value):
    if value.type == "free" and any(item is not None for item in (value.currency, value.initial, value.final)):
        raise ValueError("Free products have null currency, initial and final")


@dataclass
class Bundle(Model):
    bundle_id: int
    name: str | None = None
    price: PriceValue = field(default_factory=PriceValue)
    included_apps: dict[str, str | None] = field(default_factory=dict)


@dataclass
class Bundles(Model):
    meta: Meta
    items: list[Bundle] | None = None
