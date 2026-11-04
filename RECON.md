# Data sources and coverage

This file summarizes the sources used in the completed analyses and the main
limits on reproducing them from this repository.

## Sources

- **Kalshi:** Historical NBA game-market trade records, market metadata, and
  one-minute candles. The main trade analysis excludes block trades. The
  historical applicability of maker fees for this series could not be
  established from the available records.
- **NBA play-by-play:** ESPN game summaries provide play events, game-clock
  values, scores, and wall-clock timestamps for the 2025–26 season. The
  timestamps have one-second resolution; any common timing difference between
  ESPN and Kalshi remains unknown. The NBA CDN endpoint could not be accessed
  during collection, so it did not provide an independent timestamp check.
- **Polymarket:** Public Data API fills and selected Polygon receipts support
  the exploratory venue and wallet analyses. Wallet categories describe
  observed activity patterns only; they do not identify people, automation,
  skill, or intent.
- **Win-probability benchmark:** The market-independent NBA probability
  estimates are produced from historical play-by-play and are used where
  specified in the results. They are estimates, not known true probabilities.

## Reproduction limits

Raw inputs and large intermediate caches are not included. The repository
contains selected derived summaries, figures, and analysis code, but a full
rerun requires the original data files in the `data/raw/` and `data/interim/`
directory structure. The included `Makefile` targets expect those files to
exist; a fresh clone alone is not a complete reproduction environment. See
[`ANALYSIS_README.md`](ANALYSIS_README.md) and [`RESULTS.md`](RESULTS.md) for
the available outputs, methods, and remaining limitations.
