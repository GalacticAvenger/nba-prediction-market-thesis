# Prospective Polymarket NBA study protocol

Status: protocol drafted before persistent collection began. Short smoke
captures and first-poll records used to validate the collector are pipeline
checks and are excluded from the confirmatory cohort. Do not call the result
preregistered unless this file is timestamped/archived with the advisor before
examining new-season outcomes. Exclude games with incomplete capture from the
confirmatory cohort; retain them only for pipeline validation.

## Question

Does the late-game longshot calibration gap appear in Polymarket executable
prices, in midpoint prices, or both; and are pre-existing wallet behavior
profiles associated with subsequent midpoint movements relative to a
market-independent NBA win-probability benchmark?

The study may estimate source-associated order flow. Public wallet addresses do
not reveal verified human/algorithmic status, retail/professional status, or
intent. Profile names must describe observed behavior only.

## Population and collection

- Census of Polymarket NBA single-game moneyline markets matched to the
  2026–27 ESPN regular-season schedule, from the first date with complete
  capture through the end of the regular season.
- Match each game using the ESPN event ID, away/home teams, scheduled tip time,
  and the Gamma market slug. Select only the two-outcome `moneyline` market;
  do not mix spreads, totals, player props, or exact-margin markets.
- Capture full L2 order-book snapshots and updates, best-bid/ask updates,
  last-trade events, server timestamps, and local receipt timestamps from the
  public Polymarket market WebSocket. Cache raw messages losslessly as gzip
  JSONL and write a parallel normalized quote-event JSONL stream with token,
  game, outcome, best bid/ask, midpoint, spread, and available trade fields.
- Poll the public Polymarket Data API on a fixed interval for wallet-linked
  trades, retaining raw responses, request bounds, retries, and per-market
  watermarks. `make phase6-prospective-materialize` deterministically rebuilds
  deduplicated maker/taker parquet tables from the gzip response cache. It
  subtracts taker records from the all-trades endpoint using transaction,
  wallet, asset, size, and price; it links maker records to the transaction's
  taker wallet where available. Deduplicate overlaps only in derived analysis
  files; never delete raw responses.
- Collect ESPN scoreboard/play-by-play timestamps and final outcomes for
  matchup and game-state alignment. Record data gaps, reconnects, delayed API
  indexing, and all exclusions.

## Completeness rule

A game is eligible for the primary quote analysis only if the collector was
connected before tip, the ESPN match/outcome mapping is unambiguous, and both
outcome books have valid two-sided quotes no more than five seconds old for at
least 95% of eligible quiet-stoppage observations in the final-five regulation
minutes. Evaluate coverage on a one-second UTC wall-time grid over the Phase 4
clean-timeout intervals (the Phase 2 first-shot/rebound/turnover restart anchor,
five-second end buffer, and Phase 4 exclusions for score/review/challenge and
foul/free-throw activity); both outcomes must have uncrossed quotes satisfying
`0 < bid < ask < 1`, with each latest BBO update received within the preceding
five seconds. Do not forward-fill through invalid updates or interpolate gaps.
Freeze this rule before outcome analysis. Report the full census flow diagram
and quote coverage.

## Primary measurements

1. **Midpoint calibration:** Within Phase 4-defined quiet stoppages in the
   final five regulation minutes and the 5–20¢ longshot midpoint band, compare
   longshot midpoint with the realized longshot outcome. Weight games equally;
   bootstrap games. This is the prospective venue-level estimate most directly
   comparable with the Kalshi registered estimand.
2. **Execution-price decomposition:** For every wallet-linked fill, compare
   execution price with the nearest *prior* valid same-token midpoint, using a
   quote-age tolerance frozen before outcome analysis. Report execution-minus-
   midpoint separately from midpoint-minus-outcome. This separates a trade
   print/spread component from a quote-level calibration gap; it does not
   establish executable profit after fees or market impact.
3. **Participant-flow replication:** Freeze the existing pre-game behavior
   profile rules and test the previously observed limited-prior-history
   signed-flow association at a single 30-second game-clock horizon using the
   main P* benchmark. The primary coefficient is limited-history signed
   home-direction shares divided by all same-bin taker shares, predicting the
   next consecutive-bin change in midpoint-minus-P*, conditional on initial
   gap, P* change, game fixed effects, and within-game-clock-bin effects.
   Cluster uncertainty by game. Use possession-adjusted and spline-logistic P*
   as named robustness benchmarks. Other profile/horizon comparisons are
   exploratory and corrected as a family.

## Benchmark and profile timing

- Freeze the NBA P* model, training seasons, and outcome-blind feature set
  before analyzing the prospective markets. Report held-out-season Brier score
  and calibration. Never train on Polymarket prices or the target season's
  outcomes.
- For each wallet/game, compute profile features strictly before that game's
  first play. Exclude all activity in the target game, including pre-tip
  activity. Prefer continuous prior-game counts, active-day rate, and historical
  maker/taker record shares alongside the frozen coarse categories.
- Call categories `limited prior history`, `high prior activity`,
  `maker-record dominant`, `taker-record dominant`, and `established mixed`.
  Do not call any group bots, retail traders, professionals, informed traders,
  or market makers.

## Analysis and reporting rules

- Primary inference is game weighted; fills are not independent observations.
- Define the market-window and quote-age rule before outcome-linked analysis.
- Publish sample counts, raw/derived data dictionaries, capture completeness,
  and all benchmark variants, including null results.
- The flow analysis is predictive association, not causal source attribution.
  Causal attribution would require exogenous flow variation or another
  defensible identification design.
- This Polymarket study can test whether the behavior is present at Polymarket;
  by itself it cannot identify the source of the Kalshi estimate.

## Start-of-collection caveat

The 2026–27 NBA season began shortly before this protocol was prepared. The
confirmatory cohort begins with the first game whose continuous capture starts
before tip and passes the completeness rule. Earlier games can be backfilled
for descriptive work but must remain outside the prospective primary cohort
unless order-book coverage and wallet-trade completeness are independently
demonstrated.
