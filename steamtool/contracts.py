"""Adapt existing runner evidence to the formal contract; no I/O or new data sources."""
from schema.base import (Achievement, Achievements, Bundles, GameIdentity, Market, Meta,
                         Ownership, Playtime, PlaytimePlatform, Price, Wishlist)
from schema.feature import (BlockCoverage, CollectionCoverage, GameRecord, GamesResult, LibraryCoverage,
                            LibraryRecord, LibraryResult, Run, WishlistCoverage, WishlistRecord,
                            WishlistResult, block_coverage, games_summary, library_summary,
                            record_status, run_status, wishlist_summary)


def meta(block, state=None):
    state = state or block.get("state", "not_requested")
    if state not in {"ok", "partial", "unavailable", "not_applicable", "not_requested"}:
        state = "unavailable"
    return Meta(state, block.get("source"), block.get("fetched_at"), block.get("error_id"))


def integer(value):
    return value if type(value) is int else None


def boolean(value):
    return value if type(value) is bool else None


def string(value):
    return value if isinstance(value, str) else None


def identity(item):
    store = item["store"]
    if store["state"] == "ok":
        evidence = store
    else:
        evidence = item.get("_identity_meta", {})
    state = "ok" if evidence.get("state") == "ok" and item.get("name") else "partial"
    # A known AppID is still a meaningful identity if name/type enrichment is unavailable.
    return GameIdentity(meta(evidence, state), item["appid"], string(item.get("name")),
                        string(item.get("app_type")))


def ownership(item):
    value = item["ownership"]
    ids = value.get("owner_steamids")
    owners = {str(steamid): {"persona_name": None} for steamid in ids} if ids is not None else None
    subject = item["playtime"].get("subject_steamid")
    if value.get("owned_by_self") is True and subject:
        # The owned-games evidence confirms this owner even outside a Steam Family.
        owners = dict(owners or {})
        owners.setdefault(subject, {"persona_name": None})
    # TODO: there is no confirmed multi-owner nickname lookup in the existing ports.
    return Ownership(meta(value), *(value.get(key) for key in (
        "owned_by_self", "owned_by_other_family_members", "available_via_family")), owners)


def playtime(item):
    value = item["playtime"]
    platforms = value.get("platform_minutes", {})
    store_platforms = (item["store"].get("data") or {}).get("platforms") or {}
    normalized = {}
    for platform in ("windows", "mac", "linux", "deck"):
        minutes = integer(platforms.get(platform))
        # Only an explicit platform-support flag may establish the -1 sentinel.
        support = boolean(store_platforms.get(platform))
        normalized[platform] = (minutes if minutes is not None and minutes > 0 else
                                -1 if support is False else 0 if minutes == 0 and support is True else None)
    state = "partial" if value["state"] == "ok" and value.get("total_minutes") is None else None
    return Playtime(meta(value, state), value.get("total_minutes"), value.get("last_2weeks_minutes"),
                    value.get("last_played_at"), value.get("unit", "minutes"), PlaytimePlatform(**normalized))


def achievements(item):
    value = item["achievements"]
    if value["state"] == "not_applicable":
        return Achievements(meta(value), -1, -1, None, None)
    entries = value.get("items")
    entries = None if entries is None else [Achievement(**{
        key: entry.get(key) for key in ("apiname", "display_name", "description", "unlocked", "unlock_time")
    }) for entry in entries]
    return Achievements(meta(value), value.get("total"), value.get("unlocked"),
                        value.get("completion_ratio"), entries)


def wish(item):
    value = item["wishlist"]
    state = "partial" if value["state"] == "ok" and value.get("present") is None else None
    return Wishlist(meta(value, state), value.get("present"), value.get("priority"), value.get("date_added"))


def market_and_price(item, region):
    store = item["store"]
    data = store.get("data") or {}
    release = data.get("release_date") or {}
    coming_soon = boolean(release.get("coming_soon")) if isinstance(release, dict) else None
    released = not coming_soon if coming_soon is not None else None
    # TODO: appdetails success is not proof of purchase/acquisition availability.
    market = Market(meta(store, "partial" if store["state"] == "ok" else None), region, released, None)
    free = boolean(data.get("is_free"))
    value = data.get("price_overview") or {}
    if not isinstance(value, dict):
        value = {}
    if free is True:
        price = Price(meta(store), "free", None, None, None)
    else:
        kind = "paid" if free is False else None
        currency = string(value.get("currency"))
        initial, final = integer(value.get("initial")), integer(value.get("final"))
        state = ("ok" if kind and currency and initial is not None and final is not None
                 else "partial" if kind or currency or initial is not None or final is not None else "unavailable")
        if store["state"] != "ok":
            state = None
        price = Price(meta(store, state), kind, currency, initial, final)
    return market, price


def build_record(item, feature, region):
    ident, owned = identity(item), ownership(item)
    if feature == "library":
        played, achieved = playtime(item), achievements(item)
        return LibraryRecord(record_status(ident, owned, played, achieved), ident, owned, played, achieved)
    market, price = market_and_price(item, region)
    wishes = wish(item)
    # TODO: current registry has no Bundle source. Do not invent a crawler or imply an empty list.
    bundles = Bundles(Meta("unavailable"), None)
    if feature == "wishlist":
        return WishlistRecord(record_status(ident, market, owned, wishes, price, bundles),
                              ident, market, owned, wishes, price, bundles)
    played, achieved = playtime(item), achievements(item)
    return GameRecord(record_status(ident, market, owned, wishes, played, achieved, price, bundles),
                      ident, market, owned, wishes, played, achieved, price, bundles)


def collection_coverage(document, name):
    value = document["coverage"].get(name, {})
    return CollectionCoverage(meta(value).state, value.get("complete"),
                              value.get("distinct_count", value.get("count")))


def build_result(document, config, *, ranking_limit=None):
    feature = document["meta"]["feature"]
    items = [build_record(item, feature, config.country) for item in document["data"]["items"]]
    errors = list({error["error_id"]: error for error in document["errors"]}.values())
    incomplete = False
    coverage = None
    if feature == "library":
        coverage = LibraryCoverage(
            collection_coverage(document, "owned"), collection_coverage(document, "family"),
            block_coverage([item.playtime for item in items], [item.playtime.total is not None for item in items]),
            block_coverage([item.achievements for item in items], [
                item.achievements.total is not None and item.achievements.unlocked is not None for item in items]))
        incomplete = any(block.complete is not True for block in (coverage.self_library, coverage.family_library))
        if not items and incomplete:
            coverage.playtime = BlockCoverage("unavailable", False, 0, 0)
            coverage.achievements = BlockCoverage("unavailable", False, 0, 0)
    elif feature == "wishlist":
        coverage = WishlistCoverage(collection_coverage(document, "wishlist"), *[
            block_coverage([getattr(item, name) for item in items])
            for name in ("market", "ownership", "price", "bundles")])
        incomplete = coverage.wishlist.complete is not True
        if not items and incomplete:
            for name in ("market", "ownership", "price", "bundles"):
                setattr(coverage, name, BlockCoverage("unavailable", False, 0, 0))
    status = run_status(items, cancelled=document["status"] == "cancelled",
                        core_failed=document["status"] == "failed", incomplete=incomplete, has_errors=bool(errors))
    info = document["meta"]
    run = Run(info["run_id"], feature, info["started_at"], info["finished_at"], info["subject_steamid"], status)
    if feature == "library":
        summary = library_summary(items, config.ranking_limit if ranking_limit is None else ranking_limit)
        return LibraryResult(run, summary, coverage, errors, items)
    if feature == "wishlist":
        return WishlistResult(run, wishlist_summary(items), coverage, errors, items)
    return GamesResult(run, games_summary(items), errors, items)
