"""Plot the project-designated quiet-stoppage estimate and cost sensitivity."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/interim/phase5/phase5_primary_costs.json"
OUT = ROOT / "figures/phase5/quiet_stoppage_estimate_cost_sensitivity.pdf"


def main() -> None:
    result = json.loads(DATA.read_text())
    full = result["primary_full_sample"]
    valid = result["quote_valid_subset"]
    rows = [
        ("Project-designated outcome: gross gap", full, "A"),
        ("Quote-valid subset: gross gap", valid, "A"),
        ("Quote-valid subset: gap less taker fee + half-spread", valid, "net_taker_large"),
    ]
    labels, points, lows, highs, counts = [], [], [], [], []
    for label, sample, key in rows:
        est = sample["estimates"][key]
        labels.append(label)
        points.append(est["estimate"] * 100)
        lows.append(est["ci95"][0] * 100)
        highs.append(est["ci95"][1] * 100)
        counts.append(f"{sample['trades']:,} trade rows; {sample['games']} games")

    fig, ax = plt.subplots(figsize=(10.0, 4.4))
    fig.subplots_adjust(left=0.36, right=0.98, top=0.86, bottom=0.22)
    y = list(range(len(rows)))[::-1]
    for i, (yi, point, lo, hi) in enumerate(zip(y, points, lows, highs)):
        color = "#173f5f" if i == 0 else "#3caea3" if i == 1 else "#ed553b"
        ax.errorbar(point, yi, xerr=[[point - lo], [hi - point]], fmt="o",
                    color=color, ecolor=color, capsize=4, elinewidth=2,
                    markersize=7, zorder=3)
        ax.text(5.35, yi, counts[i], va="center", ha="left", fontsize=8.5,
                color="#444444")
    ax.axvline(0, color="#333333", linewidth=1.2, linestyle="--")
    ax.set_yticks(y, labels)
    ax.set_xlim(-2.2, 9.2)
    ax.set_xticks([-2, 0, 2, 4, 6, 8])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel("Longshot price minus realized payout (percentage points per $1 contract)")
    ax.set_title("Quiet-stoppage longshot gap: estimate and cost sensitivity", loc="left", pad=14)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.grid(axis="x", color="#dddddd", linewidth=0.7, zorder=0)
    fig.text(0.36, 0.04,
             "Dots show estimates; bars are 95% game-cluster bootstrap intervals. Exact estimator and filter chronology is unverified.",
             ha="left", va="bottom", fontsize=8.5, color="#444444")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight")
    fig.savefig(OUT.with_suffix(".png"), dpi=240, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
