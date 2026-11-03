# Phase 2 deviations and unresolved data issues

## Phase 4 amendments approved before Phase 5 outcomes (2026-10-21)

Before any outcome-based Phase 5 result was computed, Sam amended the locked plan:

1. The Phase 4 proposed practical-zero margin (3.23 price points) is wider than
   the approximately one-point fee band and could label economically meaningful
   plateaus as zero. Phase 5d therefore drops TOST-to-zero and `m0`. It reports
   the two-sided test of A=0, one-sided tests of A above the taker and maker
   bands, the 95% upper confidence bound, and the requested three-way
   classification (significant and above band / significant but not shown above
   band / not significant).
2. The primary Phase 5h microstructure analysis requires no quote reconstruction.
   It calculates game-and-cell gaps separately for taker-buys-longshot and
   taker-sells-longshot, then reports A_buy, A_sell, their average (approximate
   mid-based gap), and difference (approximate spread effect), with game-clustered
   inference. Reconstructed mids are secondary: both sides must be observed in a
   five-second trade lookback; one-minute candles are validation only. The valid
   quote share and differences between valid-quote and other rows will be
   reported.

The final five regulation minutes remain primary and final ten are secondary.
The Phase 3 possession result is explicitly resolved as follows: possession is
treated as a broken/low-value feature for the main pipeline given residual
reconstruction error and negligible final-five Brier gain; monotone LightGBM
without possession supplies the main P* panel. The with-possession LightGBM and
spline logistic without possession remain robustness specifications.

## Phase 3 model-selection rule and possession feature

The first Phase 3 report selected by overall holdout Brier. Per Sam's instruction,
the selection was rerun using final-five-minute 2024–25 holdout Brier because P* is
used late in games. Monotone LightGBM without possession is the main specification
(0.063906); spline logistic without possession is retained as robustness (0.064237).
Adding reconstructed possession lowers holdout final-five Brier by only 0.000257 and
2025–26 final-five Brier by 0.000166. The possession feature is therefore treated as
unreliable/low-value for the main pipeline, with the possession model reported as
robustness. The 2025–26 outcomes were not used to select or tune models. All late
regulation windows now call the shared predicate in `src/game_windows.py`.

## Phase 4 timestamp precision and quote availability

Phase 2 restart estimates contain mixed timestamp precision, including nanosecond
fractions. Phase 4 now parses mixed timestamp formats explicitly; the final aligned
panel retains all 23,072,381 Phase 1 non-block in-play trade rows. The quiet-window
screen additionally removes timeout intervals containing a foul or free-throw record
before the estimated restart (531 intervals in the market-matched sample). Candidate
trade/candle bid-ask extrema cross in 68.96% of rows. Those pairs are marked
undetermined and their mid/spread is null; only 31.04% of rows have an uncrossed
candidate pair. This limits later mid-price analyses, while leaving price-based power
counts unaffected.

## Sample exclusions and missing wall clocks

The ESPN `season_type=2` schedule contains 1,235 records. Removing the NBA Cup final and the four ESPN records with `STATUS_POSTPONED` and zero PBP plays leaves 1,230 standings games; every franchise then has exactly 82 games. The Cup final is San Antonio at New York (ESPN game `401809839`, Dec. 16 ET / Dec. 17 UTC). The four zero-play postponed records are:

| ESPN ID | Original local date | Matchup | Kalshi event | Kalshi cumulative volume_fp (both outcomes) |
|---|---|---|---|---:|
| `401810384` | 2026-01-08 | Miami at Chicago | `KXNBAGAME-26JAN08MIACHI` | 1,385,772 |
| `401810499` | 2026-01-24 | Golden State at Minnesota | `KXNBAGAME-26JAN24GSWMIN` | 7,643,652 |
| `401810506` | 2026-01-25 | Denver at Memphis | `KXNBAGAME-26JAN25DENMEM` | 1,656,861 |
| `401810507` | 2026-01-25 | Dallas at Milwaukee | `KXNBAGAME-26JAN25DALMIL` | 1,045,231 |

These are postponed event records, not completed fixtures. The Kalshi volumes are not zero, but they are not assigned an in-play window because the ESPN IDs have no plays or wall clocks. The postponed-game markets have median cumulative volume_fp 1.52 million, versus 5.59 million for the other matched regular-season games. All four are January events and involve ordinary franchises; the date distribution is therefore not comparable to the full season.

The playoffs robustness feed has four matched games whose ESPN summary endpoint returned 404:

| ESPN ID | Kalshi event date | Matchup | Kalshi event | Kalshi cumulative volume_fp |
|---|---|---|---|---:|
| `401869402` | 2026-04-30 | Denver at Minnesota | `KXNBAGAME-26APR30DENMIN` | 34,572,418 |
| `401871334` | 2026-05-07 | Cleveland at Detroit | `KXNBAGAME-26MAY07CLEDET` | 24,392,376 |
| `401871337` | 2026-05-13 | Cleveland at Detroit | `KXNBAGAME-26MAY13CLEDET` | 43,203,851 |
| `401873343` | 2026-05-23 | New York at Cleveland | `KXNBAGAME-26MAY23NYKCLE` | 45,309,461 |

Their median cumulative volume_fp is 38.89 million, versus 30.92 million for the other matched playoff games. These are playoff dates and teams, so they differ by design from the regular-season sample. Across the eight omitted records, missingness does not mean low Kalshi volume.

The `KXNBAGAME-26JAN24GSWMIN` event was initially matched to the postponed ESPN record `401810499`. Its contract rules identify the Golden State–Minnesota game originally scheduled for Jan. 24; ESPN records that completed fixture as game `401857824` on Jan. 25. The Kalshi market closes at 01:01:32 UTC, after the completed game's final ESPN play at 00:49:32 UTC, and its GSW/MIN contract outcomes agree with the ESPN winner. The in-game trade and candle histories were retrieved into an isolated sensitivity sidecar and aligned to `401857824`; the canonical historical market mapping was not overwritten. The two contracts contribute 29,336 aligned in-game rows, but zero qualifying final-five quiet-stoppage longshot trades and zero 5–20¢ longshot trades in the ten-minute realized-end window. Therefore this correction does not change the registered primary estimate or the headline 5–20¢ selection diagnostic. Reproduce with `make phase5-postponed-game-sensitivity`; provenance and outputs are under `data/interim/phase4_postponed_market_sensitivity/`. The other three postponed markets have no completed ESPN counterpart identified in this audit.

## Kalshi maker-fee status

The archived Oct. 1, 2025 and Feb. 5, 2026 fee PDFs establish the general taker and maker formulas and rounding rules, but do not enumerate maker-fee-eligible series. Current `KXNBAGAME` series metadata reports `quadratic_with_maker_fees` (multiplier 1); the current value does not establish historical status. The accessible historical series API and archived fee PDFs do not establish when maker fees began on `KXNBAGAME` or the applicability on each 2025–26 trade date. The earlier specific start-date claim is withdrawn. Maker amounts in `RESULTS.md` are formula illustrations only and must not be applied as observed historical costs until series history is established.

## Possession sequence limits

Phase 2 initially undercounted because missed field goals without an explicit defensive-rebound record were not always closing the offense, and because the comparison used ESPN's misleading `totalTurnovers` statistic (zero in some summaries) instead of the ordinary `turnovers` field. The revised sequence closes a missed-shot possession when a subsequent opponent live action or period end confirms transfer, uses explicit offensive/defensive rebounds and turnovers, and carries the offense state forward. The comparison is now against each side's box-score estimate `FGA - ORB + turnovers + 0.44 * FTA`. Across 2,460 team-game rows, median absolute error is 1.64 possessions; 79.7% of team-game rows are within ±3, and both sides are within ±3 in 783/1,230 games (at least one side in 1,178/1,230). There are no separate `Team Rebound` action types in the ESPN feed; explicit rebound actions are classified offensive or defensive. Residual discrepancies remain, so Phase 3 compares models with and without possession rather than assuming the reconstructed possession is exact. See `data/interim/phase2/possessions_by_game.csv` and `possession_validation.json`.

## ESPN wall-clock limitations

The ESPN clock parser has been corrected: before 1:00, summary `clock.displayValue` switches from `M:SS` to decimal seconds (for example, `23.4`). The parser now accepts both forms, and all interim PBP parquet files were rebuilt from cached raw summaries without network requests. ESPN wall clocks have one-second resolution. In the regular-season standings PBP after this repair, 5,008 of 595,970 within-game adjacent wall-clock transitions are non-monotone, affecting 1,204 of 1,230 games; 282 games have more than five such transitions and are flagged weakly aligned. Those games cover 281 Kalshi-traded games, 5,912,567 trade rows. Excluding them leaves 939 traded games and 17,159,814 trade rows for a timing-quality robustness sample. No per-game price-response offset was fitted. The zero-second global correction is a convention/assumption only: interval checks can detect clock-rate and local timing errors but cannot detect a constant ESPN entry lag shared by all actions. A made-field-goal diagnostic finds pre-ESPN trade-price changes in the scoring team's YES contract in 75.6% of 72,361 matched events (median lead 7.82 seconds among movers; median magnitude one cent). This is not a response-onset estimator: prior events and other market activity can produce these moves, so it is used only as context for the quiet-window buffer, never to fit or alter alignment.

NBA CDN requests were blocked with HTTP 403 despite the required browser headers. No CDN comparison was possible in this environment. The saved local probe remains available in `src/ingest_pbp.py`.

## Timeout restart convention

The revised restart estimate anchors only on the next promptly logged shot, rebound, or turnover in the same period, skipping free throws, fouls, substitutions and other delayed records. The quiet-window end buffer is configured to 5 seconds; sensitivity counts are reported at 0, 5 and 10 seconds.

## Polymarket coverage

The Oct. 21, 2025 test market was fully paginated (6,232 rows; offset 7,000 empty), and its API permits offsets only through 10,000. The final 10 minutes before the actual `closedTime` contain one Data API row, so a two-parameter 6a-lite calibration cannot be estimated. The event `endDate` is scheduled tip-off; its 170 rows in the final ten minutes are pre-game and are not a valid substitute.

One in-game transaction per month from October 2025 through June 2026 was initially checked on Polygon. The June 2026 taker-only Data API response reached 11,000 rows through offset 10,000 and rejected offset 10,001. Subsequent testing confirmed that inclusive `start`/`end` time windows recover the cached 11,000-row span without truncation, so season coverage will use those windows and maker-inclusive responses.

### Polymarket Data API collection update

The no-key legacy `GET /trades` endpoint was tested for the Oct. 21, 2025 Rockets–Thunder and June 3, 2026 Knicks–Spurs markets. `takerOnly=false` returns both maker and taker rows; on Oct. 21 it reproduced all 4,525 maker `OrderFilled` receipt rows (alongside 3,488 taker rows). Inclusive epoch-second `start`/`end` filters page the June market below the 10,000-offset ceiling: the full Gamma open-to-close span returned 38,950 taker rows across seven windows (largest 8,989), and the four windows over the previously cached span reproduced its 11,000-row multiset. Six maker fills across five additional game markets matched cached receipts. The Data API is the approved primary source for continuation; no paid/keyed source has been used. See `RESULTS_POLYMARKET.md` and the raw probes under `data/raw/polymarket/api_step1_probe/`.

### Polymarket sports order delay assumption

Current Polymarket Help Center documentation states a 3-second delay for marketable orders in sports markets. Apply **3 seconds as the working delay assumption**, but mark it unverified for historical 2025–26 fills. Do not use a wallet-latency cutoff below **5 seconds**; latency analysis should net out the 3-second assumed delay only as a sensitivity/working adjustment, not as historically observed platform metadata.

For planning only, the seven regular-season monthly spot checks averaged 1,535 in-game Data API rows per game. Linear extrapolation to 1,230 games is about 1.89 million rows. The test game's ratio of OrderFilled logs to in-game API rows (8,013/3,488) would imply roughly 4.34 million on-chain fill logs. This estimate is highly uncertain and only scopes a future Phase 6 ingestion; no season-wide Polymarket decoder or log ingest was built.

## Superseded initial Phase 5a attempt (before revised paper definition)

An initial close-window calculation used a bounded fit and an incomplete post-game
window; it contained only 26 games and is superseded by the revised analysis
below. Its old outputs are retained with `superseded` in their filenames and are
not the reported Phase 5a estimates.

## Phase 5a benchmark definition and limits (2026-10-21)

Sam clarified that Moshrefi's close is intended to coincide with game end. Recorded Kalshi `close_time` is a median 14.25 minutes after last ESPN play, so the recorded-close version (a) is only a diagnostic. The earlier post-game explanation is rejected. Version (d) uses the last ESPN play as game end, the prior `[0,10)` wall-clock minutes, in-game rows, each market's YES price/outcome, and the date scope including playoffs. Its paper-date sample is 958,727 trades. Restricting to regular-season games, the closer product-scope comparison has 659,214 trades across 334 games, versus the 327,473 reference used for the paper's near-expiry estimate. Splitting by ticker side gives 315,062 home-YES and 344,152 away-YES rows (333 games each), which suggests a possible market-side or trade-unit convention behind the approximate factor-of-two difference. This remains an unverified explanation: side-specific fitted curves differ, and the preprint does not publish a row-level count rule that resolves it. The combined regular-season isotonic α is 1.526 [1.311, 1.856], β=1.197 [1.090, 1.373], versus the reference α=1.516, β=1.182. Keep this as a qualified curve-shape comparison, not an exact replication. Other candidate differences include market/date filters, source coverage, and timing. Quick checks and game-clustered intervals are reported in RESULTS.md and `data/interim/phase5/phase5_quick_checks.json`.

## Phase 5 estimator weighting amendment (2026-10-22)

Game weighting was pre-registered. In each cell, the equal-game mean first
averages observations within a game, so the per-trade weight depends inversely
on that game's eventual trade count in the cell. This uses future trading
intensity and is not a stopping-time/typical-trade estimator; retain that
interpretive limitation. The prior 2026-10-22 amendment made first-entry the
headline for the 10–40¢ table and quiet estimates. Sam has now clarified that
the originally registered game-weighted **final-five quiet-stoppage estimand
is primary**; first-entry and pooled trade-weighted values are sensitivities
for that primary. The 10–40¢ table keeps its first-entry headline under the
earlier amendment. The weighting table was regenerated on 2026-10-22: it labels the registered
game-weighted quiet result as primary, reports first-entry upper bounds as
sensitivity estimates, and no longer reports fee-band tests that combined
first-entry outcomes with quote costs from a smaller sample. Current primary
prose and the separate primary estimand table use the registered
game-weighted result.

The same-observation primary cost output uses `phase5_primary_trades.parquet`
for both the full sample and quote-valid subset. Five-second taker cost/net
comparisons use only rows with both inferred quote sides observed, uncrossed,
and finite spread; trade and game coverage are reported. Net inference
resamples game-level A and costs together. Full-sample taker-fee-only amounts
are not presented as full taker costs because spread is unavailable on invalid
quote rows. Fee rounding at the observed per-row size is only a conservative
per-trade approximation: a source row is not proven to equal one
fee-assessed order, and one order may have multiple fills. These are
counterfactual costs per contract, not realized strategy P&L. Historical
KXNBAGAME maker-fee eligibility remains unresolved.

## Overtime-exclusion and decomposition correction (2026-10-22)

All estimates that exclude overtime games are invalid for inference because OT
status is determined by the realized game path, including whether the trailing
team ties. This applies to Kalshi and Polymarket Prelec fits and P* placebo fits,
paired alpha differences, selection-formula calibration fits, 10–40¢ rows, and
selection-gap decomposition rows. The numeric diagnostics remain in archived
Phase 5 outputs and are explicitly labeled invalid in RESULTS.md; OT-excluded
rows/series have been removed from thesis tables and figures. No estimates were
rerun.

The P* rows were removed from the market-price-band selection decomposition.
Those bands condition on market price, so P* gaps there measure disagreement
with the market, not P* calibration. The P* placebo remains the calibration
assessment, with Prelec fits binned by P* itself.


## Phase 5 residual investigation correction (2026-10-22)

All price−P* estimates based on market-price bands in the residual investigation (Kalshi and Polymarket localization, clock-decay regressions, and event-free convergence) are marked UNINTERPRETABLE. Band selection conditions the difference on the market value; moreover, regressing change in absolute gap on initial absolute gap is mechanically positive under measurement noise. The affected values remain only as labeled archived diagnostics and are excluded from thesis tables. The `Price − P*` rows were also removed from `tables/phase5/paired_residuals.tex`; the market `price − Y` and benchmark `P* − Y` outcome rows remain.

The investigation's Y−price outcomes were recomputed as trade-weighted, first eligible trade per game per cell, and game-weighted sensitivity estimates, with game-clustered bootstrap CIs. The same estimators were computed for valid-mid rows and Polymarket maker fills. Score-by-possession cells are labeled descriptive. Full results are in `data/interim/phase5/phase5_residual_outcome_estimators.csv`; code is `src/phase5_residual_outcome_weighting.py`.

### Polymarket residual outcome-join correction (2026-10-22)

The residual loader lowercased abbreviations before looking them up in `TEAM_ALIASES`, whose abbreviation keys include uppercase forms (for example, `NY`, `GS`, `SA`, and `UTAH`). It then inferred the winner from a home-abbreviation comparison rather than joining fills to the resolved CLOB outcome token. This produced an incorrect home-winner flag for 126 of 1,227 mapped markets and inflated the earlier Polymarket `Y−price` estimates. The outcome fold itself flipped `Y` together with price, but used the incorrect winner flag. The loader now uses the audited outcome-to-token mapping and derives fill outcomes from `asset == winner_token`, matching `src/run_polymarket_selection_analysis.py`; price and outcome are then folded together to the longshot contract.

The minute-median audit now compares the outcome for the longshot team implied by each venue's median selected-team price. Of 2,086 matched window-band game-minutes in 650 games, 16 minute-median outcomes differ; all 16 select different longshot teams across venues, with zero outcome mismatch when both select the same team. Intraminute longshot-side switches occur in 121 Kalshi and 69 Polymarket cells; at least one venue switches in 14 of the 16 different-team rows. The prior count of 29 is superseded because it paired the first fill's folded outcome with the minute-median price, a mismatch of observation coordinates when the selected-team price crossed 0.50 within the minute. The corrected crosswalk is `data/interim/phase5/phase5_residual_outcome_mismatch_audit.csv`, with summary JSON alongside it. Corrected trade-weighted and first-entry residual estimates, including maker-side cells, are in `data/interim/phase5/phase5_residual_outcome_estimators.csv` and `phase5_residual_polymarket_matched_estimators.csv`.

The Polymarket selection-analysis fits were not affected: `src/run_polymarket_selection_analysis.py` already maps Gamma outcome labels to token IDs, resolves the winner token through `TEAM_ALIASES`, and sets fill `Y` from `asset == winner_token`. Its saved summary reports 4,598,761 maker rows assigned, zero unknown outcome tokens, and one market-mapping error (game 401857824, market/shared assignment missing). The saved alpha-by-window, P* placebo, and inside/outside results therefore remain as reported; the OT-excluded estimates remain invalid for inference under the prior correction.

## Primary estimand and cost comparison correction (2026-10-22)

The final-five quiet-stoppage game-weighted estimate is restored as the
pre-registered primary, following Sam's explicit correction. The previous
first-entry amendment still applies to the separate 10–40¢ table; it no longer
relabels the quiet-stoppage primary. First-entry and trade-weighted quiet
estimates remain sensitivity results. The weighting concern remains disclosed:
each game's realized trade count determines within-cell per-trade weights.

The primary cost comparison is regenerated from the same cached 309,318-row
primary sample. The full-sample outcome estimate is game weighted. Taker
fee-plus-half-spread inference uses only the 251,686 quote-valid rows, with the
same rows used for outcome, fee and spread; 376/390 primary games contribute.
The row-size fee calculation is labeled an approximation, not an observed fee,
because fill rows need not match fee-assessed orders. No execution or strategy
P&L is inferred. See `src/phase5_primary_costs.py` and
`data/interim/phase5/phase5_primary_costs.json`.

## Reproduction and sample-extension inventory

`make phase5` provides the Phase 5 cached-data runner, with a preflight for
the Phase 4 trade panel/team assignment, 2025–26 P*, ESPN play-by-play, the
Polymarket fill parquet/map, and the saved Polymarket selection summary. The
ordered recipes are in `Makefile`; source inspection found no network calls in
the Phase 5 scripts. The target was run end to end on 2026-10-22 and completed
with exit code 0. It regenerated the Phase 5 tables, including
`tables/phase5/weighting_sensitivity.tex`.

ESPN play-by-play caches cover 2015–16 through 2025–26 (season folders 2016
through 2026). Kalshi trade and interim panel partitions are only the
2025–26 sample; the Polymarket season fill parquet and market map are likewise
2025–26. There are no earlier-season market inputs in the project inventory,
so an earlier-season late-market extension cannot currently be made comparable
without acquiring new market data. No expanded sample was built.

## Phase 6 wallet-mechanism prerequisites and absolute-clock limitation

The season Data API files contain wallet identities, sides, sizes, and fills.
The cached taker table has 3,182,525 rows and 3,182,525 distinct transaction
hashes; 4,601,635 maker fills have a taker identity assigned. Thus the
ingestion script's first-taker-per-hash join is unambiguous for the cached API
rows. Validation is not season-wide on-chain: all 3,488 Oct. 21 taker rows
matched `OrdersMatched` in the V1 sample, and 9,459 May 1 V2 maker fills
matched receipt logs, but the V2 check does not independently compare every
taker wallet. Nine monthly spot checks include V2 examples.

Even correct fill identities do not establish pre-trade inventories. An
initial ten-wallet Oct. 21 pilot matched the API winning-token redemption to
recorded trades and merges in 9/9 redeeming wallets. A broader stratified
sample of 210 target wallet-market pairs returned 4,344 TRADE, 100 MERGE, and
143 REDEEM rows, but no SPLIT, CONVERSION, or TRANSFER rows. For 60 positive
redemptions, every Activity payout amount matched the corresponding
Conditional Tokens receipt event within 1e-6 USDC. Recorded winning-token net
matched the reported claim amount within 1e-5 in 54 cases; six differences may
reflect partial claims, starting balances, transfers, or other ledger gaps and
do not establish an error. All 210 sampled
pairs have target-second activity, and 80 have no strictly earlier API
activity. The sampled API ledger is thus useful but not sufficiently complete
for exact pre-fill inventory classification. Direct historical balance calls
at the prior Polygon block succeeded for all 210 target transactions; target
token balances matched the recorded Activity trade/merge net within 1e-5 in
201/210. Applying earlier ERC-1155 transfer logs within the target block
reconstructs balances at the target transaction start: 107 had positive
target-token balances, 64 had positive opposite-token balances, and 41 held
both. Activity net matches these transaction-start balances in 194/210 pairs.
This establishes that some sampled target transactions started with an
existing longshot position; order within the target transaction is unresolved
and the sample is not representative. Position-conditioned loss
attribution and fresh-buyer tests remain blocked. Do not substitute trade
direction or zero recorded inventory for a verified position.

To unlock those tests, collect the complete V1/V2 market-lifecycle ledger from each
market's creation through redemption: fill events (`OrdersMatched` and maker
`OrderFilled`), Conditional Tokens `PositionSplit`, `PositionsMerge`, and
`PayoutRedemption`, and ERC-1155 `TransferSingle`/`TransferBatch` mints, burns,
and wallet transfers. Reconstruct token balances per wallet and market from
those events, then validate ending balances and payouts against redemption
records on a stratified sample before assigning position groups. Fine-grained
bot/latency classification remains weak because event timestamps are coarse
and historical sports-order delay is not observed.

### 2026-10-22 profile-pass operationalization

The outcome-free wallet profile pass uses maker-role share of participant
activity records at the existing 0.50/0.75/0.90 config thresholds. It does
not use maker/taker share of reported contract volume: the summed maker and
taker sizes match within 1e-5 in 89.3% of transactions, so that volume
measure is not yet fully reconciled. This is a descriptive profile of observed
record roles, not a market-maker or bot classification. The pass used only
in-game 2025–26 NBA records and did not access outcomes.

The zero-second ESPN correction is not empirically identified: same-UTC
timestamps and running-clock interval checks cannot detect constant source
entry lag. A separate sensitivity now shifts cached ESPN event, timeout, and
quarter-break wall timestamps relative to fixed Kalshi trade times, rebuilds
Phase 4 into isolated output directories, and recomputes the registered
primary/cost estimates. The −10, −5, 0, +5, and +10-second offsets are
researcher-chosen sensitivities motivated by one-second ESPN timestamp
resolution and the existing five-second restart buffer; they are not empirical
bounds on the true lag. The full-sample primary estimate ranges from 0.0135 to
0.0308; its CI includes zero at four offsets and excludes zero at +10 seconds.
Quote-valid primary and net-of-taker-cost CIs include zero at all offsets.
Results are in
`data/interim/phase4_clock_sensitivity/phase5_clock_shift_sensitivity.csv` and
are reproducible with `make phase5-clock-shift`. Neither these shifts nor
weak-alignment exclusions identify an absolute source timestamp lag.

### 2026-10-22 expanded on-chain inventory validation

The original 210-pair wallet-market feasibility sample was retained. A
follow-on sample selected the next five stable hash ranks in each month ×
observable-profile × recorded-Activity-role cell, then removed the one pair
that overlapped the original sample. This produced 346 additional pairs and
556 total nonoverlapping records. Activity histories, prior-block Polygon
balances, same-block ERC-1155 transfers, and transaction receipts were cached
in separate extension directories. The same strict wallet/token/size/price
`OrderFilled` plus unique transfer-bundle rule yields 477 unique matches and
221 positive pre-transfer inventory balances. The high-activity versus other
profile comparison and worst-case unresolved-match bounds are descriptive
within these selected strata only; no population estimate or causal inference
is claimed. Reproduction targets are `phase6-wallet-inventory-extension-*`
in the Makefile; combined counts and bounds are in
`data/interim/phase6/polymarket_wallet_inventory_extension_summary.json`.

### 2026-10-22 prior-purchase opportunity diagnostic

Added a descriptive link between strictly earlier same-token Activity API
BUYs and on-chain target-token balance at the start of the sampled transaction.
High-activity sampled wallets have more prior recorded BUYs and higher
inventory prevalence, while inventory prevalence conditional on a prior BUY
is closer across profile groupings. This does not establish mediation because
the wallet-market sample is stratified rather than population representative,
the Activity API history is incomplete, and acquisition routes/cost basis are
not fully reconstructed. An audit also found only 515/556 sampled pairs use
the earliest target-cohort BUY. Therefore no population-weighted or causal
profile estimate is added. Reproduce with `make
phase6-wallet-inventory-opportunity`; outputs are under
`data/interim/phase6/polymarket_wallet_inventory_opportunity/`.

### 2026-10-22 time-ordered participant profiles

Added exploratory profiles measured strictly before each target game's first
ESPN play, excluding all target-game records. This replaces full-season
behavior labels for this comparison and avoids using future-season activity
to classify an earlier purchase. The profile categories use explicit
researcher-defined minimum-history, activity-intensity, and maker/taker-share
thresholds; they are not account identity labels. Outcomes are compared only
on game × final-five-minute × P* band × participant-role common support, with
two-way game/wallet clustered uncertainty. The contrasts are exploratory,
post hoc, and do not identify causality, wallet P&L, bots/retail, or price
impact. Reproduce with `make phase6-wallet-prior-game-profiles`; outputs are
under `data/interim/phase6/prior_game_behavior/`.

### 2026-10-23 transaction-level account-style proxies

At the user's request, added an exploratory account-style analysis based on
distinct wallet-transaction cadence and median ticket notional. Multiple maker
fills sharing a wallet, transaction hash, and game are collapsed before
computing cadence, and each target profile uses only activity before that
game's first ESPN play while excluding the target game. The rapid-cycle rule
(at least 20 transactions per active day and median within-day gap ≤30 seconds)
and large-ticket/low-frequency rule (median ticket ≥$100 and ≤5 transactions
per active day) are researcher-defined post hoc thresholds, not registered
tests. A complete outcome-free threshold grid and top-versus-bottom quartile
matched comparisons are reported. These categories are not verified bots,
retail/professional identities, or causal sources of market prices. The
large-ticket group is sparse. Reproduce with `make
phase6-wallet-execution-style-analysis` and `make
phase6-wallet-execution-style-decomposition`; outputs are under
`data/interim/phase6/prior_game_behavior/execution_style/`.
