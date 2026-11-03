"""Fetch a stratified wallet-market Activity sample for position validation.

This is a feasibility/coverage audit, not a representative estimate of trader
types. Every raw page is cached before parsing so the sample is reproducible.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
P6 = ROOT / "data/interim/phase6"
RAW = ROOT / "data/raw/polymarket/activity_wallet_market_sample"
PAGE = 500
SAMPLE_PER_CELL = 3


def target_pairs(p6_dir=P6, start_rank=0, sample_per_cell=SAMPLE_PER_CELL):
    target = pd.read_parquet(p6_dir / "polymarket_wallet_late5_target_trades.parquet")
    target["wallet"] = target.wallet.astype(str).str.lower()
    target["month"] = pd.to_datetime(target.timestamp, unit="s", utc=True).dt.strftime("%Y-%m")
    # Mutually exclusive, observable sampling strata; not identity labels.
    target["profile_stratum"] = "other"
    target.loc[target.maker_record_share.le(.25).fillna(False), "profile_stratum"] = "taker_dominant"
    target.loc[target.maker_record_share.ge(.75).fillna(False), "profile_stratum"] = "maker_dominant"
    target.loc[target.high_activity_ge_20_per_active_day.fillna(False), "profile_stratum"] = "high_activity"
    target.loc[target.low_activity_low_stake_proxy.fillna(False), "profile_stratum"] = "low_activity_low_stake"
    # One wallet-market pair per cell. Stable hash ordering makes selection fixed.
    pairs = target[["wallet", "conditionId", "game_id", "month", "role", "profile_stratum"]].drop_duplicates()
    pairs["sort_key"] = pairs.apply(lambda r: hashlib.sha256(
        f"{r.wallet}|{r.conditionId}|{r.role}|{r.profile_stratum}".encode()).hexdigest(), axis=1)
    selected = []
    for (_, _, role), cell in pairs.groupby(["month", "profile_stratum", "role"], sort=True):
        selected.append(cell.sort_values("sort_key").iloc[start_rank:start_rank + sample_per_cell])
    if selected:
        pairs = pd.concat(selected, ignore_index=True).drop_duplicates(["wallet", "conditionId"])
    # A ranked follow-on draw must be disjoint from the original feasibility
    # sample even if a wallet-market pair appears in multiple role cells.
    original_design = P6 / "polymarket_wallet_history_sample_design.csv"
    if start_rank > 0 and p6_dir.resolve() != P6.resolve() and original_design.exists():
        original = pd.read_csv(original_design)
        excluded = set(zip(original.wallet.astype(str).str.lower(),
                           original.conditionId.astype(str).str.lower()))
        pairs = pairs.loc[~pairs.apply(
            lambda r: (str(r.wallet).lower(), str(r.conditionId).lower()) in excluded,
            axis=1)].copy()
    return pairs.drop(columns="sort_key").reset_index(drop=True)


def fetch_pair(session, wallet, condition, raw_dir=RAW):
    folder = raw_dir / wallet
    folder.mkdir(parents=True, exist_ok=True)
    rows, offset = [], 0
    while True:
        path = folder / f"{condition}_off{offset}.json"
        if path.exists():
            page = json.loads(path.read_text())
        else:
            params = {"user": wallet, "market": condition, "limit": PAGE, "offset": offset}
            for attempt in range(8):
                response = session.get("https://data-api.polymarket.com/activity", params=params, timeout=45)
                if response.status_code == 429 or response.status_code >= 500:
                    time.sleep(min(30, 2 ** attempt))
                    continue
                response.raise_for_status()
                page = response.json()
                if not isinstance(page, list):
                    raise RuntimeError(f"Unexpected Activity payload for {wallet}/{condition}")
                path.write_text(json.dumps(page, separators=(",", ":")))
                time.sleep(.1)
                break
            else:
                raise RuntimeError(f"Activity API retries exhausted for {wallet}/{condition}/{offset}")
        rows.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
        if offset > 20000:
            raise RuntimeError(f"Wallet-market pagination unexpectedly large: {wallet}/{condition}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p6-dir", type=Path, default=P6)
    parser.add_argument("--raw-dir", type=Path, default=RAW)
    parser.add_argument("--start-rank", type=int, default=0)
    parser.add_argument("--per-cell", type=int, default=SAMPLE_PER_CELL)
    args = parser.parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    sample = target_pairs(args.p6_dir, args.start_rank, args.per_cell)
    sample.to_csv(args.p6_dir / "polymarket_wallet_history_sample_design.csv", index=False)
    session = requests.Session()
    audit, ledger = [], []
    for i, pair in sample.iterrows():
        rows = fetch_pair(session, pair.wallet, str(pair.conditionId), args.raw_dir)
        types = {}
        for row in rows:
            kind = str(row.get("type", "")).upper()
            types[kind] = types.get(kind, 0) + 1
            ledger.append({**row, "sample_wallet": pair.wallet,
                           "sample_condition_id": pair.conditionId,
                           "sample_game_id": pair.game_id,
                           "sample_role": pair.role,
                           "sample_profile_stratum": pair.profile_stratum,
                           "sample_month": pair.month})
        audit.append({"wallet": pair.wallet, "conditionId": pair.conditionId,
                      "game_id": pair.game_id, "role": pair.role,
                      "profile_stratum": pair.profile_stratum, "month": pair.month,
                      "rows": len(rows), "types": json.dumps(types, sort_keys=True),
                      "first_timestamp": min((int(x["timestamp"]) for x in rows), default=None),
                      "last_timestamp": max((int(x["timestamp"]) for x in rows), default=None)})
        if (i + 1) % 10 == 0:
            print(f"Fetched {i+1}/{len(sample)} wallet-market histories", flush=True)
    pd.DataFrame(audit).to_csv(args.p6_dir / "polymarket_wallet_history_sample_audit.csv", index=False)
    pd.DataFrame(ledger).to_parquet(args.p6_dir / "polymarket_wallet_history_sample.parquet", index=False)
    print(json.dumps({"wallet_market_pairs": len(sample), "activity_rows": len(ledger),
                      "types": pd.Series([r["type"] for r in ledger]).value_counts().to_dict(),
                      "pairs_with_transfer_or_conversion": int(sum(
                          any(k in r["types"] for k in ['TRANSFER', 'CONVERSION']) for r in audit)),
                      "raw_cache": str(args.raw_dir)}, indent=2))


if __name__ == "__main__":
    main()
