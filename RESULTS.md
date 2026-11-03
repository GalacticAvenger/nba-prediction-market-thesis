# Phases 1–5h: Ingest, timing diagnostics, P*, power design, replication, and late-game analysis

## Current conclusions (2026-11-03)

1. A window anchored to the realized end of the game yields late-game curvature
   close to Moshrefi's reported NBA fit, but only as a qualified benchmark.
   Across the full 2025–26 regular season, the fitted Prelec curvature is
   α=1.526 [1.311, 1.856], versus 1.516 in the paper. In the paper-date
   comparison window (March 1 through May 15, 2026), the estimate is α=1.674
   [1.125, 2.499] across 659,214 trades and 334 games. The paper's cited
   near-expiry count is 327,473; the row-count convention remains unreconciled.
   Home-YES and away-YES subsets are individually closer to that count,
   suggesting a possible market-side convention, but this does not verify it
   and the side-specific fits differ. The earlier selection decomposition predicted 60–64% of the
   observed point-estimated gap under a base-calibration assumption. A later
   game-held-out diagnostic, restricted to the same market-price cohort and
   allowing base miscalibration, predicts the pooled trade-weighted 5–20¢
   realized-end gap on both Kalshi and Polymarket, for both market price and
   P*. For Kalshi, however,
   the near-zero random-fold remainder is specific to trade weighting; the
   game-weighted and chronological holdout audits are less decisive. This is
   an outcome-conditioned measurement result, not a causal account of trader
   behavior or ex-ante profits. A
   market-price-independent P* placebo shows similar curvature
   (α=1.482 [1.316, 1.703]), and the selection formula curve has α=1.350
   [1.216, 1.523].
2. The pre-specified primary is the game-weighted final-five quiet-stoppage
   estimate: A=price−Y is 2.33 price points [−0.53, 4.94], with one-sided
   95% upper bound 4.51; its two-sided bootstrap test does not reject A=0
   (p=.0965). The planning MDE was 4.61 points at 80% power, so the interval
   does not exclude a gap near four to five points. On the quote-valid subset,
   the same-observation taker band is
   1.08 points [1.05, 1.11] and A minus cost is 1.15 [−1.62, 3.82]
   (one-sided p=.2065). First-entry and trade-weighted estimates are
   sensitivities; the original pre-specified game-weighted estimate is primary.
   A manual remapping audit of the postponed GSW–MIN fixture found no
   qualifying trades under the primary or the headline 5–20¢ realized-end
   filters, so this omitted event does not change either headline estimate.
3. The earlier positive Polymarket residual was caused by an incorrect winner
   mapping in the residual loader. After joining fills through audited outcome
   tokens and folding price and outcome to the same longshot side, first-entry
   Y−price is −1.17 points [−3.96, 1.70] in the knowable window and −0.45
   [−3.09, 2.32] in the final five regulation minutes. In the matched
   minute-median audit, 16 of 2,086 venue/game-minute comparisons select
   different longshot teams; outcome mismatches are zero when both venues
   select the same team. The Polymarket selection analysis already used the
   audited outcome-token join and is unchanged.
4. Suggestive only: for first-entry Kalshi taker buys of 0.05–0.20 longshots,
   A=price−Y is 3.07 points [0.44, 5.47] in the knowable window and 2.53
   [0.07, 4.77] in the final five regulation minutes, before trading costs.
   The final-five trade-weighted estimate is 1.85 [−1.84, 4.97]. These are
   selected cells among multiple splits; treat them as future-work evidence,
   not a central result.
5. **Exploratory inventory signal:** In 556 nonoverlapping stratified
   Polymarket wallet-market validations, 477 buys have a unique on-chain
   fill/transfer join and 221 show positive pre-existing target-token
   inventory. Positive inventory is much more frequent among matched
   high-activity pairs (83/98) than the other profile strata combined
   (138/379). Worst-case assignment of unresolved matches leaves a 28.4-point
   sample-level gap. The result is not a population estimate and does not show
   that inventory caused a price pattern. The API payout matches on-chain
   redemption events in all 144 sampled positive-redemption transactions;
   recorded trade/merge net equals the claim in 122/144; this comparison does
   not validate the full position ledger.

Describe the replicated curve as a result of a window anchored to the realized
game end, and avoid attributing an error to Moshrefi's implementation. The
selection and residual sections below give the methods and limits.

Phases 1 through 4 were completed on 2026-10-21. Phase 5a's realized-end benchmark produces a similar fitted curvature but is not an exact replication because the paper's sample count cannot be reconciled. Phases 5b–5h are complete. Calibration fits are trade-weighted publication fits. For the pre-registered final-five quiet outcome estimand, game-weighting is primary; first-entry and trade-weighting are sensitivities. The separate 10–40¢ table retains first-entry as its headline under the earlier amendment and shows game- and trade-weighted sensitivities. The regenerated [weighting_sensitivity.tex](tables/phase5/weighting_sensitivity.tex) now labels the pre-specified primary correctly; it reports first-entry upper bounds as a sensitivity and omits the old mismatched cost-band tests.

**Literature-positioning update (2026-10-22):** Moshrefi (2026) already reports
expiry-related calibration changes in Kalshi sports markets, and a newly
available Lee, Lee, and Lee study directly examines NBA/NFL Kalshi post-score
adjustment and cost-aware trading. Position this project around the narrower
game-state/quiet-stoppage question and the distinction between calibration,
adjustment speed, and net profitability. Do not present generic event
underreaction or near-expiry calibration distortion as a novel contribution.
See the proposal-aligned draft in [THESIS_DRAFT.md](THESIS_DRAFT.md) and the
claim audit/research plan in [THESIS_STRATEGY.md](THESIS_STRATEGY.md).

## Phase 1 ingestion snapshot (before Phase 2 sample exclusions)

The main sample is the 2025–26 regular season (`season=2026`, ESPN `season_type=2`); the 2024–25 tail and 2026–27 markets are excluded. Playoffs (`season_type=3`) are retained separately for robustness. Kalshi markets were matched to ESPN by local event date and team codes.

| Sample | ESPN schedule games | Kalshi-matched games | Matched games with usable play windows | Games with ≥1 non-block in-play Kalshi trade | Non-block in-play trade rows | Market rows | 1-minute candles |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025–26 regular season | 1,235 | 1,233 | 1,229 | **1,220** | 23,072,381 | 2,458 | 341,326 |
| 2025–26 playoffs (robustness) | 85 | 81 | 77 | 77 | 6,685,615 | 154 | 38,392 |
| **Usable-window total** |  |  | **1,306** |  | **29,757,996** | **2,612** | **379,718** |

At Phase 1, the live-play census was **1,220 distinct Kalshi-matched regular-season games with at least one non-block trade between the first and last ESPN play timestamps**, among 1,229 matched games with usable windows. Nine of those 1,229 matched games had no in-play trade rows. Four additional matched postponed records had no play data and were not assigned guessed windows. Phase 2 applies the standings definition and reports the corrected sample below. The playoff count is 77 of 77 matched games with usable ESPN wall clocks; four other matched playoff games had ESPN summary requests return 404.

Phase 2 resolved this schedule discrepancy. See the Phase 2 sample definition below; the ESPN type-2 schedule contains four postponed, zero-play records and the NBA Cup championship fixture in addition to the 1,230 standings games.

Kalshi returned 2,898 historical market objects across 1,449 event tickers. The selected ESPN-matched 2025–26 set has 1,314 events (1,233 regular-season and 81 postseason) and 2,628 team markets. Eight matched games (four regular, four postseason) had no usable ESPN window, so no Kalshi trade/candle window was assigned to their 16 markets. The finished windowed files contain 2,612 metadata rows. There are 2,594 nonempty trade partitions and 2,594 candle partitions; the 18 missing partitions are the two team markets for nine regular-season games with no returned in-play trades/candles.

## Kalshi trade fields, precision, and candles

- The historical endpoint was queried with `is_block_trade=false`; returned block rows were also filtered out locally. Each market’s trades were padded by two minutes for retrieval, then retained only from the first through last ESPN play wall-clock timestamp.
- **Field interpretation, empirical check:** in all 29,757,996 ingested trade rows, legacy `taker_side` equaled `taker_outcome_side`. `taker_outcome_side` was `yes` on 22,300,948 rows and `no` on 7,457,048. The only observed tuples were `(taker_side, taker_outcome_side, taker_book_side) = (yes, yes, bid)` (22,300,948 rows) and `(no, no, ask)` (7,457,048 rows). In the economic outcome coordinate, the taker’s acquired-side price is `yes_price` for YES and `1 - yes_price` for NO. The empirical candle comparison supports treating `taker_outcome_side` as the acquired outcome; it also shows that `taker_book_side` must not be read as the consumed quote side in untransformed YES-price coordinates.
- For a deterministic check, I selected 35 market tickers by SHA-256 order and sampled up to 100 trades per market using seed 11 (3,500 trades with matching one-minute candles). Converting NO trades to their NO price, **all 3,500 (100%) were within 1.1¢ of that outcome’s candle ask OHLC range**, with a median distance of zero. The candle bid OHLC range was also within 1.1¢ for 96.7% of the sample because one-minute OHLC ranges and narrow spreads often overlap; this is a coarse consistency check, not sub-minute quote identification. Phase 4 will validate trade-inferred quotes against the one-minute candles as requested.
- `count_fp` is not always integral: all 23,072,381 regular-season rows were whole contracts, while 3,824,932 of 6,685,615 playoff rows were fractional (3,452,460 with two decimal places and 372,472 with one). The observed playoff examples include 93.51, 37.4, and 374.07. The ingest stores `count_fp` as a float and does not round it.
- Trade IDs had zero duplicate rows within market partitions. Timestamps are not unique: summed across market partitions, regular-season files contain 18,384,805 distinct timestamp strings across 23,072,381 rows (4,687,576 rows repeat a timestamp); playoff files contain 5,851,512 distinct timestamps across 6,685,615 rows (834,103 repeats). `created_time` is represented with up to six fractional digits (microsecond formatting), so timestamps can order many trades within a second but ties are common. Trade ID, not timestamp, is the unique trade key.
- Prices in the ingested archive range from $0.01 to $0.99. One-minute historical candles were available for 2,594 markets, totaling 379,718 candle rows.

## Fees for 2025–26 and Phase 5f fee component

Historical Kalshi fee PDFs downloaded from archived copies show the following schedule on the observed trade dates:

| Trade dates | Fee PDF effective date | Taker formula | Maker formula |
|---|---|---|---|
| 2025-10-21 through 2026-02-04 | 2025-10-01 | `ceil_cent(0.07 × C × P × (1−P))` | `ceil_cent(0.0175 × C × P × (1−P))` |
| 2026-02-05 through last observed in-play trade, 2026-06-13 ET (2026-06-14 UTC) | 2026-02-05 | same | same |

Both dated schedules apply a cent ceiling to the fee for the trade/order and show the same taker and maker formulas. The current public series metadata in [data/raw/kalshi/series_KXNBAGAME_current.json](data/raw/kalshi/series_KXNBAGAME_current.json) reports `quadratic_with_maker_fees`, multiplier 1, but that is a current value and does not establish its historical applicability. The archived PDFs available here do not list the series that were maker-fee eligible. Historical `KXNBAGAME` maker-fee status on each 2025–26 date, including its start date, remains unresolved; see [DEVIATIONS.md](DEVIATIONS.md). Trade timestamps are stored in UTC; the fee intervals above are expressed by Eastern calendar date.

For the Phase 5f fee component, the large-size per-contract limit is the formula without material cent-rounding. The median regular-season trade size is 51 contracts. The table shows the cent-ceiling at an illustrative 50-contract size (maker amounts are conditional on historical maker-fee eligibility, which remains unresolved):

| Contract price P | Taker, large size | Taker, C=50 | Maker, large size | Maker, C=50 |
|---:|---:|---:|---:|---:|
| $0.05 | 0.3325¢ | 0.34¢ | 0.0831¢ | 0.10¢ |
| $0.10 | 0.6300¢ | 0.64¢ | 0.1575¢ | 0.16¢ |
| $0.20 | 1.1200¢ | 1.12¢ | 0.2800¢ | 0.28¢ |

These are formula fee costs. The completed same-observation taker cost comparison, including half-spread, is reported in the primary result below. Historical maker-fee eligibility remains unresolved, so maker amounts are conditional. Position limits remain unresolved and are not needed for the main sample.

## Play-by-play sources and timeouts

- **ESPN summary API:** `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=<ESPN_GAME_ID>` returned per-play `plays[].wallclock` values for the 2025–26 games noted above and game clock (`clock`), period, action text/type, team, and scores. The season summary-level `wallclockAvailable` flag is imperfect: it is true for 1,230 regular-season summaries, but actual play wall clocks are present for 1,231; the ingest now checks actual per-play fields and retains those timestamps. There are 1,235 regular-season summaries; four games have no per-play wall clocks. Of 85 playoff schedule games, four summary calls returned 404 and 81 returned plays with wall clocks.
- **Training seasons:** ESPN summary PBP was cached for regular seasons 2015–16 through 2024–25 (5,587,782 action rows). Only game clock is retained for those seasons; wall-clock stamps are kept for 2025–26 only. ESPN does not expose explicit possession or `clock_running` fields in this summary response, so those fields remain null in the Phase 1 PBP files.
- **NBA CDN:** the requested NBA CDN URL returned HTTP 403 in this environment even when retried with browser `User-Agent`, `Referer: https://www.nba.com/`, and `Origin: https://www.nba.com` headers. No CDN payload was ingested, so there is no independent timestamp agreement check yet. A locally runnable probe is included in [src/ingest_pbp.py](src/ingest_pbp.py): `python3 src/ingest_pbp.py --cdn-probe-game-id 0022500001`. It saves the raw JSON under `data/raw/nba_cdn/` if the local network allows it. If you can run it locally and it succeeds, Phase 2 can compare the two sources.
- **Timeouts:** ESPN action type `Full Timeout` supplies timeout onsets (13,266 regular-season and 894 playoff actions); the regular-season feed also includes four `Excess Timeout Technical` and one `Excess Timeout Turnover` entries. Phase 2 estimates restart time from the next live action and the game-clock difference; see below.

## Polymarket side-track checks

Checks used the Rockets–Thunder game event `nba-hou-okc-2025-10-21`, which has an on-chain Polygon market. Phase 2 paginated its Data API market endpoint through completion and checked the in-game transaction receipts; updated counts are below.

- In the complete 6,232-row Data API result for the market, all transaction hashes were unique; the 3,488 in-game rows also had unique hashes. Offset 7,000 returned an empty page; offset 10,001 returned HTTP 400 with a maximum historical offset of 10,000. Thus this market was fully paginated, but high-volume markets can reach the API cap. The in-game receipt audit found 8,013 V1 `OrderFilled` logs and 3,488 `OrdersMatched` logs across the 3,488 in-game transactions: a transaction may contain multiple maker fills, so the on-chain fill count exceeds the Data API row count.
- The official exchange event that identifies the economic taker is `OrdersMatched`, specifically its `takerOrderMaker` address. I checked five in-game fills by transaction receipt on PolygonScan; each Data API `proxyWallet` matched that `takerOrderMaker` address: [fill 1](https://polygonscan.com/tx/0x2143adada2423ddf685644b2d8352a0dd37624b2d49893d14e5feb6ee0618e7b), [fill 2](https://polygonscan.com/tx/0x098453d662eae2d35cc1f3bf4054f558abdc90f9e0729c6a1b65a258757f9199), [fill 3](https://polygonscan.com/tx/0x7118357c274294b3df88b342e9362220dcd1856d49bfdb0be149b31eed04b77e), [fill 4](https://polygonscan.com/tx/0x6cf78e2b3d6e2eed993ed36ae271eb7c4b1ae31f26c3ba69cc271078ef029d43), [fill 5](https://polygonscan.com/tx/0x7aa8cef5c5f31fc289e44ef86fb7dde7c5453f656cf3a635acd0b54dfbb195dd). The official contract interface names `takerOrderMaker` in [`OrdersMatched`](https://github.com/Polymarket/ctf-exchange/blob/main/src/exchange/interfaces/ITrading.sol).
- One transaction from each month October 2025–June 2026 was checked on Polygon; all nine samples emitted on-chain fill events. May and June samples used the V2 exchange after its April 2026 migration. These checks show that sampled in-game NBA activity was on Polygon / Polymarket International; they do not measure the season-wide share or rule out activity on Polymarket’s separate US exchange. See the monthly audit in [data/interim/phase2/polymarket_monthly_spotchecks.json](data/interim/phase2/polymarket_monthly_spotchecks.json). Kalshi remains the approved main analysis venue; no Polymarket decoder was built.

## Questions and scope limits

1. Four postponed ESPN records have no play data; Kalshi event tickers remain attached to the original scheduled dates. Some corresponding games were later played under different ESPN game IDs. They are excluded as requested; see [DEVIATIONS.md](DEVIATIONS.md).
2. NBA CDN access returned 403 even with browser headers. No user-run CDN data has been provided for source-to-source comparison.
3. Historical KXNBAGAME maker-fee applicability and its start date remain unresolved.
4. Possession sequence still has residual per-team errors, but it meets the revised majority-within-±3 target; Phase 3 compares validation performance with and without possession.
5. Kalshi position limits remain unresolved by design and out of scope for the main results.

## Reproducibility and source files

Raw API responses are cached under `data/raw/`; interim parquet files are under `data/interim/`. Phase 1 ingest entry points are [src/ingest_kalshi.py](src/ingest_kalshi.py) and [src/ingest_pbp.py](src/ingest_pbp.py). `make all` currently runs Phases 1–4; run `make phase5` afterward to reproduce the Phase 5 analyses, figures, and tables from cached inputs. The Phase 5 preflight checks the Phase 4 panel/assignment, Phase 3 2025–26 P*, 2025–26 ESPN play-by-play, Polymarket season fills/map, and saved read-only Polymarket summary. The full cached target completed successfully on 2026-10-22 (exit code 0); no network fetches are in its recipes. It regenerates `weighting_sensitivity.tex` and related Phase 5 artifacts. PBP caches include seasons 2015–16 through 2025–26, but Kalshi and Polymarket market inputs cover only 2025–26; a prior-season extension needs new comparable market data. Phase 2 outputs are under [data/interim/phase2](data/interim/phase2). The archived fee PDFs used are [Oct 8, 2025](data/raw/kalshi/fees/2025-10-08.pdf), [Dec 24, 2025](data/raw/kalshi/fees/2025-12-24.pdf), [Feb 21, 2026](data/raw/kalshi/fees/2026-02-21.pdf), and [Jun 12, 2026](data/raw/kalshi/fees/2026-06-12.pdf). NBA schedule source: [2025–26 schedule release](https://pr.nba.com/2025-26-nba-regular-season-schedule/). Polymarket sources: [Data API](https://data.polymarket.com/), [US data guide](https://docs.polymarket.us/data-guide/overview), the V1 [`OrdersMatched` interface](https://github.com/Polymarket/ctf-exchange/blob/main/src/exchange/interfaces/ITrading.sol), and [V2 exchange source](https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/interfaces/ITrading.sol).

## Phase 2: Match and timing diagnostics

### Standings sample and trade census

ESPN has 1,235 `season_type=2` records. I removed the non-standings NBA Cup final (San Antonio at New York, ESPN `401809839`) and four postponed records with zero PBP plays. The resulting standings schedule has **1,230 games, with exactly 82 games for each of the 30 franchises**. The official NBA schedule announcement distinguishes the 1,230-game regular season from the Cup championship, which does not count in the standings. The four postponed records are documented in [DEVIATIONS.md](DEVIATIONS.md).

The analysis universe is the 1,230 standings games. Kalshi markets matched to 1,229 of those games; one completed Golden State–Minnesota game (`401857824`) is not matched to the Kalshi market keyed to its postponed Jan. 24 fixture. The observed in-play census is **1,220 distinct regular-season games with at least one non-block Kalshi trade during play** (23,072,381 rows), or 99.2% of the standings universe. The count includes only trades between the first and last ESPN play timestamps; no in-play window is guessed for postponed markets. The GSW–MIN postponed-market mapping is a conservative omission described in DEVIATIONS. Playoffs remain robustness-only: 77 matched games have usable ESPN wall clocks, and 77 have at least one in-play Kalshi trade.

### Kalshi taker-side test and candle cross-check

Across non-block trades, I grouped each market into non-overlapping UTC 5-second buckets and retained buckets with at least one YES-taker and one NO-taker. In **1,595,888 buckets**, mean YES-price was higher for YES takers in **95.03%**, tied in 2.27%, and lower in 2.69%. This sharper within-market test supports the direction that YES takers pay higher YES prices than NO takers in the same short window.

I also sampled up to 100 trades per market across 2,594 markets and compared trade YES-price with the matching one-minute candle close: YES-taker price versus `yes_ask.close`, and NO-taker price versus `yes_bid.close`. Of 259,247 matched trade/candle observations, the median absolute distance was 1¢; 68.7% were within 1¢ and 79.8% within 2¢. This is a coarse minute-close check, not a contemporaneous best-quote reconstruction. Results are saved in [data/interim/phase2/kalshi_candle_close_check.json](data/interim/phase2/kalshi_candle_close_check.json) and can be regenerated with [src/validate_phase2_candles.py](src/validate_phase2_candles.py).

### ESPN timestamp quality, clock-running state, and alignment

The ESPN wall-clock string has **one-second resolution**. After correcting the clock parser and rebuilding interim PBP from the cached raw summaries, the 1,230 standings games have 5,008 of 595,970 adjacent wall-clock transitions (0.84%) going backward; 1,204 games have at least one such transition, and 282 have more than five. There are 49,301 timestamp groups with multiple plays (120,799 plays are in such groups; 9.38% of timestamp groups are batched). These issues are retained as timing-quality flags, not repaired by reordering or price-based offsets.

For adjacent records in selected running-clock stretches, 156,884 action intervals were evaluated. Wall-clock elapsed and game-clock elapsed differ by no more than 2 seconds in 88.1% of intervals and by no more than 5 seconds in 95.4%. Common action types with strong interval agreement include defensive rebounds (99.8% within 2 seconds), offensive rebounds (98.5%), jump shots (92.4%), pull-up jump shots (91.1%), and common turnover records (about 90%). Foul, timeout, and substitution records are delayed or batched and do not qualify as timing anchors. These checks support using ordinary shot, rebound, and turnover records as the only candidate anchors; they do not establish absolute timestamp accuracy to 2 seconds.

ESPN and Kalshi timestamps are both UTC, so the applied global clock correction is **0 seconds by assumption**. No per-game offset was fitted to event-price responses. Interval checks establish local clock-rate agreement but cannot reveal a constant ESPN entry lag shared by every action. The 282 games with more than five backward wall-clock transitions are weak-alignment flags; 281 have in-play Kalshi trades (5,912,567 rows). The timing-quality subset without those flags has 939 traded games and 17,159,814 rows. Offset and per-game flags are in [data/interim/phase2/alignment_diagnostics.json](data/interim/phase2/alignment_diagnostics.json) and [data/interim/phase2/alignment_game_flags.csv](data/interim/phase2/alignment_game_flags.csv). No NBA CDN data was provided, and CDN requests remain blocked in this environment.

`clock_running` is derived as an interval state: the game clock decreased within the same period, and the current action is not an explicit stoppage. The corrected Phase 2 file has 349,490 `True`, 246,480 `False`, and 1,230 initial null states. This is a sequence-based working state for later validation, not an official ESPN field.

### Timeout restart estimates and possession diagnostic

For each timeout, the estimated restart is `next_prompt_action_wall - (game_clock_at_timeout - game_clock_at_next_prompt_action)`, where the anchor is the first subsequent shot, rebound, or turnover. Delayed fouls, free throws, substitutions, and other actions are skipped. Windows containing scoring, replay review, or coach challenge are excluded. The config-selected end buffer is 5 seconds. Final-five-minute regulation survivors are 1,747 at buffer 0, 1,746 at buffer 5, and 1,745 at buffer 10 (966 games at each setting). Across all clocks, survivors are 9,648, 9,643, and 9,641 respectively. Interval-level data and sensitivity counts are in [data/interim/phase2/timeout_intervals.csv](data/interim/phase2/timeout_intervals.csv) and [data/interim/phase2/timeout_buffer_summary.json](data/interim/phase2/timeout_buffer_summary.json).

Possessions are reconstructed from made shots, turnovers, offensive/defensive rebounds, free-throw completion, opponent live actions following a missed shot without a recorded defensive rebound, and period ends. There is no separate `Team Rebound` action type in the feed. The benchmark is each team's box-score estimate `FGA - ORB + turnovers + 0.44 * FTA`. Across 2,460 team-games, mean box-score and action estimates are 101.84 and 102.12; median absolute difference is 1.64. 1,961/2,460 (79.7%) team-game estimates are within ±3; both teams are within ±3 in 783/1,230 games (63.7%) and at least one team in 1,178/1,230 (95.8%). This meets the requested majority target, but residual error motivates model comparisons with and without possession. Per-game differences are in [data/interim/phase2/possessions_by_game.csv](data/interim/phase2/possessions_by_game.csv); summary in [data/interim/phase2/possession_validation.json](data/interim/phase2/possession_validation.json).

### Polymarket pagination, on-chain fills, and 6a-lite

For the Oct. 21 Rockets–Thunder market, the complete Data API `/trades` result has 6,232 rows and 6,232 unique hashes. The in-game window contains 3,488 rows/hashes. Polygon receipts for all 3,488 in-game transactions contain 8,013 V1 `OrderFilled` logs and 3,488 `OrdersMatched` logs. Thus maker fills do not appear as separate Data API rows in this sample, while one transaction may produce multiple on-chain maker-fill events. The Data API returns no more than 1,000 rows per page and rejects offsets above 10,000; this test market ends at offset 6,000, but the June 2026 sample hit the cap.

One in-game transaction was verified on Polygon for each month from October 2025 through June 2026. All nine receipts had on-chain fill events; May and June use the V2 `OrderFilled` event after the April 2026 exchange migration. This spot check supports on-chain International venue use in each sampled month, but it is not a census of all Polymarket US activity. Monthly game and API counts are in [data/interim/phase2/polymarket_monthly_spotchecks.json](data/interim/phase2/polymarket_monthly_spotchecks.json).

The October test market was completely paginated, but only one Data API row falls in the final ten minutes before the market's actual `closedTime`. A calibration fit is not estimable from one row. Its metadata `endDate` is scheduled tip-off, whose final ten minutes are pre-game, so that window is not a valid late-game substitute. The 6a-lite coverage result is saved in [data/interim/phase2/polymarket_6a_lite_coverage.json](data/interim/phase2/polymarket_6a_lite_coverage.json). The June sample returned 11,000 rows through offset 10,000, including at least 10,579 in-game rows, before hitting the pagination ceiling. A rough future log-ingest scope is about 1.9 million in-game API rows and 4.3 million OrderFilled logs if monthly regular-season samples extrapolate linearly; this is planning only, not a season estimate. No decoder or season-wide on-chain ingest was built.

### Made-shot price timing diagnostic

For each made field goal with usable ESPN wall time, I compared the scoring team's YES-contract trades: the last price in the 10 seconds before the ESPN stamp against the last prior trade at or before the start of that 10-second interval. A ≥0.5¢ price change occurred before the ESPN stamp for 54,697 of 72,361 matched shots (75.6%). Among those movers, median lead was 7.82 seconds (90th percentile 9.74 seconds); median absolute movement was 1¢ (mean 1.28¢). This is a coarse movement diagnostic, not event attribution or a response-onset estimate: other actions/trading can move prices in the interval. It was not used to fit or change offsets; it only contextualizes the 5-second quiet-window buffer. See [data/interim/phase2/kalshi_made_shot_lead.json](data/interim/phase2/kalshi_made_shot_lead.json).

The corrected ESPN clock parser accepts both `M:SS` and decimal seconds below one minute. All cached PBP parquet batches were rebuilt from raw local summaries. This adds usable clock observations for the last minute and restores the full 2025–26 per-second game-clock grid. The constant-lag limitation and parser repair are also recorded in [DEVIATIONS.md](DEVIATIONS.md).

## Phase 3: Win-probability benchmark P*

### Design and model selection

The benchmark uses only game states and outcomes from standings regular-season games, with NBA Cup finals removed. It has no market prices or betting lines. Selection trains on 2015–16 through 2023–24 (10,749 games) and holds out all 1,230 games in 2024–25. Late-window definitions in the code use the shared `is_final_regulation_window` predicate in [src/game_windows.py](src/game_windows.py).

**Model choice follows final-five holdout Brier**, because P* is used late in games. Among no-possession candidates, monotone LightGBM is best: holdout final-five Brier 0.063906, versus 0.064237 for spline logistic. LightGBM with possession scores 0.063649, an absolute gain of only 0.000257. Given the residual possession reconstruction error and this negligible increment, possession is treated as a broken/low-value feature for the main pipeline; the no-possession LightGBM is primary, while LightGBM with possession and spline logistic remain robustness specifications. This selection-rule change is recorded in [DEVIATIONS.md](DEVIATIONS.md). No 2025–26 outcome was used to tune or select a model.

The selected LightGBM was refit on all ten training seasons through 2024–25, then scored on 2025–26. The 2025–26 output has 1,230 games and 3,565,982 one-second states. Its Brier is 0.163951 overall and 0.059547 in the final five regulation minutes (370,230 states, all 1,230 games). On those same held-out states, the possession model's Brier is 0.059380 and spline logistic is 0.059762; the possession increment is only 0.000166. These are state-weighted out-of-sample diagnostics, not game-clustered inference.

Final-five reliability by the thesis price bins (mean P*, observed home-win frequency, and distinct games represented) is:

| P* bin | Mean P* | Observed frequency | Games |
|---|---:|---:|---:|
| 0.03–0.05 | 0.0390 | 0.0298 | 263 |
| 0.05–0.10 | 0.0720 | 0.0548 | 289 |
| 0.10–0.20 | 0.1466 | 0.1650 | 297 |
| 0.20–0.35 | 0.2626 | 0.3336 | 327 |
| 0.35–0.50 | 0.4076 | 0.4777 | 249 |
| 0.50–0.65 | 0.5662 | 0.5706 | 268 |
| 0.65–0.80 | 0.7270 | 0.7385 | 306 |
| 0.80–0.90 | 0.8511 | 0.8629 | 333 |
| P* bin | Mean P* | Observed frequency | Games |
|---|---:|---:|---:|
| 0.03–0.05 | 0.0390 | 0.0298 | 263 |
| 0.05–0.10 | 0.0720 | 0.0548 | 289 |
| 0.10–0.20 | 0.1466 | 0.1650 | 297 |
| 0.20–0.35 | 0.2626 | 0.3336 | 327 |
| 0.35–0.50 | 0.4076 | 0.4777 | 249 |
| 0.50–0.65 | 0.5662 | 0.5706 | 268 |
| 0.65–0.80 | 0.7270 | 0.7385 | 306 |
| 0.80–0.90 | 0.8511 | 0.8629 | 333 |
| 0.90–0.97 | 0.9411 | 0.9683 | 355 |

The bin table is [data/interim/phase3/reliability_2025_26_final5_main_price_bins.csv](data/interim/phase3/reliability_2025_26_final5_main_price_bins.csv). The selected model uses score differential, log seconds remaining, period, home indicator, free-throw state, and score-differential × log-time interaction; no Elo feature was used. Selection metrics and test predictions are in [data/interim/phase3/model_selection.csv](data/interim/phase3/model_selection.csv) and [data/interim/phase3/pstar_2025_26_every_second.parquet](data/interim/phase3/pstar_2025_26_every_second.parquet); model summary is [data/interim/phase3/phase3_summary.json](data/interim/phase3/phase3_summary.json).

**Phase 3 is complete.**

## Phase 3 possession decision carried into Phase 4/5

Following the requested final-five holdout comparison, reconstructed possession is treated as a broken/low-value feature for the main pipeline: its residual box-score disagreement and negligible final-five Brier improvement do not justify making it a main predictor. The main P* panel uses monotone LightGBM without possession. LightGBM with possession and spline logistic without possession remain robustness specifications.

## Phase 4: Trade panel, quiet windows, quotes, and power

The Phase 4 panel contains **23,072,381** non-block in-play trades from **2,440 markets and 1,220 games**, matching the Phase 1 regular-season trade census. All panel rows have a mapped game clock; 5,912,567 rows are from weak-alignment games as flagged by the Phase 2 backward-timestamp diagnostic. The panel uses the saved one-team-per-game assignment in [data/interim/phase4/selected_team_by_game.csv](data/interim/phase4/selected_team_by_game.csv) (seed 17); trades from the complementary market are converted into that selected team's price and taker-side coordinates. Per-trade fields include game clock/running state, P* and robustness predictions, event age/type/direction and dP*, running-clock decay, stoppage type/progress, inferred quotes/mid/spread, and alignment flags. See [data/interim/phase4/trade_panel](data/interim/phase4/trade_panel).

The final-five quiet-stoppage power sample has **390 games and 309,318 trade rows** in the folded longshot price band 0.05–0.20. The market-free P* forecast averages 0.1304 for the longshot side. Under the game-level Bernoulli variance forecast, the expected 95% confidence-interval half-width is **0.03229** (3.23 price points per $1 contract); this was the original Phase 4 practical-zero proposal; Sam later removed `m0` before Phase 5 outcomes. The two-sided 80%-power minimum detectable gap is **0.04615** (4.61 points), above the four-point planning target. This means effects smaller than about 4.61 points will be hard to distinguish from zero at the approved sample size. This power calculation is retained as a design diagnostic; the 3.23-point CI half-width is no longer used as a practical-zero margin.

The cell census covers 252 combinations (final 5/final 10 × quiet/running × nine price bins × seven tau buckets). **156 cells have fewer than 150 games.** Counts are games with at least one trade in the cell; zero-coverage cells are retained in [data/interim/phase4/power_cells.csv](data/interim/phase4/power_cells.csv).

| Regulation window | Clock state | Cells | Cells under 150 games | Maximum games in a cell |
|---|---|---:|---:|---:|
| Final 5 | Quiet | 63 | 59 | 179 |
| Final 5 | Running | 63 | 36 | 403 |
| Final 10 | Quiet | 63 | 28 | 277 |
| Final 10 | Running | 63 | 33 | 493 |

Within final-five quiet stoppages, every individual longshot price-bin × tau cell is below 150 games; the 390-game power figure pools those price/tau cells for the prespecified primary band.

The 5-second end buffer leaves 9,636 Phase 2 timeout intervals in the market-matched games; 531 contain a foul or free-throw record before estimated restart and are removed from the Phase 4 quiet-stoppage set. The remaining 9,105 intervals include 1,634 final-five-minute timeouts across 947 games. Before the additional foul/free-throw screen, the Phase 2 buffer-5 recount was 1,746 final-five timeouts in 966 games (the 0/5/10-second sensitivity remains 1,747/1,746/1,745). Timeout starts and restarts use the prompt-action anchor and the shared final-window function. Event-free quarter breaks are also classified as quiet when trading continues.

The saved Phase 4 panel retains its original 60-second trade lookback plus one-minute candle quote fields as a pre-amendment diagnostic. For Phase 5, the amended five-second, both-sides-observed trade quotes were rebuilt separately; candles were used only for validation. The five-second validity and validation results are reported in the Phase 5h section below. The original quote/power diagnostic is in [data/interim/phase4/power_summary.json](data/interim/phase4/power_summary.json).

`config.yaml` remains locked for the sample, price/tau bins, windows, stoppage rules, and team assignment, with the two pre-outcome amendments above applied to Phase 5 testing and quote reconstruction. The original `m0` is removed. No Phase 5 outcome result had been computed before Sam approved the amendments and Phase 5.

## Phase 5a: Qualified Moshrefi benchmark comparison

### Benchmark definition

Moshrefi defines TTE using scheduled trading close and says this “coincides with the end of the game.” She describes the sample as “early March through mid-May 2026.” Her final window is `[0,10)` minutes, and Figure 4 reports NBA Prelec-II α=1.516, β=1.182, N=327,473. Prices 0 and 1 are excluded; calibration is trade weighted, binned by price, isotonic-smoothed, then fit with `C(p)=exp(-β(-ln p)^α)`. Her paper does not state numeric price-bin width. This replication uses one-cent price bins. [Moshrefi (2026), arXiv:2607.14430v1, §§III–IV and Fig. 4](https://arxiv.org/html/2607.14430v1).

### Close-time diagnostic and rejected post-game hypothesis

The recorded Kalshi `close_time` is a median 14.25 minutes after the last ESPN play across 1,229 matched regular-season games. Since the paper says close coincides with game end, recorded `close_time` does not implement that stated definition in these data. The earlier hypothesis that post-game trading explains the mismatch is **rejected**. Version (a) remains a recorded-close diagnostic and is not the faithful test of the stated game-end definition. Post-game rows remain archived separately in [post_game_trades.parquet](data/interim/phase5/post_game_trades/post_game_trades.parquet); they are excluded from (b) and (d).

### Fits and game-clustered bootstrap intervals

Each entry reports trades, games, α (95% game-cluster bootstrap CI), and β (95% game-cluster bootstrap CI). “Raw” fits the observed binned calibration rates; “isotonic” fits the trade-weighted isotonic calibration rates. Each interval uses 2,000 game-cluster bootstrap draws (seed 5132026). Primary fits use one-cent price bins; the previously reported five-cent sensitivity fits for (a) and (b) are also included below. Calibration units are trade rows. Her reported reference is 327,473 trades and α=1.516, β=1.182.

| Version and scope | N trades | Games | Calibration | α [95% CI] | β [95% CI] |
|---|---:|---:|---|---:|---:|
| (a) recorded close, paper dates, selected-team coordinate | 43,167 | 128 | Raw | 197.027 [7.720, 197.030] | 0.0001 [0.0001, 32.798] |
| (a) recorded close, paper dates, selected-team coordinate | 43,167 | 128 | Isotonic | 29.068 [9.800, 29.826] | 0.313 [0.0001, 33.364] |
| (a) recorded close, full regular season, selected-team coordinate | 130,988 | 445 | Raw | 2.486 [1.535, 50.635] | 1.073 [0.137, 5541.846] |
| (a) recorded close, full regular season, selected-team coordinate | 130,988 | 445 | Isotonic | 2.488 [1.633, 31.046] | 1.058 [0.194, 3317.415] |
| (b) final 10 regulation minutes, paper dates, selected-team coordinate | 2,069,180 | 336 | Raw | 1.119 [0.866, 1.507] | 0.929 [0.662, 1.341] |
| (b) final 10 regulation minutes, paper dates, selected-team coordinate | 2,069,180 | 336 | Isotonic | 1.122 [0.881, 1.502] | 0.930 [0.664, 1.318] |
| (b) final 10 regulation minutes, full regular season, selected-team coordinate | 7,689,937 | 1,211 | Raw | 1.052 [0.928, 1.193] | 0.944 [0.814, 1.097] |
| (b) final 10 regulation minutes, full regular season, selected-team coordinate | 7,689,937 | 1,211 | Isotonic | 1.053 [0.934, 1.204] | 0.945 [0.813, 1.100] |
| (a) recorded close, paper dates, selected-team coordinate, 5¢ bins | 43,167 | 128 | Raw | 20.847 [9.611, 27.998] | 0.242 [0.0001, 30.158] |
| (a) recorded close, paper dates, selected-team coordinate, 5¢ bins | 43,167 | 128 | Isotonic | 20.714 [9.635, 27.963] | 0.240 [0.0001, 30.128] |
| (a) recorded close, full regular season, selected-team coordinate, 5¢ bins | 130,988 | 445 | Raw | 2.474 [1.520, 23.068] | 1.070 [0.167, 251.323] |
| (a) recorded close, full regular season, selected-team coordinate, 5¢ bins | 130,988 | 445 | Isotonic | 2.444 [1.621, 19.710] | 1.049 [0.169, 108.399] |
| (b) final 10 regulation minutes, paper dates, selected-team coordinate, 5¢ bins | 2,069,180 | 336 | Raw | 1.120 [0.884, 1.513] | 0.929 [0.666, 1.351] |
| (b) final 10 regulation minutes, paper dates, selected-team coordinate, 5¢ bins | 2,069,180 | 336 | Isotonic | 1.120 [0.895, 1.513] | 0.929 [0.663, 1.337] |
| (b) final 10 regulation minutes, full regular season, selected-team coordinate, 5¢ bins | 7,689,937 | 1,211 | Raw | 1.052 [0.928, 1.206] | 0.945 [0.811, 1.101] |
| (b) final 10 regulation minutes, full regular season, selected-team coordinate, 5¢ bins | 7,689,937 | 1,211 | Isotonic | 1.052 [0.936, 1.207] | 0.945 [0.811, 1.093] |
| (d) final 10 wall-clock minutes before last ESPN play, March 1–May 15, regular season + playoffs, market YES | 958,727 | 394 | Raw | 1.451 [1.081, 2.283] | 1.269 [1.069, 1.657] |
| (d) same window, dates and sample | 958,727 | 394 | Isotonic | 1.479 [1.112, 2.202] | 1.276 [1.067, 1.636] |
| (d) final 10 wall-clock minutes before last ESPN play, full season + playoffs, market YES | 3,206,677 | 1,279 | Raw | 1.400 [1.213, 1.694] | 1.121 [0.999, 1.292] |
| (d) same window, full season + playoffs | 3,206,677 | 1,279 | Isotonic | 1.404 [1.225, 1.702] | 1.121 [1.003, 1.295] |
| (d) final 10 wall-clock minutes before last ESPN play, full regular season, market YES | 2,524,781 | 1,202 | Raw | 1.524 [1.306, 1.837] | 1.196 [1.089, 1.358] |
| (d) same window, full regular season | 2,524,781 | 1,202 | Isotonic | 1.526 [1.311, 1.856] | 1.197 [1.090, 1.373] |

Version (d) uses each traded market's YES price and its own YES/no settlement outcome, not the seed-17 selected-team coordinate. It includes only trade rows with `0 < YES price < 1`, excludes block trades, and requires trade timestamp strictly before the last ESPN play. The paper-date sample including playoffs is 958,727; the closer regular-season-only sample is 659,214 trades across 334 games. The project's current comparison reference is 327,473 trades. For the regular-season-only sample, splitting by which team's ticker carries YES yields 315,062 home-YES records and 344,152 away-YES records (333 games each), each within about 5% of that reference. This near two-to-one count relationship suggests that market-side or trade-unit conventions may explain much of the discrepancy, but the paper does not provide enough detail to establish that reconciliation. The reproducible 2,000-draw game-cluster bootstrap gives home-YES α=1.750 (95% CI [1.273, 2.836]), β=1.159 ([0.682, 2.295]); away-YES α=1.587 ([0.987, 2.614]), β=1.541 ([0.936, 2.828]). The wide, overlapping intervals and differing point estimates show that choosing one side would be a consequential modeling choice. We therefore do not select a side after seeing which fit is closer or call this an exact replication. On the combined regular-season data, isotonic α is 1.526 (95% CI [1.311, 1.856]) and β is 1.197 (95% CI [1.090, 1.373]); the paper reference is α=1.516 and β=1.182. The estimator and uncertainty intervals are compatible with a similar near-expiry curve, but data construction remains unresolved. This is a qualified benchmark, not a reproduction of Moshrefi's data. The preprint's data section reports 13,009,643 NBA trades over its broader 11-week window; the 327,473 value is the near-expiry reference currently used in this project's replication comparison, and its exact counting rule remains unverified. See the paper's [data description and time-to-expiry definitions](https://arxiv.org/pdf/2607.14430). Reproduce the side-count sensitivity with `make phase5a-market-side-sensitivity`; its design and fits are in [`phase5a_market_side_sensitivity.json`](data/interim/phase5/phase5a_market_side_sensitivity.json).

Candidate explanations for the sample-size difference are recorded in DEVIATIONS.md. No further investigation of the discrepancy was performed.

Reproducible estimates and binned curves are in [phase5a_bootstrap.json](data/interim/phase5/phase5a_bootstrap.json), [phase5a_bootstrap_bins.csv](data/interim/phase5/phase5a_bootstrap_bins.csv), and [src/phase5a.py](src/phase5a.py). The separate post-game archive manifest is [manifest.json](data/interim/phase5/post_game_trades/manifest.json).


## Phase 5a quick checks

All fits use the trade-row calibration unit, one-cent bins, Prelec-II, 2,000 game-cluster bootstrap draws, and raw plus isotonic calibration curves. Scope for the coordinate cross and game-clock windows is March 1–May 15, 2026, regular season only, so each comparison uses the same seed-17 assigned games and trade rows. Values below are isotonic fits; raw fits and both sets of CIs are in [phase5_quick_checks.json](data/interim/phase5/phase5_quick_checks.json).

### Coordinate cross

| Window | Coordinate | Trades | Games | α [95% CI] | β [95% CI] |
|---|---|---:|---:|---:|---:|
| Final 10 regulation minutes by game clock (b) | Market YES | 2,069,180 | 336 | 1.108 [0.877, 1.452] | 1.033 [0.936, 1.190] |
| Final 10 regulation minutes by game clock (b) | Seed-17 selected team | 2,069,180 | 336 | 1.122 [0.898, 1.534] | 0.930 [0.663, 1.318] |
| Final 10 wall-clock minutes before last ESPN play (d) | Market YES | 659,214 | 334 | 1.674 [1.125, 2.499] | 1.340 [1.042, 1.814] |
| Final 10 wall-clock minutes before last ESPN play (d) | Seed-17 selected team | 659,214 | 334 | 1.688 [1.200, 2.794] | 0.999 [0.597, 2.049] |

### Final regulation game-clock windows

| Final window | Coordinate | Trades | Games | α [95% CI] | β [95% CI] |
|---|---|---:|---:|---:|---:|
| 2 minutes | Market YES | 711,717 | 336 | 0.954 [0.660, 1.697] | 1.000 [0.868, 1.324] |
| 2 minutes | Seed-17 selected team | 711,717 | 336 | 0.958 [0.727, 1.743] | 0.851 [0.522, 1.611] |
| 3 minutes | Market YES | 869,103 | 336 | 0.967 [0.682, 1.636] | 0.996 [0.870, 1.286] |
| 3 minutes | Seed-17 selected team | 869,103 | 336 | 0.960 [0.724, 1.680] | 0.886 [0.556, 1.584] |
| 5 minutes | Market YES | 1,235,927 | 336 | 1.019 [0.760, 1.466] | 1.021 [0.904, 1.232] |
| 5 minutes | Seed-17 selected team | 1,235,927 | 336 | 1.039 [0.813, 1.546] | 0.879 [0.587, 1.368] |
| 10 minutes | Market YES | 2,069,180 | 336 | 1.108 [0.877, 1.452] | 1.033 [0.936, 1.190] |
| 10 minutes | Seed-17 selected team | 2,069,180 | 336 | 1.122 [0.898, 1.534] | 0.930 [0.663, 1.318] |

### Clock span of the (d) window

For the 659,214 regular-season trades in the paper-date (d) window, 573,980 have a preceding ESPN clock state. Mean wall-clock time remaining to the last ESPN play is 5.642 minutes. Mean regulation game-clock time remaining at the preceding PBP state is 1.131 minutes (median 0.678; 10th–90th percentiles 0.073–3.000 minutes).

The selected-team coordinate does not remove the (d)-window fit curvature (α=1.688; 95% CI [1.200, 2.794]). Continue to Phase 5b–5h.

## Phase 5b–5h: Kalshi late-game analysis

### Primary estimand and calibration cells (5b)

The pre-specified primary final-five quiet-stoppage sample has **309,318 trades across 390 games**. Using the Phase 4 seed-17 contract assignment, folded to the longshot side, the primary game-weighted estimate is A=`price − Y` **0.02332** (95% game-cluster bootstrap CI **[−0.00527, 0.04937]**). Equivalently, `Y − price = −0.02332` [−0.04937, 0.00527]. Mean longshot price is 0.11697; trade-weighted win frequency is 0.10346. The final-ten quiet-stoppage game-weighted estimate is secondary: A=0.02321 [0.00110, 0.04352], 520,103 trades, 622 games. Bootstrap draws: 2,000; primary seed 9142026. First-entry and trade-weighted quiet estimates are sensitivities.

The other game-weighted calibration-cell output covers final 5/final 10, quiet/running, selected-contract price bin × tau bucket. It contains 258 populated cells with game-equal estimates and game-clustered 95% CIs: [phase5b_calibration_cells.csv](data/interim/phase5/phase5b_calibration_cells.csv). These cell fits are secondary calibration summaries; the trade-weighted publication fits headline calibration, while first-entry remains a sensitivity for quiet outcomes and the headline estimator for the separate 10–40¢ table under the earlier amendment.

### Persistent overpricing tests (5d)

Define `A = price − Y` for the folded longshot contract, so positive A is overpricing. For the primary sample, **A=0.02332** (2.33 price points; 95% CI **[−0.00527, 0.04937]**). The two-sided bootstrap test of A=0 has p=0.0965. Its one-sided 95% upper confidence bound is 0.04513 (4.51 points).

A post-hoc dynamic timeout-cutoff sensitivity was computed from the cached Phase 2 PBP and Phase 5 late-trade data on 2026-11-03. It preserves the Phase 2 interval exclusions and the five-second restart buffer, but includes trades strictly before the first later foul/free-throw in intervals that the primary rule excluded in full. The baseline reproduces 309,318 trades / 390 games and +2.332 price points. The dynamic-cutoff sample adds 34,505 pre-event trades across 46 games and yields +2.036 points (411 games; 10,000-draw game-bootstrap 95% CI −0.773 to +4.589). The estimate remains inconclusive. This is a post-hoc sensitivity, not a replacement primary or a fully trade-time-identifiable estimate: it retains retrospective Phase 2 interval exclusions, the restart buffer, and uncertain common timestamp lag. Reproduce with `python src/phase5_dynamic_timeout_sensitivity.py --output timing_sensitivity.json`; The machine-readable summary is included as `TIMING_SENSITIVITY.json` in the advisor handoff package.

The earlier Phase 5f band figures paired the full-sample A distribution with mean spread from only quote-valid rows; that denominator mismatch is superseded by the same-observation comparison in “Primary estimates, residuals, and fee bands” below. The pre-specified A=0 result remains a two-sided game-clustered bootstrap p=.0965. Historical KXNBAGAME maker-fee eligibility is unresolved, so all maker-formula comparisons are conditional.

### Event decay shape (5c) and benchmark-free drift (5e)

The event-path estimates use a fixed bin from the selected-contract price immediately before each event, compare to the event's 120–300 second trade-price average, and orient the response by whether the event helped or hurt the selected contract. The running-event set contains 2,504 event episodes across its price-bin/direction strata; the followed-by-timeout set contains 2,011. There are 20 B/κ fits for each set (direction × pre-event price bin), each with game-clustered bootstrap intervals. Four B fits and five κ fits reached their lower numerical bounds; every per-bin estimate and interval is in [phase5c_decay_fits.csv](data/interim/phase5/phase5c_decay_fits.csv). The event curves are in [phase5_dynamics.json](data/interim/phase5/phase5_dynamics.json).

The 5e drift estimates are price changes from a trade to the first trade at τ+h within the same quiet-stoppage event episode, for h=5, 15, 30, and 60 seconds, stratified by event direction, raw action type, and tau bucket. The input includes 828,793 final-five and 1,252,738 final-ten quiet-stoppage trade rows. There are 3,374 reported groups with game-clustered 95% CIs: [phase5e_drift.csv](data/interim/phase5/phase5e_drift.csv) and [phase5e_drift.json](data/interim/phase5/phase5e_drift.json). No P* or outcome is used in this drift calculation.

### Fees and trading-cost bands (5f)

The primary band's mean longshot price is 0.11697 and median trade size is 51 contracts. At that price, the large-size taker fee is 0.00723 per contract (0.72¢), the maker-formula fee is 0.00181 (0.18¢), and observed five-second half-spread averages 0.00374 (0.37¢). Thus the large-size taker band including half-spread is 0.01097 (1.10¢); the formula maker band is 0.00181 (0.18¢). At median trade size, cent rounding gives taker and maker fees of 0.00725 and 0.00196 per contract (0.73¢ and 0.20¢); with the same half-spread, the taker band is 0.01100 (1.10¢). Across the 0.05–0.20 price endpoints, large-size taker fees are 0.00333–0.01120 per contract and median-size rounded taker fees are 0.00333–0.01137; the corresponding maker-formula values are 0.00083–0.00280 and 0.00098–0.00294. Historical KXNBAGAME maker-fee status is unresolved.

### Prelec mappings (5g)

The following game-weighted sensitivity fits use game-equal calibration curves and 2,000 game-cluster bootstrap draws. For the final-five raw curve (4,677,599 trades, 1,211 games), the isotonic reduced-form Prelec-II fit is α=1.014 (95% CI [0.914, 1.131]), β=0.891 ([0.778, 1.027]); 1/α=0.986 ([0.884, 1.094]). On the quiet-stoppage plateau (904,887 trades, 933 games), α=1.138 ([0.957, 1.441]), β=0.944 ([0.775, 1.181]); 1/α=0.879 ([0.694, 1.045]). The trade-weighted publication fits headline calibration; first-entry quiet estimates are sensitivities, while first-entry remains headline only for the separate 10–40¢ table.

Under the binary CPT indifference mapping, assuming linear value and no loss aversion, final-five α=1.156 (95% CI [0.754, 1.446]) and δ=0.886 ([0.660, 1.303]); quiet-plateau α=1.349 ([0.439, 1.787]) and δ=0.665 ([0.443, 1.799]). Loss aversion and the resulting no-trade region are not identified from prices. Raw and isotonic binned curves and all fit outputs are in [phase5g_calibration_bins.csv](data/interim/phase5/phase5g_calibration_bins.csv) and [phase5_dynamics.json](data/interim/phase5/phase5_dynamics.json).

### Microstructure and five-second quote reconstruction (5h)

The **game-weighted secondary** trade-price microstructure calculation uses no quotes. For each game × longshot-price-bin × tau cell it reports A_buy, A_sell, their average, and their difference, with paired game-clustered CIs. There are 13 populated cells; all estimates are in [phase5h_microstructure_cells.csv](data/interim/phase5/phase5h_microstructure_cells.csv). Trade-weighted publication fits are the headline calibration results; for quiet-window outcome estimates, the registered game-weighted estimator is primary and first-entry is a sensitivity.

For the secondary mid analysis, both trade-inferred sides must be observed within five seconds; one-minute candles are used only for validation. Valid quotes occur on 13,548,324/23,072,381 panel rows (58.72%). Within the primary sample, 251,686/309,318 rows (81.37%) have valid quotes, across 376 games; the remaining 57,632 rows span 361 games. The valid subset has mean longshot price 0.11556 and mean τ=63.80 seconds; the other subset has 0.12313 and 44.34 seconds. The **game-weighted secondary** `Y − trade price` gaps are −0.02235 (95% CI [−0.04813, 0.00531]) for valid rows and −0.02499 ([−0.05308, 0.00418]) for invalid rows. On valid rows, the game-weighted `Y − mid` gap is −0.02312 ([−0.04880, 0.00433]). Trade-weighted publication fits and first-entry quiet-window estimates are the headline results for their respective analyses.

For candle validation, 5,009,482 late-window rows had a comparable candle quote range; both inferred sides were within the respective one-minute candle bid/ask OHLC ranges, allowing one cent tolerance, on 3,637,365 rows (72.61%). Candles did not supply quotes to the five-second mid estimate. The full analysis outputs are in [phase5_main.json](data/interim/phase5/phase5_main.json), with the primary trade sample in [phase5_primary_trades.parquet](data/interim/phase5/phase5_primary_trades.parquet).

**Phase 5 is complete.** The read-only Polymarket season calibration and selection summaries are integrated. The cached maker/taker identity join is unambiguous by transaction hash, with sampled V1/V2 receipt checks, but the data do not contain complete wallet balance transitions. Registered position-conditioned Phase 6 mechanism tests were therefore not run; see [DEVIATIONS.md](DEVIATIONS.md).

## Phase 5 outcome-selection diagnostics (before Phase 6)

Trade counts below are for the 2025–26 regular season unless stated otherwise. Prelec fits use one-cent bins and game-clustered 2,000-draw CIs. The full raw and isotonic fit output is in [phase5_outcome_selection.json](data/interim/phase5/phase5_outcome_selection.json); the reproducible script is [phase5_outcome_selection.py](src/phase5_outcome_selection.py).

### Market-free P* placebo

| Window | P* coordinate | Trades | Games | Isotonic α [95% CI] | Isotonic β [95% CI] |
|---|---|---:|---:|---:|---:|
| (d), final 10 wall minutes before last ESPN play | Market YES | 2,524,779 | 1,202 | 1.482 [1.316, 1.703] | 1.183 [1.098, 1.299] |
| Final 2 regulation game-clock minutes | Selected team | 2,702,963 | 1,207 | 1.144 [0.957, 1.399] | 0.979 [0.794, 1.213] |
| Final 3 regulation game-clock minutes | Selected team | 3,289,309 | 1,210 | 1.086 [0.930, 1.331] | 0.956 [0.783, 1.152] |
| Final 5 regulation game-clock minutes | Selected team | 4,677,599 | 1,211 | 1.021 [0.885, 1.185] | 0.913 [0.764, 1.085] |
| Final 10 regulation game-clock minutes | Selected team | 7,689,930 | 1,211 | 0.983 [0.867, 1.128] | 0.898 [0.773, 1.043] |

Raw fits and their game-clustered intervals are in the JSON output.

Raw fit values (same trade and game counts):

| Window | Raw α [95% CI] | Raw β [95% CI] |
|---|---:|---:|
| (d), final 10 wall minutes | 1.477 [1.309, 1.696] | 1.184 [1.097, 1.308] |
| Final 2 regulation game-clock minutes | 1.131 [0.940, 1.383] | 0.974 [0.794, 1.186] |
| Final 3 regulation game-clock minutes | 1.076 [0.912, 1.291] | 0.951 [0.791, 1.152] |
| Final 5 regulation game-clock minutes | 1.012 [0.874, 1.184] | 0.910 [0.773, 1.078] |
| Final 10 regulation game-clock minutes | 0.977 [0.855, 1.121] | 0.897 [0.783, 1.034] |

### Final 3 game-clock minutes: longshot trades at 0.05–0.20

| Longshot outcome | Trades | Games | Mean wall minutes to last ESPN play | Median wall minutes | Games with OT | Share of games with OT |
|---|---:|---:|---:|---:|---:|---:|
| Y=1 | 116,608 | 112 | 17.944 | 17.203 | 28 | 25.00% |
| Y=0 | 1,067,408 | 554 | 11.472 | 7.952 | 37 | 6.68% |

The game-weighted `Y − price` estimates within the same final-3-minute longshot sample are:

| Relative to (d) window | Trades | Games | Mean `Y − price` [95% game-cluster CI] |
|---|---:|---:|---:|
| Inside (d) | 727,030 | 473 | −0.06429 [−0.07598, −0.05094] |
| Outside (d) | 456,986 | 328 | 0.03291 [−0.00284, 0.07185] |

### Overtime-excluded diagnostics — invalid for inference

Every estimate conditioning on no overtime is invalid for inference: whether a game reaches overtime depends on its realized outcome path, including whether the trailing team ties. The regular-season (d) market-YES diagnostic had 2,206,053 trades / 1,149 games, isotonic α=1.503 [1.282, 1.807], β=1.187 [1.083, 1.341], raw α=1.502 [1.279, 1.821], and β=1.187 [1.075, 1.350]. These values are retained here only to identify the superseded diagnostic; they are removed from thesis tables and figures.

### Knowable wall-clock window

The first knowable-window calculation included post-game rows and was invalid; it is superseded below. The corrected window is in-game only, starting at the first Q4 state at or below 3:00 and ending at the earlier of ten wall minutes later or the last ESPN play.

### Kalshi close-time metadata

The regular-season metadata contains 2,458 market records across 1,229 games, with created, open, and close timestamps on all records. At the distinct-game level, close_time precedes the last ESPN play in 27 games and follows it in 1,202; none are equal. Close_time minus last-play time has game-level p10/p50/p90 of 7.435/14.250/25.933 minutes. The metadata is a single snapshot and contains no close_time change history, so it does not establish when that field was set.

### Final-10 quiet secondary overpricing tests

The corrected inclusive 0.05–0.20 longshot-band sample contains 520,103 trades across 622 games. Updated estimates and band tests are recorded in the consolidated Phase 5 summary below; these supersede the earlier 512,193-row calculation.

### Plain-language summaries of 5c and 5e

In 5c, the fitted event-response amplitudes were small across the price-bin and event-direction strata: median B was 0.00134 for 2,504 running-event episodes and 0.0000147 for 2,011 event-followed-by-timeout episodes. Median fitted decay rates κ were 0.218/s and 0.0884/s, respectively. Four B fits and five κ fits reached the lower numerical bound; the per-stratum estimates and bootstrap intervals are in [phase5c_decay_fits.csv](data/interim/phase5/phase5c_decay_fits.csv).

In 5e, pooled game-equal, event-oriented price changes were close to zero at the requested horizons. For final five minutes, the 5-second estimate was 0.000037 (95% CI [−0.000093, 0.000175]) and the 60-second estimate was −0.000063 ([−0.001238, 0.001032]); for final ten minutes, the corresponding estimates were 0.000020 ([−0.000058, 0.000106]) and 0.000052 ([−0.000552, 0.000691]). All eight pooled intervals at 5, 15, 30, and 60 seconds include zero. Stratified action, event-direction, and tau-bucket results remain in [phase5e_drift.csv](data/interim/phase5/phase5e_drift.csv).

No position-conditioned Phase 6 wallet mechanism analysis was performed because season-wide inventory transitions are missing. Fill-based calibration, selection, and cross-venue overlay analyses were performed; the available Polymarket results are described below.


## Consolidated Phase 5 publication summary (including read-only Polymarket outputs)

All confidence intervals below are 95% game-cluster bootstrap intervals (2,000 draws) unless a row is explicitly descriptive. This section supersedes the earlier knowable-window estimate, the preliminary 10–40¢ table, and the earlier final-10 quiet overpricing paragraph. The publication analysis script is [src/phase5_publication.py](src/phase5_publication.py); its numeric output is [phase5_publication_summary.json](data/interim/phase5/phase5_publication_summary.json). The analysis covered 23,072,360 panel rows, with 0 selected-team assignment mismatches, 0 duplicate market-trade keys, and 0 mismatches across 520,103 audited outcome joins.

**Correction:** all overtime-excluded estimates are invalid for inference because OT status depends on the realized outcome path. They are excluded from thesis tables and figures; any retained numerical mention is explicitly labeled invalid. The selection-gap decomposition is market-only because its price bands are defined by market price; P* calibration remains in the separate P*-binned placebo fits.

### Figures and tables

Figures: [pre-specified primary estimate and cost sensitivity](figures/phase5/registered_primary_estimate.pdf), [Kalshi/Polymarket calibration curves](figures/phase5/calibration_market_vs_pstar.pdf), [Kalshi/Polymarket Prelec α by window](figures/phase5/prelec_alpha_by_window.pdf), [wall-time distribution](figures/phase5/longshot_wall_time_distribution.pdf), and [5c response / 5e drift](figures/phase5/event_response_and_drift.pdf).

Tables: [5a replication](tables/phase5/replication_5a_d.tex), [P* placebo fits](tables/phase5/pstar_placebo.tex), [wall time and overtime](tables/phase5/mechanism_walltime_overtime.tex), [primary estimand and fee bands](tables/phase5/primary_estimand_band_tests.tex), [paired residuals](tables/phase5/paired_residuals.tex), and [Moshrefi 10–40¢ claim](tables/phase5/moshrefi_10_40_claim.tex), [weighting sensitivity](tables/phase5/weighting_sensitivity.tex), and [Kalshi/Polymarket mechanism comparison](tables/phase5/mechanism_platform_comparison.tex).

### Estimator comparisons

For every 10–40¢ window and both sources, the linked table headlines first-entry estimates and shows pre-registered game-weighted and pooled trade-weighted sensitivity columns for win rate and Y−p, with counts and 95% game-clustered CIs. The primary and final-10 quiet rows report A=p−Y in the same order. Knowable calibration has 36 rows: nine bins × two probability sources × trade-weighted/first-entry; each row includes mean P, observed Y, trade/game counts, and game-clustered 95% CIs. Source: [weighting_sensitivity.tex](tables/phase5/weighting_sensitivity.tex), [phase5_weighting_estimators.csv](data/interim/phase5/phase5_weighting/phase5_weighting_estimators.csv), and [phase5_knowable_weighting_bins.csv](data/interim/phase5/phase5_weighting/phase5_knowable_weighting_bins.csv). The weighting amendment is recorded in [DEVIATIONS.md](DEVIATIONS.md).

### 5a qualified benchmark comparison and calibration fits

The replication table compares the 327,473 near-expiry reference count and reported α=1.516, β=1.182 with our requested (d) market-YES fits. In the paper-date window including playoffs, our sample has N=958,727 / 394 games, α=1.479 [1.112, 2.202], β=1.276 [1.067, 1.636]. The closer regular-season-only paper-date sample has N=659,214 / 334 games; full 2025–26 regular season has N=2,524,781 / 1,202 games, α=1.526 [1.311, 1.856], β=1.197 [1.090, 1.373]. The paper-date one-side sensitivities are documented above and in [phase5a_market_side_sensitivity.json](data/interim/phase5/phase5a_market_side_sensitivity.json). The raw and isotonic fits and intervals are in [phase5_publication_summary.json](data/interim/phase5/phase5_publication_summary.json) and the table above.

P* has only regular-season Phase 4 panel coverage for the paper-date subset: 659,214 trades / 334 games, versus the market sample's 958,727 / 394; the 60 postseason games (299,513 market trades) have no P* estimates. The matched available market/P* paper-date fits are α=1.674 [1.125, 2.499] and 1.507 [1.190, 4.816], respectively. For full-season (d), market α=1.526 [1.312, 1.851], P* α=1.482 [1.316, 1.703]. The no-overtime fits—market α=1.503 [1.282, 1.807], P* α=1.360 [1.222, 1.568]—are invalid for inference because OT status is outcome-dependent and are omitted from thesis tables/figures. Corrected knowable window: market α=1.162 [1.014, 1.373], P* α=1.025 [0.908, 1.192]. Final 2 minutes: market α=1.114 [0.930, 1.362], P* α=1.109 [0.953, 1.311]. Final 5: market α=1.053 [0.917, 1.214], P* α=0.990 [0.877, 1.121]. Final 10: market α=1.042 [0.931, 1.176], P* α=0.945 [0.849, 1.057]. Fit counts and β estimates are in [pstar_placebo.tex](tables/phase5/pstar_placebo.tex); complete raw/isotonic α and β intervals are in [phase5_publication_summary.json](data/interim/phase5/phase5_publication_summary.json).

### Corrected knowable-window calibration

The corrected in-game-only knowable sample has 2,615,732 trades / 1,210 games. Market-YES isotonic fit: α=1.162 [1.014, 1.373], β=1.033 [0.972, 1.124]. P* fit: α=1.025 [0.908, 1.192], β=1.003 [0.953, 1.076]. Calibration rows below give trade count, game count, mean probability, observed win rate, and the game-clustered 95% CI for observed win rate. Source: [phase5_knowable_calibration_bins.csv](data/interim/phase5/phase5_knowable_calibration_bins.csv).

| Bin | Source | Trades | Games | Mean p | Observed Y [95% CI] |
|---|---|---:|---:|---:|---:|
| .03–.05 | Market | 53,141 | 509 | .0400 | .0281 [.0071, .0612] |
| .05–.10 | Market | 206,129 | 519 | .0685 | .0514 [.0209, .0936] |
| .10–.20 | Market | 311,410 | 479 | .1433 | .1065 [.0743, .1422] |
| .20–.35 | Market | 403,446 | 408 | .2737 | .2577 [.2110, .3069] |
| .35–.50 | Market | 286,147 | 295 | .4184 | .3940 [.3487, .4414] |
| .50–.65 | Market | 275,054 | 311 | .5791 | .6107 [.5757, .6463] |
| .65–.80 | Market | 239,466 | 403 | .7258 | .7493 [.7008, .7938] |
| .80–.90 | Market | 238,534 | 472 | .8523 | .8901 [.8543, .9230] |
| .90–.97 | Market | 184,951 | 534 | .9375 | .9582 [.9285, .9800] |
| .03–.05 | P* | 113,100 | 370 | .0388 | .0213 [.0060, .0414] |
| .05–.10 | P* | 204,299 | 402 | .0717 | .0507 [.0250, .0831] |
| .10–.20 | P* | 332,459 | 411 | .1462 | .1587 [.1127, .2105] |
| .20–.35 | P* | 449,658 | 366 | .2600 | .2643 [.2182, .3137] |
| .35–.50 | P* | 218,079 | 236 | .4278 | .4088 [.3342, .4914] |
| .50–.65 | P* | 198,645 | 236 | .5699 | .5809 [.4955, .6587] |
| .65–.80 | P* | 330,415 | 366 | .7393 | .7307 [.6817, .7736] |
| .80–.90 | P* | 233,854 | 411 | .8536 | .8580 [.8148, .8968] |
| .90–.97 | P* | 226,042 | 505 | .9406 | .9540 [.9259, .9756] |

### Primary estimates, residuals, and fee bands

The pre-specified primary is the **game-weighted** final-five quiet longshot estimate: A_market=price−Y is 0.02332 [−0.00527, 0.04937], across 309,318 trades / 390 games; two-sided bootstrap p(A=0)=0.0965 and one-sided 95% upper bound is 0.04513. A_P*=P*−Y is 0.04398 [0.01493, 0.07137], as a benchmark sensitivity. The trade-weighted and first-entry estimates are sensitivities. The final-ten quiet sample is secondary (520,103 trades / 622 games): A_market=0.02321 [0.00110, 0.04352]; A_P*=0.03513 [0.01301, 0.05609]. The paired price−P* figures previously displayed for market-price bands are UNINTERPRETABLE and removed from thesis tables because the bands condition on market value. P* and market outcomes are folded to the same selected-team contract side. Source: [paired_residuals.tex](tables/phase5/paired_residuals.tex).

### Constant timestamp-offset sensitivity

Phase 4 was rebuilt after shifting ESPN event, timeout, and quarter-break wall timestamps by −10, −5, 0, +5, and +10 seconds relative to fixed Kalshi trades. These are researcher-chosen sensitivity offsets, not empirically estimated lag bounds. The full-sample primary A estimates range from 0.0135 to 0.0308; four of five two-sided 95% CIs include zero, while +10 seconds gives 0.0308 [0.0037, 0.0551]. On the same-observation quote-valid subset, A ranges from 0.0173 to 0.0262 and all CIs include zero. The estimated taker cost including half-spread ranges from 0.0104 to 0.0109; net A−cost ranges from 0.0069 to 0.0152, with every net CI including zero. Thus the sign remains positive across this grid, but inferential status depends on offset for the full sample, and the cost-adjusted evidence remains inconclusive throughout. Counts vary from 291,383–328,526 trades and 377–431 games. Full results: [phase5_clock_shift_sensitivity.csv](data/interim/phase4_clock_sensitivity/phase5_clock_shift_sensitivity.csv); reproducible with `make phase5-clock-shift`.

Same-observation primary cost comparison: 251,686/309,318 trades (81.37%) have valid five-second quotes, in 376/390 games (96.41%). The full-sample game-weighted fee components are 0.671 points [0.644, 0.696] for large-size taker fees and 0.714 [0.687, 0.741] using per-row observed-size cent rounding; maker-formula components are 0.168 [0.161, 0.174] and 0.227 [0.219, 0.236], respectively. The observed-size calculation rounds each trade row as if it were one fee-assessed order; that is a conservative per-trade approximation, not an observed fee, because the data do not prove that a row equals an order and one order may produce several fills.

On the quote-valid rows, game-weighted A=0.02235 [−0.00546, 0.04894]. Mean half-spread is 0.00416 [0.00399, 0.00434]. At large size, the same-observation taker band is 0.01080 [0.01051, 0.01110], and A−cost is 0.01154 [−0.01616, 0.03820] (one-sided p=0.2065). At observed per-row size, the band is 0.01123 [0.01092, 0.01154], and net is 0.01112 [−0.01657, 0.03780] (p=0.2165). The full-sample maker-formula band is 0.00168 [0.00161, 0.00174] and its conditional net p-value is 0.0520; historical KXNBAGAME maker-fee eligibility remains unresolved. All CIs and net inference use paired game-cluster bootstrap resamples; costs are counterfactual per-contract comparisons, not realized strategy P&L. Final-ten estimates remain secondary. See [phase5_primary_costs.json](data/interim/phase5/phase5_primary_costs.json) and [primary_estimand_band_tests.tex](tables/phase5/primary_estimand_band_tests.tex).

### 10–40¢ weighting sensitivity

The band is defined by market price; P* is evaluated on those same trades. Values below are 95% game-cluster bootstrap CIs. Estimators, counts, and estimates for (d), knowable, final 2, final 5, primary final-5 quiet, and final-10 quiet are in [weighting_sensitivity.tex](tables/phase5/weighting_sensitivity.tex) and [phase5_weighting_estimators.csv](data/interim/phase5/phase5_weighting/phase5_weighting_estimators.csv). Here “trade” is pooled trade-weighted, “game” equally weights games, and “first” uses each game's first eligible trade.

Knowable-window calibration bins for trade-weighted and first-entry observations, including trade/game counts, mean probability, observed frequency, and 95% clustered intervals, are in [phase5_knowable_weighting_bins.csv](data/interim/phase5/phase5_weighting/phase5_knowable_weighting_bins.csv). The full knowable sample contains 2,615,732 trades / 1,210 games.

First-entry sensitivity estimates (95% two-sided CI; one-sided 95% upper bound): primary final-five quiet A_market=.01154 [−.01918,.04136]; U=.03729; A_P*=.02418 [−.00640,.05465]; U=.05023. Final-ten quiet A_market=.01613 [−.00671,.03880]; U=.03590; A_P*=.02182 [−.00223,.04476]; U=.04247. These are sensitivity estimates, not the pre-specified primary. The regenerated [weighting_sensitivity.tex](tables/phase5/weighting_sensitivity.tex) shows these first-entry upper bounds separately; its prior first-entry-primary caption and cost tests with mismatched quote coverage have been removed. The separate 10–40¢ table still headlines first-entry by the earlier estimator amendment.

### Selection diagnostics and mechanisms

For final-three-minute longshots at 0.05–0.20, Y=1 rows: 118,673 trades / 114 games; mean wall time to last ESPN play 17.95 minutes; median 16.88; 29 OT games / 25.4%. Y=0: 1,079,970 / 555; mean 11.52; median 7.95; 38 OT games / 6.8%. These descriptive counts and moments are in [mechanism_walltime_overtime.tex](tables/phase5/mechanism_walltime_overtime.tex); the distribution is plotted with the x-axis shown through 60 minutes and counts above 60 minutes labeled in [longshot_wall_time_distribution.pdf](figures/phase5/longshot_wall_time_distribution.pdf).

Within final-three-minute longshots at .05–.20, P* gap for trades inside (d): N=736,299 / 473 games, Y−market=−.06514 [−.07680, −.05185], Y−P*=−.09393 [−.10591, −.08113]. Outside (d): N=462,342 / 330, Y−market=.03336 [−.00362, .07388], Y−P*=.00828 [−.02819, .04753]. Source: [phase5_publication_summary.json](data/interim/phase5/phase5_publication_summary.json).

Dose response uses final-three regulation-minute trades, in-game only, 0.03–0.97 market quotes, grouped by wall minutes to last ESPN play. Estimates are game-weighted with 95% game-cluster CIs. P* and Y are folded to the same longshot side: P* is kept when selected-contract price ≤.5 and complemented when it is >.5. Source: [phase5_dose_response.csv](data/interim/phase5/phase5_dose_response.csv).

| Wall min | Side | Trades / games | Y−market [95% CI] | Y−P* [95% CI] |
|---|---|---:|---:|---:|
| 0–2 | Longshot | 182,582 / 213 | −.0776 [−.0948, −.0587] | −.1382 [−.1607, −.1150] |
| 0–2 | Favorite | 182,582 / 213 | .0776 [.0587, .0948] | .1382 [.1150, .1607] |
| 2–5 | Longshot | 485,927 / 409 | −.0623 [−.0774, −.0463] | −.0916 [−.1073, −.0744] |
| 2–5 | Favorite | 485,927 / 409 | .0623 [.0463, .0774] | .0916 [.0744, .1073] |
| 5–10 | Longshot | 962,770 / 542 | −.0532 [−.0680, −.0371] | −.0548 [−.0700, −.0384] |
| 5–10 | Favorite | 962,770 / 542 | .0532 [.0371, .0680] | .0548 [.0384, .0700] |
| 10–20 | Longshot | 799,087 / 372 | −.0219 [−.0497, .0086] | −.0210 [−.0486, .0085] |
| 10–20 | Favorite | 799,087 / 372 | .0219 [−.0086, .0497] | .0210 [−.0085, .0486] |
| 20+ | Longshot | 436,589 / 88 | .1027 [.0249, .1840] | .0857 [.0110, .1637] |
| 20+ | Favorite | 436,589 / 88 | −.1027 [−.1840, −.0249] | −.0857 [−.1637, −.0110] |

5c event-response paths (mean response; event count) for tau bins 0–5, 5–15, 15–30, 30–60, and 60–120 seconds: running clock = .000602 (2,486), .000600 (1,843), −.003633 (388), −.003942 (132), −.006003 (46); followed by timeout = .001350 (1,983), .000629 (2,007), −.000175 (2,006), −.000294 (2,011), .000055 (2,011). Source: [phase5c_decay_fits.csv](data/interim/phase5/phase5c_decay_fits.csv) for fitted stratum results and [phase5_publication_summary.json](data/interim/phase5/phase5_publication_summary.json) for pooled paths.

5e pooled oriented drift is in price points per contract: final 5, horizons 5/15/30/60 seconds = .000037 [−.000093,.000175] (683 games), .000064 [−.000239,.000384] (680), .000011 [−.000576,.000609] (671), −.000063 [−.001238,.001032] (639); final 10 = .000020 [−.000058,.000106] (1,032), .000059 [−.000130,.000267] (1,028), .000070 [−.000252,.000400] (1,018), .000052 [−.000552,.000691] (985). Source: [phase5e_drift.csv](data/interim/phase5/phase5e_drift.csv).

No position-conditioned Phase 6c wallet mechanism analysis was run; the read-only Polymarket selection summary and fill-level calibration overlay were used. The Data API maker/taker join itself is one-to-one by transaction hash in the cached season file; this does not establish wallet inventories.


### Read-only Polymarket integration

The Phase 6 summary [polymarket_selection_summary.json](data/interim/phase6/polymarket_selection_summary.json) was read without modification. The reproducible overlay is [src/phase5_polymarket_overlay.py](src/phase5_polymarket_overlay.py). The calibration figure now overlays Polymarket market and P* curves on the Kalshi figure; Polymarket bin-level game-cluster intervals are not present in the supplied summary, so the figure uses game-clustered 95% bands for both venues, computed from the read-only fill-level parquet. Each panel uses one coordinate across venues: own-token/market-YES for (d), and seed-17 selected-team for final 5. Bins and intervals are in [phase5_calibration_common_coordinates.csv](data/interim/phase5/phase5_calibration_common_coordinates.csv); validation is [phase5_calibration_common_coordinates_validation.json](data/interim/phase5/phase5_calibration_common_coordinates_validation.json). The α figure shows both platforms with game-clustered 95% intervals.

The P* placebo table now places Kalshi and Polymarket fits side by side. Full-season (d) Polymarket fits: market α=1.541 [1.313, 1.852], β=1.196; P* α=1.497 [1.339, 1.723], β=1.189; 389,439 maker fills / 1,201 games. The Polymarket no-overtime market α=1.515 [1.296, 1.845], β=1.177, and P* α=1.381 [1.245, 1.582], β=1.125 (351,414 / 1,148) are invalid for inference because OT status depends on the realized outcome path; omitted from thesis tables/figures. Knowable: market α=1.115 [0.943, 1.358], β=.989; P* α=1.028 [.891, 1.218], β=.953; 402,173 / 1,201. Final 2: market α=1.116 [.919, 1.405], β=1.001; P* α=1.170 [.999, 1.434], β=.975; 389,153 / 1,191. Final 3: market α=1.086 [.917, 1.328], β=.972; P* α=1.092 [.952, 1.310], β=.946; 492,480 / 1,203. Final 5: market α=1.055 [.901, 1.247], β=.940; P* α=1.025 [.896, 1.190], β=.908; 738,935 / 1,207. Final 10: market α=1.057 [.930, 1.208], β=.951; P* α=.981 [.875, 1.112], β=.901; 1,295,617 / 1,210. Exact paired Kalshi/Polymarket estimates and counts are in [pstar_placebo.tex](tables/phase5/pstar_placebo.tex). The paper-date playoff subset is not available in the Polymarket summary; the table caption records this coverage limit.

The supplied Polymarket summary does not contain wall minutes to game end or overtime indicators grouped by final longshot outcome, so the existing [wall-time/overtime table](tables/phase5/mechanism_walltime_overtime.tex) remains Kalshi-only. For the mechanism fields present in both platform summaries, a side-by-side table reports final-three-minute 0.05–0.20 longshot `Y−p` inside and outside (d): inside (d), Kalshi market −.0651 [−.0768, −.0518], P* −.0939 [−.1059, −.0811]; Polymarket market −.0646 [−.0774, −.0500], P* −.0906 [−.1035, −.0769] (90,512 fills / 453 games). Outside (d), Kalshi market .0334 [−.0036, .0739], P* .0083 [−.0282, .0475]; Polymarket market .0346 [−.0042, .0737], P* .0135 [−.0247, .0516] (61,855 / 301). Source: [mechanism_platform_comparison.tex](tables/phase5/mechanism_platform_comparison.tex), with complete inputs in the read-only Polymarket summary and Phase 5 publication JSON.

For calibration curves, each panel uses one coordinate across venues: own-token/market-YES for (d), and the shared seed-17 selected-team contract for final five. Game-clustered 95% bands for both venues are computed from the read-only Polymarket fill-level parquet. Validated Polymarket counts: (d), 389,439 fills / 1,201 games; final five, 738,935 / 1,207. Data and intervals: [phase5_calibration_common_coordinates.csv](data/interim/phase5/phase5_calibration_common_coordinates.csv); validation: [phase5_calibration_common_coordinates_validation.json](data/interim/phase5/phase5_calibration_common_coordinates_validation.json).

## Selection formula, paired Prelec differences, and headline-fit robustness

For the (d) selection formula, the base is all in-game final-regulation and overtime trades with probability in the analysis range 0.03–0.97. At each price bin, π₁ and π₀ are the shares of base trades that fall in (d), separately by realized outcome. One-cent bins with fewer than 30 distinct in-window games for either outcome are pooled to their five-cent bin. The predicted curve is evaluated at the in-window mean probability in each bin. Observed and predicted calibration bands, and Prelec-fit intervals, use 2,000 game-cluster bootstrap draws. The predicted-curve market-price fit is α=1.350 [1.216, 1.523], β=1.087 [1.041, 1.151] (8,559,393 base trades / 1,000 games; 2,053,734 in-window / 683 games). With P* substituted, α=1.462 [1.319, 1.631], β=1.139 [1.090, 1.203] (8,464,104 / 955; 2,185,828 / 648). The no-overtime predicted fits (market α=1.204 [1.070, 1.355], β=1.037 [0.995, 1.089]; P* α=1.289 [1.167, 1.441], β=1.078 [1.042, 1.127]) are invalid for inference because OT status is outcome-dependent; those series were removed from the thesis figure. Curves: [selection_formula_calibration.pdf](figures/phase5/selection_formula_calibration.pdf) and [selection_formula_calibration.png](figures/phase5/selection_formula_calibration.png). Bin estimates and bands: [phase5_selection_formula_bins.csv](data/interim/phase5/phase5_selection_formula_bins.csv); fit summaries: [phase5_selection_formula.json](data/interim/phase5/phase5_selection_formula.json).

Paired market-minus-P* isotonic Prelec α differences, using the same trades and resampled games for each pair, are: (d) +0.047 [−0.105, 0.228] (1,202 games); knowable +0.132 [0.051, 0.234] (1,210); final 5 +0.060 [−0.003, 0.130] (1,211). The no-overtime paired difference (+0.142 [−0.003, 0.318], 1,149 games) is invalid for inference because OT status is outcome-dependent and has been removed from thesis tables/figures. Intervals are 95% game-clustered bootstrap CIs, 2,000 draws. Full results: [phase5_paired_alpha_differences.csv](data/interim/phase5/phase5_paired_alpha_differences.csv) and [phase5_paired_alpha_differences.json](data/interim/phase5/phase5_paired_alpha_differences.json).

Headline-fit robustness reports isotonic trade-weighted α with 95% game-clustered bootstrap CIs (2,000 draws). Each cell below is main convention / excluding the 282 weak-alignment games / home-team convention:

| Window | Coordinate | Main convention | Excluding weak games | Home-team convention |
|---|---|---:|---:|---:|
| (d) | Market | 1.526 [1.316, 1.822] | 1.589 [1.316, 1.966] | 1.582 [1.340, 1.928] |
| (d) | P* | 1.479 [1.319, 1.700] | 1.472 [1.295, 1.735] | 1.536 [1.343, 1.838] |
| Knowable | Market | 1.161 [1.012, 1.356] | 1.236 [1.049, 1.495] | 1.194 [1.032, 1.425] |
| Knowable | P* | 1.029 [0.900, 1.174] | 1.078 [0.943, 1.260] | 1.046 [0.913, 1.231] |
| Final 5 | Market | 1.053 [0.919, 1.210] | 1.088 [0.935, 1.281] | 1.114 [0.964, 1.299] |
| Final 5 | P* | 0.993 [0.874, 1.121] | 1.041 [0.907, 1.205] | 1.030 [0.892, 1.195] |

The full samples, game counts, β estimates, and intervals are in [phase5_alpha_robustness.csv](data/interim/phase5/phase5_alpha_robustness.csv) and [phase5_alpha_robustness.json](data/interim/phase5/phase5_alpha_robustness.json). The analyses are reproducible with [phase5_selection_formula.py](src/phase5_selection_formula.py).

## Selection-gap decomposition by price band

Estimates are trade weighted and shown in price points; CIs are 95% game-cluster bootstrap intervals (2,000 draws). Bands are defined by market-YES price, so the reported decomposition is market-only; applying these bands to P* would measure disagreement with market price, not P* calibration. For the (d) estimates, π₁ and π₀ are re-estimated within each bootstrap draw from all in-game final-regulation and OT trades; predicted is the average `C(p) - p`, and remainder is observed minus predicted. Knowable rows report observed market gaps only. P* calibration is assessed by the separate placebo fits binned on P* itself.

| Window | Market price band | Source | Trades / games | Observed `Y-p` | Selection-predicted `C(p)-p` | Remainder |
|---|---:|---|---:|---:|---:|---:|
| (d) | 0.05–0.20 | Market | 532,303 / 561 | −6.24 [−8.37, −3.52] | −3.97 [−5.39, −2.47] | −2.27 [−4.26, −0.02] |
| (d) | 0.10–0.40 | Market | 678,974 / 450 | −8.99 [−12.18, −5.62] | −5.40 [−7.61, −3.30] | −3.59 [−6.15, −0.88] |
| Knowable | 0.05–0.20 | Market | 525,915 / 541 | −3.00 [−5.89, 0.39] | — | — |
| Knowable | 0.10–0.40 | Market | 812,839 / 478 | −2.64 [−6.30, 1.18] | — | — |

The archived no-overtime market decomposition rows (0.05–0.20: observed −6.61 [−8.81, −3.86], predicted −2.33 [−4.08, −0.69], remainder −4.28 [−6.56, −1.62]; 0.10–0.40: observed −8.71 [−12.32, −4.76], predicted −3.01 [−5.43, −0.59], remainder −5.70 [−8.58, −2.58]) are invalid for inference because OT status is outcome-dependent and are excluded from the thesis table. Archived P* no-OT rows are invalid for the same reason and removed; P* market-price-band decomposition rows are omitted because they do not measure P* calibration.

Point estimates, bootstrap details, and the scripts are in [phase5_selection_decomposition.json](data/interim/phase5/phase5_selection_decomposition.json), [phase5_selection_decomposition.csv](data/interim/phase5/phase5_selection_decomposition.csv), and [phase5_selection_decomposition.py](src/phase5_selection_decomposition.py). Knowable-window estimates are separately saved in [phase5_selection_decomposition_knowable.json](data/interim/phase5/phase5_selection_decomposition_knowable.json).

### Cross-fitted test of realized-end selection

The earlier 60–64% accounting decomposition substitutes quoted probability
for the base-sample outcome rate, implicitly assuming market-price calibration
before selection. It also estimates selection rates over all prices while
reporting a selected market-price band. The replacement diagnostic estimates
the base outcome rate and the outcome-specific chance of entering the window
on other games, restricting both training and target observations to the same
5–20¢ selected-team market-price cohort and common market/P* support. The
target is the ten wall minutes before the last ESPN play, ending before that
play. Five-fold splits are by game. Fixed 5¢ and 10¢ bins are used, with
Jeffreys Beta(0.5, 0.5) smoothing for sparse cells. A game-cluster bootstrap
re-estimates the conditional outcome and selection rates in each of 2,000
draws.

The common cohort contains 532,303 trades in 561 games. For market price,
the observed `Y−price` gap is −6.24 percentage points (95% CI −8.32 to −3.64).
The held-out base gap on the same target trade mix is −0.62 points (−2.93 to
+1.93); the selection-adjusted prediction is −6.24 (−8.33 to −3.71). The
unexplained remainder is −0.003 points (−0.14 to +0.17). At 10¢ bins, the
remainder is +0.01 (−0.11 to +0.18). The estimated selection shift from the
base is −5.62 points at 5¢ bins (−8.00 to −3.11). Thus, for this
trade-weighted longshot cohort, the market-price calibration gap in the
realized-end window is predicted by the outcome-dependent change in which
trades enter that window.

On the same cohort, `Y−P*` is −12.08 points (−14.22 to −9.46). Its base gap
is already −5.15 points (−7.47 to −2.38); the selection-adjusted prediction
is −12.13 (−14.14 to −9.87), leaving a +0.05-point remainder (−0.55 to
+0.84). At 10¢ bins the remainder is −0.12 (−0.59 to +0.32). This separates
P*'s baseline discrepancy in the market-defined longshot cohort from the
additional change associated with entering the realized-end window; it does
not validate P* as a true probability for this subgroup.

This is a held-out predictive accounting result, not a causal estimate or a
claim about who trades. It shows that the realized-end window—defined using a
future event—can generate the observed calibration pattern in the selected
cohort. It strengthens the case for making windows defined by information
available at the trade time central to the thesis. Reproduce with `make
phase5-crossfit-selection-diagnostic`; implementation:
[phase5_crossfit_selection_diagnostic.py](src/phase5_crossfit_selection_diagnostic.py),
summary: [phase5_crossfit_selection_diagnostic.json](data/interim/phase5/phase5_crossfit_selection_diagnostic.json),
and game-level predictions:
[phase5_crossfit_selection_diagnostic_games.csv](data/interim/phase5/phase5_crossfit_selection_diagnostic_games.csv).

The independent-venue validation applies the same outcome-token mapping and
cross-fitted estimator to Polymarket maker fills. In its common-support
5–20¢ cohort, 49,659 fills across 265 games, the observed `Y−price` gap is
−6.41 points (95% CI −9.33 to −2.73); the held-out selection prediction is
−6.39 (−9.21 to −2.84), leaving −0.02 points (−0.30 to +0.38). The estimated
base-to-window selection shift is −6.24 points (−10.06 to −2.52). At 10¢
bins, the remainder is −0.01 (−0.31 to +0.40). For P*, the observed gap is
−11.60 points (−14.78 to −7.50), selection predicts −11.71 (−14.47 to
−8.25), and the remainder is +0.11 (−1.44 to +1.41); the 10¢-bin remainder
is also near zero. Both venues therefore show a similar selection shift in
the 5–20¢ market-defined longshot cohort. The Polymarket target has fewer
independent games and these results share ESPN timing and model construction
with the Kalshi analysis, so they are cross-venue corroboration, not a fully
independent measurement system. The near-zero remainder is also trade-weight
specific: the game-weighted Polymarket remainder is +2.89 points, with a
fixed-prediction game-bootstrap interval of −0.13 to +6.19 points. Reproduce with `make
phase5-polymarket-selection-crossfit`; implementation:
[phase5_polymarket_selection_crossfit.py](src/phase5_polymarket_selection_crossfit.py),
summary: [polymarket_crossfit_selection_diagnostic.json](data/interim/phase2/polymarket_crossfit_selection_diagnostic.json),
game-level predictions:
[polymarket_crossfit_selection_diagnostic_games.csv](data/interim/phase2/polymarket_crossfit_selection_diagnostic_games.csv).

The diagnostic also varies the market-defined cohort to 10–40¢ and the
retrospective window to 5, 10, and 15 wall minutes. At ten minutes in the
10–40¢ cohort, Kalshi has 678,974 trades/450 games: observed market gap
−8.99 points, predicted −8.99, remainder 0.00 (95% CI −0.27 to +0.32);
P* is −10.84 observed versus −10.80 predicted, remainder −0.04 (−0.68 to
+0.53). Polymarket has 64,351 fills/258 games: market gap −9.38 observed
versus −9.45 predicted, remainder +0.07 (−0.55 to +0.70); P* is −10.29
versus −9.99, remainder −0.31 (−1.78 to +0.71). Across 5-, 10-, and
15-minute windows, market-price remainders include zero in both venues and
both price bands. The P* remainders also include zero except Polymarket's
5-minute 10–40¢ estimate at 5¢ bins (−2.19 points, 95% CI −7.37 to −0.12);
at 10¢ bins that remainder is −1.49 points (−4.55 to +0.08). Treat that
small-cell exception as exploratory; these specification checks are not
multiple-testing adjusted and use the original model-refit bootstrap. The
point estimates support outcome-dependent selection as a plausible accounting
mechanism in pooled trades, but weighting and chronological holdouts do not
establish a stable, game-level predictive fit. The ten-minute cross-venue comparison is visualized in
[crossfit_selection_validation.pdf](figures/phase5/crossfit_selection_validation.pdf)
and [crossfit_selection_validation.png](figures/phase5/crossfit_selection_validation.png);
recreate it with `make phase5-selection-crossfit-figure`.

### Cross-fit weighting, influence, and chronological holdout audit

The near-zero remainder in the headline random-fold result is specific to the
trade-weighted estimand. Giving each of the same 561 games equal weight yields
an observed market gap of −6.68 points, a selection-adjusted prediction of
−5.70 points, and a remainder of −0.98 points. A fixed-prediction game
bootstrap gives the equal-game remainder a 95% interval of −2.17 to +0.35
points. For the trade-weighted remainder, the analogous interval is −2.20 to
+2.67 points, much wider than the original model-refit bootstrap interval
(−0.14 to +0.17 points). The fixed-prediction interval conditions on the
cross-fitted predictions and does not refit the training folds; it is an
inference sensitivity, not a replacement interval. The difference signals
that uncertainty about this cross-fitted aggregate depends materially on the
bootstrap treatment of shared training information.

The target residual is also concentrated. Game 401810879 contributes +0.92
points to the trade-weighted remainder while accounting for 1.0% of target
trades; holding all fitted predictions fixed, omitting it moves the pooled
remainder to −0.93 points. This leave-one-game-out calculation is a target
influence diagnostic, not a refitted influence estimate.

The same weighting pattern appears on Polymarket. Its 265-game, 49,659-fill
10-minute 5–20¢ cohort has a trade-weighted remainder of −0.02 points, with a
fixed-prediction game-bootstrap interval of −2.99 to +3.90 points; equal-game
weighting gives +2.89 points (−0.13 to +6.19). Game 401810879 contributes
+1.25 points to the trade-weighted remainder in this sample. Thus the two
venues' point estimates align when trades are pooled, but their game-level
performance does not support a claim of uniformly accurate prediction.

A post-hoc chronological transport check trains on the first 70% of games by
last-play timestamp (847 training games before filters; cutoff February 25,
2026) and evaluates on the final 30%. In the 5–20¢ market-price cohort, 137
held-out games contribute 161,087 selected trades. The observed `Y−price`
gap is −4.85 points (two-way game-bootstrap 95% CI −10.05 to +2.48); the
earlier-game selection model predicts −6.73 points (−8.47 to −4.77), leaving
a +1.89-point remainder (−3.68 to +9.41). The held-out P* remainder is +0.71
points (−5.35 to +8.27). The model therefore predicts the direction and
approximate scale of the market gap, but this test is underpowered to
distinguish a close fit from a meaningful miss. It does not validate the
random-fold near-zero remainder as a stable out-of-time result. This is one
post-hoc same-season split, not an independent-season replication. Full
outputs are in [phase5_temporal_selection_validation.json](data/interim/phase5/phase5_temporal_selection_validation.json),
reproducible with `make phase5-temporal-selection-validation`.

The postponed Golden State–Minnesota contract originally scheduled for
January 24 was separately remapped to its ESPN completed-game record for
January 25 and its 29,336 in-game market rows were aligned in a sidecar.
It contributes zero final-five quiet-stoppage longshot trades and zero
5–20¢ trades in the ten-minute realized-end window; adding it therefore does
not alter the pre-specified primary or headline selection diagnostic. This
resolves the linkage question without changing the canonical sample. Details
and reproduction are in [DEVIATIONS.md](DEVIATIONS.md) and
`make phase5-postponed-game-sensitivity`.

The weighting and fixed-prediction bootstrap calculations are in
[phase5_selection_inference_audit.json](data/interim/phase5/phase5_selection_inference_audit.json),
reproducible with `make phase5-selection-inference-audit`. Taken together,
these checks support the narrower statement that outcome-dependent selection
can account for much of the retrospective-window gap in this season's
random-fold, trade-weighted analysis. They do not establish that the
adjustment fully explains the gap across games or time.

## Corrected selection-free residual investigation

All price−P* estimates in market-price bands from the prior localization, clock-decay regression, and event-free convergence analyses are **UNINTERPRETABLE**. Market-price band selection conditions price−P* on market value; the initial-gap-size convergence regression is mechanically positive under noise. These values remain archived with this status in [phase5_residual_mechanisms.json](data/interim/phase5/phase5_residual_mechanisms.json) and [phase5_residual_localization.csv](data/interim/phase5/phase5_residual_localization.csv). No such estimates are retained in thesis tables.

The reported outcome is `Y − price` in price points. Results use only the knowable window and final five regulation game-clock minutes, without game-end or overtime conditioning. CIs are 95% game-cluster bootstrap intervals (2,000 draws). `First-entry` is the first eligible observation per game per cell. Game weighting is labeled sensitivity. Each cell shows trades/games for trade-weighted and game-weighted estimates, and selected observations/games for first-entry.

### Kalshi


#### Overall


| Window | Band | Cell / measure | Trade-weighted | First-entry | Game-weighted sensitivity |
|---|---:|---|---:|---:|---:|
| Knowable | 0.05–0.20 | all | -3.12 [-5.92, -0.01] (932,022/567) | 1.26 [-1.54, 4.21] (567/567) | -2.42 [-4.39, -0.26] (932,022/567) |
| Knowable | 0.10–0.40 | all | -3.02 [-6.57, 0.58] (1,382,217/483) | -1.07 [-4.68, 2.37] (483/483) | -7.53 [-9.67, -5.34] (1,382,217/483) |
| Final 5 | 0.05–0.20 | all | -1.28 [-4.52, 2.26] (1,681,531/684) | 0.60 [-2.02, 3.26] (684/684) | -3.44 [-5.05, -1.72] (1,681,531/684) |
| Final 5 | 0.10–0.40 | all | -0.76 [-4.07, 2.55] (2,455,551/579) | -0.50 [-3.57, 2.58] (579/579) | -7.62 [-9.57, -5.68] (2,455,551/579) |


#### Running vs stopped


| Window | Band | Cell / measure | Trade-weighted | First-entry | Game-weighted sensitivity |
|---|---:|---|---:|---:|---:|
| Knowable | 0.05–0.20 | running | -4.05 [-6.55, -1.30] (290,252/544) | -0.73 [-3.45, 2.20] (544/544) | -1.90 [-4.07, 0.39] (290,252/544) |
| Knowable | 0.05–0.20 | stopped | -2.70 [-5.67, 0.60] (641,770/518) | -0.09 [-2.93, 2.61] (518/518) | -2.17 [-4.32, 0.11] (641,770/518) |
| Knowable | 0.10–0.40 | running | -2.18 [-6.08, 1.72] (474,995/473) | -0.84 [-4.53, 2.86] (473/473) | -6.01 [-8.64, -3.40] (474,995/473) |
| Knowable | 0.10–0.40 | stopped | -3.46 [-7.29, 0.39] (907,222/440) | -2.50 [-5.99, 1.16] (440/440) | -7.44 [-9.99, -4.75] (907,222/440) |
| Final 5 | 0.05–0.20 | running | -2.55 [-5.11, 0.27] (474,780/674) | 0.34 [-2.31, 2.84] (674/674) | -2.42 [-4.22, -0.62] (474,780/674) |
| Final 5 | 0.05–0.20 | stopped | -0.78 [-4.16, 3.41] (1,206,751/654) | 0.01 [-2.41, 2.55] (654/654) | -3.69 [-5.37, -2.04] (1,206,751/654) |
| Final 5 | 0.10–0.40 | running | -0.58 [-4.04, 2.93] (756,005/570) | -0.45 [-3.98, 2.75] (570/570) | -6.17 [-8.35, -3.98] (756,005/570) |
| Final 5 | 0.10–0.40 | stopped | -0.84 [-4.39, 3.12] (1,699,546/551) | -1.47 [-4.89, 2.20] (551/551) | -7.88 [-9.86, -5.79] (1,699,546/551) |


#### Taker buys vs sells


| Window | Band | Cell / measure | Trade-weighted | First-entry | Game-weighted sensitivity |
|---|---:|---|---:|---:|---:|
| Knowable | 0.05–0.20 | buy longshot | -3.54 [-6.22, -0.35] (541,946/555) | -3.07 [-5.47, -0.44] (555/555) | -3.53 [-5.48, -1.47] (541,946/555) |
| Knowable | 0.05–0.20 | sell longshot | -2.55 [-5.44, 0.57] (390,076/543) | 1.74 [-1.22, 4.94] (543/543) | -1.95 [-3.96, 0.25] (390,076/543) |
| Knowable | 0.10–0.40 | buy longshot | -3.64 [-7.15, -0.10] (796,932/483) | -1.66 [-5.23, 2.08] (483/483) | -7.91 [-10.11, -5.54] (796,932/483) |
| Knowable | 0.10–0.40 | sell longshot | -2.18 [-5.64, 1.57] (585,285/469) | -0.31 [-3.90, 3.55] (469/469) | -6.91 [-9.16, -4.46] (585,285/469) |
| Final 5 | 0.05–0.20 | buy longshot | -1.85 [-4.97, 1.84] (981,596/681) | -2.53 [-4.77, -0.07] (681/681) | -4.02 [-5.60, -2.32] (981,596/681) |
| Final 5 | 0.05–0.20 | sell longshot | -0.48 [-3.80, 3.17] (699,935/651) | 1.10 [-1.58, 3.91] (651/651) | -3.02 [-4.68, -1.25] (699,935/651) |
| Final 5 | 0.10–0.40 | buy longshot | -1.28 [-4.68, 2.17] (1,424,548/578) | -1.58 [-5.09, 1.77] (578/578) | -7.89 [-9.76, -5.84] (1,424,548/578) |
| Final 5 | 0.10–0.40 | sell longshot | -0.04 [-3.49, 3.74] (1,031,003/565) | 0.23 [-3.11, 3.75] (565/565) | -7.15 [-9.21, -5.05] (1,031,003/565) |


#### Trade price vs valid mid


Valid-mid rows require both reconstructed sides in the 5-second lookback and no crossed quote. `trade price` reports Y−trade price; `mid` reports Y−mid, on the same rows.


| Window | Band | Cell / measure | Trade-weighted | First-entry | Game-weighted sensitivity |
|---|---:|---|---:|---:|---:|
| Knowable | 0.05–0.20 | trade price | -2.71 [-5.41, 0.23] (604,592/558) | -0.80 [-3.57, 1.93] (558/558) | -2.12 [-4.21, 0.18] (604,592/558) |
| Knowable | 0.05–0.20 | mid: Y − mid | -2.67 [-5.39, 0.46] (604,592/558) | -3.38 [-6.10, -0.63] (558/558) | -2.49 [-4.52, -0.40] (604,592/558) |
| Knowable | 0.10–0.40 | trade price | -2.44 [-6.04, 1.52] (784,476/480) | -0.45 [-3.96, 3.18] (480/480) | -6.79 [-9.21, -4.43] (784,476/480) |
| Knowable | 0.10–0.40 | mid: Y − mid | -2.36 [-6.05, 1.74] (784,476/480) | -0.35 [-3.99, 3.46] (480/480) | -6.55 [-8.91, -4.25] (784,476/480) |
| Final 5 | 0.05–0.20 | trade price | -0.93 [-4.01, 2.76] (1,150,563/678) | -0.50 [-3.06, 2.07] (678/678) | -2.67 [-4.41, -0.94] (1,150,563/678) |
| Final 5 | 0.05–0.20 | mid: Y − mid | -0.87 [-3.96, 2.73] (1,150,563/678) | -2.31 [-4.78, 0.19] (678/678) | -2.77 [-4.48, -0.99] (1,150,563/678) |
| Final 5 | 0.10–0.40 | trade price | -0.08 [-3.69, 3.83] (1,505,628/574) | -0.29 [-3.70, 3.03] (574/574) | -6.58 [-8.60, -4.45] (1,505,628/574) |
| Final 5 | 0.10–0.40 | mid: Y − mid | 0.02 [-3.62, 3.92] (1,505,628/574) | -0.09 [-3.47, 3.25] (574/574) | -6.34 [-8.40, -4.14] (1,505,628/574) |


#### Minutes remaining


| Window | Band | Cell / measure | Trade-weighted | First-entry | Game-weighted sensitivity |
|---|---:|---|---:|---:|---:|
| Final 5 | 0.05–0.20 | 0–1 min | -0.82 [-5.25, 4.29] (722,801/406) | 0.12 [-3.11, 3.42] (406/406) | -2.09 [-4.35, 0.30] (722,801/406) |
| Final 5 | 0.05–0.20 | 1–2 min | -3.05 [-6.78, 1.78] (280,913/420) | -0.83 [-3.99, 2.40] (420/420) | 0.27 [-2.46, 3.47] (280,913/420) |
| Final 5 | 0.05–0.20 | 2–3 min | -2.85 [-6.89, 1.49] (194,927/425) | -0.93 [-3.91, 2.33] (425/425) | -0.15 [-3.08, 2.88] (194,927/425) |
| Final 5 | 0.05–0.20 | 3–5 min | -0.30 [-4.11, 3.94] (482,890/533) | 0.27 [-2.72, 3.10] (533/533) | 1.25 [-1.48, 3.96] (482,890/533) |
| Final 5 | 0.10–0.40 | 0–1 min | -4.11 [-8.54, 0.95] (918,822/355) | -3.86 [-7.59, 0.16] (355/355) | -8.08 [-10.71, -5.19] (918,822/355) |
| Final 5 | 0.10–0.40 | 1–2 min | -0.70 [-6.27, 5.07] (441,002/415) | -2.60 [-6.42, 1.24] (415/415) | -4.12 [-7.31, -0.81] (441,002/415) |
| Final 5 | 0.10–0.40 | 2–3 min | 0.44 [-5.07, 6.05] (327,473/451) | -0.51 [-4.25, 3.39] (451/451) | -1.87 [-5.43, 1.89] (327,473/451) |
| Final 5 | 0.10–0.40 | 3–5 min | 2.71 [-2.15, 7.85] (768,254/548) | 0.22 [-3.26, 3.75] (548/548) | -0.42 [-3.51, 2.63] (768,254/548) |


#### Score × possession (descriptive)


Descriptive cells only.


| Window | Band | Cell / measure | Trade-weighted | First-entry | Game-weighted sensitivity |
|---|---:|---|---:|---:|---:|
| Knowable | 0.05–0.20 | 1–3 × yes | -3.57 [-8.80, 2.75] (89,517/236) | 0.96 [-3.29, 5.95] (236/236) | -0.05 [-4.13, 4.28] (89,517/236) |
| Knowable | 0.05–0.20 | 1–3 × no | -1.65 [-7.31, 4.82] (127,722/255) | -0.60 [-4.79, 3.83] (255/255) | -1.01 [-4.95, 3.16] (127,722/255) |
| Knowable | 0.05–0.20 | 1–3 × unknown | -3.26 [-7.35, 1.29] (215,857/330) | 4.24 [0.10, 8.49] (330/330) | -0.46 [-3.95, 3.22] (215,857/330) |
| Knowable | 0.05–0.20 | 4–6 × yes | -4.71 [-8.75, 0.46] (85,407/271) | -3.06 [-6.21, 0.58] (271/271) | -2.63 [-5.73, 0.60] (85,407/271) |
| Knowable | 0.05–0.20 | 4–6 × no | -2.79 [-7.35, 2.26] (109,106/287) | -5.36 [-8.43, -2.16] (287/287) | -2.68 [-5.45, 0.50] (109,106/287) |
| Knowable | 0.05–0.20 | 4–6 × unknown | -2.17 [-5.94, 2.33] (210,994/391) | -2.73 [-5.68, 0.44] (391/391) | -1.24 [-3.96, 1.75] (210,994/391) |
| Knowable | 0.05–0.20 | 7+ × yes | -5.19 [-8.46, -0.02] (21,224/133) | -4.18 [-6.61, -1.03] (133/133) | -3.93 [-6.28, -0.89] (21,224/133) |
| Knowable | 0.05–0.20 | 7+ × no | -5.38 [-7.79, -2.39] (21,189/147) | -3.90 [-6.60, -0.76] (147/147) | -3.09 [-5.72, 0.22] (21,189/147) |
| Knowable | 0.05–0.20 | 7+ × unknown | -5.42 [-6.96, -3.37] (42,221/241) | -5.64 [-7.39, -3.40] (241/241) | -4.13 [-5.90, -2.02] (42,221/241) |
| Knowable | 0.10–0.40 | 1–3 × yes | -1.38 [-7.81, 5.41] (228,012/330) | 0.73 [-4.08, 5.45] (330/330) | -3.51 [-7.55, 0.62] (228,012/330) |
| Knowable | 0.10–0.40 | 1–3 × no | -3.84 [-9.53, 2.10] (240,657/328) | -5.29 [-9.67, -0.72] (328/328) | -5.91 [-9.66, -2.20] (240,657/328) |
| Knowable | 0.10–0.40 | 1–3 × unknown | -1.71 [-5.91, 2.71] (479,798/376) | 0.35 [-4.17, 4.71] (376/376) | -6.33 [-9.64, -3.03] (479,798/376) |
| Knowable | 0.10–0.40 | 4–6 × yes | -1.55 [-9.03, 6.74] (65,823/216) | -4.62 [-8.52, -0.43] (216/216) | -4.89 [-8.74, -0.63] (65,823/216) |
| Knowable | 0.10–0.40 | 4–6 × no | -4.94 [-10.56, 1.68] (79,208/239) | -6.61 [-10.49, -2.39] (239/239) | -4.80 [-8.54, -0.68] (79,208/239) |
| Knowable | 0.10–0.40 | 4–6 × unknown | -4.99 [-10.32, 0.54] (148,320/347) | -6.41 [-10.07, -2.65] (347/347) | -3.98 [-7.22, -0.62] (148,320/347) |
| Knowable | 0.10–0.40 | 7+ × yes | -1.55 [-13.22, 18.66] (5,533/35) | -6.86 [-12.74, 1.60] (35/35) | -6.69 [-12.54, 1.74] (5,533/35) |
| Knowable | 0.10–0.40 | 7+ × no | -9.37 [-14.83, 5.29] (3,979/35) | -6.66 [-12.83, 2.26] (35/35) | -6.19 [-12.11, 2.39] (3,979/35) |
| Knowable | 0.10–0.40 | 7+ × unknown | -9.70 [-13.99, -2.90] (6,794/85) | -10.20 [-13.67, -5.72] (85/85) | -8.77 [-12.24, -4.43] (6,794/85) |
| Final 5 | 0.05–0.20 | 1–3 × yes | 0.46 [-5.27, 7.09] (156,357/303) | 0.63 [-3.27, 4.93] (303/303) | -1.89 [-4.97, 1.36] (156,357/303) |
| Final 5 | 0.05–0.20 | 1–3 × no | -0.05 [-6.09, 6.79] (201,187/310) | -1.39 [-5.14, 2.82] (310/310) | -2.80 [-6.12, 0.67] (201,187/310) |
| Final 5 | 0.05–0.20 | 1–3 × unknown | -0.68 [-5.62, 4.39] (352,805/376) | 4.01 [0.19, 8.19] (376/376) | -1.63 [-4.58, 1.39] (352,805/376) |
| Final 5 | 0.05–0.20 | 4–6 × yes | -1.93 [-6.17, 3.02] (129,922/371) | 0.15 [-3.03, 3.55] (371/371) | -0.36 [-3.53, 3.20] (129,922/371) |
| Final 5 | 0.05–0.20 | 4–6 × no | -1.95 [-5.78, 2.30] (162,869/394) | -2.20 [-5.57, 1.06] (394/394) | -0.98 [-4.05, 2.11] (162,869/394) |
| Final 5 | 0.05–0.20 | 4–6 × unknown | -3.01 [-6.17, 0.71] (322,768/483) | -0.68 [-3.70, 2.24] (483/483) | -0.52 [-3.15, 2.27] (322,768/483) |
| Final 5 | 0.05–0.20 | 7+ × yes | -1.29 [-6.64, 6.06] (67,381/295) | -0.16 [-3.05, 3.05] (295/295) | -0.10 [-3.00, 3.12] (67,381/295) |
| Final 5 | 0.05–0.20 | 7+ × no | 1.32 [-4.56, 7.55] (87,048/335) | -2.68 [-5.18, -0.04] (335/335) | -1.42 [-3.80, 1.27] (87,048/335) |
| Final 5 | 0.05–0.20 | 7+ × unknown | -2.15 [-5.54, 1.62] (187,001/435) | -2.72 [-5.06, -0.22] (435/435) | -0.80 [-3.02, 1.74] (187,001/435) |
| Final 5 | 0.10–0.40 | 1–3 × yes | 0.35 [-4.98, 6.22] (360,772/394) | 1.55 [-2.44, 6.08] (394/394) | -3.00 [-6.41, 0.55] (360,772/394) |
| Final 5 | 0.10–0.40 | 1–3 × no | -2.78 [-7.69, 2.20] (365,623/391) | -3.63 [-7.94, 0.94] (391/391) | -6.56 [-9.75, -3.31] (365,623/391) |
| Final 5 | 0.10–0.40 | 1–3 × unknown | 1.48 [-2.73, 5.58] (754,112/433) | 3.51 [-0.50, 7.91] (433/433) | -6.70 [-9.64, -3.89] (754,112/433) |
| Final 5 | 0.10–0.40 | 4–6 × yes | 0.51 [-5.51, 6.80] (141,161/370) | 0.33 [-3.70, 4.20] (370/370) | -0.00 [-3.81, 3.89] (141,161/370) |
| Final 5 | 0.10–0.40 | 4–6 × no | -1.41 [-6.64, 4.07] (157,811/390) | -2.69 [-6.40, 1.05] (390/390) | -1.08 [-4.51, 2.58] (157,811/390) |
| Final 5 | 0.10–0.40 | 4–6 × unknown | -5.28 [-9.04, -1.22] (333,379/481) | -2.05 [-5.67, 1.53] (481/481) | -1.80 [-5.02, 1.13] (333,379/481) |
| Final 5 | 0.10–0.40 | 7+ × yes | 4.84 [-10.14, 24.69] (24,972/127) | -1.83 [-7.04, 4.04] (127/127) | -2.01 [-7.28, 3.62] (24,972/127) |
| Final 5 | 0.10–0.40 | 7+ × no | 8.11 [-6.20, 24.01] (33,697/148) | -1.43 [-6.48, 4.03] (148/148) | -0.41 [-5.34, 5.16] (33,697/148) |
| Final 5 | 0.10–0.40 | 7+ × unknown | 3.98 [-6.27, 14.97] (72,890/257) | -4.16 [-7.70, -0.33] (257/257) | -2.09 [-5.77, 1.88] (72,890/257) |


### Polymarket

Read-only maker fills; all estimates below use the audited outcome-token join. The earlier residual loader lowercased abbreviations before alias lookup, then inferred winners from home-team abbreviations rather than joining fill assets to the resolved CLOB outcome token. It gave the wrong winner flag for 126 of 1,227 mapped markets. The corrected loader maps Gamma outcome labels to CLOB token IDs and sets each fill outcome from `asset == winner_token`, matching `src/run_polymarket_selection_analysis.py`. In every row-level residual, selected-team `Y` and price are folded together using that row's selected-team price; the longshot team can change during a minute if the selected-team price crosses 0.50.

All estimates are `Y − price` in percentage points. CIs are 95% game-clustered bootstrap intervals (2,000 draws). Counts are trades/games for trade-weighted and games for first-entry.

| Window | Band | Polymarket cell | Trade-weighted | First-entry |
|---|---:|---|---:|---:|
| Knowable | 0.05–0.20 | all | -2.55 [-5.60, 0.69] (123,561/540) | -1.17 [-3.96, 1.70] (540) |
| Knowable | 0.05–0.20 | maker buys longshot | -1.92 [-5.16, 1.82] (66,390/523) | -0.85 [-3.73, 2.06] (523) |
| Knowable | 0.05–0.20 | maker sells longshot | -3.28 [-6.02, 0.00] (57,171/530) | -2.74 [-5.32, -0.07] (530) |
| Knowable | 0.10–0.40 | all | -2.33 [-6.12, 1.64] (185,689/476) | -0.04 [-3.71, 3.52] (476) |
| Knowable | 0.10–0.40 | maker buys longshot | -2.06 [-5.86, 1.92] (94,284/465) | 0.21 [-3.40, 3.84] (465) |
| Knowable | 0.10–0.40 | maker sells longshot | -2.60 [-6.38, 1.35] (91,405/473) | -0.88 [-4.49, 2.89] (473) |
| Final 5 | 0.05–0.20 | all | 0.19 [-3.82, 4.76] (106,363/556) | -0.45 [-3.09, 2.32] (556) |
| Final 5 | 0.05–0.20 | maker buys longshot | 0.50 [-3.45, 5.30] (56,297/528) | 0.17 [-2.61, 3.12] (528) |
| Final 5 | 0.05–0.20 | maker sells longshot | -0.16 [-4.10, 4.18] (50,066/538) | -1.47 [-3.98, 1.11] (538) |
| Final 5 | 0.10–0.40 | all | 1.79 [-2.45, 6.27] (156,396/550) | 0.57 [-2.82, 4.04] (550) |
| Final 5 | 0.10–0.40 | maker buys longshot | 2.43 [-2.08, 6.98] (78,690/533) | 1.13 [-2.47, 4.84] (533) |
| Final 5 | 0.10–0.40 | maker sells longshot | 1.13 [-3.31, 5.76] (77,706/547) | -0.86 [-4.29, 2.56] (547) |

Matched-minute estimates use the jointly observed first minute selected for the Kalshi/Polymarket price comparison. The minute-median outcome is folded to the side implied by the venue's median selected-team price; the other columns use individual maker fills and row-level folding. Across 2,086 matched window-band game-minutes in 650 games, 16 minute-median longshot outcomes differ, and all 16 are different longshot teams across venues. Same-longshot-team outcome mismatches: 0. Intraminute longshot-side switches occur in 121 Kalshi and 69 Polymarket matched cells; 14 of the 16 different-team rows contain a switch in at least one venue. The previously reported count of 29 is superseded: it paired the first fill's folded outcome with a minute-median price, which is inconsistent when the longshot side changes within that minute.

| Window | Band | Game | Selected | Kalshi longshot (Y) | Polymarket longshot (Y) | Q4 minute bin |
|---|---|---:|---|---|---|---:|
| Knowable | 0.05–0.20 | 401810754 | ORL | ORL (1) | DAL (0) | 1 |
| Knowable | 0.05–0.20 | 401810064 | BOS | PHI (1) | BOS (0) | 1 |
| Knowable | 0.10–0.40 | 401810946 | PHI | PHI (0) | MIA (1) | 3 |
| Knowable | 0.10–0.40 | 401810386 | UTAH | DAL (0) | UTAH (1) | 3 |
| Knowable | 0.10–0.40 | 401810309 | NO | NO (0) | NY (1) | 3 |
| Knowable | 0.10–0.40 | 401836750 | CHI | CHA (0) | CHI (1) | 3 |
| Knowable | 0.10–0.40 | 401809818 | SA | SA (1) | DEN (0) | 3 |
| Knowable | 0.10–0.40 | 401810019 | MIA | LAC (0) | MIA (1) | 3 |
| Final 5 | 0.05–0.20 | 401810695 | LAL | ORL (1) | LAL (0) | 1 |
| Final 5 | 0.05–0.20 | 401810324 | MIL | WSH (1) | MIL (0) | 1 |
| Final 5 | 0.10–0.40 | 401810830 | SAC | SAC (1) | LAC (0) | 5 |
| Final 5 | 0.10–0.40 | 401810494 | NO | MEM (0) | NO (1) | 5 |
| Final 5 | 0.10–0.40 | 401810404 | MEM | BKN (0) | MEM (1) | 5 |
| Final 5 | 0.10–0.40 | 401810177 | MEM | MEM (0) | SA (1) | 5 |
| Final 5 | 0.10–0.40 | 401810169 | ORL | ORL (1) | CHI (0) | 5 |
| Final 5 | 0.10–0.40 | 401809236 | IND | IND (0) | OKC (1) | 5 |

| Window | Band | Matched game-minutes | Trade-weighted `Y−price` | First-entry `Y−price` | First-entry `Y−minute-median price` |
|---|---:|---:|---:|---:|---:|
| Knowable | 0.05–0.20 | 531 | -1.50 [-5.17, 2.39] (54,763) | -1.82 [-4.44, 0.99] (531) | -0.60 [-3.21, 2.06] (531) |
| Knowable | 0.10–0.40 | 466 | 0.88 [-4.62, 6.68] (54,474) | 0.06 [-3.75, 3.60] (466) | -1.53 [-5.00, 1.91] (466) |
| Final 5 | 0.05–0.20 | 545 | -2.06 [-5.29, 1.70] (54,444) | -0.85 [-3.50, 1.96] (545) | 0.03 [-2.55, 2.55] (545) |
| Final 5 | 0.10–0.40 | 544 | 1.61 [-3.53, 6.82] (62,499) | 0.24 [-3.32, 3.74] (544) | -0.13 [-3.39, 3.22] (544) |

The full outcome crosswalk is [phase5_residual_outcome_mismatch_audit.csv](data/interim/phase5/phase5_residual_outcome_mismatch_audit.csv), with a summary in [phase5_residual_outcome_mismatch_audit.json](data/interim/phase5/phase5_residual_outcome_mismatch_audit.json). Recomputed trade-weighted and first-entry estimates, including maker-side splits, are in [phase5_residual_outcome_estimators.csv](data/interim/phase5/phase5_residual_outcome_estimators.csv); corrected matched-minute estimates are in [phase5_residual_polymarket_matched_estimators.csv](data/interim/phase5/phase5_residual_polymarket_matched_estimators.csv). The audited residual input is cached at [phase5_residual_polymarket_audited_cache.parquet](data/interim/phase5/phase5_residual_polymarket_audited_cache.parquet). Reproduction: [audit_polymarket_residual_outcomes.py](src/audit_polymarket_residual_outcomes.py), [phase5_residual_mechanisms.py](src/phase5_residual_mechanisms.py), [phase5_residual_outcome_weighting.py](src/phase5_residual_outcome_weighting.py), and [phase5_residual_polymarket_matched_estimators.py](src/phase5_residual_polymarket_matched_estimators.py). No position-conditioned wallet mechanism analysis was performed; inventory transitions are required to identify those mechanisms.

The Polymarket selection-analysis outputs already use the audited token join in `src/run_polymarket_selection_analysis.py`: `y_own = (asset == winner_token)`, followed by selected-team/longshot folding. The saved selection summary reports 4,598,761 maker rows assigned, zero unknown outcome-token rows, and one market-mapping error for game 401857824 (market/shared assignment missing). The published isotonic alpha estimates (95% game-clustered CIs) are unchanged: (d) market 1.541 [1.313, 1.852], P* 1.497 [1.339, 1.723]; knowable market 1.115 [0.943, 1.358], P* 1.028 [0.891, 1.218]; final 5 market 1.055 [0.901, 1.247], P* 1.025 [0.896, 1.190]. The inside/outside-(d) split is unchanged as well: market `Y−p` −6.46 [−7.74, −5.00] vs +3.46 [−0.42, 7.37] points; P* placebo `Y−P*` −9.06 [−10.35, −7.69] vs +1.35 [−2.47, 5.16] points. The OT-excluded fit remains invalid for inference under the prior selection-bias correction.

## Phase 6b: outcome-free participant profile feasibility (2026-10-22)

Ran `make phase6-wallet-profiles` before estimating outcome differences by
wallet type. The in-game 2025–26 Polymarket panel contains 4,601,635 maker
fill activity records and 3,182,525 taker activity records from 1,218 games,
with 95,513 distinct wallet addresses across roles. The median wallet has 4
participant records (90th percentile 62); median per-wallet activity is 2
records per active day (90th percentile 8.4). The most active 1% account for
73.9% of maker fill records and 54.2% of taker activity records. Median
record notional is $9.12 for maker-side records and $9.75 for taker-side
records. These are account-activity facts within the sampled NBA games, not
evidence that an address is a bot, retail bettor, or professional trader.

All 3,182,525 taker hashes appear in the maker file; the transaction-level
taker wallet and side fields match for every joined transaction. About 20.3%
of transactions contain multiple maker fills. Aggregate maker- and
taker-reported shares agree within 1e-5 for 89.3% of transactions, with a
95th-percentile relative discrepancy of 2.7%. Since share volume does not
reconcile for every transaction, maker-role profiles currently use
participant-record share, not volume share. Maker and taker API records can
refer to complementary outcome tokens at different prices; their fields must
remain in their own outcome coordinates.

This establishes that an account-profile study is feasible. It does not yet
locate the source of the pricing gap: no outcome-based wallet-type estimates
are included here. The profile file and code are
[`polymarket_wallet_behavior_profiles.csv`](data/interim/phase6/polymarket_wallet_behavior_profiles.csv),
[`polymarket_wallet_behavior_summary.json`](data/interim/phase6/polymarket_wallet_behavior_summary.json),
and [`phase6_wallet_profiles.py`](src/phase6_wallet_profiles.py). The study
definitions and the position-ledger requirements are in
[`WALLET_STUDY.md`](WALLET_STUDY.md).

## Phase 6c: exploratory profile outcomes and position-history validation (2026-10-22)

The exact screening cohort is BUY records for a wallet's own outcome token in
the final five regulation minutes, priced 5–20¢, with own-token P* below
0.50. It contains 137,343 records (11,246 wallets; 642 games). For all
screened purchases, game-weighted settlement payoff less price (`Y−price`)
is −2.72 percentage points (95% two-way game/wallet clustered CI −4.56 to
−0.88). This describes the realized outcomes of the selected purchase
records, not wallet P&L, and is not a causal effect. Mean price minus P* is
also negative in all observed profile groups, while realized outcomes are
still worse than price. This shows the benchmark is not calibrated to this
selected buyer sample and blocks a simple interpretation of the profile
differences as overpayment relative to fair value. The group estimates overlap
and do not adjust for common game-state support; treat them as exploratory.
For the secondary `Y−price` purchase outcome, the game-weighted estimates are
−2.55 points for ≥20-record/day accounts (95% CI −4.42 to −0.68), −2.51 for
maker-record-dominant accounts (−4.33 to −0.69), −3.59 for taker-record-
dominant accounts (−5.47 to −1.70), and −3.13 for the low-activity/low-stake
proxy (−5.02 to −1.24). These marginal profile estimates do not establish
meaningful performance differences; the main activity contrast is checked on
common support below.

### Common-support activity comparison

To address the major composition concern, we compare high-activity accounts
(at least 20 observed participant records per active day) with all other
accounts only in game × regulation-minute × P* band × participant-role cells
containing both groups. This retains 117,253 target purchases (85.4%) across
624 games and 10,997 wallets. An OLS contrast with fixed effects for those
four dimensions and two-way game/wallet clustered standard errors estimates a
high-activity association of −0.01 percentage points for `Y−price` (95% CI
−0.24 to +0.21) and −0.10 points for `Y−P*` (−0.32 to +0.12). Both include
zero. A second, mutually exclusive comparison of maker-record-dominant versus
taker-record-dominant accounts retains 62,934 records (57.0% of eligible
profile rows) across 586 games and 7,638 wallets. Maker-dominant accounts have
a +0.35-point `Y−price` difference (95% CI +0.23 to +0.47), a −0.35-point
`price−P*` difference (−0.45 to −0.24), and essentially zero `Y−P*`
difference (−0.03 to +0.03). Their difference therefore appears in entry
prices, not realized outcomes relative to the benchmark. This is consistent
with differing entry prices or execution conditions, but does not establish
forecasting skill, net wallet profits, causal price impact, or account
identity. Both comparisons remain exploratory and selected on the target
cohort.
Reproduce with `make phase6-wallet-common-support`; outputs are
[`polymarket_wallet_common_support.csv`](data/interim/phase6/polymarket_wallet_common_support.csv)
and its JSON design summary.

Cutoff sensitivity is directionally consistent. The maker-versus-taker
`Y−price` difference is +0.29 points at a 50/50 record-share split (95% CI
+0.18 to +0.39) and +0.42 points at a 90/10 split (+0.22 to +0.62); `Y−P*`
includes zero at both cutoffs. Across alternate P* bands (2.5¢, 5¢/10¢, and
10¢) and 30- or 60-second clock cells, the 75/25 maker/taker `Y−price`
difference remains +0.35 to +0.38 points, while `Y−P*` includes zero. High-
activity contrasts at 20, 100, and 500 records per active day have `Y−price`
intervals that include zero. With 30-second cells, the high-activity `Y−P*`
association is statistically distinguishable from zero in two P* schemes but
is only −0.01 to −0.03 points; the 60-second and coarse-P* intervals include
zero. This is a small sensitivity that should be reported rather than hidden.
These checks remain exploratory. Reproduce with
`make phase6-wallet-profile-sensitivity`; output is
[`polymarket_wallet_profile_sensitivity.csv`](data/interim/phase6/polymarket_wallet_profile_sensitivity.csv).

A deterministic, stratified 210 wallet-market-pair sample was fetched from
the public Activity API from the target cohort (4,344 TRADE, 100 MERGE, and
143 REDEEM records; no SPLIT, CONVERSION, or TRANSFER rows returned). Strictly
earlier recorded TRADE/MERGE flows imply positive holdings in the target token
for 103 sampled pairs and zero recorded net for 107; 64 show positive recorded
net in the other token. All 210 have activity in the target trade's same
second, so one-second timestamps cannot order events within that second.
Seventy-three pairs have no strictly earlier Activity record. These counts cannot
classify accounts as fresh or inventory-conditioned because starting
positions, transfers, and omitted events are not ruled out.

An independent chain query improves this feasibility check. For all 210
sampled target trades, the target transaction receipt was found and both
Conditional Tokens outcome balances were queried at the end of the prior
Polygon block. One hundred three wallets already held a positive balance in the
target longshot token at the prior-block boundary; 64 held the opposite token,
including 39 with both balances positive. Applying earlier ERC-1155 transfer
logs within each target block gives balances at the start of the target
transaction: 107 with positive target-token inventory, 64 with positive
opposite-token inventory, and 41 with both. The Activity-based target-token
net matches on-chain balances within 1e-5 in 201/210 cases at the prior-block
boundary and 194/210 at transaction start. The latter differences reflect
same-second or same-block flow that the strict-prior Activity reconstruction
does not include. Exact ordering among fills within the target transaction
remains unresolved. The balanced profile strata had positive target-token
inventory in 34/42 high-activity, 21/42 low-activity/low-stake, 17/42
maker-dominant, 17/42 taker-dominant, and 18/42 residual-group pairs; these
are not representative rates or tests of differences.

Across the original and extension samples, all 144 wallet-market histories
with positive redemptions have Activity API payout amounts matching the
corresponding Conditional Tokens `PayoutRedemption` receipt logs within 1e-6
USDC. This verifies the API field against the chain event in these sampled
transactions. Separately, recorded net winning-token trades and merges equal
the claim amount within 1e-5 in 122/144 cases. The 22 differences are not
necessarily errors: a claim may redeem only
part of the position, and transfers or starting balances are not observed in
this API sample. This comparison therefore does not validate full token
balances. A complete position mechanism test still requires on-chain
split/merge/redemption and ERC-1155 transfer reconstruction, plus independent
balance checks. Reproduction is `make phase6-wallet-position-sample`; see
[`phase6_wallet_position_sample.py`](src/phase6_wallet_position_sample.py)
and the raw cached sample under
`data/raw/polymarket/activity_wallet_market_sample/`.
Receipt validation is reproduced with `make phase6-wallet-receipt-validation`
from cached receipts and saved in
`data/interim/phase6/polymarket_wallet_redemption_receipt_validation.csv`.
The historical balance and same-block transfer query is reproducible with
`make phase6-wallet-balance-validation`; results are in
`data/interim/phase6/polymarket_wallet_pretransaction_balances.csv`.

The follow-up now combines the original 210-pair feasibility sample with 346
additional nonoverlapping hash-ranked pairs drawn from the next five ranks in
each month × profile × recorded-Activity-role cell. Across 556 pairs, the
strict join matches 477 selected BUY records to a V1 exchange `OrderFilled`
event using wallet, target token, share quantity, and price, then requires a
unique inbound ERC-1155 transfer bundle for that event. Of the 477 matches,
438 use a single exact-size transfer and 39 use the observed 90%/10% pattern.
Thirty-eight records are ambiguous and 41 have no unique event/transfer pair.
Among the 477 unique matches, 221 have positive target-token balance
immediately before the first matched inbound transfer, after earlier
same-transaction transfer logs are applied. These are selected-sample
observations, not a population prevalence estimate. Positive pre-transfer
balances occur in 83/98 matched high-activity pairs, compared with 138/379
across the other four profile strata. The high-activity balances are material
relative to the sampled buy: 79/98 are at least one-tenth of buy size, and
64/98 are at least the buy size. Match-attrition bounds within these sampled
strata put the positive-inventory share at 74.1–86.6% for high activity and
31.1–45.7% for other profiles; even this worst-case assignment leaves at least
a 28.4-point gap. These bounds do not include sampling uncertainty and do not
support population inference. The inventory measure also does not identify
better information: among the 477 matched buys, mean `Y−P*` is −1.49 points
without positive pre-transfer inventory and −1.64 points with it. Mean
`Y−price` is +0.51 and −0.55 points, respectively, reflecting higher average
entry prices among the inventory-positive buys; all are descriptive sample
means without inferential intervals. The Activity API row label does not necessarily
equal the maker or taker field in the contract event; matching uses the
selected BUY's wallet, token, size, and price. The event decode follows the archived V1
[`OrderFilled` definition](https://github.com/Polymarket/ctf-exchange/blob/main/src/exchange/interfaces/ITrading.sol)
and [settlement implementation](https://github.com/Polymarket/ctf-exchange/blob/main/src/exchange/mixins/Trading.sol).
Reproduce the original sample with
`make phase6-wallet-exact-fill-balance-sample`; reproduce the extension with
`make phase6-wallet-inventory-extension-fill`; the combined descriptive
summary is written by `make phase6-wallet-inventory-extension-summary`. Output is
[`polymarket_wallet_exact_fill_balance_sample.csv`](data/interim/phase6/polymarket_wallet_exact_fill_balance_sample.csv).

Current implication: maker-record-dominant accounts are associated with lower
purchase prices than taker-record-dominant accounts in matched game-state
cells, but their outcomes relative to P* are indistinguishable. This is an
execution/entry-price association, not evidence that those accounts caused a
market-level residual. The selected sample also shows pre-existing longshot
inventory in many wallets, but the stratified design does not give population
rates. There is no evidence that bots, retail-like accounts, or any profile
caused the late-game pattern. Kalshi has no comparable participant identifiers
in the assembled data, so Polymarket account profiles cannot explain the
Kalshi primary estimate.

### Phase 6d: prior-purchase opportunity and strict pretransaction inventory

To distinguish prior same-token buying opportunity from a possible profile
inventory difference, we linked the 477 unique fill/transfer matches to
strictly earlier, second-resolution Activity API BUY records for the same
wallet and token. Inventory is measured from on-chain balance at the start of
the selected transaction, before any transfers in that transaction. Among
high-activity wallets, 83/98 (84.7%) had positive inventory and 86/98 (87.8%)
had at least one recorded prior same-token BUY; among the other four profile
strata, the corresponding rates were 137/379 (36.1%) and 143/379 (37.7%).
Conditional on at least one recorded prior BUY, the inventory rates were
82/86 (95.3%) and 126/143 (88.1%), respectively. Without a recorded prior
BUY they were 1/12 (8.3%) and 11/236 (4.7%). Thus, the large marginal
high-activity inventory gap coincides with a large gap in observed purchase
history, while conditional rates are much closer. This is descriptive
stratified-sample evidence that prior exposure/opportunity is an important
alternative explanation; it does not establish mediation, causation, or why
the tokens were held. The positive balances among wallets with no recorded
prior BUY also show that API trade history is incomplete for this purpose.

Among all matched buys, positive versus zero strict pretransaction inventory
is associated with mean `Y−price` of −0.46 versus +0.43 percentage points,
but mean `Y−P*` is nearly identical at −1.60 versus −1.52 points. The outcome
means are unadjusted, selected-sample descriptions without inferential
intervals; they do not support a claim of superior information or loss
chasing. The sample does not identify account type, cost basis, motive, or
price impact. Reproduce using `make phase6-wallet-inventory-opportunity`;
outputs are in
[`polymarket_wallet_inventory_opportunity`](data/interim/phase6/polymarket_wallet_inventory_opportunity/).

The sample-design audit found 39,364 unique wallet-market pairs in the target
cohort, with 4,111 appearing in two recorded-role cells; no pair spans more
than one month in the sampling frame. However, the 556 validated rows do not
always represent the wallet-market pair's chronologically earliest target
BUY (515 of 556 unique sampled pairs did). Therefore, a pair-weighted prevalence
estimate for first-entry inventory would require a new sample-to-target-event
mapping and revalidation of on-chain balances at those earliest transactions.
The current follow-up is not a population estimate.

### Phase 6e: profiles defined before the target game (2026-10-22)

The earlier wallet profiles used whole-season behavior and therefore were not
known at the time of each purchase. I rebuilt the profile at the start of
each target game using only participant-side NBA market records timestamped
strictly before that game's first ESPN play; all records from the target game
are excluded. Profiles are observable behavior labels, not identities. A
wallet is “limited prior history” with fewer than 20 earlier participant-side
records or activity in fewer than three earlier NBA games. Among adequately
observed accounts, “high prior activity” means at least 20 recorded
participant-side fills per earlier UTC active day; otherwise maker- or
taker-record dominance is assigned at a 75% share, with the remainder labeled
established mixed. The rules and data scope are researcher-defined, so these
comparisons are exploratory.

The frozen target cohort remains 137,343 final-five longshot BUY records from
11,246 wallets in 642 games. At the target-game start, 15,683 buys (7,782
wallets) have limited prior NBA history, 101,980 (1,479 wallets) are in the
high-prior-activity group, 5,799 (1,148 wallets) are established mixed, 5,221
(644 wallets) are maker-record dominant, and 8,660 (2,560 wallets) are
taker-record dominant. Counts are buy-weighted; the number of buys is not a
count of unique traders or a population share.

The common-support analysis compares purchases only within game × final-five
minute × P* band × participant-role cells containing both groups. High-prior-
activity buyers versus other adequately observed buyers show no detectable
difference: `Y−price` +0.04 points (95% CI −0.11 to +0.20), `Y−P*` 0.00
(−0.08 to +0.07), and `price−P*` −0.05 (−0.19 to +0.10), across 98,983
buys, 606 games, and 5,130 wallets. Limited-history buyers versus all other
profiles have `Y−price` +0.01 points (−0.27 to +0.29) and `Y−P*` +0.13
(−0.17 to +0.43); their `price−P*` is +0.12 points (+0.02 to +0.22).
Because this is one of several exploratory contrasts and actual outcomes
relative to P* do not differ, the small price-benchmark difference is not
evidence of trader skill or a mechanism.

Among established accounts with maker- or taker-record dominance, the
common-support contrast retains 5,215 buys in 329 games and 1,921 wallets.
Maker-dominant buyers have `price−P*` 0.42 points lower (95% CI −0.68 to
−0.16) and `Y−price` 0.32 points higher (+0.04 to +0.61) than taker-dominant
buyers, while `Y−P*` differs by −0.10 points (−0.25 to +0.06). This
replicates the earlier pattern: the distinction is in observed entry prices,
not in realized outcomes relative to the independent benchmark. Common-support
restrictions sharply narrow this comparison, and it remains observational.

The result supports a careful behavioral-profile analysis but not labels such
as bot, retail, or professional trader, and it does not explain the Kalshi
primary estimate or identify price impact. Reproduce with
`make phase6-wallet-prior-game-profiles`. The time-indexed profile file,
target-buy file, common-support contrasts, and summary are in
[`prior_game_behavior`](data/interim/phase6/prior_game_behavior/). Two-way
uncertainty is clustered by game and wallet. No profile comparison was
preregistered; thresholds and multiple comparisons must be treated as
exploratory, and a future-season replication should freeze them in advance.

One-at-a-time threshold sensitivities vary the minimum-history cutoff (10/20/50
records), high-activity cutoff (10/20/50 records per active day), and
maker/taker dominance cutoff (70/75/90%). High-activity contrasts remain close
to zero for `price−P*` (−0.09 to −0.02 points) and `Y−P*` (−0.06 to +0.02),
with every 95% interval containing zero. The maker-minus-taker `price−P*`
contrast remains negative (−0.80 to −0.35 points) across tested variants,
while its `Y−P*` interval includes zero in every variant. Limited-history
`price−P*` remains positive (+0.12 to +0.14 points), but the corresponding
`Y−P*` intervals include zero. These are unadjusted exploratory sensitivity
intervals, not confirmatory evidence. Reproduce with
`make phase6-wallet-prior-profile-sensitivity`; outputs are the
`prior_behavior_profile_threshold_sensitivity` CSV and JSON in the same
directory.

### Profile accounting decomposition of the selected Polymarket gap

To quantify which observable profiles account for the selected 2025–26
Polymarket `price−outcome` gap, I decomposed the same 137,343 prior-profile
BUY records across 642 games and 11,246 wallets. The cohort is final-five
regulation-minute buys priced 5–20¢ when that token's P* is below 50%.
The observation unit is a participant-side Activity API BUY record, not a
unique matched market transaction; a taker transaction may correspond to
multiple maker fill records.
For each profile, the contribution is its within-game share of the chosen
weight times its own within-profile `price−outcome` gap; contributions sum
exactly to the aggregate gap. I report per-record, share-weighted, and
dollar-notional-weighted estimates, each pooled and with games weighted
equally. Percentile CIs use 2,000 two-way pigeonhole bootstrap draws over
games and wallets.
Profile-component intervals are exploratory and are not multiplicity-adjusted
across the profile, outcome, weighting, and estimator combinations.

The equal-game per-record estimate is +2.72 points (95% CI +0.83 to +4.67).
High-prior-activity accounts account arithmetically for the largest component,
+1.75 points (64.3% of the total; CI +0.31 to +3.22), largely because they
make up 74.3% of records. Their own equal-game gap is +2.62 points, slightly
below the cohort total. The same group's contribution is +1.59 points under
equal-game share weighting (CI −0.02 to +3.19), again reflecting its 81.3%
share volume. Under pooled share weighting, however, its own `price−outcome`
gap is −0.17 points and its additive contribution is −0.14; the overall pooled
share-weighted gap is only +0.21 points (CI −4.98 to +4.11). Dollar-notional
equal-game weighting gives +3.11 points overall, of which high-activity
accounts contribute +2.28 (73.2%; CI +0.63 to +3.89). The pooled
dollar-notional total is +0.11 points (CI −5.59 to +4.52). Thus high-activity
accounts account for most of the positive equal-game gap under the weighted
estimands because they dominate activity, but their within-group gap is not
uniquely large and the pooled share-weighted result is nearly zero. The
allocation is sensitive to game and trade weighting.

This is an accounting attribution within a selected buyer cohort, not evidence
that a profile caused price impact or the broader market-level mispricing. The
per-record realized payoff gap is noisy, P* is estimated, and profile labels
are behavioral proxies rather than verified bot/retail/professional identities.
No historical 2025–26 quote-midpoint series is assembled in this project, so
the current analysis cannot separate execution costs from contemporaneous
market valuation. Polymarket's public API documents current order-book reads
and bucketed historical prices; its finer retained histories are limited to
7–90 days depending on resolution ([Polymarket market-data documentation](https://docs.polymarket.com/market-data/prices-order-books)).
A third-party vendor advertises full L2 order-book history from August 2025 at
one-minute resolution, which could cover this season, but coverage of our NBA
markets, quote completeness, timestamp semantics, and licensing have not yet
been audited ([vendor coverage](https://www.polymarketdata.co/polymarket-order-book-data),
[vendor pricing](https://www.polymarketdata.co/pricing)). The vendor also
advertises specialized academic access, but its discount price is not public
([academic research page](https://www.polymarketdata.co/polymarket-academic-research-data)).
Reproduce with
`make phase6-wallet-gap-decomposition`. Code and machine-readable outputs are
in [`gap_decomposition`](data/interim/phase6/prior_game_behavior/gap_decomposition/)
and [`phase6_wallet_gap_decomposition.py`](src/phase6_wallet_gap_decomposition.py).

### Phase 6f: profile-level taker flow and subsequent price deviations

To test more directly whether observable participant groups are associated
with the source of price pressure, I matched Polymarket taker activity to the
same transaction's game clock and joined each fill to the home-team P* for
that game state. The analysis is restricted to the final five regulation
minutes and uses profiles constructed strictly before each game. A taker BUY
or SELL is signed according to whether it increases or decreases the home
team's probability exposure. The primary outcome in this exploratory test is
the next consecutive 30-, 60-, or 120-second game-clock bin's change in the
last observed home-token trade price minus P*. Since the signed flow shares
for all five profiles sum to one in each bin, the regression enters four
profile-flow shares relative to limited-prior-history flow (the omitted
reference), adjusts for the initial price-minus-P* gap and the P* movement,
includes game and within-window-bin fixed effects, and clusters uncertainty
by game.

The final-five sample contains 160,100 matched taker records from 763 games
and 25,858 wallets. Limited-prior-history accounts account for 77.5% of
records and 81.3% of traded shares; high-prior-activity accounts account for
18.4% of records and 16.6% of shares. These labels describe observed NBA activity before each
game and cannot identify retail participants, bots, professionals, or market
makers. Under the corrected compositional-flow specification, none of the
four non-reference profile-flow coefficients is statistically distinguishable
from zero at 30, 60, or 120 seconds; the main-benchmark joint tests have
p=.662, .721, and .933, respectively. No individual coefficient survives
Holm correction across the 12 profile-by-horizon comparisons (all adjusted
p=1.00). The limited-history flow signal reported in the earlier version does
not persist once one profile is omitted as the reference category. Benchmark
sensitivity gives the same conclusion: all profile-by-horizon intervals
include zero, and no joint test is significant. This is no evidence that any
observed profile group's flow predicts short-run divergence from P* in this
specification; it is not proof that the groups have identical effects.

As a separate trade-level description, 45.8% of high-prior-activity taker
volume was in transactions that bought a token above P* or sold it below P*;
the corresponding figure was 50.4% for limited-prior-history accounts.
These are unadjusted, P*-relative execution classifications, not realized
profits or proof of mispricing. They do not show that high-activity accounts
have better information, nor that limited-history activity causes the market
residual.

The corrected main-benchmark and benchmark-sensitivity models provide no
detectable association between any observable profile's taker flow and
subsequent divergence from P*. This remains a predictive association analysis,
not a causal price-impact estimate: trader flow is endogenous, the price mark
is a last execution rather than a midpoint, P* is estimated, game-clock
buckets can span different amounts of wall-clock time because the clock stops
during stoppages, and no historical order-book quote series is available in
this panel. This Polymarket result cannot explain the Kalshi registered
estimate. Reproduce
with `make phase6-taker-flow-impact`; code and outputs are in
[`phase6_taker_flow_impact.py`](src/phase6_taker_flow_impact.py) and
[`data/interim/phase6/taker_flow_impact`](data/interim/phase6/taker_flow_impact/).

#### Benchmark and timing-quality sensitivity completed 2026-10-22

The cross-fitted 10-minute retrospective-selection accounting was repeated
with the possession-adjusted and spline-logistic P* series. The target remained
the 5–20¢ market-price cohort, using 5¢ bins, five-fold game cross-fitting,
and 2,000 game-cluster bootstrap draws. In the market-price coordinate, the
observed gap was −6.24 to −6.26 points for all three P* support screens, and
the selection-predicted gap was nearly identical; each unexplained remainder
was near zero and its 95% interval included zero. In the P* coordinate,
observed gaps ranged from −11.70 to −16.35 points, with predicted gaps
similarly close and all remainder intervals including zero. The stable point
accounting in market-price space is reassuring, but this is an in-sample
same-season descriptive adjustment—not causal identification or independent
validation. Full estimates are in
[`phase5_crossfit_benchmark_sensitivity.csv`](data/interim/phase5/phase5_crossfit_benchmark_sensitivity.csv).
Reproduce with `make phase5-crossfit-benchmark-sensitivity`.

The pre-specified primary Kalshi estimate was also recalculated after excluding
games with more than five backward ESPN wall-clock steps. The full sample's
equal-game overpricing estimate was +2.33 points (390 games; diagnostic
10,000-draw bootstrap 95% CI −0.52 to +4.97); excluding flagged games gave
+2.43 points (291 games; CI −0.73 to +5.29). The registered 2,000-draw
interval remains −0.53 to +4.94. Thus the point estimate barely changes,
while uncertainty increases. In 390 leave-one-game-out estimates, every estimate remained
positive and ranged from +2.29 to +2.58 points. This says no single game or
the flagged timing-quality subset drives the point estimate. It does not
resolve the uncertain absolute ESPN timestamp lag, nor make the estimate
statistically distinguishable from zero. The input estimate remains the
registered 390-game, equal-game result; bootstrap values here use 10,000
draws solely for this diagnostic. Reproduce with
`make phase5-primary-influence-diagnostic`; outputs are
[`phase5_primary_influence_diagnostic.csv`](data/interim/phase5/phase5_primary_influence_diagnostic.csv)
and its adjacent JSON files.

Correction completed 2026-10-23: an earlier version entered all five profile
flow shares despite their summing to one in every time bin. That created an
exact compositional collinearity with the intercept/fixed effects; the earlier
coefficient and p-value claims in this subsection are superseded. The corrected
models omit limited-prior-history flow as the reference and estimate the four
other profile shares relative to it. Across the three benchmarks and three
horizons, all 36 profile-flow confidence intervals include zero; all Holm
adjusted individual p-values are 1.00. The joint tests of the four non-reference
flows are also null (main-benchmark p=.662, .721, and .933 at 30, 60, and 120
seconds; all nine benchmark-by-horizon joint tests have Holm-adjusted p=1.00).
This rules out the earlier apparent short-horizon signal under the corrected
specification, but does not show that profile effects are exactly zero. The
result remains exploratory and predictive, not causal. Outputs are in
`profile_flow_benchmark_sensitivity.csv` and
`profile_flow_benchmark_joint_tests.csv` under the Phase 6f output directory.

### Phase 6g: prospective Polymarket quote and wallet-flow capture

A public-data collector is implemented in
[`collect_polymarket_prospective.py`](src/collect_polymarket_prospective.py).
It matches ESPN's current and near-term NBA schedule to Polymarket's exact
single-game moneyline markets, captures the full public CLOB market stream
(including order-book levels, best bid/ask and last-trade messages), and
incrementally caches wallet-linked Data API trade responses with overlapping
time bounds, per-market watermarks, retry logging, and raw gzip archives. The
protocol is in
[`PROSPECTIVE_POLYMARKET_PROTOCOL.md`](PROSPECTIVE_POLYMARKET_PROTOCOL.md).

Initial pipeline checks at 2026-10-23 00:50 UTC mapped 14 games to 28 outcome
tokens. A 20-second WebSocket smoke capture received 3,496 raw market messages.
The first trade-API poll retrieved 8,287 all-trade rows and 2,673 taker-only
rows for the already-started Cleveland–Philadelphia game; the next game had no
trades in the initial short lookback. These are coverage checks, not analysis.
Those first partial-game records are excluded from the prospective confirmatory
cohort because continuous pre-tip capture was not established. The persistent
collector is running locally; it must remain on an awake, network-connected
machine. Raw files are under
[`data/raw/polymarket/prospective`](data/raw/polymarket/prospective), market
mapping and trade watermarks are under
[`data/interim/phase6/prospective`](data/interim/phase6/prospective), and
`make phase6-prospective-collect` restarts collection. The public wallet IDs
support behavioral profiling, not verified labels such as bot, retail, or
professional.

The updated collector also writes a normalized
`quote_events/events_YYYY-MM-DD.jsonl` stream alongside the raw WebSocket
archive. `make phase6-prospective-materialize` converts cached
Data API responses into reproducible wallet-level maker and taker parquet
tables and records how many maker rows could not be linked to the transaction's
taker wallet. Treat these as derived files; do not interpret their rows as
complete until polling and quote coverage have been audited for every eligible
game.

At the 2026-10-22 20:58 ET refresh, the first cache materialization produced
6,246 unique maker rows and 3,061 unique taker rows across the two games with
trade responses; zero maker rows in this small partial cache lacked a linked
taker wallet. It removed 1,592 overlapping/duplicate all-trade rows for
Cleveland–Philadelphia and 12 for Denver–Oklahoma City. These counts are
pipeline diagnostics only: the collector had not yet observed complete games,
and zero missing links in this tiny early cache does not establish complete
coverage. After the updated collector restarted, its normalized stream began
accumulating quote events (1,513 records observed during the initial check).

The first coverage audit was run at 2026-10-23 21:27 ET using ESPN play-by-play
and the prespecified one-second grid. Of the three completed games, two had
both outcome tokens observed before tip. Chicago–Milwaukee passed the coverage
rule: both outcome books had valid, fresh two-sided quotes for all 273 unique
eligible seconds (100%). Denver–Oklahoma City had 133 eligible seconds and passed 0
(0%), so it fails the 95% rule. Cleveland–Philadelphia began before capture and
is excluded regardless of retrospective data. **One completed game currently
qualifies.** This audits data completeness, not market calibration. Reproduce
with `make phase6-prospective-audit`; outputs are `coverage_audit.csv` and
`coverage_audit_summary.json` under the Phase 6 prospective directory.
The Denver failure reflects unusable boundary books during its eligible
stoppage: observed best prices were 0/0.01 on one outcome and 0.99/1 on the
other, leaving no uncrossed, interior two-sided quote. This is an observed
market-quote limitation rather than a WebSocket collection gap.

Exploratory, non-inferential price-path check for Chicago–Milwaukee: in its
single clean final-five timeout interval, the longshot midpoint never entered
the 5–20¢ band, so the game contributes no observation to the planned primary
longshot comparison. Across the whole final five minutes, only 21 one-second
states had a valid 5–20¢ longshot midpoint, all during running-clock play. The
eventual loser (Milwaukee) moved from about 21.5¢ at the start of the final five
minutes to about 1.5¢ before quotes disappeared at game end. That path is
directionally consistent with the realized result; one realized loss cannot
test calibration. It motivates checking whether apparent trade-price gaps are
concentrated in fast, running-clock transitions or in thin/boundary books, and
whether execution prices diverge from contemporaneous midpoints. It provides
no evidence about which wallet types caused the behavior.

### Phase 6g: transaction-cadence and ticket-size account-style proxies

To test Sam's proposed bot-like/high-cadence versus larger-ticket/less-frequent
account distinction, I rebuilt account features at the wallet-transaction
level. Multiple maker fills with the same wallet, transaction hash, and game
are one transaction event; the median ticket is the sum of that wallet's fill
notional within each transaction. For every target wallet-game pair, the
features use NBA-market transactions strictly before the game's first ESPN
play and remove all target-game activity. This avoids using the target
purchase or outcome to assign the profile.

The profile panel contains 137,343 selected late-game longshot BUY records in
642 games and 11,246 wallets. The source scan retained 5,984,171 transaction
events for those wallets. A “rapid-cycle proxy” has at least 20 distinct
transactions per active day and a median within-day inter-transaction gap of
30 seconds or less. A “large-ticket/low-frequency proxy” has a median
transaction notional of at least $100 and at most five transactions per active
day, after the rapid-cycle rule. These are observable style proxies, not
verified bots, retail traders, or professionals.

Rapid-cycle wallets account for 92,719 target records (67.5%) across 965
wallets. Across their 13,077 wallet-game histories, median cadence is 225.8
transactions per active day and the median within-day gap is 8 seconds. Their
equal-game record-weighted `price−outcome` gap is +2.62 pp, and
their additive component of the total +2.72 pp gap is +1.54 pp (95% CI +0.23
to +2.89). Their component is large mainly because they generate most of the
records; their own gap is slightly below the other observed-style group's
+3.65 pp. The large-ticket/low-frequency proxy is only 336 records (0.24%)
across 162 wallets, too small to support a precise account-type conclusion.

As a less threshold-dependent check, I compared the highest and lowest
quartiles of prior transactions per active day and, separately, the largest
and smallest quartiles of median transaction notional. Quartile cutoffs are
8.67 versus 186.69 transactions per active day and $4.11 versus $27.28 per
transaction, defined across wallet-game pairs. Comparisons are restricted to
common game × final-five-minute × P* band × participant-role cells, with
two-way game/wallet clustered intervals. The high-cadence-minus-low-cadence
difference in `price−outcome` is −0.03 pp (95% CI −0.22 to +0.16); the
large-ticket-minus-small-ticket difference is +0.03 pp (95% CI −0.17 to
+0.23). Both include zero. Benchmark-adjusted comparisons also include zero.

Threshold sensitivity shows the count of rapid-cycle wallet-game pairs varies
with the cutoffs (for example, 4,674 at ≥20 transactions/day and ≤5-second
median gap; 13,077 at ≥20/day and ≤30 seconds; 14,954 at ≥20/day and ≤60
seconds). At a five-transaction/day low-frequency cutoff, the number of
large-ticket wallet-game pairs is 979 using a $25 median ticket threshold,
278 using $100, and 46 using $500. Thus the selected large-ticket definition
is sparse, and its accounting component is not evidence of no effect.

Interpretation: this narrows the account-style hypothesis but does not identify
the source of the market gap. The broad high-cadence group dominates selected
buyer volume, but the matched high-versus-low cadence comparison does not show
greater realized overpayment among the highest-cadence accounts. No result
establishes automation, account identity, causality, or market-price impact.
The Activity API participant-side BUY sample is selected and its records are
not unique matched executions. The profile component intervals are exploratory
and not multiplicity-adjusted. Reproduce with
`make phase6-wallet-execution-style-analysis` and
`make phase6-wallet-execution-style-decomposition`; outputs are under
`data/interim/phase6/prior_game_behavior/execution_style/`.
