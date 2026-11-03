"""Exploratory account-profile order-flow and benchmark-adjusted price dynamics.

This asks whether signed Polymarket taker flow from observable, pre-game
account profiles predicts the next in-game minute's change in market price
relative to P*. It is a predictive association, not a causal price-impact
estimate: trades are endogenous and no order-book midquote is available.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
P2 = ROOT / "data/interim/phase2"
P3 = ROOT / "data/interim/phase3"
P6 = ROOT / "data/interim/phase6"
OUT = P6 / "taker_flow_impact"
MAKER = P2 / "polymarket_maker_fills_season_raw.parquet"
TAKER = P2 / "polymarket_taker_rows_season.parquet"
PSTAR = P3 / "pstar_2025_26_every_second.parquet"
MARKET_MAP = P2 / "polymarket_nba_2025_26_market_map.json"
PROFILES = P6 / "prior_game_behavior/wallet_game_prior_profiles.csv"


def load_token_map() -> dict[str, dict[str, str]]:
    markets = json.loads(MARKET_MAP.read_text())["markets"]
    out: dict[str, dict[str, str]] = {}
    for market in markets:
        game = str(market["espn_game_id"])
        gamma = market["gamma_event"]
        nested = next((m for m in gamma.get("markets", [])
                       if str(m.get("conditionId", "")).lower()
                       == str(market["condition_id"]).lower()), None)
        if nested is None:
            continue
        outcomes = json.loads(nested["outcomes"])
        token_ids = list(map(str, json.loads(nested["clobTokenIds"])))
        token_by_team = {}
        for outcome, token in zip(outcomes, token_ids):
            for t in market["gamma_event"].get("teams", []):
                if outcome in {t.get("name"), t.get("alias"), t.get("abbreviation")}:
                    token_by_team[str(t.get("abbreviation", "")).upper()] = token
        home, away = str(market["home_team"]).upper(), str(market["away_team"]).upper()
        if home in token_by_team and away in token_by_team:
            out[game] = {"home_token": token_by_team[home], "away_token": token_by_team[away]}
    return out


PSTAR_VARIANTS = ("pstar", "pstar_with_possession", "pstar_spline_logistic")


def make_pstar_lookup() -> dict[tuple[str, int], tuple[np.ndarray, dict[str, np.ndarray]]]:
    p = pd.read_parquet(PSTAR, columns=["game_id", "period", "clock_s_remaining", *PSTAR_VARIANTS, "is_home"])
    p = p.loc[p.is_home.astype(bool)].copy()
    p["game_id"] = p.game_id.astype(str)
    p["period"] = pd.to_numeric(p.period, errors="coerce")
    p["clock_s_remaining"] = pd.to_numeric(p.clock_s_remaining, errors="coerce")
    for col in PSTAR_VARIANTS:
        p[col] = pd.to_numeric(p[col], errors="coerce")
    out = {}
    for (game, period), z in p.dropna().groupby(["game_id", "period"], sort=False):
        z = z.sort_values("clock_s_remaining", ascending=False)
        out[(game, int(period))] = (z.clock_s_remaining.to_numpy(float),
                                    {col: z[col].to_numpy(float) for col in PSTAR_VARIANTS})
    return out


def pstar_at(lookup, game: str, period: int, clock: float) -> dict[str, float]:
    grid = lookup.get((game, period))
    if grid is None or not np.isfinite(clock):
        return {col: np.nan for col in PSTAR_VARIANTS}
    clocks, probs_by_variant = grid
    # The P* grid is one second. Use nearest second, matching the other thesis analyses.
    ix = int(np.searchsorted(-clocks, -round(float(clock)), side="left"))
    return {col: float(probs[min(max(ix, 0), len(probs) - 1)])
            for col, probs in probs_by_variant.items()}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    token_map = load_token_map()
    print(f"mapped {len(token_map)} games to home/away outcome tokens", flush=True)

    # The maker activity file includes the market-clock mapping for the same
    # transaction/token; the taker activity file identifies the initiating wallet.
    mk = pd.read_parquet(MAKER, columns=["transactionHash", "espn_game_id", "asset", "period", "clock_s_remaining"])
    for c in ("transactionHash", "asset"):
        mk[c] = mk[c].astype(str).str.lower()
    mk["espn_game_id"] = mk.espn_game_id.astype(str)
    mk["period"] = pd.to_numeric(mk.period, errors="coerce")
    mk["clock_s_remaining"] = pd.to_numeric(mk.clock_s_remaining, errors="coerce")
    clock_map = mk.dropna(subset=["period", "clock_s_remaining"]).groupby(
        ["transactionHash", "asset"], sort=False).agg(
            game_id=("espn_game_id", "first"), period=("period", "first"),
            clock_s_remaining=("clock_s_remaining", "first")).reset_index()
    del mk

    taker = pd.read_parquet(TAKER, columns=["transactionHash", "proxyWallet", "side", "asset", "size", "price", "timestamp", "espn_game_id"])
    for c in ("transactionHash", "asset", "proxyWallet"):
        taker[c] = taker[c].astype(str).str.lower()
    taker["game_id"] = taker.espn_game_id.astype(str)
    for c in ("size", "price", "timestamp"):
        taker[c] = pd.to_numeric(taker[c], errors="coerce")
    taker = taker.merge(clock_map, on=["transactionHash", "asset"], how="inner", suffixes=("", "_clock"), validate="many_to_one")
    # Preserve the fill's own game ID, but reject inconsistent transaction joins.
    taker = taker.loc[taker.game_id.eq(taker.game_id_clock)].copy()
    n_taker_clock_join = int(len(taker))
    taker["period"] = pd.to_numeric(taker.period, errors="coerce")
    taker["clock_s_remaining"] = pd.to_numeric(taker.clock_s_remaining, errors="coerce")
    taker = taker.dropna(subset=["period", "clock_s_remaining", "price", "size", "timestamp"])
    taker = taker.loc[taker["size"].gt(0) & taker.price.between(0, 1, inclusive="neither")]
    taker["period"] = taker.period.astype(int)
    taker["asset"] = taker.asset.astype(str)
    taker["side"] = taker.side.str.upper()
    taker = taker.loc[taker.game_id.isin(token_map)].copy()
    taker["home_token"] = taker.game_id.map({g: v["home_token"] for g, v in token_map.items()})
    taker["away_token"] = taker.game_id.map({g: v["away_token"] for g, v in token_map.items()})
    taker = taker.loc[taker.asset.isin(taker.home_token) | taker.asset.isin(taker.away_token)].copy()
    taker["is_home_token"] = taker.asset.eq(taker.home_token)
    taker["home_price"] = np.where(taker.is_home_token, taker.price, 1 - taker.price)
    taker["signed_home_shares"] = taker["size"] * np.where(taker.side.eq("BUY"), 1., -1.) * np.where(taker.is_home_token, 1., -1.)

    profiles = pd.read_csv(PROFILES, dtype={"game_id": str})
    profiles["wallet"] = profiles.wallet.astype(str).str.lower()
    profiles["game_id"] = profiles.game_id.astype(str)
    profiles = profiles[["wallet", "game_id", "prior_behavior_profile"]].drop_duplicates(["wallet", "game_id"])
    taker = taker.merge(profiles, left_on=["proxyWallet", "game_id"], right_on=["wallet", "game_id"], how="left", validate="many_to_one")
    taker["prior_behavior_profile"] = taker.prior_behavior_profile.fillna("limited_prior_history")

    pstar = make_pstar_lookup()
    pstar_rows = [pstar_at(pstar, g, p, c) for g, p, c in zip(taker.game_id, taker.period, taker.clock_s_remaining)]
    for col in PSTAR_VARIANTS:
        taker[f"{col}_home"] = [r[col] for r in pstar_rows]
    taker = taker.dropna(subset=[f"{PSTAR_VARIANTS[0]}_home"])
    n_taker_with_pstar = int(len(taker))
    # Focus on final five regulation minutes, the thesis's principal ex-ante window.
    taker = taker.loc[taker.period.eq(4) & taker.clock_s_remaining.between(0, 300)].copy()
    for variant in PSTAR_VARIANTS:
        home_col = f"{variant}_home"
        taker[f"price_error_{variant}"] = taker.home_price - taker[home_col]
        own_pstar = np.where(taker.is_home_token, taker[home_col], 1 - taker[home_col])
        own_error = taker.price - own_pstar
        taker[f"own_price_error_{variant}"] = own_error
        taker[f"benchmark_adverse_trade_{variant}"] = (
            (taker.side.eq("BUY") & own_error.gt(0))
            | (taker.side.eq("SELL") & own_error.lt(0)))
    # Preserve the primary benchmark's historical column names in existing outputs.
    taker["pstar_home"] = taker[f"{PSTAR_VARIANTS[0]}_home"]
    taker["price_error"] = taker[f"price_error_{PSTAR_VARIANTS[0]}"]
    taker["own_price_error"] = taker[f"own_price_error_{PSTAR_VARIANTS[0]}"]
    taker["benchmark_adverse_trade"] = taker[f"benchmark_adverse_trade_{PSTAR_VARIANTS[0]}"]
    taker["flow_shares"] = taker.signed_home_shares
    taker["total_shares"] = taker["size"]

    # Descriptive profile-level flow accounting. Share-weighted net flow is in
    # home-probability direction; benchmark and realized outcomes are separate.
    profile_rows = []
    for profile, z in taker.groupby("prior_behavior_profile", sort=True):
        profile_rows.append({
            "profile": profile, "taker_records": int(len(z)),
            "wallets": int(z.proxyWallet.nunique()), "games": int(z.game_id.nunique()),
            "share_of_records": float(len(z) / len(taker)),
            "share_of_traded_shares": float(z["size"].sum() / taker["size"].sum()),
            "net_home_direction_shares": float(z.signed_home_shares.sum()),
            "net_home_flow_share_of_all_shares": float(z.signed_home_shares.sum() / taker["size"].sum()),
            "mean_own_token_price_minus_pstar_pp": float(z.own_price_error.mean() * 100),
            "share_buys_overpriced_or_sells_underpriced": float(z.benchmark_adverse_trade.mean()),
            "share_volume_buys_overpriced_or_sells_underpriced": float(
                z.loc[z.benchmark_adverse_trade, "size"].sum() / z["size"].sum()),
        })
    pd.DataFrame(profile_rows).to_csv(OUT / "profile_flow_summary.csv", index=False)

    profile_names = sorted(taker.prior_behavior_profile.unique())
    regression_rows = []
    joint_tests = []
    panel_counts = {}
    panels = []
    # 30-, 60-, and 120-second game-clock bins test short and more persistent
    # benchmark-adjusted price response on a common, predetermined time scale.
    for horizon in (30, 60, 120):
        key = f"bucket_{horizon}s"
        taker[key] = np.floor((300 - taker.clock_s_remaining) / horizon).clip(
            0, int(np.ceil(300 / horizon)) - 1).astype(int)
        group_keys = ["game_id", "period", key]
        flow = taker.pivot_table(index=group_keys, columns="prior_behavior_profile",
            values="signed_home_shares", aggfunc="sum", fill_value=0).reset_index()
        flow.columns = [str(c) for c in flow.columns]
        total = taker.groupby(group_keys, as_index=False).agg(total_shares=("size", "sum"))
        marks = taker.sort_values(["timestamp", "transactionHash"], kind="stable").groupby(
            group_keys, as_index=False).tail(1)[group_keys + ["home_price", "pstar_home", "price_error"]]
        panel = flow.merge(total, on=group_keys, validate="one_to_one").merge(
            marks, on=group_keys, validate="one_to_one")
        panel = panel.sort_values(["game_id", "period", key])
        panel["next_price_error"] = panel.groupby(["game_id", "period"]).price_error.shift(-1)
        panel["next_pstar"] = panel.groupby(["game_id", "period"]).pstar_home.shift(-1)
        panel["next_price"] = panel.groupby(["game_id", "period"]).home_price.shift(-1)
        panel["next_bucket"] = panel.groupby(["game_id", "period"])[key].shift(-1)
        panel = panel.loc[panel.next_bucket.eq(panel[key] + 1)].copy()
        panel["delta_price_error"] = panel.next_price_error - panel.price_error
        panel["delta_pstar"] = panel.next_pstar - panel.pstar_home
        panel["delta_market_price"] = panel.next_price - panel.home_price
        panel["initial_error"] = panel.price_error
        for name in profile_names:
            panel[f"flow_{name}"] = panel.get(name, 0) / panel.total_shares
        panel["horizon_game_clock_seconds"] = horizon
        panels.append(panel)
        panel_counts[str(horizon)] = {"consecutive_buckets": int(len(panel)),
                                      "games": int(panel.game_id.nunique())}

    # Include all disjoint profiles jointly; cluster uncertainty by game.
        # Profile flows are compositional and sum to one in each bin. Omit
        # limited-history flow as the reference to avoid perfect collinearity
        # with the intercept and fixed effects.
        reference_profile = "limited_prior_history"
        flow_profiles = [name for name in profile_names if name != reference_profile]
        flow_cols = [f"flow_{name}" for name in flow_profiles]
        formula = ("delta_price_error ~ " + " + ".join(flow_cols)
                   + f" + delta_pstar + initial_error + C(game_id) + C({key})")
        fit = smf.ols(formula, data=panel).fit(
            cov_type="cluster", cov_kwds={"groups": panel.game_id}, method="qr")
        for name, col in zip(flow_profiles, flow_cols):
            ci = fit.conf_int().loc[col]
            regression_rows.append({
                "horizon_game_clock_seconds": horizon, "profile": name,
                "flow_measure": f"signed home-direction shares by profile / all taker shares in {horizon}-second game-clock bin",
                "outcome": f"next consecutive {horizon}-second-bin change in last-trade home price minus P*",
                "coef": float(fit.params[col]), "se_game_cluster": float(fit.bse[col]),
                "ci95_low": float(ci.iloc[0]), "ci95_high": float(ci.iloc[1]),
                "p_value": float(fit.pvalues[col]), "n_game_bins": int(fit.nobs),
                "games": int(panel.game_id.nunique()), "r_squared": float(fit.rsquared),
            })
        joint = fit.wald_test(", ".join(f"{col} = 0" for col in flow_cols), scalar=True)
        joint_tests.append({"horizon_game_clock_seconds": horizon,
            "null": "all four non-reference profile flow coefficients are zero",
            "statistic": float(np.asarray(joint.statistic).squeeze()),
            "p_value": float(joint.pvalue), "df_num": int(len(flow_cols)),
            "games": int(panel.game_id.nunique()), "n_game_bins": int(fit.nobs)})

    adjusted = multipletests([r["p_value"] for r in regression_rows], method="holm")[1]
    for row, p_adj in zip(regression_rows, adjusted):
        row["p_value_holm_12_tests"] = float(p_adj)
    pd.DataFrame(regression_rows).to_csv(OUT / "profile_flow_forward_regressions.csv", index=False)
    pd.concat(panels, ignore_index=True).to_csv(OUT / "profile_flow_forward_panels.csv", index=False)

    # Benchmark sensitivity: keep the exact same matched taker fills, profiles,
    # flow bins and game-clock horizons; only replace the estimated P* series.
    sensitivity_rows = []
    sensitivity_joint = []
    for variant in PSTAR_VARIANTS:
        for horizon in (30, 60, 120):
            key = f"bucket_{horizon}s"
            group_keys = ["game_id", "period", key]
            flow = taker.pivot_table(index=group_keys, columns="prior_behavior_profile",
                values="signed_home_shares", aggfunc="sum", fill_value=0).reset_index()
            flow.columns = [str(c) for c in flow.columns]
            total = taker.groupby(group_keys, as_index=False).agg(total_shares=("size", "sum"))
            marks = taker.sort_values(["timestamp", "transactionHash"], kind="stable").groupby(
                group_keys, as_index=False).tail(1)[group_keys + ["home_price", f"{variant}_home"]]
            marks = marks.rename(columns={f"{variant}_home": "benchmark"})
            panel = flow.merge(total, on=group_keys, validate="one_to_one").merge(
                marks, on=group_keys, validate="one_to_one")
            panel = panel.sort_values(["game_id", "period", key])
            panel["error"] = panel.home_price - panel.benchmark
            by_game = panel.groupby(["game_id", "period"])
            panel["next_error"] = by_game.error.shift(-1)
            panel["next_benchmark"] = by_game.benchmark.shift(-1)
            panel["next_bucket"] = by_game[key].shift(-1)
            panel = panel.loc[panel.next_bucket.eq(panel[key] + 1)].copy()
            panel["delta_error"] = panel.next_error - panel.error
            panel["delta_benchmark"] = panel.next_benchmark - panel.benchmark
            panel["initial_error"] = panel.error
            for name in profile_names:
                panel[f"flow_{name}"] = panel.get(name, 0) / panel.total_shares
            reference_profile = "limited_prior_history"
            flow_profiles = [name for name in profile_names if name != reference_profile]
            flow_cols = [f"flow_{name}" for name in flow_profiles]
            formula = ("delta_error ~ " + " + ".join(flow_cols)
                       + f" + delta_benchmark + initial_error + C(game_id) + C({key})")
            model = smf.ols(formula, data=panel)
            if not np.isfinite(model.exog).all() or not np.isfinite(model.endog).all():
                bad_columns = model.exog_names[
                    ~np.isfinite(model.exog).all(axis=0)].tolist()
                raise ValueError(
                    f"Non-finite regression design: benchmark={variant}, "
                    f"horizon={horizon}, columns={bad_columns}, "
                    f"bad outcomes={int((~np.isfinite(model.endog)).sum())}")
            fit = model.fit(cov_type="cluster", cov_kwds={"groups": panel.game_id}, method="qr")
            for name, col in zip(flow_profiles, flow_cols):
                ci = fit.conf_int().loc[col]
                sensitivity_rows.append({
                    "benchmark": variant, "horizon_game_clock_seconds": horizon,
                    "profile": name, "coef": float(fit.params[col]),
                    "se_game_cluster": float(fit.bse[col]),
                    "ci95_low": float(ci.iloc[0]), "ci95_high": float(ci.iloc[1]),
                    "p_value": float(fit.pvalues[col]), "n_game_bins": int(fit.nobs),
                    "games": int(panel.game_id.nunique()), "r_squared": float(fit.rsquared)})
            joint = fit.wald_test(", ".join(f"{col} = 0" for col in flow_cols), scalar=True)
            sensitivity_joint.append({
                "benchmark": variant, "horizon_game_clock_seconds": horizon,
                "statistic": float(np.asarray(joint.statistic).squeeze()),
                "p_value": float(joint.pvalue), "df_num": len(flow_cols),
                "games": int(panel.game_id.nunique()), "n_game_bins": int(fit.nobs)})
    p_adj = multipletests([r["p_value"] for r in sensitivity_rows], method="holm")[1]
    for row, p in zip(sensitivity_rows, p_adj):
        row["p_value_holm_36_tests"] = float(p)
    joint_adjusted = multipletests([r["p_value"] for r in sensitivity_joint], method="holm")[1]
    for row, p in zip(sensitivity_joint, joint_adjusted):
        row["p_value_holm_9_tests"] = float(p)
    pd.DataFrame(sensitivity_rows).to_csv(OUT / "profile_flow_benchmark_sensitivity.csv", index=False)
    pd.DataFrame(sensitivity_joint).to_csv(OUT / "profile_flow_benchmark_joint_tests.csv", index=False)
    profile_benchmark_rows = []
    for profile, z in taker.groupby("prior_behavior_profile", sort=True):
        for variant in PSTAR_VARIANTS:
            profile_benchmark_rows.append({
                "profile": profile, "benchmark": variant,
                "mean_own_token_price_minus_benchmark_pp": float(z[f"own_price_error_{variant}"].mean() * 100),
                "share_buys_overpriced_or_sells_underpriced": float(z[f"benchmark_adverse_trade_{variant}"].mean()),
                "share_volume_buys_overpriced_or_sells_underpriced": float(
                    z.loc[z[f"benchmark_adverse_trade_{variant}"], "size"].sum() / z["size"].sum())})
    pd.DataFrame(profile_benchmark_rows).to_csv(OUT / "profile_flow_profile_benchmark_sensitivity.csv", index=False)

    summary = {
        "purpose": "Exploratory test of whether observable pre-game account-profile taker flow predicts subsequent Polymarket divergence from P* in final-five regulation minutes.",
        "taker_records_matched_to_transaction_clock": n_taker_clock_join,
        "taker_rows_with_pstar_and_token_map_before_final5_filter": n_taker_with_pstar,
        "final5_taker_rows": int(len(taker)),
        "games": int(taker.game_id.nunique()), "wallets": int(taker.proxyWallet.nunique()),
        "profile_categories": profile_names,
        "flow_regression_reference_profile": "limited_prior_history",
        "flow_coefficients": "four profile flow shares relative to omitted limited-history flow; flows sum to one",
        "consecutive_game_clock_bucket_counts": panel_counts,
        "profile_outcomes": profile_rows, "regressions": regression_rows,
        "joint_flow_tests": joint_tests,
        "interpretation_limits": [
            "Profiles are observable pre-game activity patterns, not bots, retail, professionals, or true market-maker identities.",
            "Taker flow is endogenous: informed traders may trade because prices or public information are changing.",
            "The outcome uses last transaction price, not an order-book midpoint; bid-ask bounce and liquidity changes may matter.",
            "P* is an estimated benchmark, not truth; alternate possession-adjusted and spline-logistic P* sensitivity is reported separately, and the profile regressions remain exploratory.",
            "This is Polymarket only and cannot attribute the Kalshi primary estimate.",
            "The regression is predictive association, not causal price impact. A causal claim requires exogenous flow variation or order-book/exogenous information data.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
