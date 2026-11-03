"""Reuse the audited additive decomposition for transaction-style profiles."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import phase6_wallet_gap_decomposition as decomposition  # noqa: E402

decomposition.INPUT = (ROOT / "data/interim/phase6/prior_game_behavior/"
                       "execution_style/target_buys_with_execution_styles.parquet")
decomposition.OUT = (ROOT / "data/interim/phase6/prior_game_behavior/"
                     "execution_style/gap_decomposition")
decomposition.PROFILE_COLUMN = "execution_style_profile"
decomposition.PROFILE_ORDER = [
    "limited_prior_history", "rapid_cycle_proxy",
    "large_ticket_low_frequency_proxy", "other_observed_style",
]

if __name__ == "__main__":
    decomposition.main()
