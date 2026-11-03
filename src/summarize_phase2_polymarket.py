"""Summarize cached Phase 2 Polymarket Data API pages and Polygon receipts."""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

from common import ROOT

RAW = ROOT / "data/raw/polymarket"
OUT = ROOT / "data/interim/phase2"
V1_ORDER_FILLED = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
V1_ORDERS_MATCHED = "0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c"
V2_ORDER_FILLED = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"


def read_pages(pattern: str) -> list[dict]:
    rows = []
    for path in glob.glob(str(RAW / pattern)):
        try:
            payload = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            rows.extend(payload)
    return rows


def game_window(game_id: str) -> tuple[float, float]:
    season_type = 3 if game_id.startswith(("401869", "401871", "401873", "401859")) else 2
    files = glob.glob(str(ROOT / f"data/interim/espn_pbp/season=2026/season_type={season_type}/*.parquet"))
    frame = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    frame = frame[(frame.game_id.astype(str) == game_id) & frame.ts_wall_utc.notna()]
    if frame.empty:
        raise ValueError(f"No cached wall-clock PBP for {game_id}")
    times = pd.to_datetime(frame.ts_wall_utc, utc=True)
    return times.min().timestamp(), times.max().timestamp()


def receipt_counts(receipt: dict, topics: set[str]) -> dict[str, int]:
    counts = {topic: 0 for topic in topics}
    for log in receipt.get("logs", []):
        topic = (log.get("topics") or [None])[0]
        if topic in counts:
            counts[topic] += 1
    return counts


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Full October test event.
    test_rows = read_pages("trades_nba-hou-okc-2025-10-21_offset*.json")
    test_unique = {r["transactionHash"]: r for r in test_rows}
    start, end = game_window("401809243")
    in_game = [r for r in test_unique.values() if start <= int(r["timestamp"]) <= end]
    onchain = {V1_ORDER_FILLED: 0, V1_ORDERS_MATCHED: 0}
    batches = glob.glob(str(RAW / "onchain_receipts/batch_*.json"))
    for path in batches:
        payload = json.loads(Path(path).read_text())
        for item in payload:
            receipt = item.get("result") or {}
            for log in receipt.get("logs", []):
                if log.get("address", "").lower() != "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e":
                    continue
                topic = (log.get("topics") or [None])[0]
                if topic in onchain:
                    onchain[topic] += 1

    test_result = {
        "test_event": "nba-hou-okc-2025-10-21",
        "data_api_rows": len(test_rows),
        "unique_transaction_hashes": len(test_unique),
        "in_game_rows": len(in_game),
        "unique_in_game_transaction_hashes": len({r["transactionHash"] for r in in_game}),
        "in_game_V1_OrderFilled_logs": onchain[V1_ORDER_FILLED],
        "in_game_V1_OrdersMatched_logs": onchain[V1_ORDERS_MATCHED],
    }
    (OUT / "polymarket_onchain_check.json").write_text(json.dumps(test_result, indent=2))

    gamma = json.loads((RAW / "gamma_event_nba-hou-okc-2025-10-21.json").read_text())
    market = gamma["markets"][0]
    closed_at = pd.Timestamp(market["closedTime"], tz="UTC") if "+" not in market["closedTime"] else pd.Timestamp(market["closedTime"])
    end_date = pd.Timestamp(market["endDate"])
    close_rows = [r for r in test_unique.values() if closed_at.timestamp() - 600 <= int(r["timestamp"]) <= closed_at.timestamp()]
    scheduled_end_rows = [r for r in test_unique.values() if end_date.timestamp() - 600 <= int(r["timestamp"]) <= end_date.timestamp()]
    (OUT / "polymarket_6a_lite_coverage.json").write_text(json.dumps({
        "test_event": "nba-hou-okc-2025-10-21",
        "pagination_complete": len(test_rows) == len(test_unique) == 6232,
        "data_api_rows": len(test_rows),
        "unique_transaction_hashes": len(test_unique),
        "market_closedTime": market["closedTime"],
        "final_10m_before_closedTime_rows": len(close_rows),
        "final_10m_before_scheduled_endDate_rows": len(scheduled_end_rows),
        "six_a_lite_fit": "not estimable: only one Data API row is in the final ten minutes before actual closedTime; endDate is scheduled tip-off and its final ten-minute window is pre-game."
    }, indent=2))

    # Monthly spot-check manifest is based on cached pages and one cached receipt
    # from each month. June is intentionally incomplete: offset 10001 is rejected.
    old_manifest = json.loads((OUT / "polymarket_monthly_spotchecks.json").read_text())
    monthly = []
    for old in old_manifest:
        slug = old["slug"]
        rows = read_pages(f"monthly_{slug}_offset*.json")
        if not rows and old["month"] == "2025-10":
            rows = read_pages(f"trades_{slug}_offset*.json")
        txs = {r["transactionHash"]: r for r in rows}
        begin, finish = game_window(str(old["game_id"]))
        live = [r for r in txs.values() if begin <= int(r["timestamp"]) <= finish]
        rec_path = RAW / f"monthly_receipt_{old['month']}.json"
        rec = json.loads(rec_path.read_text()).get("result") or {}
        counts = receipt_counts(rec, {V1_ORDER_FILLED, V2_ORDER_FILLED})
        row = {k: v for k, v in old.items() if k not in {
            "data_api_rows", "data_api_rows_observed", "in_game_rows", "in_game_rows_observed",
            "unique_in_game_tx", "unique_in_game_tx_observed", "spot_tx_orderfilled_logs",
            "data_api_complete"
        }}
        row["data_api_rows_observed"] = len(rows)
        row["in_game_rows_observed"] = len(live)
        row["unique_in_game_tx_observed"] = len({r["transactionHash"] for r in live})
        row["spot_tx_orderfilled_logs"] = counts[V1_ORDER_FILLED] + counts[V2_ORDER_FILLED]
        row["data_api_complete"] = old["month"] != "2026-06"
        monthly.append(row)
    (OUT / "polymarket_monthly_spotchecks.json").write_text(json.dumps(monthly, indent=2))
    print(json.dumps(test_result, indent=2))
    print(f"Monthly spot checks summarized: {len(monthly)}")


if __name__ == "__main__":
    main()
