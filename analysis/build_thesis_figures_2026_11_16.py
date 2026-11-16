"""Build thesis Figures 1–3 from saved analysis outputs.

Only the retrospective equal-game interval is newly bootstrapped, as requested.
All outcome gaps use A = price - payoff (p - Y), in percentage points.
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures" / "thesis"
OUT.mkdir(parents=True, exist_ok=True)
PHASE5 = ROOT / "data" / "interim" / "phase5"
DRAW_CI_PATH = PHASE5 / "retrospective_equal_game_ci_for_figures.json"

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 10,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def prelec(p: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    return np.exp(-beta * np.exp(alpha * np.log(-np.log(p))))


def bootstrap_retrospective_equal_game(game_values: np.ndarray, saved_point_a_pp: float) -> dict:
    # Source is the saved game-level retrospective selection diagnostic, the same
    # 561-game sample as the pooled retrospective estimate in Figure 3.
    vals = -100 * np.asarray(game_values, dtype=float)
    draws = 2000
    seed = 9142026
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(vals), size=(draws, len(vals)))
    boot = vals[indices].mean(axis=1)
    result = {
        "estimand": "equal game weight A in the retrospective window",
        "A_convention": "A = price - payoff (p - Y), percentage points",
        "estimate_pp": float(saved_point_a_pp),
        "ci95_pp": [float(v) for v in np.quantile(boot, [0.025, 0.975])],
        "games": int(len(vals)),
        "draws": draws,
        "seed": seed,
        "bootstrap_unit": "game, sampled with replacement; mean recomputed in each draw",
        "source_values": "data/interim/phase5/phase5_crossfit_selection_diagnostic_games.csv; window_minutes=10, price_band=05_20, coordinate=price, bin_width=0.05; 561 retrospective-window games",
    }
    DRAW_CI_PATH.write_text(json.dumps(result, indent=2) + "\n")
    return result


def save_figure(fig: plt.Figure, stem: str) -> None:
    # Do not use bbox_inches="tight": the requested output width is exactly 6.5 in.
    fig.savefig(OUT / f"{stem}.png", dpi=300, facecolor="white")
    fig.savefig(OUT / f"{stem}.pdf", facecolor="white")
    plt.close(fig)


def figure1(manifest: dict) -> None:
    bins_path = PHASE5 / "phase5a_bootstrap_bins.csv"
    bins = pd.read_csv(bins_path)
    bins = bins.loc[bins.version.eq("d_full_regular_season")].sort_values("cent").copy()
    if len(bins) != 99:
        raise ValueError(f"Expected 99 calibration bins; found {len(bins)}")

    x = bins.p.to_numpy(float)
    y = bins.raw_rate.to_numpy(float)
    pgrid = np.linspace(0.001, 0.999, 501)
    own = prelec(pgrid, 1.526, 1.196)
    moshrefi = prelec(pgrid, 1.516, 1.182)

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.plot([0, 1], [0, 1], color="#666666", linestyle=(0, (2, 2)), linewidth=1.4,
            label="Diagonal (price equals win rate)", zorder=1)
    ax.plot(pgrid, own, color="#111111", linewidth=2.0,
            label="Fitted Prelec curve, this thesis", zorder=2)
    ax.plot(pgrid, moshrefi, color="#555555", linewidth=1.8, linestyle=(0, (5, 2)),
            label="Moshrefi (2026), her sample", zorder=2)
    ax.scatter(x, y, s=22, marker="o", facecolor="#9a9a9a", edgecolor="#222222",
               linewidth=0.45, label="Binned win rates", zorder=3)
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Trade price", ylabel="Win rate")
    ax.set_xticks(np.arange(0, 1.01, 0.2))
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.grid(color="#d8d8d8", linewidth=0.55)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="#b0b0b0")
    fig.tight_layout()
    save_figure(fig, "figure1_retrospective_window_calibration")

    binned = pd.DataFrame({"trade_price": x, "observed_win_rate": y,
                           "trade_count": bins.n.astype(int).to_numpy()})
    binned.to_csv(OUT / "figure1_calibration_bins.csv", index=False)
    curves = pd.DataFrame({"trade_price": pgrid, "my_prelec_curve": own,
                           "moshrefi_2026_her_sample": moshrefi,
                           "diagonal": pgrid})
    curves.to_csv(OUT / "figure1_calibration_curves.csv", index=False)
    manifest["figure1"] = {
        "source": str(bins_path.relative_to(ROOT)),
        "sample": "2,524,781 trades; 1,202 games; d_full_regular_season calibration version",
        "binned_win_rate": "raw_rate from each of 99 saved bins; no interval displayed",
        "own_prelec": {"alpha": 1.526, "beta": 1.196, "source": "user-specified fitted parameters"},
        "moshrefi_prelec": {"alpha": 1.516, "beta": 1.182, "label": "Moshrefi (2026), her sample"},
        "all_bin_values_csv": "figure1_calibration_bins.csv",
        "curve_values_csv": "figure1_calibration_curves.csv",
    }


def figure2(manifest: dict) -> pd.DataFrame:
    path = ROOT / "data" / "interim" / "phase5" / "phase5_paired_window_game_differences.csv"
    all_games = pd.read_csv(path)
    comp = "10-minute realized-end vs final-five regulation clock"
    full = all_games.loc[all_games.comparison.eq(comp) & ~all_games.overtime_games_excluded.astype(bool)].copy()
    non_ot = all_games.loc[all_games.comparison.eq(comp) & all_games.overtime_games_excluded.astype(bool)]
    ot_ids = set(full.game_id.astype(str)) - set(non_ot.game_id.astype(str))
    full["game_id"] = full.game_id.astype(str)
    full["overtime"] = full.game_id.isin(ot_ids)
    if len(full) != 557 or int(full.overtime.sum()) != 51:
        raise ValueError(f"Expected 557 paired games with 51 overtime games; got {len(full)}, {int(full.overtime.sum())}")
    full["retrospective_window_A_pp"] = -full.retrospective_y_minus_p_pp
    full["final_five_regulation_minutes_A_pp"] = -full.clock_window_y_minus_p_pp

    fig, ax = plt.subplots(figsize=(6.5, 5.0))
    n_ot = full.overtime.to_numpy(bool)
    xx = full.retrospective_window_A_pp.to_numpy(float)
    yy = full.final_five_regulation_minutes_A_pp.to_numpy(float)
    ax.scatter(xx[~n_ot], yy[~n_ot], s=27, marker="o", color="#b7b7b7", alpha=0.58,
               edgecolor="#333333", linewidth=0.35, label="Non-overtime games", zorder=2)
    ax.scatter(xx[n_ot], yy[n_ot], s=40, marker="^", color="#555555", alpha=0.82,
               edgecolor="#111111", linewidth=0.45, label="Overtime games", zorder=3)
    ax.plot([-100, 30], [-100, 30], color="#111111", linestyle=(0, (5, 2)), linewidth=1.2,
            label="Equal gaps", zorder=1)
    ax.set(xlim=(-100, 30), ylim=(-100, 30),
           xlabel="Gap in retrospective window (percentage points)",
           ylabel="Gap in final five regulation minutes (percentage points)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(color="#dedede", linewidth=0.55)
    ax.set_axisbelow(True)
    # This left-side pocket is empty in the requested crop and does not cross
    # the equal-gaps diagonal or any plotted point.
    ax.legend(loc="center", bbox_to_anchor=(0.23, 0.64), frameon=True,
              facecolor="white", edgecolor="#b0b0b0")
    fig.tight_layout()
    save_figure(fig, "figure2_paired_games_window_gaps")

    points = full[["game_id", "overtime", "retrospective_window_A_pp", "final_five_regulation_minutes_A_pp"]]
    points.to_csv(OUT / "figure2_paired_game_points.csv", index=False)
    manifest["figure2"] = {
        "source": str(path.relative_to(ROOT)),
        "sample": "557 paired games; 51 overtime games and 506 non-overtime games",
        "sign_conversion": "Saved y - p game gaps multiplied by -1 to plot A = p - Y",
        "all_plotted_game_values_csv": "figure2_paired_game_points.csv",
    }
    return full


def figure3(manifest: dict) -> None:
    audit = read_json(PHASE5 / "fresh_results_audit_2026_11_10.json")
    additional = read_json(PHASE5 / "additional_estimands_2026_11_10.json")
    sim = read_json(PHASE5 / "fair_pricing_null_simulation_2026_11_10.json")["NBA"]["estimators"]
    quiet_df = pd.read_csv(PHASE5 / "phase5_weighting" / "phase5_weighting_estimators.csv")
    quiet = quiet_df.loc[(quiet_df.window == "Primary final 5 quiet") &
                         (quiet_df.source == "Market") & (quiet_df.metric == "A")].set_index("estimator")

    # group, estimator label, window label, point, low, high, trade count, game count, simulation mean, sample description
    rows = []
    full = audit["N2_full_game_baseline"]
    first_full = audit["G1_full_game_first_entry"]
    rows.extend([
        [1, "pooled trades", "full game", full["trade_weighted_A_pp"], *full["trade_weighted_CI95_pp"], full["trades"], full["trades"], full["games"], sim["full_pooled"]["mean_A_pp"], "saved full-game 5–20¢ longshot sample; no P* support screen"],
        [1, "pooled trades", "final five regulation minutes", audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["trade_weighted_A_pp"], *audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["trade_weighted_CI95_pp"], audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["trades"], audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["trades"], audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["games"], sim["final5_pooled"]["mean_A_pp"], "final-five sample with P* common support"],
        [1, "pooled trades", "quiet stoppages", 100*quiet.loc["trade_weighted", "estimate"], 100*quiet.loc["trade_weighted", "ci95_low"], 100*quiet.loc["trade_weighted", "ci95_high"], int(quiet.loc["trade_weighted", "trades"]), int(quiet.loc["trade_weighted", "trades"]), int(quiet.loc["trade_weighted", "games"]), np.nan, "primary final-five quiet sample; market A; no fair-pricing simulation estimate"],
        [1, "first trade per game", "full game", first_full["A_pp"], *first_full["CI95_pp"], first_full["eligible_trade_rows_in_full_game_population"], first_full["trades"], first_full["games"], sim["full_first_trade"]["mean_A_pp"], "saved full-game 5–20¢ longshot sample; no P* support screen; one first trade per game"],
        [1, "first trade per game", "final five regulation minutes", audit["G1_final5_Pstar_first_entry"]["A_pp"], *audit["G1_final5_Pstar_first_entry"]["CI95_pp"], audit["G1_final5_Pstar_first_entry"]["eligible_trades"], audit["G1_final5_Pstar_first_entry"]["first_entry_trades"], audit["G1_final5_Pstar_first_entry"]["games"], sim["final5_first_trade"]["mean_A_pp"], "final-five sample with P* common support; one first trade per game"],
        [1, "first trade per game", "quiet stoppages", 100*quiet.loc["first_entry", "estimate"], 100*quiet.loc["first_entry", "ci95_low"], 100*quiet.loc["first_entry", "ci95_high"], int(quiet.loc["first_entry", "trades"]), int(quiet.loc["first_entry", "games"]), int(quiet.loc["first_entry", "games"]), np.nan, "primary final-five quiet sample; market A; one first trade per game; no fair-pricing simulation estimate"],
        [1, "fixed clock sampling", "final five regulation minutes", additional["3_fixed_game_clock_sampling"]["with_Pstar"]["overall_all_sampled_trades"]["pooled_A_pp"], *additional["3_fixed_game_clock_sampling"]["with_Pstar"]["overall_all_sampled_trades"]["pooled_CI95_pp"], additional["3_fixed_game_clock_sampling"]["with_Pstar"]["overall_all_sampled_trades"]["trades"], additional["3_fixed_game_clock_sampling"]["with_Pstar"]["overall_all_sampled_trades"]["trades"], additional["3_fixed_game_clock_sampling"]["with_Pstar"]["overall_all_sampled_trades"]["games"], sim["final5_fixed_clock"]["mean_A_pp"], "final-five sample with P* common support; pooled sampled observations"],
        [2, "equal game weight", "full game", full["equal_game_A_pp"], *full["equal_game_CI95_pp"], full["trades"], full["games"], full["games"], sim["full_equal_game"]["mean_A_pp"], "saved full-game 5–20¢ longshot sample; no P* support screen"],
        [2, "equal game weight", "final five regulation minutes", audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["equal_game_A_pp"], *audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["equal_game_CI95_pp"], audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["trades"], audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["games"], audit["N6_final5_weighting_sensitivity"]["Pstar_common_support_market_yes"]["games"], sim["final5_equal_game"]["mean_A_pp"], "final-five sample with P* common support"],
        [2, "equal game weight", "quiet stoppages", 100*quiet.loc["game_weighted", "estimate"], 100*quiet.loc["game_weighted", "ci95_low"], 100*quiet.loc["game_weighted", "ci95_high"], int(quiet.loc["game_weighted", "trades"]), int(quiet.loc["game_weighted", "games"]), int(quiet.loc["game_weighted", "games"]), np.nan, "primary final-five quiet sample; market A; no fair-pricing simulation estimate"],
    ])

    retro_diag = read_json(PHASE5 / "phase5_crossfit_selection_diagnostic.json")["coordinates"]["05_20_10m_price_0.050"]
    retro_point = -100 * retro_diag["observed_gap"]
    retro_ci = [-100 * retro_diag["observed_gap_ci95"][1],
                -100 * retro_diag["observed_gap_ci95"][0]]
    selection_audit = read_json(PHASE5 / "phase5_selection_inference_audit.json")["kalshi"]["observed_gap"]["equal_game"]
    retro_equal_point_a = -100 * selection_audit["estimate"]
    game_values = pd.read_csv(PHASE5 / "phase5_crossfit_selection_diagnostic_games.csv")
    game_values = game_values.loc[(game_values.window_minutes == 10) &
                                  (game_values.price_band == "05_20") &
                                  (game_values.coordinate == "price") &
                                  (game_values.bin_width == 0.05)]
    if len(game_values) != 561:
        raise ValueError(f"Expected 561 saved retrospective game values; got {len(game_values)}")
    equal_retro_ci = bootstrap_retrospective_equal_game(game_values.observed_gap.to_numpy(float), retro_equal_point_a)
    rows.extend([
        [3, "pooled trades", "retrospective window", retro_point, *retro_ci, int(retro_diag["trades"]), int(retro_diag["trades"]), int(retro_diag["games"]), sim["retro10m_pooled"]["mean_A_pp"], "saved retrospective sample with market and P* common support"],
        [3, "equal game weight", "retrospective window", equal_retro_ci["estimate_pp"], *equal_retro_ci["ci95_pp"], int(retro_diag["trades"]), equal_retro_ci["games"], equal_retro_ci["games"], sim["retro10m_equal_game"]["mean_A_pp"], "saved retrospective sample with market and P* common support; newly computed 2,000-draw game bootstrap interval"],
    ])
    cols = ["group", "estimator", "window", "estimate_pp", "ci95_low_pp", "ci95_high_pp", "eligible_trade_rows", "estimator_observations", "games", "simulation_mean_pp", "sample_definition"]
    df = pd.DataFrame(rows, columns=cols)

    fig, ax = plt.subplots(figsize=(7.5, 6.4))
    group_titles = {
        1: "Fixed at the time of the trade",
        2: "Equal game weight",
        3: "Retrospective window",
    }
    y_positions = {}
    # Leave the first group's top-right area for the legend, with the group
    # heading occupying only the left margin.
    y = 0.0
    group_bounds = {}
    for group in [1, 2, 3]:
        sub = df.loc[df.group.eq(group)]
        y += 0.72
        group_bounds[group] = y
        for idx in sub.index:
            y_positions[idx] = y
            y += 0.78
        y += 0.26
    legend_space_bottom = y + 0.15

    # Horizontal scale is in percentage points; cap kept wide enough for all intervals.
    ax.axvline(0, color="#333333", linewidth=1.2, linestyle=(0, (3, 2)), zorder=1)
    for idx, row in df.iterrows():
        yp = y_positions[idx]
        ax.hlines(yp, row.ci95_low_pp, row.ci95_high_pp, color="#333333", linewidth=1.6, zorder=2)
        ax.vlines([row.ci95_low_pp, row.ci95_high_pp], yp-0.095, yp+0.095, color="#333333", linewidth=1.0, zorder=2)
        ax.scatter(row.estimate_pp, yp, marker="o", s=34, color="#111111", zorder=3)
        if np.isfinite(row.simulation_mean_pp):
            ax.scatter(row.simulation_mean_pp, yp+0.20, marker="D", s=34, facecolor="white",
                       edgecolor="#111111", linewidth=1.25, zorder=4)

    labels = []
    for _, r in df.iterrows():
        if r.group == 2:
            labels.append(r.window)
        elif r.group == 3:
            labels.append(r.estimator)
        else:
            labels.append(f"{r.estimator}, {r.window}")
    ax.set_yticks([y_positions[i] for i in df.index], labels)
    ax.invert_yaxis()
    ax.set_ylim(legend_space_bottom, -0.75)
    ax.set_xlabel("Gap (percentage points)")
    ax.set_xlim(-8.5, 11.0)
    ax.grid(axis="x", color="#dddddd", linewidth=0.55)
    ax.set_axisbelow(True)
    fig.subplots_adjust(left=0.61, right=0.98, top=0.98, bottom=0.29)
    # Align each heading with the left edge of the longest row label. Measure
    # after the tick labels are laid out so the alignment follows their actual
    # rendered width rather than a guessed offset.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    leftmost_label_px = min(label.get_window_extent(renderer).x0 for label in ax.get_yticklabels())
    heading_x = ax.transAxes.inverted().transform((leftmost_label_px, 0))[0]
    for group, ytop in group_bounds.items():
        ax.text(heading_x, ytop-0.30, group_titles[group], transform=ax.get_yaxis_transform(),
                ha="left", va="bottom", fontsize=10, fontweight="bold")
        if group > 1:
            ax.axhline(ytop-0.50, color="#c6c6c6", linewidth=0.8)
    legend = [
        Line2D([0], [0], color="#333333", marker="o", markersize=5, linewidth=1.6,
               label="Estimate and 95% interval"),
        Line2D([0], [0], color="none", marker="D", markerfacecolor="white",
               markeredgecolor="#111111", markersize=6, label="Basketball simulation mean"),
        Line2D([0], [0], color="#333333", linestyle=(0, (3, 2)), linewidth=1.2, label="Zero gap"),
        Line2D([0], [0], color="none", marker=None, label="No simulation for quiet stoppages"),
    ]
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, 0.07), ncol=2,
               frameon=True, facecolor="white", edgecolor="#b0b0b0", columnspacing=1.4,
               handletextpad=0.6, labelspacing=0.5)
    save_figure(fig, "figure3_nba_estimates_and_simulation")
    df.to_csv(OUT / "figure3_estimates_and_intervals.csv", index=False)
    manifest["figure3"] = {
        "A_convention": "A = p - Y; percentage points",
        "sample_note": "P* common support is used for final five regulation minutes estimates; the saved full-game longshot estimates do not have that support restriction; quiet stoppage results use their saved primary sample.",
        "all_estimates_and_intervals_csv": "figure3_estimates_and_intervals.csv",
        "retrospective_equal_game_ci_json": str(DRAW_CI_PATH.relative_to(ROOT)),
        "simulation": "Basketball base scenario, fair_pricing_null_simulation_2026_11_10.json; diamond marks the saved mean for estimators available in that simulation; no quiet-stoppage marks.",
        "rows": df.to_dict(orient="records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure3-only", action="store_true",
                        help="Regenerate Figure 3 without rewriting final Figures 1 and 2")
    args = parser.parse_args()
    manifest_path = OUT / "figure_values_manifest.json"
    if args.figure3_only and manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {
            "created_by": "analysis/build_thesis_figures_2026_11_16.py",
            "format": {"png_dpi": 300, "width_inches": 6.5, "pdf": True, "titles_inside_figures": False},
            "plot_convention": "A = p - Y for outcome-gap figures; Figure 1 plots win rate against trade price.",
        }
    if not args.figure3_only:
        figure1(manifest)
        figure2(manifest)
    figure3(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote figures and plotted-value files under {OUT}")
    print(f"Wrote newly computed interval to {DRAW_CI_PATH}")


if __name__ == "__main__":
    main()
