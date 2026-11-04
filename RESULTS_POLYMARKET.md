# Polymarket Phase 6: on-chain ingest and 6a-lite

## Status (season run update, 2026-10-21)

The market map confirms **1,227 of 1,230** regular-season games against team/date and
resolved winner. The full Data API ingest collected **4,601,635 maker fills** across
all 1,227 mapped markets. The initial 6a-lite result was wrong: ESPN aliases were
compared literally with Gamma winner abbreviations, marking 89 wins as losses. The
fixed result uses canonical team abbreviations, matches Kalshi outcomes in all 903
games, and has game-weighted `Y - price` **0.0127** (95% game-clustered bootstrap
CI **[−0.0047, 0.0306]**). No paid or keyed source was used.

The only team assignment used was the existing
`data/interim/phase4/selected_team_by_game.csv` (seed 17). Position reconstruction is
still incomplete: the Activity API probe did not expose SPLIT or CONVERSION events,
so this report stops at 6a-lite and does not claim a Phase 6c position validation.

## Season market enumeration

Gamma pagination returned 1,544 events for the NBA 2026 series. Exact slug matching
mapped 1,138 games; rematching by both teams plus event date within +/-1 day in UTC
or Eastern found 89 additional games. Each mapped market's resolved winner was
checked against the ESPN final score. Total confirmed: **1,227 / 1,230**. Remaining:

| ESPN game | Matchup | Reason |
|---|---|---|
| 401810469 | Clippers at Bulls | Gamma candidate `nba-lac-chi-2026-01-20`, but cached ESPN summary has no End Game score/team assignment to verify resolution |
| 401858693 | Nuggets at Grizzlies | No Gamma event with both teams within +/-1 day in UTC or Eastern |
| 401858694 | Mavericks at Bucks | No Gamma event with both teams within +/-1 day in UTC or Eastern |

The complete match and unmatched-game manifests are in
`data/interim/phase2/polymarket_nba_2025_26_market_map.json`; raw Gamma pages are cached
under `data/raw/polymarket/gamma_nba_series_10345_*.json`.

## No-key Data API source checks

On the legacy `GET https://data-api.polymarket.com/trades` endpoint, `market` takes
the condition ID. `takerOnly=true` (also the default) returns taker rows;
`takerOnly=false` returns both the taker and maker sides. For Oct. 21 in-game time,
the false query returned **8,013 rows** across 3,488 transactions. Matching by
transaction, maker wallet, token, side, size and price reproduced **4,525 / 4,525**
on-chain maker `OrderFilled` events (numeric size/price tolerance 1e-5); the remaining
3,488 rows are the taker side. The true query returned exactly 3,488 rows. Raw probes
and the row-level validation are cached under
`data/raw/polymarket/api_step1_probe/`.

The legacy endpoint accepts inclusive epoch-second `start` and `end` filters. The
June 3 Knicks–Spurs market had 11,000 cached taker rows at offsets 0 through 10,000;
offset 10,001 returns HTTP 400 (`max historical trades offset of 10000 exceeded`).
Partitioning the cached timestamp span into four contiguous windows returned 1,728,
2,571, 4,488 and 2,213 rows, exactly reproducing the cached 11,000-row multiset with
zero missing or extra rows. I then queried the complete Gamma open-to-close interval
with inclusive `start`/`end`, recursively splitting saturated windows. This recovered
**38,950 taker rows in seven windows**, each below 10,000 rows (largest window: 8,989),
with every row inside its requested time bounds. `startTs` / `endTs` did not apply the
same bounds; use `start` / `end`.

The maker-row response was also checked against receipts in five other regular-season
markets: Nov. 1 Knicks–Bulls, Dec. 6 Pelicans–Nets, Jan. 1 Rockets–Nets, Feb. 1
Bulls–Heat, and Mar. 1 Spurs–Knicks. Across those five sampled transactions, **6 / 6**
receipt maker fills matched API maker rows; the February transaction contained two
maker fills. This is a transaction-level spot validation per market, not a complete
market receipt census. Details and raw responses are in
`data/raw/polymarket/api_step1_probe/five_game_receipt_validation.json`.

**Step 1 passes.** Use the no-key Data API as the primary source, fetching
`takerOnly=false` and dividing dense markets into bounded `start`/`end` windows.
The Dune and archive-RPC paths have not been used.

## Full-season Data API ingest

The collector queried each mapped market over that game's ESPN wall-clock span. API
`start`/`end` bounds are inclusive; saturated windows were divided into adjacent
non-overlapping intervals `[a, b]` and `[b+1, c]`. Raw pages are cached under
`data/raw/polymarket/data_api_season/` and the per-market checkpoint is
`data/interim/phase2/polymarket_data_api_progress.json`. There were **54,496** exact
duplicate participant rows removed using `(transaction hash, wallet, token, size,
price)`. The deduplicated panel contains **7,784,160** participant rows: **4,601,635
maker fills** and **3,182,525 taker rows**. Each maker fill has a matched initiating
wallet and side; no maker rows were missing this identity. Taker rows are retained
only as counterparty metadata and are never included in calibration.

Before the full run, I timed five nights. Per-night logs:

| Eastern night | Games | Participant rows | Maker rows | Collector seconds |
|---|---:|---:|---:|---:|
| 2025-10-21 | 2 | 11,962 | 6,779 | 9.0 |
| 2025-11-15 | 5 | 19,977 | 11,512 | 19.3 |
| 2025-12-15 | 5 | 45,468 | 26,678 | 61.9 |
| 2026-01-15 | 9 | 72,986 | 42,970 | 100.4 |
| 2026-03-15 | 7 | 88,486 | 51,425 | 167.1 |
| **Total** | **28** | **238,879** | **139,364** | **357.7** |

The five-night projection was **4.35 hours** for 1,227 markets. The completed run
recorded 12,212 seconds of per-market request time (about 3.4 hours), plus final
alignment and parquet writing. The collector completed all markets with its rate
limit retry and raw-cache behavior; no source switch was needed. The machine-readable
benchmark is `data/interim/phase2/polymarket_data_api_benchmark.json`.

The May 1, 2026 Detroit–Orlando V2 market was postseason; no May/June regular-season
market exists in this 2025–26 NBA season. In the available V2 reconciliation, 9,548
receipt `OrderFilled` logs reduce to **9,459 unique fills** after the required exact
dedup key (89 duplicate logs removed). All **9,459 / 9,459** unique API maker rows
match the unique receipt fills; no maker row or receipt fill remains unmatched.
Machine-readable result: `data/interim/phase2/polymarket_v2_may01_reconciliation.json`.

The earlier RPC fallback investigation found Goldsky's public orderbook endpoint
deprecated, dRPC's free historical-range restriction, PublicNode's archive-token
requirement, and 1RPC's usage limit. Those findings no longer block this work because
the no-key Data API checks above passed. The season plan still groups the sample into
164 Eastern game nights. `src/ingest_polymarket_onchain.py` remains available for
receipt validation and V1/V2 event decoding; layouts follow Polymarket's [CTF Exchange V2
event implementation](https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/mixins/Events.sol).

## Oct. 21, 2025: Rockets–Thunder validation

The full cached Data API sample contains 6,232 rows. Mapping timestamps to the ESPN
wall-clock interval yields 3,488 in-game rows and 3,488 unique transactions. Every one
of those rows matches a cached Polygon receipt's `OrdersMatched` event on transaction,
token ID, side, size, and price: **3,488 / 3,488 matched; zero missing receipts or
field mismatches**. Those same receipts contain 4,525 maker-side `OrderFilled` logs
(exchange-as-taker aggregate logs excluded). This verifies the distinction between
one taker order per transaction and the multiple maker fills that can satisfy it.

The machine-readable validation is in `data/interim/phase2/polymarket_onchain_check.json`.
The 4,525 maker fill rows are saved in
`data/interim/phase2/polymarket_oct21_onchain_maker_fills.csv`.

## Cross-month transaction checks

Nine sampled transactions from October 2025 through June 2026 were decoded from
their Polygon receipts and matched to the Data API fields. All nine matched,
including samples from both the V1 and post-migration V2 exchanges. Transaction
identifiers and wallet-level receipt details are omitted from this release.
These spot checks validate the sampled API-to-receipt mapping; they do not
measure season-wide coverage or establish trader identity.

## 6a-lite: validation-market game-clock diagnostic

The shared window predicate in `src/game_windows.py` defines the final 10 minutes as
the fourth-quarter ESPN clock at 600 seconds or less. Overtime periods are excluded
from that window and counted separately. For Rockets–Thunder, the cached receipt set
has 1,140 maker fills in Q4 at <=600 seconds, plus 1,508 maker fills in overtime.
`src/run_polymarket_6a_lite.py` imports this shared predicate. The main session's
Kalshi pipeline should import `is_final_regulation_window` from this module too; no
Kalshi or play-by-play files were changed. This one-game diagnostic is not a season
calibration estimate. The binned data are in
`data/interim/phase2/polymarket_6a_lite_gameclock_bins.csv`.

This was the one-game diagnostic before the full season panel was collected. The
season estimate below uses the same shared regulation-window predicate.

## Observation unit, fees, and order delay

The comparison unit is **one maker fill**: each Polymarket `OrderFilled` maker event
is one observation, paired with its taker from `OrdersMatched`. A taker-side matched
transaction can aggregate multiple maker fills; Oct. 21's 3,488 in-game taker rows
expand to 4,525 maker fills. Cached Kalshi public trade rows have a unique `trade_id`
per execution record; `count_fp` is the contract quantity. Calibration therefore
uses the maker-fill unit for Polymarket.

In the Oct. 21 receipt sample, all **8,013 / 8,013** decoded V1 `OrderFilled` fee
fields were zero. This is direct evidence for that game, not a season-wide fee survey.
Polymarket's current [Help Center limit-order documentation](https://help.polymarket.com/en/articles/13364444-limit-orders)
says sports markets have a **3-second delay** on marketable-order placement. Current
Gamma metadata shows `secondsDelay` 3 for most mapped markets and 1 for 58; mutable
metadata does not establish historical per-game settings during 2025-26, so the
historical delay remains unresolved.

## 6a-lite diagnosis and corrected season result

The incorrect result came from comparing the selected ESPN abbreviation directly to
Gamma's `resolved_winner_abbreviation`. ESPN's `GS`, `NO`, `NY`, `SA`, `UTAH`, and
`WSH` differ from Gamma's `GSW`, `NOP`, `NYK`, `SAS`, `UTA`, and `WAS`. When one of
those six teams was selected and won, literal string comparison assigned `Y=0`.
There were **89 such outcome mismatches** among the 903 calibration games. The runner
now canonicalizes both team abbreviations through `TEAM_ALIASES` before comparing.
The corrected Polymarket `Y` matches the Kalshi main-panel `y_selected` on **903/903
same-game, same-team outcomes** (0 mismatches).

This audit applies to the Phase 6 selection-analysis runner, which already used the
audited outcome-token join. A separate Phase 5 residual loader had an abbreviation
normalization defect; its correction and matched-minute longshot-side comparison
are documented in [`RESULTS.md`](RESULTS.md) and [`DEVIATIONS.md`](DEVIATIONS.md).

All 89 pre-fix mismatches (game id, market, selected team, Gamma resolved winner):

| ESPN game | Polymarket market | Selected team | Resolved winner |
|---|---|---|---|
| 401809235 | `nba-sas-dal-2025-10-22` | SA | SAS |
| 401809237 | `nba-den-gsw-2025-10-23` | GS | GSW |
| 401809238 | `nba-cle-nyk-2025-12-25` | NY | NYK |
| 401809239 | `nba-sas-okc-2025-12-25` | SA | SAS |
| 401809781 | `nba-mia-nyk-2025-11-14` | NY | NYK |
| 401809809 | `nba-sas-por-2025-11-26` | SA | SAS |
| 401809818 | `nba-sas-den-2025-11-28` | SA | SAS |
| 401809836 | `nba-sas-lal-2025-12-10` | SA | SAS |
| 401809837 | `nba-nyk-orl-2025-12-13` | NY | NYK |
| 401809838 | `nba-sas-okc-2025-12-13` | SA | SAS |
| 401809945 | `nba-bos-nyk-2025-10-24` | NY | NYK |
| 401809949 | `nba-sas-nop-2025-10-24` | SA | SAS |
| 401809950 | `nba-was-dal-2025-10-24` | WSH | WAS |
| 401809973 | `nba-tor-sas-2025-10-28` | SA | SAS |
| 401809975 | `nba-phx-uta-2025-10-28` | UTAH | UTA |
| 401809976 | `nba-mem-gsw-2025-10-28` | GS | GSW |
| 401809982 | `nba-lac-gsw-2025-10-29` | GS | GSW |
| 401810008 | `nba-chi-nyk-2025-11-03` | NY | NYK |
| 401810023 | `nba-cha-nop-2025-11-05` | NO | NOP |
| 401810024 | `nba-phx-gsw-2025-11-05` | GS | GSW |
| 401810075 | `nba-gsw-sas-2025-11-12` | GS | GSW |
| 401810089 | `nba-sac-sas-2025-11-16` | SA | SAS |
| 401810107 | `nba-mem-sas-2025-11-18` | SA | SAS |
| 401810117 | `nba-nyk-dal-2025-11-19` | NY | NYK |
| 401810122 | `nba-atl-sas-2025-11-20` | SA | SAS |
| 401810140 | `nba-nyk-bkn-2025-11-24` | NY | NYK |
| 401810153 | `nba-nop-gsw-2025-11-29` | GS | GSW |
| 401810171 | `nba-hou-uta-2025-12-01` | UTAH | UTA |
| 401810190 | `nba-uta-bkn-2025-12-04` | UTAH | UTA |
| 401810216 | `nba-gsw-chi-2025-12-07` | GS | GSW |
| 401810221 | `nba-sas-nop-2025-12-08` | SA | SAS |
| 401810227 | `nba-nyk-ind-2025-12-18` | NY | NYK |
| 401810230 | `nba-hou-nop-2025-12-18` | NO | NOP |
| 401810246 | `nba-was-mem-2025-12-20` | WSH | WAS |
| 401810247 | `nba-phx-gsw-2025-12-20` | GS | GSW |
| 401810272 | `nba-okc-sas-2025-12-23` | SA | SAS |
| 401810280 | `nba-tor-was-2025-12-26` | WSH | WAS |
| 401810298 | `nba-mem-was-2025-12-28` | WSH | WAS |
| 401810332 | `nba-bkn-was-2026-01-02` | WSH | WAS |
| 401810386 | `nba-dal-uta-2026-01-08` | UTAH | UTA |
| 401810394 | `nba-sac-gsw-2026-01-09` | GS | GSW |
| 401810400 | `nba-sas-bos-2026-01-10` | SA | SAS |
| 401810439 | `nba-nyk-gsw-2026-01-15` | GS | GSW |
| 401810453 | `nba-min-sas-2026-01-17` | SA | SAS |
| 401810454 | `nba-cha-gsw-2026-01-17` | GS | GSW |
| 401810467 | `nba-mia-gsw-2026-01-19` | GS | GSW |
| 401810471 | `nba-min-uta-2026-01-20` | UTAH | UTA |
| 401810494 | `nba-nop-mem-2026-01-23` | NO | NOP |
| 401810509 | `nba-nop-sas-2026-01-25` | NO | NOP |
| 401810519 | `nba-por-was-2026-01-27` | WSH | WAS |
| 401810520 | `nba-sac-nyk-2026-01-27` | NY | NYK |
| 401810530 | `nba-nyk-tor-2026-01-28` | NY | NYK |
| 401810534 | `nba-sas-hou-2026-01-28` | SA | SAS |
| 401810558 | `nba-orl-sas-2026-02-01` | SA | SAS |
| 401810562 | `nba-sac-was-2026-02-01` | WSH | WAS |
| 401810563 | `nba-lal-nyk-2026-02-01` | NY | NYK |
| 401810572 | `nba-uta-ind-2026-02-03` | UTAH | UTA |
| 401810593 | `nba-sas-dal-2026-02-05` | SA | SAS |
| 401810599 | `nba-nop-min-2026-02-06` | NO | NOP |
| 401810618 | `nba-uta-mia-2026-02-09` | UTAH | UTA |
| 401810643 | `nba-sas-gsw-2026-02-11` | SA | SAS |
| 401810653 | `nba-phx-sas-2026-02-19` | SA | SAS |
| 401810658 | `nba-ind-was-2026-02-20` | WSH | WAS |
| 401810671 | `nba-hou-nyk-2026-02-21` | NY | NYK |
| 401810693 | `nba-gsw-nop-2026-02-24` | NO | NOP |
| 401810698 | `nba-sas-tor-2026-02-25` | SA | SAS |
| 401810723 | `nba-sas-nyk-2026-03-01` | NY | NYK |
| 401810755 | `nba-uta-was-2026-03-05` | UTAH | UTA |
| 401810757 | `nba-gsw-hou-2026-03-05` | GS | GSW |
| 401810759 | `nba-det-sas-2026-03-05` | SA | SAS |
| 401810762 | `nba-nop-sac-2026-03-05` | NO | NOP |
| 401810780 | `nba-was-nop-2026-03-08` | NO | NOP |
| 401810782 | `nba-hou-sas-2026-03-08` | SA | SAS |
| 401810789 | `nba-gsw-uta-2026-03-09` | UTAH | UTA |
| 401810797 | `nba-bos-sas-2026-03-10` | SA | SAS |
| 401810817 | `nba-nyk-ind-2026-03-13` | NY | NYK |
| 401810828 | `nba-cha-sas-2026-03-14` | SA | SAS |
| 401810836 | `nba-gsw-nyk-2026-03-15` | NY | NYK |
| 401810845 | `nba-sas-lac-2026-03-16` | SA | SAS |
| 401810860 | `nba-lac-nop-2026-03-18` | NO | NOP |
| 401810868 | `nba-phx-sas-2026-03-19` | SA | SAS |
| 401810903 | `nba-nop-nyk-2026-03-24` | NY | NYK |
| 401810915 | `nba-bkn-gsw-2026-03-25` | GS | GSW |
| 401810998 | `nba-nyk-atl-2026-04-06` | NY | NYK |
| 401811001 | `nba-phi-sas-2026-04-06` | SA | SAS |
| 401811009 | `nba-sac-gsw-2026-04-07` | GS | GSW |
| 401811016 | `nba-por-sas-2026-04-08` | SA | SAS |
| 401836754 | `nba-uta-mem-2025-12-12` | UTAH | UTA |
| 401836797 | `nba-was-ind-2025-12-14` | WSH | WAS |

### Outcome and team mapping checks

All Gamma outcome names and abbreviations map to the ESPN ids below. The ESPN
abbreviation column shows the alias used in the shared assignment file; team ids are
from the ESPN season schedule.

| Polymarket outcome | Gamma abbr. | ESPN abbr. | ESPN team id |
|---|---|---|---|
| Hawks | ATL | ATL | 1 |
| Nets | BKN | BKN | 17 |
| Celtics | BOS | BOS | 2 |
| Hornets | CHA | CHA | 30 |
| Bulls | CHI | CHI | 4 |
| Cavaliers | CLE | CLE | 5 |
| Mavericks | DAL | DAL | 6 |
| Nuggets | DEN | DEN | 7 |
| Pistons | DET | DET | 8 |
| Warriors | GSW | GS | 9 |
| Rockets | HOU | HOU | 10 |
| Pacers | IND | IND | 11 |
| Clippers | LAC | LAC | 12 |
| Lakers | LAL | LAL | 13 |
| Grizzlies | MEM | MEM | 29 |
| Heat | MIA | MIA | 14 |
| Bucks | MIL | MIL | 15 |
| Timberwolves | MIN | MIN | 16 |
| Pelicans | NOP | NO | 3 |
| Knicks | NYK | NY | 18 |
| Thunder | OKC | OKC | 25 |
| Magic | ORL | ORL | 19 |
| 76ers | PHI | PHI | 20 |
| Suns | PHX | PHX | 21 |
| Trail Blazers | POR | POR | 22 |
| Kings | SAC | SAC | 23 |
| Spurs | SAS | SA | 24 |
| Raptors | TOR | TOR | 28 |
| Jazz | UTA | UTAH | 26 |
| Wizards | WAS | WSH | 27 |

Alias pairs specifically checked: `GS/GSW`, `NO/NOP`, `NY/NYK`, `SA/SAS`,
`UTAH/UTA`, `WSH/WAS`, `BRK/BKN`, and `PHO/PHX`. No selected-token team
mapping errors remain.
The corrected selected-team win rate is **52.49%** across 903 games. Conditional on
the selected franchise, the most distant rates from 50% (at least 15 percentage
points, with at least 25 selections) are:

| Selected team | Games | Win rate |
|---|---:|---:|
| ATL | 26 | 65.4% |
| BKN | 29 | 34.5% |
| CLE | 42 | 69.0% |
| IND | 31 | 29.0% |
| LAL | 36 | 69.4% |
| MIN | 29 | 65.5% |
| NO | 30 | 30.0% |
| OKC | 29 | 69.0% |
| SA | 39 | 74.4% |
| UTAH | 32 | 31.2% |

### Corrected 6a-lite estimate

The late window remains regulation period 4 with ESPN clock at or below 600 seconds;
overtime is separate. The unit is one maker fill, one assigned team/token per game,
with selected-token prices restricted to [0.03, 0.97]. Shared team assignment remains
the only assignment: `data/interim/phase4/selected_team_by_game.csv` (seed 17).

| Measure | Corrected result |
|---|---:|
| Eligible games | 903 |
| Eligible maker fills | 1,062,795 |
| Game-weighted mean selected-token price | 0.5122 |
| Game-weighted realized win rate | 0.5249 |
| Game-weighted mean `Y - price` | **0.0127** |
| 95% game-clustered bootstrap CI, 2,000 draws | **[-0.0047, 0.0306]** |

Corrected calibration bins:

| Selected-token price bin | Games | Maker fills | Mean price | Win rate | `Y - price` | 95% CI |
|---|---:|---:|---:|---:|---:|---|
| [0.03,0.05) | 420 | 33,216 | 0.0352 | 0.0333 | -0.0019 | [-0.0185, 0.0149] |
| [0.05,0.10) | 416 | 75,406 | 0.0705 | 0.0769 | 0.0064 | [-0.0176, 0.0324] |
| [0.10,0.20) | 411 | 103,798 | 0.1468 | 0.1679 | 0.0211 | [-0.0125, 0.0570] |
| [0.20,0.35) | 406 | 132,406 | 0.2707 | 0.3054 | 0.0347 | [-0.0104, 0.0799] |
| [0.35,0.50) | 397 | 139,305 | 0.4191 | 0.4635 | 0.0444 | [-0.0034, 0.0945] |
| [0.50,0.65) | 410 | 152,117 | 0.5716 | 0.6073 | 0.0357 | [-0.0110, 0.0837] |
| [0.65,0.80) | 446 | 162,710 | 0.7224 | 0.7309 | 0.0085 | [-0.0335, 0.0466] |
| [0.80,0.90) | 453 | 123,334 | 0.8462 | 0.8477 | 0.0015 | [-0.0314, 0.0337] |
| [0.90,0.97] | 494 | 140,503 | 0.9389 | 0.9231 | -0.0158 | [-0.0396, 0.0067] |

### Selected-token price comparison with Kalshi

For each 4th-quarter game-clock minute (index 0 is the final 0:00–0:59; index 9 is
9:00–9:59 remaining), the comparison uses the median of Polymarket maker-fill
selected-token prices and the median of Kalshi trade prices for only the assigned
team's contract. Prices are not censored in this diagnostic. Across **8,984 matched
game-minute pairs**, Polymarket minus Kalshi has mean **−0.0022**, median **0.0000**,
standard deviation **0.0257**, 5th/95th percentiles **[−0.0250, 0.0200]**, and range
**[−0.7800, 0.4300]**. **43 game-minute pairs in 39 games** have absolute difference
above 0.10; the full values are in
`data/interim/phase2/polymarket_6a_minute_price_comparison.csv`. The affected game
slugs and minute indices are:

| Game | Minutes with absolute difference > 0.10 | Largest signed difference |
|---|---|---:|
| `nba-atl-chi-2025-10-28` | 2 | +0.230 |
| `nba-atl-ind-2026-01-31` | 4 | -0.120 |
| `nba-bkn-was-2026-01-02` | 3, 4, 6, 9 | -0.780 |
| `nba-bos-chi-2026-01-24` | 0 | -0.140 |
| `nba-cha-tor-2025-11-17` | 0 | +0.150 |
| `nba-chi-cha-2025-12-12` | 2 | -0.290 |
| `nba-cle-mil-2026-02-25` | 0 | -0.120 |
| `nba-cle-orl-2026-03-11` | 0 | +0.130 |
| `nba-cle-phi-2026-01-16` | 2 | -0.115 |
| `nba-dal-orl-2026-03-05` | 0 | +0.160 |
| `nba-dal-uta-2025-12-15` | 1 | +0.100 |
| `nba-den-okc-2026-02-27` | 1 | +0.220 |
| `nba-den-orl-2025-12-27` | 2 | +0.130 |
| `nba-gsw-dal-2026-01-22` | 8 | -0.110 |
| `nba-gsw-phx-2025-12-18` | 3 | +0.110 |
| `nba-gsw-por-2025-12-14` | 0 | +0.110 |
| `nba-gsw-sac-2025-11-06` | 5 | +0.140 |
| `nba-ind-mem-2025-10-25` | 0 | -0.430 |
| `nba-lac-ind-2026-03-27` | 0 | +0.240 |
| `nba-lac-nop-2026-03-19` | 0 | +0.150 |
| `nba-mem-phx-2025-10-30` | 0 | +0.430 |
| `nba-mem-sas-2025-11-18` | 3 | +0.130 |
| `nba-mia-bos-2026-02-06` | 1 | +0.110 |
| `nba-min-phx-2025-11-21` | 0 | -0.110 |
| `nba-min-tor-2026-02-04` | 1 | +0.120 |
| `nba-nop-dal-2025-11-21` | 1, 2 | -0.140 |
| `nba-nop-lac-2025-11-01` | 7 | -0.130 |
| `nba-nyk-phx-2026-01-09` | 1 | -0.140 |
| `nba-phi-bos-2025-10-22` | 1 | +0.175 |
| `nba-phi-mil-2025-11-20` | 0 | +0.130 |
| `nba-por-mia-2025-11-09` | 7 | +0.140 |
| `nba-por-min-2026-03-20` | 0 | -0.240 |
| `nba-sas-den-2026-04-04` | 2 | +0.120 |
| `nba-sas-nop-2025-10-24` | 1 | +0.120 |
| `nba-uta-atl-2026-02-05` | 6 | -0.115 |
| `nba-uta-sac-2025-10-24` | 0 | -0.130 |
| `nba-was-bkn-2026-04-05` | 2 | +0.190 |
| `nba-was-mil-2025-12-31` | 0 | +0.280 |

### Price perspective on Oct. 21 receipts

The API `price` is the execution price of the row's own token for both maker `BUY`
and maker `SELL`. In the Oct. 21 live-game rows, **4,492 unique API maker fills**
match unique receipt `OrderFilled` keys (transaction, maker wallet, token, side, size,
and price); receipt decoding independently computes `cash / shares`. After rounding
only for the join key, the maximum API/receipt price residual is below **5e-11** for
both sides. The receipt cache has 33 duplicate log rows with an already-seen fill key.
The selected-token transform is applied only when the row's asset is the other token:
use `price` if selected, otherwise `1 - price`. Maker side does not change that rule.

Oct. 21's selected team was OKC, the winner (`Y=1`). The late regulation sample's
`Y - selected price` by side and asset was:

| Maker side | Row asset | Rows | Mean own-asset price | Mean selected-token price | Mean `Y - price` |
|---|---|---:|---:|---:|---:|
| BUY | non-selected | 383 | 0.5776 | 0.4224 | 0.5776 |
| BUY | selected | 345 | 0.3748 | 0.3748 | 0.6252 |
| SELL | non-selected | 204 | 0.5997 | 0.4003 | 0.5997 |
| SELL | selected | 195 | 0.4304 | 0.4304 | 0.5696 |

The corrected estimate and calibration bins are stored in
`data/interim/phase2/polymarket_6a_lite_season.json` and
`data/interim/phase2/polymarket_6a_lite_season_bins.csv`. Audits are saved in
`polymarket_6a_outcome_audit.csv`, `polymarket_6a_team_mapping.csv`,
`polymarket_6a_team_win_rates.csv`, `polymarket_6a_minute_price_comparison.csv`, and
`polymarket_oct21_price_perspective.csv` under `data/interim/phase2/`. The diagnosis
is reproducible with `python3 src/diagnose_polymarket_6a.py`; the corrected calibration
is reproducible with `python3 src/run_polymarket_6a_season.py`.

## Activity endpoint and positions

The cached season maker/taker API join is unambiguous by transaction hash:
3,182,525 taker rows have 3,182,525 distinct hashes, and all 4,601,635 maker
fills have a taker identity assigned. On-chain confirmation is sampled rather
than season-wide: the V1 Oct. 21 probe matched all 3,488 in-game taker rows to
`OrdersMatched`; the V2 May 1 check matched 9,459 API maker fills to receipt
logs but did not compare every API taker wallet to its `OrdersMatched` wallet.
Nine monthly receipt spot checks include V2 examples. This supports the
cached event-level identity join; it does not reconstruct participant
positions.

The legacy `/activity` endpoint accepts both `user` and `market` (condition ID) and
supports filtering by activity type. For the ten Oct. 21 wallets, the cached user+market
pages contained **2,619 rows**: 2,584 `TRADE`, 25 `MERGE`, and 10 `REDEEM`; no
`SPLIT` or `CONVERSION` rows were returned. This endpoint is therefore insufficient
for complete wallet positions, and the requested ten-wallet redemption reconciliation
is not claimed.

The position-ingest approach reported before implementation is to decode the relevant
Conditional Tokens `PositionSplit`, `PositionsMerge`, and `PayoutRedemption` receipt
events and ERC-1155 `TransferSingle`/`TransferBatch` mint, burn, and wallet-transfer
logs, then combine those balance changes with maker and taker fills. The implementation
and 10-wallet validation remain outside this 6a-lite run; do not use this season
calibration as a Phase 6c position panel.

## Reproduction

Run `python3 src/ingest_polymarket_data_api.py` to resume/rebuild the Data API season
panel from cached pages, and `python3 src/run_polymarket_6a_season.py` to regenerate
the full-season estimate. `src/validate_polymarket_v2_market.py` reproduces the V2
receipt check; `src/run_polymarket_6a_lite.py` reproduces the Oct. 21 diagnostic.
The API collector stores every raw response under `data/raw/polymarket/`.

## Shared team assignment for season analysis

Confirmed: all Polymarket calibration used the existing
`data/interim/phase4/selected_team_by_game.csv` (seed 17) as the only team assignment.
No other assignment file was created or used.

## Phase 6 selection analysis replication (2026-10-21)

This replication uses the same `phase5a.summarize()` Prelec-II fitter as the Kalshi analysis: one-cent bins, trade-weighted fits, raw and isotonic bin rates, and 2,000 game-cluster bootstrap draws (seed 5132026). The observation is one Polymarket maker fill only. The only team assignment is the shared `data/interim/phase4/selected_team_by_game.csv` (seed 17). The main-session selected-team file, P* parquet, game-window definitions, and raw ESPN wall-clock files were read only; no Kalshi or play-by-play files were changed.

For wall-clock **d**, the sample is the last 10 minutes before the last ESPN play, and each fill is expressed in its own token’s coordinate. The OT-excluded d estimate removes games with overtime. The knowable window starts at the first Q4 ESPN state at or below 3:00 and ends at the earlier of ten wall minutes later or the last ESPN play; fills are in-game only. Game-clock windows use regulation clock remaining in Q4 and the seed-17 selected-team coordinate. To match the saved Kalshi quick-check scope, all game-clock comparisons use regular-season fills from 2026-03-01 through 2026-05-15 UTC; this restriction leaves 332–336 Polymarket games. P* is the home-coordinate P* at the nearest rounded ESPN period/clock second, transformed to the row’s outcome coordinate. Fits use the main-session price filter `0 < coordinate < 1`.

### Prelec-II alpha estimates

Table cells show alpha and 95% game-clustered bootstrap CI. Raw and isotonic estimates are reported for both venues. Kalshi game-clock and several P* estimates were recomputed in memory from read-only Phase 4 panels with the shared fitter where no matching saved estimate existed. The main-session saved Kalshi knowable-window **price** fit is at the lower alpha boundary; it is transcribed as saved and flagged for interpretation in that pipeline.

| Window / coordinate | Curve | PM alpha [95% CI] | Kalshi alpha [95% CI] | PM fills / games | Kalshi fills / games |
|---|---|---:|---:|---:|---:|
| d_wall10_own_token / price | raw | 1.540 [1.305, 1.865] | 1.524 [1.306, 1.837] | 389,439 / 1,201 | 2,524,781 / 1,202 |
| d_wall10_own_token / price | isotonic | 1.541 [1.313, 1.852] | 1.526 [1.311, 1.856] | 389,439 / 1,201 | 2,524,781 / 1,202 |
| d_wall10_own_token / Pstar | raw | 1.494 [1.327, 1.721] | 1.477 [1.309, 1.696] | 389,439 / 1,201 | 2,524,779 / 1,202 |
| d_wall10_own_token / Pstar | isotonic | 1.497 [1.339, 1.723] | 1.482 [1.316, 1.703] | 389,439 / 1,201 | 2,524,779 / 1,202 |
| d_wall10_excluding_ot_own_token / price | raw | 1.514 [1.284, 1.843] | 1.502 [1.279, 1.821] | 351,414 / 1,148 | 2,206,053 / 1,149 |
| d_wall10_excluding_ot_own_token / price | isotonic | 1.515 [1.296, 1.845] | 1.503 [1.282, 1.807] | 351,414 / 1,148 | 2,206,053 / 1,149 |
| d_wall10_excluding_ot_own_token / Pstar | raw | 1.382 [1.229, 1.576] | 1.361 [1.213, 1.552] | 351,414 / 1,148 | 2,206,053 / 1,149 |
| d_wall10_excluding_ot_own_token / Pstar | isotonic | 1.381 [1.245, 1.582] | 1.360 [1.222, 1.568] | 351,414 / 1,148 | 2,206,053 / 1,149 |
| knowable_wall10_selected / price | raw | 1.113 [0.949, 1.341] | 0.000 [0.000, 0.015] | 402,173 / 1,201 | 2,634,066 / 1,211 |
| knowable_wall10_selected / price | isotonic | 1.115 [0.943, 1.358] | 0.013 [0.008, 0.022] | 402,173 / 1,201 | 2,634,066 / 1,211 |
| knowable_wall10_selected / Pstar | raw | 1.018 [0.884, 1.204] | 1.019 [0.881, 1.195] | 402,173 / 1,201 | 2,615,732 / 1,210 |
| knowable_wall10_selected / Pstar | isotonic | 1.028 [0.891, 1.218] | 1.030 [0.901, 1.233] | 402,173 / 1,201 | 2,615,732 / 1,210 |
| gameclock_final2_selected / price | raw | 1.035 [0.756, 1.845] | 0.938 [0.671, 1.763] | 124,058 / 332 | 711,717 / 336 |
| gameclock_final2_selected / price | isotonic | 1.052 [0.788, 1.893] | 0.958 [0.727, 1.743] | 124,058 / 332 | 711,717 / 336 |
| gameclock_final2_selected / Pstar | raw | 1.066 [0.817, 1.630] | 0.959 [0.701, 1.533] | 124,058 / 332 | 711,717 / 336 |
| gameclock_final2_selected / Pstar | isotonic | 1.113 [0.900, 1.787] | 1.013 [0.796, 1.676] | 124,058 / 332 | 711,717 / 336 |
| gameclock_final3_selected / price | raw | 0.997 [0.740, 1.709] | 0.944 [0.677, 1.683] | 157,798 / 333 | 869,103 / 336 |
| gameclock_final3_selected / price | isotonic | 1.011 [0.756, 1.733] | 0.960 [0.724, 1.680] | 157,798 / 333 | 869,103 / 336 |
| gameclock_final3_selected / Pstar | raw | 0.989 [0.762, 1.476] | 0.927 [0.678, 1.422] | 157,798 / 333 | 869,103 / 336 |
| gameclock_final3_selected / Pstar | isotonic | 1.029 [0.823, 1.562] | 0.968 [0.758, 1.560] | 157,798 / 333 | 869,103 / 336 |
| gameclock_final5_selected / price | raw | 1.077 [0.814, 1.591] | 1.027 [0.769, 1.534] | 238,933 / 335 | 1,235,927 / 336 |
| gameclock_final5_selected / price | isotonic | 1.089 [0.826, 1.618] | 1.039 [0.813, 1.546] | 238,933 / 335 | 1,235,927 / 336 |
| gameclock_final5_selected / Pstar | raw | 0.993 [0.785, 1.342] | 0.950 [0.734, 1.316] | 238,933 / 335 | 1,235,927 / 336 |
| gameclock_final5_selected / Pstar | isotonic | 1.015 [0.836, 1.372] | 0.977 [0.798, 1.385] | 238,933 / 335 | 1,235,927 / 336 |
| gameclock_final10_selected / price | raw | 1.177 [0.919, 1.564] | 1.119 [0.864, 1.495] | 430,349 / 336 | 2,069,180 / 336 |
| gameclock_final10_selected / price | isotonic | 1.178 [0.932, 1.576] | 1.122 [0.898, 1.534] | 430,349 / 336 | 2,069,180 / 336 |
| gameclock_final10_selected / Pstar | raw | 0.982 [0.813, 1.253] | 0.971 [0.775, 1.254] | 430,349 / 336 | 2,069,180 / 336 |
| gameclock_final10_selected / Pstar | isotonic | 0.994 [0.830, 1.266] | 0.986 [0.815, 1.284] | 430,349 / 336 | 2,069,180 / 336 |

The game-clock comparison window scopes are Mar. 1–May 15, 2026. The knowable-window actual-price Kalshi fit has raw alpha 0.0001 (CI [0.0001, 0.0148]) and isotonic alpha 0.0131 (CI [0.0078, 0.0224]), both at/near its fitting boundary in the saved main-session output. The Polymarket knowable-window price fit is raw 1.1131 (CI [0.9489, 1.3409]) and isotonic 1.1146 (CI [0.9428, 1.3583]). This large inter-venue discrepancy is present in the underlying saved Kalshi estimate and is not adjusted here.

### Longshot fills (0.05–0.20) during final 3 regulation game-clock minutes

“Inside d” means also within the final 10 wall-clock minutes before the last ESPN play; “outside d” means within the final three regulation game-clock minutes but outside that wall-clock interval. Win rates and trade-weighted gaps are fill weighted; game-weighted gaps and CIs use game clusters.

| d membership | Coordinate | Fills / games | Mean probability | Win rate | Trade-weighted Y−p | Game-weighted Y−p [95% CI] |
|---|---|---:|---:|---:|---:|---:|
| inside_d | price | 90,512 / 453 | 0.112 | 0.046 | -0.067 | -0.065 [-0.077, -0.050] |
| inside_d | Pstar | 90,512 / 453 | 0.152 | 0.046 | -0.106 | -0.091 [-0.103, -0.077] |
| outside_d | price | 61,855 / 301 | 0.120 | 0.181 | +0.061 | +0.035 [-0.004, +0.074] |
| outside_d | Pstar | 61,855 / 301 | 0.146 | 0.181 | +0.035 | +0.014 [-0.025, +0.052] |

### Contracts priced 0.10–0.40

Price refers to the selected-team coordinate; P* uses the corresponding selected-team placebo coordinate. Win rate and trade-weighted Y−p are fill weighted. The reported gap and interval are game weighted with game-clustered bootstrap CI.

| Window | Coordinate | Fills / games | Win rate | Trade-weighted Y−p | Game-weighted Y−p [95% CI] |
|---|---|---:|---:|---:|---:|
| d_wall10 | price | 78,495 / 451 | 0.141 | -0.091 | -0.117 [-0.134, -0.101] |
| d_wall10 | Pstar | 99,843 / 464 | 0.131 | -0.089 | -0.120 [-0.137, -0.104] |
| d_wall10_excluding_ot | price | 67,439 / 403 | 0.147 | -0.085 | -0.115 [-0.132, -0.096] |
| d_wall10_excluding_ot | Pstar | 83,265 / 411 | 0.140 | -0.070 | -0.114 [-0.131, -0.097] |
| knowable_wall10 | price | 79,697 / 298 | 0.236 | -0.011 | +0.049 [+0.003, +0.095] |
| knowable_wall10 | Pstar | 86,614 / 274 | 0.243 | +0.018 | +0.062 [+0.010, +0.115] |
| gameclock_final2_spring_match | price | 23,645 / 48 | 0.258 | +0.012 | +0.042 [-0.064, +0.160] |
| gameclock_final2_spring_match | Pstar | 29,591 / 46 | 0.252 | +0.026 | +0.064 [-0.057, +0.178] |
| gameclock_final5_spring_match | price | 48,918 / 75 | 0.263 | +0.017 | +0.078 [-0.018, +0.176] |
| gameclock_final5_spring_match | Pstar | 61,431 / 71 | 0.305 | +0.070 | +0.079 [-0.025, +0.183] |

The exact bin-level fit inputs are `data/interim/phase2/polymarket_selection_analysis_bins.csv`; machine-readable fit estimates and sample counts are in `data/interim/phase2/polymarket_selection_analysis.json`. The side-by-side alpha table is `data/interim/phase2/polymarket_kalshi_alpha_comparison.csv`.

Position reconstruction remains on hold; no position panel or redemption reconciliation is claimed.

## Full-season game-clock rerun and consolidated Phase 6 summary (2026-10-21)

This section supersedes the earlier spring-only game-clock fits and 0.10–0.40 game-clock rows above. I reran final 2/3/5/10 regulation game-clock windows on the full 2025–26 regular season, using the shared Q4 regulation clock predicate; overtime is excluded. The 0.10–0.40 rows for final 2 and final 5 minutes now use those full-season samples. Fitting remains one maker fill per observation, one-cent bins, trade weighted, raw and isotonic Prelec-II, 2,000 game-cluster bootstrap draws. Kalshi comparison estimates are the main session’s matching full-season fit outputs.

| Window | Curve | Polymarket alpha [95% CI] | Kalshi alpha [95% CI] | PM fills / games | Kalshi fills / games |
|---|---|---:|---:|---:|---:|
| Final 2 regulation minutes / selected team | raw | 1.113 [0.911, 1.415] | 1.113 [0.925, 1.357] | 389,153 / 1,191 | 2,702,963 / 1,207 |
| Final 2 regulation minutes / selected team | isotonic | 1.116 [0.919, 1.405] | 1.114 [0.930, 1.362] | 389,153 / 1,191 | 2,702,963 / 1,207 |
| Final 3 regulation minutes / selected team | raw | 1.085 [0.907, 1.319] | 1.105 [0.944, 1.310] | 492,480 / 1,203 | 3,289,309 / 1,210 |
| Final 3 regulation minutes / selected team | isotonic | 1.086 [0.917, 1.328] | 1.106 [0.942, 1.326] | 492,480 / 1,203 | 3,289,309 / 1,210 |
| Final 5 regulation minutes / selected team | raw | 1.054 [0.909, 1.246] | 1.052 [0.924, 1.216] | 738,935 / 1,207 | 4,677,599 / 1,211 |
| Final 5 regulation minutes / selected team | isotonic | 1.055 [0.901, 1.247] | 1.053 [0.917, 1.214] | 738,935 / 1,207 | 4,677,599 / 1,211 |
| Final 10 regulation minutes / selected team | raw | 1.057 [0.935, 1.208] | 1.041 [0.937, 1.168] | 1,295,617 / 1,210 | 7,689,930 / 1,211 |
| Final 10 regulation minutes / selected team | isotonic | 1.057 [0.930, 1.208] | 1.042 [0.931, 1.176] | 1,295,617 / 1,210 | 7,689,930 / 1,211 |

### Full-season contracts priced 0.10–0.40 (game-weighted sensitivity)

These are game-weighted outcomes for the 0.10–0.40 price band. They are a sensitivity result, not the registered final-five quiet-stoppage primary; they remain useful platform context. The main text presents the first-entry, game-weighted, and pooled trade-weighted Kalshi estimates in the same table for this separate band. Polymarket first-entry estimates for this band have not been recomputed here.

| Window | Coordinate | Maker fills / games | Fill-weighted win rate | Fill-weighted Y−p | Game-weighted Y−p [95% CI] |
|---|---|---:|---:|---:|---:|
| Final 2 regulation minutes | price | 73,807 / 257 | 0.220 | -0.026 | +0.036 [-0.012, +0.088] |
| Final 2 regulation minutes | Pstar | 89,489 / 235 | 0.193 | -0.024 | +0.041 [-0.010, +0.096] |
| Final 5 regulation minutes | price | 156,441 / 375 | 0.261 | +0.015 | +0.065 [+0.021, +0.106] |
| Final 5 regulation minutes | Pstar | 182,279 / 359 | 0.265 | +0.039 | +0.071 [+0.029, +0.114] |

All Polymarket selection-analysis estimates, CIs, sample counts, bin-level calibration data, longshot splits, contract summaries, and matching Kalshi alpha comparisons are consolidated in `data/interim/phase6/polymarket_selection_summary.json`. Its fit keys match the main Phase 5 naming convention (`d_market`, `d_pstar`, `d_no_ot_market`, `knowable_market`, `gameclock_2_market`, and so on), and each fit retains the main session’s `trades`, `games`, `price_bins`, `bin_width_cents`, `raw`, and `isotonic` fields.

The Phase 6 wallet mechanism tests remain blocked by missing season-wide
inventory transitions. The available Data API rows identify wallets and trade
sides but cannot establish each wallet's pre-trade positions. The cached
activity probe omitted SPLIT and CONVERSION records, and receipts cover only
selected markets rather than the full season. No wallet loss attribution,
position-conditioned flow, or fresh-buyer test is reported. Required inputs
and a prospective collection protocol are listed in `DEVIATIONS.md`.
