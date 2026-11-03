# Predictions for late-game longshot pricing mechanisms

This file preserves the pre-specified predictions. Later analysis corrections
in `DEVIATIONS.md` mark market-price-band `price - P*` tests uninterpretable;
those tests are not treated as supporting evidence in `RESULTS.md`.

## Scope and measurement

The analysis is restricted to two selection-free windows: the knowable window
(all in-game trades in the ten wall minutes following the first Q4 state at or
below 3:00, without game-end or overtime exclusions) and the final five
regulation game-clock minutes. Inclusion will not depend on a game's eventual
end time, overtime status, or any other future event. Outcomes are used only
for the requested `Y - price` checks and the stated exploitability calculation.
All probability and price
comparisons are folded to the longshot contract. The two requested price bands
are 0.05–0.20 and 0.10–0.40. No additional sample splits will be introduced.

The primary localization measure is the paired difference `price - P*` on the
same trade/market observation; `Y - price` is the outcome-based check. Mid
comparisons use only valid reconstructed mids requiring both quote sides.
Inference is clustered by game. Where an estimator comparison is requested,
first-entry and trade-weighted estimates are reported as specified.

## Mechanism predictions

### Slow tracking of clock decay

- In running-clock states, the longshot pricing gap should exceed the gap while
  the clock is stopped.
- `price - P*` should increase with `clock_decay` since the last event, after
  controlling for price bin.
- With no intervening event during running clock, price should move toward P*
  over the next 5, 15, and 30 seconds. The convergence should be clearest for
  observations with a larger initial `price - P*` gap. “By size” will be
  assessed continuously: signed convergence is regressed on the absolute
  initial gap, with no data-dependent gap bins.
- These within-game movements are the transitory component; a price gap that
  does not decay is not predicted by pure slow tracking.

### Microstructure

- The longshot residual should be visible in trade prices but substantially
  smaller or absent in valid mids.
- Trade-price overpricing should be concentrated in taker buys of the longshot
  relative to taker sells of the longshot.
- A gap that remains similar in mids and in both taker directions would not
  match the pure microstructure prediction.

### Behavioral pricing

- The longshot residual should persist while the clock is stopped and in valid
  mids, where clock decay is absent and the spread is removed.
- The residual should vary across the pre-specified game-state cells: remaining
  game-clock time (0–1, 1–2, 2–3, 3–5 minutes) and score margin (1–3, 4–6,
  7+) crossed with trailing-team possession (yes, no, unknown).
- This pattern is consistent with a persistent state-dependent component; these
  splits alone do not identify a specific behavioral channel or wallet motive.

## Polymarket comparison

If the same paired `price - P*` residual appears in the knowable and final-five
windows on Polymarket, the residual is not unique to Kalshi. If it is absent
there while present on Kalshi, that cross-venue contrast is consistent with a
venue-specific source. Polymarket results are read-only from the existing
fill-level parquet and use the same two longshot price bands.
