"""Prospective NBA moneyline data capture: Polymarket L2 book and wallet-linked fills.

Run continuously on an awake, networked machine. Raw HTTP bodies and WebSocket
messages are gzip cached under data/raw/polymarket/prospective/. This collector
does not place orders and uses only public market/trade data.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import websockets

from common import ROOT

RAW = ROOT / "data/raw/polymarket/prospective"
OUT = ROOT / "data/interim/phase6/prospective"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
GAMMA = "https://gamma-api.polymarket.com/events"
TRADES = "https://data-api.polymarket.com/trades"
WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
SERIES_ID = "10345"
DISCOVER_SECONDS = 300
POLL_SECONDS = 90
OVERLAP_SECONDS = 120
PAGE_SIZE = 500
MAX_OFFSET = 10_000
UTC = timezone.utc
ET = ZoneInfo("America/New_York")
TEAM_ALIASES = {"GS": "gsw", "NO": "nop", "NY": "nyk", "SA": "sas",
                "WSH": "was", "UTAH": "uta", "PHO": "phx", "PHX": "phx",
                "BRK": "bkn"}


def now_utc() -> datetime:
    return datetime.now(UTC)


def stamp(dt: datetime | None = None) -> str:
    return (dt or now_utc()).strftime("%Y%m%dT%H%M%S.%fZ")


def log_event(kind: str, **fields) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    record = {"recorded_utc": now_utc().isoformat(), "kind": kind, **fields}
    with (OUT / "collector_status.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")
    logging.info("%s %s", kind, fields)


def cache_http_body(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Raw cache path already exists: {path}")
    target = path.with_suffix(path.suffix + ".gz")
    temporary = target.with_suffix(target.suffix + ".tmp")
    with gzip.open(temporary, "wb", compresslevel=6) as f:
        f.write(body)
    temporary.replace(target)


def request_cached(session: requests.Session, url: str, params: dict,
                   cache_path: Path, timeout: int = 60) -> tuple[requests.Response, bytes]:
    for attempt in range(8):
        try:
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                pause = response.headers.get("Retry-After")
                time.sleep(float(pause) if pause else min(60, 2 ** attempt))
                continue
            response.raise_for_status()
            body = response.content
            cache_http_body(cache_path, body)
            return response, body
        except (requests.RequestException, OSError):
            if attempt == 7:
                raise
            time.sleep(min(60, 2 ** attempt))
    raise RuntimeError(f"HTTP retry limit reached: {url} {params}")


def team_slug(abbr: str) -> str:
    key = str(abbr).upper()
    return TEAM_ALIASES.get(key, key.lower())


def event_slug(away_abbr: str, home_abbr: str, start: datetime) -> str:
    date_et = start.astimezone(ET).strftime("%Y-%m-%d")
    return f"nba-{team_slug(away_abbr)}-{team_slug(home_abbr)}-{date_et}"


def parse_list_field(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []
    return []


def fetch_schedule(session: requests.Session) -> list[dict]:
    today_et = now_utc().astimezone(ET).date()
    dates = [today_et + timedelta(days=i) for i in (0, 1, 2)]
    games = []
    for day in dates:
        key = day.strftime("%Y%m%d")
        params = {"dates": key}
        path = RAW / "scoreboard" / f"{key}_{stamp()}.json"
        _, body = request_cached(session, ESPN, params, path)
        payload = json.loads(body)
        for event in payload.get("events", []):
            competitors = event.get("competitions", [{}])[0].get("competitors", [])
            by_side = {c.get("homeAway"): c for c in competitors}
            home, away = by_side.get("home", {}), by_side.get("away", {})
            if not home or not away:
                continue
            start = pd_timestamp(event.get("date"))
            games.append({
                "espn_game_id": str(event.get("id")), "event_name": event.get("name"),
                "scheduled_start_utc": start.isoformat(),
                "away_team": away.get("team", {}).get("displayName"),
                "away_abbreviation": away.get("team", {}).get("abbreviation"),
                "home_team": home.get("team", {}).get("displayName"),
                "home_abbreviation": home.get("team", {}).get("abbreviation"),
                "status": event.get("status", {}).get("type", {}).get("name"),
                "slug": event_slug(away.get("team", {}).get("abbreviation"),
                                   home.get("team", {}).get("abbreviation"), start),
                "scoreboard_event": event,
            })
    return games


def pd_timestamp(value: str) -> datetime:
    # ESPN schedule timestamps are ISO-8601 UTC values.
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def token_mapping(market: dict, game: dict, event: dict) -> dict | None:
    outcomes, tokens = parse_list_field(market.get("outcomes")), parse_list_field(market.get("clobTokenIds"))
    if len(outcomes) != 2 or len(tokens) != 2:
        return None
    teams = event.get("teams") or []
    team_ids = {}
    for team in teams:
        labels = {str(team.get(k, "")).strip().casefold()
                  for k in ("name", "alias", "abbreviation")}
        if str(team.get("ordering", "")).lower() == "home":
            team_ids["home"] = labels
        elif str(team.get("ordering", "")).lower() == "away":
            team_ids["away"] = labels
    mapped = {}
    for outcome, token in zip(outcomes, tokens):
        key = str(outcome).strip().casefold()
        for side in ("home", "away"):
            if key in team_ids.get(side, set()):
                mapped[side] = {"outcome": outcome, "token_id": str(token)}
    if set(mapped) != {"home", "away"}:
        return None
    return mapped


def discover(session: requests.Session) -> dict[str, dict]:
    games = fetch_schedule(session)
    catalog_path = OUT / "market_catalog.json"
    if catalog_path.exists():
        existing = json.loads(catalog_path.read_text())
        catalog = existing.get("markets", existing)
        # Recover gracefully if an early collector run wrote an extra envelope.
        if (isinstance(catalog, dict) and "updated_utc" in catalog
                and isinstance(catalog.get("markets"), dict)):
            catalog = catalog["markets"]
    else:
        catalog = {}
    mapped_now = []
    now = now_utc()
    for game in games:
        start = pd_timestamp(game["scheduled_start_utc"])
        # Query current and near-term games only; ESPN is the schedule source,
        # so Gamma requests are narrowly keyed by each known game slug.
        if not (now - timedelta(hours=8) <= start <= now + timedelta(hours=36)):
            continue
        prior = catalog.get(game["slug"])
        if prior and prior.get("condition_id") and prior.get("outcome_tokens"):
            prior.update({k: v for k, v in game.items() if k != "scoreboard_event"})
            prior["last_discovered_utc"] = now.isoformat()
            catalog[game["slug"]] = prior
            mapped_now.append(prior)
            continue
        params = {"slug": game["slug"]}
        path = RAW / "gamma_events" / f"{game['slug']}_{stamp()}.json"
        _, body = request_cached(session, GAMMA, params, path)
        events = json.loads(body)
        if not events:
            continue
        event = events[0]
        moneyline = next((m for m in event.get("markets", [])
                          if str(m.get("sportsMarketType", "")).lower() == "moneyline"
                          and m.get("enableOrderBook", True)
                          and not m.get("closed", False)), None)
        if moneyline is None:
            continue
        token_ids = token_mapping(moneyline, game, event)
        if token_ids is None:
            log_event("unmapped_moneyline_outcomes", slug=game["slug"],
                      outcomes=moneyline.get("outcomes"), teams=event.get("teams"))
            continue
        record = {
            **{k: v for k, v in game.items() if k != "scoreboard_event"},
            "polymarket_event_id": str(event.get("id", "")),
            "market_id": str(moneyline.get("id", "")),
            "condition_id": str(moneyline.get("conditionId", "")),
            "question": moneyline.get("question"), "sports_market_type": moneyline.get("sportsMarketType"),
            "active": bool(moneyline.get("active")), "closed": bool(moneyline.get("closed")),
            "outcome_tokens": token_ids, "market_event_updated_at": event.get("updatedAt"),
            "first_discovered_utc": catalog.get(game["slug"], {}).get("first_discovered_utc", now.isoformat()),
            "last_discovered_utc": now.isoformat(),
        }
        catalog[game["slug"]] = record
        mapped_now.append(record)
    OUT.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps({"updated_utc": now.isoformat(), "markets": catalog}, indent=2) + "\n")
    log_event("discovery_complete", scoreboard_games=len(games), mapped_markets=len(mapped_now),
              assets=len({v["token_id"] for m in catalog.values() for v in m["outcome_tokens"].values()}))
    return catalog


def api_page(session: requests.Session, market: dict, role: str, start: int, end: int,
             offset: int) -> list:
    params = {"market": market["condition_id"], "start": start, "end": end,
              "limit": PAGE_SIZE, "offset": offset, "takerOnly": str(role == "taker").lower()}
    capture = stamp()
    path = RAW / "trade_api" / market["slug"] / f"{role}_{start}_{end}_off{offset}_{capture}.json"
    _, body = request_cached(session, TRADES, params, path, timeout=90)
    result = json.loads(body)
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected trade payload for {market['slug']}: {type(result)}")
    return result


def fetch_role_interval(session: requests.Session, market: dict, role: str,
                        start: int, end: int) -> tuple[list, int]:
    rows = []
    for offset in range(0, MAX_OFFSET + 1, PAGE_SIZE):
        page = api_page(session, market, role, start, end, offset)
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows, 0
    if start >= end:
        raise RuntimeError(f"Trade API saturated at one-second interval: {market['slug']} {role} {start}")
    mid = (start + end) // 2
    left, splits_left = fetch_role_interval(session, market, role, start, mid)
    right, splits_right = fetch_role_interval(session, market, role, mid + 1, end)
    return left + right, len(rows) + splits_left + splits_right


def poll_wallet_trades(catalog: dict[str, dict]) -> None:
    """Incrementally cache Data API rows for markets near their scheduled games."""
    session = requests.Session()
    state_path = OUT / "trade_watermarks.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = int(time.time())
    statuses = []
    for slug, market in catalog.items():
        start_game = int(pd_timestamp(market["scheduled_start_utc"]).timestamp())
        if not start_game - 8 * 3600 <= now <= start_game + 6 * 3600:
            continue
        if not market.get("condition_id"):
            continue
        prior_end = int(state.get(slug, {}).get("last_successful_end", min(now, start_game)))
        start = max(start_game - 8 * 3600, prior_end - OVERLAP_SECONDS)
        end = now - 5  # leave a short indexing buffer; the next overlapping poll catches late rows
        if end <= start:
            continue
        try:
            totals = {}
            split_counts = {}
            for role in ("all", "taker"):
                rows, splits = fetch_role_interval(session, market, role, start, end)
                totals[role], split_counts[role] = len(rows), splits
            state[slug] = {"last_successful_end": end,
                           "first_capture_utc": state.get(slug, {}).get("first_capture_utc", now_utc().isoformat())}
            statuses.append({"slug": slug, "start": start, "end": end,
                             "rows_all": totals["all"], "rows_taker": totals["taker"],
                             "split_rows_due_to_page_cap": split_counts})
        except Exception as exc:
            statuses.append({"slug": slug, "start": start, "end": end, "error": repr(exc)})
            log_event("trade_poll_error", slug=slug, start=start, end=end, error=repr(exc))
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    log_event("trade_poll_complete", markets=len(statuses), results=statuses)


class WebSocketRawWriter:
    def __init__(self, connection_id: str, catalog: dict[str, dict]):
        self.connection_id = connection_id
        self.catalog = catalog
        self.day = None
        self.handle = None
        self.normalized = None
        self.count = 0

    def append(self, message: str, received_at: datetime) -> None:
        day = received_at.strftime("%Y-%m-%d")
        if day != self.day:
            self.close()
            path = RAW / "market_websocket" / f"events_{day}.jsonl.gz"
            path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = gzip.open(path, "at", encoding="utf-8", compresslevel=4)
            norm_path = OUT / "quote_events" / f"events_{day}.jsonl"
            norm_path.parent.mkdir(parents=True, exist_ok=True)
            self.normalized = norm_path.open("a", encoding="utf-8")
            self.day = day
        record = {"received_at_utc": received_at.isoformat(), "connection_id": self.connection_id,
                  "raw_message": message}
        self.handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        try:
            payload = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            payload = None
        messages = payload if isinstance(payload, list) else [payload]
        token_index = {}
        for slug, game in self.catalog.items():
            for side, token in game.get("outcome_tokens", {}).items():
                token_index[token.get("token_id")] = (slug, game, side, token)
        normalized = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            kind = item.get("event_type") or item.get("type")
            changes = item.get("price_changes") if kind == "price_change" else None
            for change in (changes if isinstance(changes, list) else [item]):
                asset = change.get("asset_id") or item.get("asset_id") or item.get("assetId")
                context = token_index.get(str(asset))
                if not context:
                    continue
                slug, game, side, token = context
                bids, asks = item.get("bids", []), item.get("asks", [])
                bid = max((float(x["price"]) for x in bids), default=None) if bids else None
                ask = min((float(x["price"]) for x in asks), default=None) if asks else None
                if kind == "best_bid_ask":
                    bid = float(item["best_bid"]) if item.get("best_bid") not in (None, "") else None
                    ask = float(item["best_ask"]) if item.get("best_ask") not in (None, "") else None
                row = {"received_at_utc": received_at.isoformat(), "connection_id": self.connection_id,
                       "event_type": kind, "asset_id": str(asset), "slug": slug,
                       "espn_game_id": game.get("espn_game_id"), "outcome_side": side,
                       "outcome": token.get("outcome"), "server_timestamp": item.get("timestamp"),
                       "best_bid": bid, "best_ask": ask,
                       "midpoint": (bid + ask) / 2 if bid is not None and ask is not None else None,
                       "spread": ask - bid if bid is not None and ask is not None else None}
                if kind == "price_change":
                    row.update({"price": change.get("price"), "size": change.get("size"),
                                "side": change.get("side"), "best_bid": change.get("best_bid", bid),
                                "best_ask": change.get("best_ask", ask)})
                elif kind == "last_trade_price":
                    row.update({"price": item.get("price"), "size": item.get("size"),
                                "side": item.get("side"), "transaction_hash": item.get("transaction_hash")})
                try:
                    bid_num, ask_num = float(row["best_bid"]), float(row["best_ask"])
                    row["midpoint"], row["spread"] = (bid_num + ask_num) / 2, ask_num - bid_num
                except (TypeError, ValueError):
                    row["midpoint"], row["spread"] = None, None
                normalized.append(row)
        if normalized:
            for row in normalized:
                self.normalized.write(json.dumps(row, separators=(",", ":")) + "\n")
        self.count += 1
        if self.count % 100 == 0:
            self.handle.flush()
            if self.normalized:
                self.normalized.flush()

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        if self.normalized is not None:
            self.normalized.close()
            self.normalized = None


async def run_collector(once: bool = False, smoke_seconds: int | None = None) -> None:
    session = requests.Session()
    catalog = await asyncio.to_thread(discover, session)
    def active_markets() -> dict[str, dict]:
        instant = now_utc()
        return {slug: market for slug, market in catalog.items()
                if instant - timedelta(hours=8) <= pd_timestamp(market["scheduled_start_utc"])
                <= instant + timedelta(hours=36)}

    tracked = active_markets()
    assets = {v["token_id"] for m in tracked.values() for v in m["outcome_tokens"].values()}
    if not assets:
        log_event("no_assets_discovered")
        if once:
            return
    connection_id = stamp()
    writer = WebSocketRawWriter(connection_id, tracked)
    try:
        async with websockets.connect(WS, ping_interval=None, max_size=None,
                                      open_timeout=30, close_timeout=10) as ws:
            if assets:
                await ws.send(json.dumps({"assets_ids": sorted(assets), "type": "market",
                                          "custom_feature_enabled": True}))
            log_event("websocket_connected", connection_id=connection_id, assets=len(assets))
            started = time.monotonic()
            last_discovery = started
            last_poll = started
            last_ping = started
            poll_task = None
            while True:
                now_mono = time.monotonic()
                if now_mono - last_ping >= 9:
                    await ws.send("PING")
                    last_ping = now_mono
                if now_mono - last_discovery >= DISCOVER_SECONDS:
                    catalog = await asyncio.to_thread(discover, requests.Session())
                    tracked = active_markets()
                    writer.catalog = tracked
                    latest_assets = {v["token_id"] for m in tracked.values()
                                     for v in m["outcome_tokens"].values()}
                    new_assets = latest_assets - assets
                    if new_assets:
                        await ws.send(json.dumps({"assets_ids": sorted(new_assets),
                                                  "operation": "subscribe",
                                                  "custom_feature_enabled": True}))
                        assets.update(new_assets)
                        log_event("websocket_assets_subscribed", connection_id=connection_id,
                                  new_assets=len(new_assets), total_assets=len(assets))
                    last_discovery = now_mono
                if now_mono - last_poll >= POLL_SECONDS and (poll_task is None or poll_task.done()):
                    poll_task = asyncio.create_task(asyncio.to_thread(poll_wallet_trades, tracked.copy()))
                    last_poll = now_mono
                if once and poll_task is None and now_mono - started >= 2:
                    poll_task = asyncio.create_task(asyncio.to_thread(poll_wallet_trades, tracked.copy()))
                if once and poll_task is not None and poll_task.done():
                    break
                if smoke_seconds is not None and now_mono - started >= smoke_seconds:
                    break
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    writer.append(message, now_utc())
                except asyncio.TimeoutError:
                    pass
            if poll_task and not poll_task.done():
                await poll_task
            log_event("websocket_disconnected_cleanly", connection_id=connection_id,
                      assets=len(assets))
    except Exception as exc:
        log_event("websocket_error", connection_id=connection_id, error=repr(exc))
        raise
    finally:
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="discover and collect one trade poll, then exit")
    parser.add_argument("--smoke-seconds", type=int, help="run a bounded live capture for this many seconds")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            asyncio.run(run_collector(once=args.once, smoke_seconds=args.smoke_seconds))
            if args.once or args.smoke_seconds is not None:
                return
        except KeyboardInterrupt:
            log_event("collector_stopped_by_keyboard_interrupt")
            return
        except Exception as exc:
            log_event("collector_restart_after_error", error=repr(exc))
            if args.once or args.smoke_seconds is not None:
                raise
            time.sleep(10)


if __name__ == "__main__":
    main()
