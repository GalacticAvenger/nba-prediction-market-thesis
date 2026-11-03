"""Build deduplicated maker/taker tables from prospective Data API raw caches."""
from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from common import ROOT

RAW = ROOT / "data/raw/polymarket/prospective/trade_api"
OUT = ROOT / "data/interim/phase6/prospective"
PATTERN = re.compile(r"^(all|taker)_(\d+)_(\d+)_off(\d+)_.*\.json\.gz$")


def key(row: dict) -> tuple:
    return (str(row.get("transactionHash", "")).lower(),
            str(row.get("proxyWallet", "")).lower(), str(row.get("asset", "")),
            round(float(row.get("size", 0) or 0), 10),
            round(float(row.get("price", 0) or 0), 10))


def load_cache() -> tuple[dict, dict]:
    roles: dict[str, dict[str, list[dict]]] = {}
    for path in RAW.glob("*/*.json.gz"):
        match = PATTERN.match(path.name)
        if not match:
            continue
        role = match.group(1)
        slug = path.parent.name
        try:
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, EOFError, json.JSONDecodeError):
            # Atomic cache writes mean this should only be a legacy/incomplete file.
            continue
        if isinstance(payload, list):
            roles.setdefault(slug, {"all": [], "taker": []})[role].extend(payload)
    return roles, json.loads((OUT / "market_catalog.json").read_text()).get("markets", {})


def dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        k = key(row)
        if k not in seen:
            seen.add(k)
            out.append(dict(row))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    roles, catalog = load_cache()
    makers, takers, summaries = [], [], []
    for slug, captured in sorted(roles.items()):
        all_rows, taker_rows = dedupe(captured["all"]), dedupe(captured["taker"])
        counts = Counter(key(row) for row in taker_rows)
        maker_rows = []
        taker_by_tx = {}
        for row in taker_rows:
            tx = str(row.get("transactionHash", "")).lower()
            if tx:
                taker_by_tx.setdefault(tx, row)
        for row in all_rows:
            k = key(row)
            if counts[k]:
                counts[k] -= 1
            else:
                tx = str(row.get("transactionHash", "")).lower()
                taker = taker_by_tx.get(tx, {})
                maker_rows.append({**row, "takerWallet": taker.get("proxyWallet"),
                                   "takerSide": taker.get("side"),
                                   "taker_identity_linked": bool(taker.get("proxyWallet"))})
        market = catalog.get(slug, {})
        for row in maker_rows:
            makers.append({**row, "slug": slug, "espn_game_id": market.get("espn_game_id")})
        for row in taker_rows:
            takers.append({**row, "slug": slug, "espn_game_id": market.get("espn_game_id")})
        summaries.append({"slug": slug, "raw_all_rows": len(captured["all"]),
                          "unique_all_rows": len(all_rows), "unique_taker_rows": len(taker_rows),
                          "maker_rows": len(maker_rows),
                          "maker_rows_missing_taker_identity": sum(not r["taker_identity_linked"] for r in maker_rows)})
    pd.DataFrame(makers).to_parquet(OUT / "wallet_maker_fills.parquet", index=False)
    pd.DataFrame(takers).to_parquet(OUT / "wallet_taker_fills.parquet", index=False)
    (OUT / "trade_materialization_summary.json").write_text(json.dumps({
        "markets_with_cache": len(summaries), "maker_rows": len(makers),
        "taker_rows": len(takers), "markets": summaries
    }, indent=2) + "\n")
    print(f"materialized {len(makers)} maker and {len(takers)} taker rows across {len(summaries)} markets")


if __name__ == "__main__":
    main()
