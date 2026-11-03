"""Reconcile cached Polymarket Activity histories to winning-token redemptions.

This is a deliberately small pilot: ten wallets in one V1 NBA market. It does
not establish season-wide inventory completeness or validate loser-token
balances, but it checks whether user-level trades and merges recover payouts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_polymarket_selection_analysis import canonical, token_map  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/polymarket/activity_probe_oct21"
MAP = ROOT / "data/interim/phase2/polymarket_nba_2025_26_market_map.json"
OUT = ROOT / "data/interim/phase6"
MARKET_SLUG = "nba-hou-okc-2025-10-21"
TOL = 1e-5


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    markets = json.loads(MAP.read_text())["markets"]
    market = next(m for m in markets if m["slug"] == MARKET_SLUG)
    gamma_market = next(
        x for x in market["gamma_event"]["markets"]
        if str(x.get("conditionId", "")).lower() == str(market["condition_id"]).lower())
    outcomes = json.loads(gamma_market["outcomes"])
    winner = canonical(market["resolved_winner_abbreviation"])
    by_team = token_map(market)
    winner_token = by_team.get(winner)
    token_to_outcome = dict(zip(
        map(str, json.loads(gamma_market["clobTokenIds"])), outcomes))
    winner_label = token_to_outcome.get(str(winner_token))
    if winner_label is None:
        raise RuntimeError("Could not match the resolved winner to a Gamma outcome")

    result = []
    unsupported = []
    for path in sorted(RAW.glob("*.json")):
        rows = json.loads(path.read_text())
        wallet = path.stem.lower()
        q = [r for r in rows if str(r.get("conditionId", "")).lower()
             == str(market["condition_id"]).lower()]
        q.sort(key=lambda r: (int(r.get("timestamp", 0)), str(r.get("transactionHash", ""))))
        holdings = {str(outcome): 0.0 for outcome in outcomes}
        changes = []
        redemptions = []
        types = {}
        for r in q:
            kind = str(r.get("type", "")).upper()
            types[kind] = types.get(kind, 0) + 1
            qty = float(r.get("size") or 0.0)
            if kind == "TRADE":
                outcome = str(r.get("outcome", ""))
                side = str(r.get("side", "")).upper()
                if outcome not in holdings or side not in {"BUY", "SELL"}:
                    unsupported.append({"wallet": wallet, "type": kind,
                                        "reason": "unmapped trade outcome or side"})
                    continue
                delta = qty if side == "BUY" else -qty
                holdings[outcome] += delta
                changes.append({"timestamp": int(r["timestamp"]), "type": kind,
                                "outcome": outcome, "delta": delta,
                                "transactionHash": r.get("transactionHash")})
            elif kind == "SPLIT":
                for outcome in holdings:
                    holdings[outcome] += qty
                    changes.append({"timestamp": int(r["timestamp"]), "type": kind,
                                    "outcome": outcome, "delta": qty,
                                    "transactionHash": r.get("transactionHash")})
            elif kind == "MERGE":
                for outcome in holdings:
                    holdings[outcome] -= qty
                    changes.append({"timestamp": int(r["timestamp"]), "type": kind,
                                    "outcome": outcome, "delta": -qty,
                                    "transactionHash": r.get("transactionHash")})
            elif kind == "REDEEM":
                redemptions.append({"timestamp": int(r["timestamp"]), "size": qty,
                                    "outcome": str(r.get("outcome", ""))})
            elif kind in {"CONVERSION", "TRANSFER"}:
                unsupported.append({"wallet": wallet, "type": kind,
                                    "reason": "position effect not implemented in this pilot"})

        winner_pre_redeem = holdings.get(winner_label)
        redeemed_winner = sum(r["size"] for r in redemptions
                              if r["outcome"] == winner_label)
        has_redeem = any(r["outcome"] == winner_label for r in redemptions)
        diff = (winner_pre_redeem - redeemed_winner) if has_redeem else None
        result.append({
            "wallet": wallet,
            "activity_rows": len(q),
            "activity_types": json.dumps(types, sort_keys=True),
            "first_activity_ts": min((int(r["timestamp"]) for r in q), default=None),
            "last_activity_ts": max((int(r["timestamp"]) for r in q), default=None),
            "winner_outcome": winner_label,
            "net_winner_tokens_before_redemption": winner_pre_redeem,
            "reported_winner_redemption_size": redeemed_winner if has_redeem else None,
            "winner_balance_minus_redemption": diff,
            "redemption_matches_within_tolerance": bool(has_redeem and abs(diff) <= TOL),
            "other_outcome_balance_before_redemption": holdings.get(
                outcomes[1] if outcomes[0] == winner_label else outcomes[0]),
            "activity_without_redemption": not has_redeem,
            "account_has_market_history_starting_at_zero_assumed": True,
        })
    out = pd.DataFrame(result)
    out.to_csv(OUT / "polymarket_wallet_position_pilot_oct21.csv", index=False)
    summary = {
        "market": MARKET_SLUG,
        "condition_id": market["condition_id"],
        "wallets": int(len(out)),
        "wallets_with_winner_redemption": int((~out.activity_without_redemption).sum()),
        "winner_redemption_matches_within_1e-5": int(out.redemption_matches_within_tolerance.sum()),
        "activity_rows": int(out.activity_rows.sum()),
        "activity_type_totals": {
            kind: int(sum(json.loads(x).get(kind, 0) for x in out.activity_types))
            for kind in sorted({k for x in out.activity_types for k in json.loads(x)})
        },
        "unsupported_event_rows": unsupported,
        "limitations": [
            "Ten cached wallets from one resolved V1 market; not a random season-wide validation sample.",
            "Assumes no unobserved initial position at first account activity.",
            "Does not process ERC-1155 wallet transfers or validate losing-token redemption/burns.",
            "The activity API redemption amount is compared with the account's net winning-token trades and merges; a match supports this path but does not validate all position pathways.",
        ],
    }
    (OUT / "polymarket_wallet_position_pilot_oct21.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
