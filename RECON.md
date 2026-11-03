# Phase 0: Recon

Checked 2026-10-21. This was the Phase 0 API and coverage reconnaissance, before the Phase 1 ingest. At the time of the Phase 0 check, no raw data had been written or cached. Phase 1 has since written the raw and interim data described in [`RESULTS.md`](RESULTS.md). The proposal file in this directory is `thesis proposal sam meddin.pdf`; it is three pages and was read in full. Where its design differs from `CLAUDE.md`, this report follows `CLAUDE.md`.

## Findings

### Kalshi

- **Series and market structure:** `KXNBAGAME` is a real series (API title “NBA Game”). The historical series response identifies `fee_multiplier=1` and `fee_type=quadratic_with_maker_fees`. Each completed event I inspected had two binary markets, one YES contract for each team. These are complementary outcomes, so the one-team-per-game rule in `CLAUDE.md` is needed.
- **Trades:** Both `GET /trade-api/v2/markets/trades` and `GET /trade-api/v2/historical/trades` exist. The latter is the route for trades archived before the exchange's historical cutoff; it accepts market ticker filters and cursor pagination. The response contains `ticker`, `trade_id`, `count_fp`, `yes_price_dollars`, `no_price_dollars`, `taker_outcome_side`, `taker_book_side`, `taker_side`, `created_time`, and `is_block_trade`. A live trade response contained a UTC timestamp with six fractional digits (`2026-10-21T06:19:19.704161Z`), so the observed data has microsecond formatting. The API example itself only shows whole seconds; precision and uniqueness should be verified across historical trades before subsecond use. Taker outcome and book side are distinct fields and should not be conflated.
- **Historical coverage / listed-game counts:** Querying the historical markets endpoint for `series_ticker=KXNBAGAME` and following all cursors returned 2,898 team markets / 1,449 event tickers. Parsing the game date in the event ticker gives:

  | NBA season / covered dates | Listed event tickers | Team markets |
  |---|---:|---:|
  | 2024–25, Apr–Jun 2025 tail only, regular season plus postseason | 86 | 172 |
  | 2025–26, Oct 2025–Jun 2026, regular season plus postseason | 1,363 | 2,726 |

  These are **listed markets**, not counts of games with trades during live play. The recent-market endpoint at the check date additionally returned 70 settled event tickers (140 team markets) from Oct 4–21, 2026. A complete live-trade census by game has not been run. Count games with at least one trade strictly between actual game start and end only after matching the historical trade timestamps to NBA game times; market volume alone is not enough to make that claim.
- **Quotes:** The market candlestick route exists and includes bid/ask OHLC fields, but its finest interval is **one minute** (other documented intervals are one hour and one day). Older settled markets use `GET /historical/markets/{ticker}/candlesticks`. One-minute candles cannot resolve second-level quote paths; trade-derived quotes remain the only documented candidate in this API for the short-horizon analysis. Historical candlestick coverage must be checked for every selected market.
- **Fees:** The archived PDFs establish the dated general taker and maker formulas, including cent rounding. Current `KXNBAGAME` series metadata says `quadratic_with_maker_fees`, multiplier 1, but no historical API series snapshots were found. Historical maker-fee applicability for each 2025–26 trade date and the start date remain unresolved; see `DEVIATIONS.md`.
- **Position limits:** I did not establish the applicable NBA contract position limit from public series/market metadata or a current authoritative rule/API response. Treat as unresolved pending an official limit source.

### NBA play-by-play

- The proposed CDN route is `https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_<GAME_ID>.json`. Direct access to a known historical game ID returned HTTP 403 in this environment, so I could not inspect an actual response or validate `timeActual`, its historical coverage, or wall-clock accuracy. A 403 here may reflect access controls on this network; it does not establish that the route is universally unavailable.
- `nba_api` / NBA Stats and `pbpstats` remain fallback candidates, but I have not validated their timestamp fields or accessed a season archive in this phase. In particular, Phase 0 does **not** establish that per-action wall times exist at useful resolution back to 2015.
- Score changes, period boundaries, fouls/free-throw trips, turnovers, and rebounds are conventional play-by-play action fields. Timeout onset/end, replay-review intervals, and actual clock stop/restart instants are not verified by the CDN sample because no sample could be fetched. A sequence of action timestamps alone may not directly expose every clock transition.

### Polymarket

- **Discovery and binary market structure:** Gamma's public API is reachable and exposes NBA-tagged events and nested markets. The pages I inspected include NBA game events, but the tag includes non-game NBA questions and postseason events; filter with game/event metadata and team labels rather than relying on the tag alone. A per-game market may have complementary YES/NO tokens; some events contain multiple markets, so the event-to-market mapping needs inspection rather than assuming every event is one two-token market.
- **Public fills endpoint:** The Data API `/trades` response exposes a `proxyWallet`, `side`, `asset` token ID, `conditionId`, `size`, `price`, and Unix-second `timestamp`. It does **not** expose both counterparties in the returned trade row. It therefore is not sufficient alone for the planned maker/taker and wallet-position tests. The public CLOB `/trades` route returned HTTP 401 without authentication in this environment.
- **On-chain records:** Polymarket's matching and settlement are separate stages (orders are matched off-chain and settled on-chain). The likely path for identifying both sides is Polygon exchange-contract event/log data plus transaction calldata/receipt. I have not verified which event identifies the economic maker and taker, nor hand-checked example fills against transactions. Do not implement wallet attribution from an `OrderFilled` address field until that check is complete.
- **Timestamp granularity:** The Data API returns a Unix timestamp in seconds; the on-chain route would use Polygon block timestamps. Thus latency labels finer than block-time resolution are not supported by this data. Measure block-time resolution on the sampled period before choosing bot cutoffs.
- **Live sports delay and fees:** I could not verify a current NBA-specific order delay and its duration from the public docs or sample records. Nor did I establish the current sports-market fee rule. Both are unresolved; don't assume there is no sports fee or treat an order-placement delay as a fill delay. Verify with current official docs/market metadata and transactions.
- **Games with in-game fills by season:** Not counted. Gamma is sufficient to enumerate candidates but not to establish live fills; `/trades` history and/or on-chain records must be joined to game times. Do not count event volume as in-game trading.

## Decisions from Sam

- Main sample: 2025–26 NBA regular season; exclude the 2024–25 tail and all 2026–27 games.
- Ingest playoffs for robustness only.
- Kalshi-only main analysis is acceptable; Phase 1 is not gated on Polymarket.
- Report the number of distinct regular-season games with at least one Kalshi trade during play at the end of Phase 1.
- Exclude Kalshi block trades.
- Empirically identify Kalshi taker fields against one-minute candles; report trade-date fee schedules and maker-fee start date. For the 5f band, report large-size per-contract fees and fees at median observed trade size. Position limits are out of scope for main results.
- NBA CDN and ESPN play-by-play should both be ingested if accessible. If network access blocks the CDN, leave a local fetch script and report the block.

## Questions for Sam

1. **Postponed Kalshi market mapping:** The original GSW–MIN fixture (Jan. 24) is marked postponed, but the game was completed under ESPN ID `401857824` on Jan. 25; the Kalshi event closed after that game and settled YES/NO. Should that market be remapped to the completed game for the in-play census, despite the original ticker date? Three other postponed markets settled `scalar` and lack an evident played-game match.
2. **Historical maker fees:** The archived PDFs do not identify eligible series and the historical series API has no captured snapshots. If Sam has an official 2025 series-history record, it would establish KXNBAGAME's maker-fee start date; otherwise this stays unresolved.

## Status

All approved work through Phase 5h and the read-only Polymarket integration is complete. Phase 6 wallet analysis has not started. See [`RESULTS.md`](RESULTS.md) and [`DEVIATIONS.md`](DEVIATIONS.md) for ingestion, corrected timing, timeout, possession, Polymarket, and P* results. The revised possession validation uses `FGA - ORB + turnovers + 0.44 * FTA`; per [`DEVIATIONS.md`](DEVIATIONS.md), the no-possession model is primary and the possession model is a robustness specification. Historical maker-fee applicability and the postponed GSW–MIN mapping remain unresolved; position limits remain out of scope per Sam's instruction.

## Source links checked

- Kalshi [Get Trades](https://docs.kalshi.com/api-reference/market/get-trades), [Get Historical Trades](https://docs.kalshi.com/api-reference/historical/get-historical-trades), [Get Historical Markets](https://docs.kalshi.com/api-reference/historical/get-historical-markets), and [Get Market Candlesticks](https://docs.kalshi.com/api-reference/market/get-market-candlesticks).
- Kalshi [Fee Schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf) (effective Feb 5, 2026 when checked).
- Polymarket [Data API](https://data-api.polymarket.com/v2/docs), [Order Lifecycle](https://docs.polymarket.com/concepts/order-lifecycle), and [Gamma API](https://gamma-api.polymarket.com/).
- NBA CDN play-by-play route tested directly; request was denied (HTTP 403): [sample URL](https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_0021500001.json).
