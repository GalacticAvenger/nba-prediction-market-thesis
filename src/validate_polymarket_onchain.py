"""Validate cached Polygon receipts against the Oct. 21 Data API and spotchecks."""
from __future__ import annotations

import glob
import json
from pathlib import Path

import pandas as pd

from common import ROOT, write_json

RAW = ROOT / "data/raw/polymarket"
OUT = ROOT / "data/interim/phase2"
MATCH_TOPICS = {
    "0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c": "v1",
    "0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c": "v2",
}
FILLED_V1 = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
V1_EXCHANGE = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
V2_EXCHANGE = "0xe111180000d2663c0091e4f400237545b87b996b"


def pages(pattern):
    out = []
    for path in glob.glob(str(RAW / pattern)):
        try:
            obj = json.loads(Path(path).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(obj, list):
            out.extend(r for r in obj if isinstance(r, dict))
    return out


def decode_match(log):
    topic = (log.get("topics") or [""])[0].lower()
    data = log["data"][2:]
    words = [int(data[i:i + 64], 16) for i in range(0, len(data), 64)]
    if MATCH_TOPICS[topic] == "v1":
        maker_asset, taker_asset, maker_amt, taker_amt = words[:4]
        if maker_asset:
            token, size, collateral, side = maker_asset, maker_amt, taker_amt, "SELL"
        else:
            token, size, collateral, side = taker_asset, taker_amt, maker_amt, "BUY"
    else:
        side_num, token, maker_amt, taker_amt = words[:4]
        side = "BUY" if side_num == 0 else "SELL"
        size, collateral = (taker_amt, maker_amt) if side_num == 0 else (maker_amt, taker_amt)
    return {"token": str(token), "size": size / 1e6, "price": collateral / size,
            "side": side, "taker_wallet": "0x" + log["topics"][2][-40:].lower(),
            "exchange_version": MATCH_TOPICS[topic]}


def cached_receipts():
    out = {}
    for path in glob.glob(str(RAW / "onchain_receipts/batch_*.json")):
        for item in json.loads(Path(path).read_text()):
            rec = item.get("result") or {}
            tx = rec.get("transactionHash")
            if tx:
                out[tx.lower()] = rec
    return out


def match_logs(receipt):
    return [log for log in receipt.get("logs", [])
            if (log.get("topics") or [""])[0].lower() in MATCH_TOPICS]


def row_matches(row, decoded):
    return (decoded["token"] == str(row["asset"])
            and decoded["side"] == row["side"]
            and abs(decoded["size"] - float(row["size"])) < 1e-6
            and abs(decoded["price"] - float(row["price"])) < 1e-7)


def test_oct21(receipts):
    rows = pages("trades_nba-hou-okc-2025-10-21_offset*.json")
    data = pd.DataFrame(rows).drop_duplicates(
        ["transactionHash", "proxyWallet", "asset", "size", "price", "timestamp"])
    pbp_files = glob.glob(str(ROOT / "data/interim/espn_pbp/season=2026/season_type=2/*.parquet"))
    pbp = pd.concat([pd.read_parquet(p, columns=["game_id", "ts_wall_utc"])
                     for p in pbp_files], ignore_index=True)
    pbp = pbp[(pbp.game_id.astype(str) == "401809243")].dropna(subset=["ts_wall_utc"])
    wall = pd.to_datetime(pbp.ts_wall_utc, utc=True)
    data["ts"] = pd.to_datetime(data.timestamp, unit="s", utc=True)
    live = data[(data.ts >= wall.min()) & (data.ts <= wall.max())]
    failures, missing, maker_fills = [], [], 0
    matched_taker_rows = 0
    for row in live.to_dict("records"):
        tx = row["transactionHash"].lower()
        receipt = receipts.get(tx)
        if not receipt:
            missing.append(tx)
            continue
        matches = [decode_match(l) for l in match_logs(receipt)]
        if any(row_matches(row, m) for m in matches):
            matched_taker_rows += 1
        else:
            failures.append(tx)
        # In V1, the exchange-address taker log is the aggregate taker order;
        # maker counterparties are the other OrderFilled logs in that transaction.
        maker_fills += sum(1 for l in receipt["logs"]
                           if (l.get("topics") or [""])[0].lower() == FILLED_V1
                           and len(l.get("topics", [])) > 3
                           and "0x" + l["topics"][3][-40:].lower() != V1_EXCHANGE)
    return {
        "test_event": "nba-hou-okc-2025-10-21",
        "data_api_rows_total": int(len(data)),
        "espn_wallclock_rows": int(len(pbp)),
        "in_game_data_api_taker_rows": int(len(live)),
        "unique_in_game_data_api_transactions": int(live.transactionHash.nunique()),
        "in_game_taker_rows_matched_on_token_side_size_price": matched_taker_rows,
        "unmatched_or_missing_receipts": len(failures) + len(missing),
        "maker_orderfilled_logs_in_those_transactions": maker_fills,
        "taker_ordersmatched_events": matched_taker_rows,
        "taker_fill_match_method": "exact transaction; token id, side, size (1e-6 shares), and price (1e-7)",
    }


def monthly_spotchecks():
    all_rows = pages("monthly_*_offset*.json") + pages("trades_nba-hou-okc-2025-10-21_offset*.json")
    by_tx = {r.get("transactionHash", "").lower(): r for r in all_rows if r.get("transactionHash")}
    results = []
    for path in sorted(glob.glob(str(RAW / "monthly_receipt_*.json"))):
        receipt = json.loads(Path(path).read_text()).get("result") or {}
        tx = receipt.get("transactionHash", "").lower()
        row = by_tx.get(tx)
        matches = [decode_match(l) for l in match_logs(receipt)]
        decoded = next((m for m in matches if row and row_matches(row, m)), None)
        results.append({
            "month": Path(path).stem.replace("monthly_receipt_", ""),
            "slug": row.get("slug") if row else None,
            "transaction_hash": tx,
            "polygonscan": f"https://polygonscan.com/tx/{tx}",
            "exchange_version": decoded["exchange_version"] if decoded else None,
            "data_api_side": row.get("side") if row else None,
            "decoded_side": decoded["side"] if decoded else None,
            "data_api_size": row.get("size") if row else None,
            "decoded_size": decoded["size"] if decoded else None,
            "data_api_price": row.get("price") if row else None,
            "decoded_price": decoded["price"] if decoded else None,
            "token_id_matches": bool(row and decoded and decoded["token"] == str(row["asset"])),
            "verified": bool(decoded),
        })
    return results


def main():
    receipts = cached_receipts()
    check = test_oct21(receipts)
    write_json(OUT / "polymarket_onchain_check.json", check)
    spots = monthly_spotchecks()
    write_json(OUT / "polymarket_monthly_spotchecks.json", spots)
    print(json.dumps(check, indent=2))
    print(f"Cross-month transaction spotchecks decoded: {sum(x['verified'] for x in spots)}/{len(spots)}")


if __name__ == "__main__":
    main()
