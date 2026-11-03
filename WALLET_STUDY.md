# Polymarket bettor heterogeneity study

## Objective

Identify which observable account behaviors are associated with late-game
longshot pricing gaps, and test whether the gap is concentrated in particular
types of participant activity. The study asks where the pattern appears to
come from; it does not assume that public wallet data reveal a person's
identity, occupation, motive, or use of automation.

## Data and unit

The current season files contain in-game NBA CLOB activity for the 2025–26
regular season: maker-side fill records and separately queried taker-side
activity records. Each record's `proxyWallet`, outcome token, action side,
price, size, timestamp, and market are the participant's own fields. A
transaction hash can contain several maker fills and one aggregated taker
record, and the two sides can concern complementary outcome tokens. Therefore
the maker record's token or price must never be copied onto the taker record.
The two participant tables will be analyzed in their own coordinates and
reconciled at transaction level before any inventory or flow interpretation.

The current extract is game-time only. It does not establish starting
positions, pregame activity, full platform activity, or postgame disposition.
Any measure based on this extract must be called in-game NBA activity.

## Observable profiles (outcome-free)

Profiles will be computed from participant activity, without using winners,
prices relative to outcomes, or the estimated pricing gap:

1. **Activity intensity:** participant activity records per active UTC day.
   Report continuously and at the pre-existing config cutoffs of 20, 100, and
   500 records per active day. These are high-activity tiers, not bot labels.
2. **Execution role:** maker-side share of participant records and filled
   shares, with thresholds 0.50, 0.75, and 0.90 from the locked config.
   Call accounts maker-dominant or taker-dominant; do not call them market
   makers unless order-book evidence supports that label.
3. **Stake proxy:** median and total trade notional in the observed sports
   sample, reported as size distributions. Low observed stakes are a
   low-stake proxy, not proof that an account is retail or has little wealth.
4. **Breadth and persistence:** distinct games, active days, and activity
   concentration across those games. These identify broad, recurring, and
   one-off account patterns within the sampled NBA markets only.

Use combinations of those features only as transparent descriptive profiles.
"Retail-like" may be used as shorthand only when immediately defined as
low-activity, low-observed-stake, and taker-dominant in this dataset. "Bot-like"
is not a primary classification. A separate rapid-response proxy can be
reported only after event-time alignment is validated, at 5/10/20-second
thresholds and with the documented sports-order-delay sensitivity. Timestamps
are too coarse to claim sub-second automation.

## Tests of where the gap comes from

1. First confirm that Polymarket exhibits the target abnormality in the exact
   sample/window used for wallet tests. If the market-level gap is absent or
   imprecise, wallet-level patterns cannot be presented as its source.
2. Estimate type-specific longshot buying, selling, and marketable execution
   outcomes in common game-state and price support. Use game-clustered
   uncertainty and report the effective number of games, not just fills.
3. Reconstruct positions only after a complete market-lifecycle ledger has
   been obtained and validated. It must include exchange fills, splits,
   merges, redemptions, migrations, and ERC-1155 transfers from market
   creation through resolution. Validate wallet balances and redemption
   payouts on a stratified sample before classifying a trader as holding the
   favorite, holding the longshot, or fresh.
4. Do not delete a wallet group's trades and call the resulting price curve a
   counterfactual. Group-level calibration is descriptive. Lagged flow and
   event-response models are supporting associations, not causal effects.
5. Do not claim that Polymarket account patterns explain Kalshi's estimate.
   Kalshi has no comparable trader identifiers in the assembled data. A
   cross-venue mechanism claim requires first establishing comparable
   abnormalities and a defensible transport argument.

## Current feasibility finding (2026-10-22)

The existing Polymarket table has 4,601,635 maker fill rows and 3,182,525
taker activity rows from 1,218 games with maker activity. The taker table has
one distinct transaction hash per row, and every taker hash occurs in the
maker table. Existing joined maker rows contain a taker identity. The
transaction join is adequate to identify participant roles, but not to infer
that both participants traded the same outcome token or at the same price:
complementary buy/buy and sell/sell matches occur. Earlier inventory
prerequisite notes remain in force: season-wide pre-trade positions are not
yet validated, so gain realization, loss chasing, true net returns, and
fresh-position tests remain pending a complete lifecycle ledger.

The outcome-free profile pass finds 95,513 distinct wallets across the two
roles. Per wallet, the median is 4 observed participant records (90th
percentile 62), and median activity is 2 records per active day (90th
percentile 8.4). The most active 1% account for 73.9% of maker fill records
and 54.2% of taker activity records. Median participant-record notional is
$9.12 for maker rows and $9.75 for taker rows. These figures describe the
in-game NBA extract only; they do not prove a retail/professional split.

All 3,182,525 taker transaction hashes occur in the maker file, and the
joined taker wallet and side agree for every transaction. About 20.3% of
transactions contain multiple maker fills. The sum of maker-reported shares
matches taker-reported shares within 1e-5 in 89.3% of transactions (95th
percentile relative discrepancy 2.7%). Because this does not reconcile in
all transactions, volume share is not used to classify maker-dominant
accounts; the current role proxy uses record share, with the unit stated
explicitly.

Reproduce the outcome-free profile files with `make phase6-wallet-profiles`.
The script and files do not calculate outcome-based group differences and do
not assign bot, retail, professional, or market-maker identities.

## Current conclusion

It is feasible to study account behavioral profiles and whether activity by
those profiles is associated with the Polymarket pricing pattern. It is not
yet established that we can truthfully identify human retail bettors, bots,
professional traders, or the causal source of the Kalshi abnormality. Those
are hypotheses to test against the observable proxies above.

## Outcome screen and lifecycle pilot (2026-10-22)

The exploratory screen contains 137,343 own-token BUY records in the final
five regulation minutes, priced 5–20 cents when the market-free benchmark
also calls that token an underdog. These rows span 11,246 wallets and 642
games. The sample's game-weighted realized outcome minus purchase price is
−2.72 percentage points (95% two-way game/wallet clustered CI −4.56 to
−0.88). This is a per-record settlement payoff comparison, not wallet P&L.
The benchmark itself overpredicts wins in this selected buyer sample, and
price minus benchmark is negative across all reported profile groups. The
analysis therefore does not support a claim that one profile overpays versus
the benchmark or causes the broader pricing pattern. Profiles overlap and the
group comparisons are exploratory, not a controlled decomposition. A
common-support comparison of high-activity accounts (at least 20 records per
active day) against all other accounts retains 117,253 records (85.4%) in 624
games where both groups traded in the same game, regulation-minute, P* band,
and participant role. Cell fixed effects estimate a high-activity association
with purchase payoff (`Y−price`) of −0.01 points (95% two-way game/wallet
clustered CI −0.24 to +0.21); the association with `Y−P*` is −0.10 points
(−0.32 to +0.12). Both include zero. A second comparison of maker-record-
dominant versus taker-record-dominant accounts (75% record-share profiles)
retains 62,934 records (57.0% of eligible profile rows) across 586 games.
Maker-dominant accounts have a +0.35-point `Y−price` difference (95% CI +0.23
to +0.47), a −0.35-point `price−P*` difference (−0.45 to −0.24), and nearly
zero `Y−P*` difference (−0.03 to +0.03). The contrast appears in purchase
prices, not realized outcome relative to the same benchmark. It is consistent
with different entry prices or execution conditions, not forecasting skill,
net wallet profit, causal impact, or account identity. Both are exploratory,
selected-sample associations. Reproduce with `make phase6-wallet-common-support`.
The maker/taker `Y−price` difference remains positive at 50/50 and 90/10
record-share cutoffs, while `Y−P*` includes zero at each. It also remains
positive under 2.5¢, 5¢/10¢, and 10¢ P* bands and both 30- and 60-second
clock cells. High-activity `Y−price` differences remain near zero across the
20/100/500-record thresholds. With 30-second cells, high-activity `Y−P*`
differences are statistically distinguishable in two P* schemes but only
−0.01 to −0.03 points; 60-second and coarser-P* versions include zero. Keep
this small sensitivity visible. These checks are exploratory; reproduce with
`make phase6-wallet-profile-sensitivity`.

The purchase-level `Y−price` estimates are −2.55 percentage points for
accounts with at least 20 records per active day (95% CI −4.42 to −0.68),
−2.51 for maker-record-dominant accounts (−4.33 to −0.69), −3.59 for
taker-record-dominant accounts (−5.47 to −1.70), and −3.13 for the
low-activity/low-stake proxy (−5.02 to −1.24). These intervals do not test
differences between groups; the comparisons are also not adjusted for common
game-state support. Do not interpret them as evidence one profile is less
profitable or causes the price pattern.

A fixed stratified sample of 210 wallet-market pairs was fetched from the
public Activity API using the target cohort. It contains 4,344 TRADE, 100
MERGE, and 143 REDEEM rows; no SPLIT, CONVERSION, or TRANSFER rows were
returned. Strictly earlier recorded trades/merges show positive net inventory
in the target token for 103 pairs, zero net in 107, and positive net in the
other token for 64. Every pair also has same-second activity as the sampled
target trade. Seventy-three pairs have no strictly earlier Activity row. These are
recorded-flow diagnostics only: same-second order is ambiguous, and missing
event types or starting balances mean zero is not a valid “fresh” label.

To validate holdings independently, Polygon transaction receipts were
retrieved for all 210 sampled target fills, then `balanceOf` was queried for
both Conditional Tokens outcome IDs at the end of the immediately preceding
block. These prior-block snapshots show 103 wallets with a positive target-token
balance, 64 with positive opposite-token balance, and 39 holding both. We
then applied ERC-1155 transfer logs from earlier transactions within each
target block. At the start of the sampled target transaction, 107 had a
positive target-token balance, 64 held the opposite token, and 41 held both.
The target-token balance agrees with the strict-prior Activity trade/merge net
within 1e-5 for 194/210 pairs at transaction start. This direct chain
reconstruction establishes pre-existing longshot inventory for some sampled
buyers, even where the Activity API showed no earlier record. It does not
give the exact balance immediately before a specific fill inside the target
transaction, and the sample is selected and stratified rather than
representative. The profile-stratum counts (34/42 high-activity, 21/42
low-activity/low-stake proxy, 17/42 maker-dominant, 17/42 taker-dominant, and
18/42 residual group had positive target-token inventory) are descriptive
feasibility results from the balanced sample, not population shares or a
causal comparison.

Across the original and extension samples, all 144 wallet-market histories
with a positive redemption have Activity API payout amounts that match the
corresponding Conditional Tokens `PayoutRedemption` event in the Polygon
transaction receipt within 1e-6 USDC. This independently validates the payout
field in these sampled transactions. Separately, recorded trade and merge
flows equal the claimed payout within 1e-5 in 122/144 cases. The other 22 may
include partial claims, starting
balances, transfers, or other ledger gaps; a claim need not equal the entire
position held. Thus the 122/144 comparison is not a direct balance validation.
A further receipt-level join covers two nonoverlapping hash-ranked stratified
samples totaling 556 BUY records. It uniquely matches 477 to a V1
`OrderFilled` event by wallet, target token, share quantity, and price, then
requires a unique inbound ERC-1155 transfer bundle for that token and
quantity. Of the 477, 438 use a single exact-size transfer and 39 use a 90%
transfer before the fill plus a 10% transfer afterward. Reconstructing
balances immediately before the first matched transfer finds positive
pre-existing target-token inventory in 221/477 matched records. Seventy-nine
records remain unresolved: 41 have no unique event/transfer pair and 38 are
ambiguous. The Activity API row label does not necessarily equal the maker or
taker field in the contract event; the join uses the wallet, target token,
share quantity, and price. Within the selected sample, positive pre-transfer
balances occur in 83/98 matched high-activity pairs, compared with 138/379 in
the other profile strata. High-activity balances are often material relative
to the sampled purchase: 79/98 are at least 10% of buy size, and 64/98 are at
least as large as the buy. Assigning every unresolved high-activity case to
zero and every unresolved other-profile case to positive still yields a
28.4-point lower-bound difference within this sample. This bound addresses
only join attrition, not sampling uncertainty or population prevalence; the
samples remain nonrepresentative. The observed 90%/10% split-bundle rule is
retained; other unmatched transfer behavior is not inferred.
Among the same 477 matched buys, mean `Y−P*` is −1.49 percentage points with
no observed pre-transfer balance and −1.64 points with positive inventory.
Mean `Y−price` is +0.51 and −0.55 points, respectively. These unadjusted
selected-sample means have no inferential intervals; they suggest that the
purchase-payoff contrast tracks entry prices rather than predictive
performance relative to the market-free benchmark.
The join follows the archived V1 [`OrderFilled` event definition](https://github.com/Polymarket/ctf-exchange/blob/main/src/exchange/interfaces/ITrading.sol)
and its [settlement implementation](https://github.com/Polymarket/ctf-exchange/blob/main/src/exchange/mixins/Trading.sol), plus Conditional Tokens transfer logs. The broader ledger still requires
on-chain split/merge/redemption reconstruction and validation beyond this
sample. The earlier 10-wallet, one-market 9/9 match was a small
feasibility signal, not general validation.

The exact target cohort and Activity sample are reproducible through
`make phase6-wallet-position-sample`; on-chain payout validation is
reproducible from cached receipts with `make phase6-wallet-receipt-validation`.
Historical position validation is reproducible with
`make phase6-wallet-balance-validation`; the receipt-level selected-fill
reconstruction is `make phase6-wallet-exact-fill-balance-sample`. The
nonoverlapping extension is run with `make phase6-wallet-inventory-extension-fill`,
and its combined summary with `make phase6-wallet-inventory-extension-summary`.
Key outputs are
`data/interim/phase6/polymarket_wallet_type_late5_longshot_buys.csv`,
`data/interim/phase6/polymarket_wallet_position_sample.csv`, and
`data/interim/phase6/polymarket_wallet_payout_reconciliation_sample.csv`.
The expanded exact-join sample and its per-profile attrition/inventory bounds
are in [`polymarket_wallet_inventory_extension_summary.json`](data/interim/phase6/polymarket_wallet_inventory_extension_summary.json)
and [`polymarket_wallet_inventory_extension_summary.csv`](data/interim/phase6/polymarket_wallet_inventory_extension_summary.csv).
The independent receipt comparison is in
`data/interim/phase6/polymarket_wallet_redemption_receipt_validation.csv`.
On-chain prior-block balances are in
`data/interim/phase6/polymarket_wallet_pretransaction_balances.csv`.
The payout decoder follows the Conditional Tokens contract's
[PayoutRedemption event definition](https://github.com/gnosis/conditional-tokens-contracts/blob/master/contracts/ConditionalTokens.sol).
These new findings make observable trader heterogeneity a promising
exploratory extension, but do not identify bots, retail investors, or a
mechanism explaining the Kalshi result.

### Prior purchase opportunity diagnostic

The reproducible follow-up in `src/phase6_wallet_inventory_opportunity.py`
compares transaction-start on-chain target-token balances with strictly
earlier, second-resolution Activity API BUY records for the same wallet and
token. Among matched records, high-activity accounts more often have prior
recorded buys (86/98) than the other profile strata (143/379), and correspondingly
more often have positive pretransaction inventory (83/98 versus 137/379).
Among records with prior buys, the positive-balance shares are 82/86 and
126/143; with no prior recorded buy they are 1/12 and 11/236. This makes
recorded exposure opportunity a concrete competing explanation for the
marginal profile gap, while the remaining differences and incomplete Activity
history prevent a causal or complete mediation interpretation. Transfers,
splits, same-second activity, and missing history can all create positive
balances without a recorded prior BUY. Neither this comparison nor the
inventory-conditioned outcome means identifies bot/retail status, cost basis,
loss chasing, or market impact.

The 556 matched-sample rows also do not uniformly capture each sampled
wallet-market pair's earliest target-cohort BUY: only 515/556 do. Estimating
first-entry inventory prevalence would require defining the unique target
event before sampling and redoing the receipt/balance validation at that
event. No reweighting of the current selected fills should be presented as a
population estimate.

### Time-ordered behavioral profiles

To avoid assigning an account's future full-season behavior to an earlier
purchase, `src/phase6_wallet_prior_game_profiles.py` defines each profile at
the start of the target game. It uses participant-side records timestamped
before the first ESPN play and excludes every record from that target game.
The profile unit remains wallet × target game, and the outcomes remain the
frozen final-five longshot BUY cohort. Categories are: limited observed history
(under 20 earlier records or under three earlier NBA games); high prior
activity (at least 20 records per earlier UTC active day); maker-record-
dominant (at least 75%); taker-record-dominant (at most 25%); and established
mixed. The activity category takes precedence over maker/taker dominance.
These rules describe records in the assembled NBA season and do not identify
account type.

The outcome comparisons condition on exact game, final-five minute, P* band,
and maker/taker participant role, retaining only cells with both comparison
groups. The three outcomes are price minus P*, settlement payoff minus entry
price, and settlement payoff minus P*. Standard errors use two-way clustering
by game and wallet. High activity versus other established wallets has no
detectable contrast in any of these outcomes. Maker-dominant versus
taker-dominant accounts retain a lower entry price relative to P* and a higher
purchase payoff, but no detectable difference in payoff relative to P*; this
is consistent with entry/execution differences rather than superior
prediction. Limited-history buys show a small positive price-minus-P* contrast,
but not a payoff advantage, and it should be treated cautiously given the
exploratory comparisons. None of these estimates is a price-impact effect or
wallet P&L.

The thresholds were not preregistered. Treat the current results as
exploratory, preserve the exact rules for transparency, and freeze them before
any next-season confirmatory sample. Reproduce with
`make phase6-wallet-prior-game-profiles`; machine-readable outputs are under
`data/interim/phase6/prior_game_behavior/`.

One-at-a-time sensitivity checks vary the minimum-history, activity-rate, and
maker/taker-share cutoffs. The high-activity outcome contrasts stay close to
zero; the maker/taker entry-price gap remains negative, while benchmark-
relative realized outcomes remain indistinguishable; the limited-history
price-minus-benchmark gap remains small and is not accompanied by a
benchmark-relative payoff difference. The sensitivity intervals are
exploratory and unadjusted for multiple comparisons. Reproduce with
`make phase6-wallet-prior-profile-sensitivity`.

## Profile-flow predictive test (2026-10-23)

Using 2025–26 Polymarket taker fills, I tested whether profile-specific signed
flow in the final five regulation minutes predicts the next consecutive
30-, 60-, or 120-second game-clock-bin change in the last-trade price minus
P*. The panel has 160,100 fills, 763 games, and 25,858 wallets. The model
adjusts for initial price-minus-P*, P* movement, game fixed effects, and
within-window-bin fixed effects, with uncertainty clustered by game.

The profile-flow shares sum to one in each bin, so limited-prior-history flow
is omitted as the reference category. None of the four other profile-flow
coefficients differs detectably from zero at any horizon. Main-benchmark joint
tests have p=.662, .721, and .933 at 30, 60, and 120 seconds. Across the three
P* specifications, all 36 individual profile-flow intervals include zero and
all Holm-adjusted p-values are 1.00; none of the nine joint benchmark-by-
horizon tests is significant after correction. This is no evidence that any
profile's flow predicts next-bin divergence in this specification, though it
does not establish that effects are exactly zero.

An earlier version included all five profile-flow shares, causing exact
compositional collinearity with the intercept and fixed effects. Its apparent
limited-history short-horizon signal is superseded by the corrected reference-
category specification. Reproduce with `make phase6-taker-flow-impact`.
This remains a same-season exploratory predictive association: fills are
endogenous, marks are last trades rather than midpoints, P* is estimated,
game-clock bins vary in wall-clock duration, and the data cannot attribute the
Kalshi result or identify accounts as bots, retail traders, or professionals.

## Additive profile accounting of the selected gap (2026-10-23)

The 137,343 final-five 5–20¢ longshot BUY records were decomposed using five
time-indexed prior-game behavior profiles. For each game and profile, the
profile's weighted sum of `price−outcome` was divided by the full game's
weight; these contributions add exactly to the within-game total. We report
trade-count, token-share, and dollar-notional weights, both pooled and with
games weighted equally. A 2,000-draw two-way pigeonhole bootstrap resamples
games and wallets independently and multiplies their row multiplicities.
Profile-component intervals are exploratory and are not multiplicity-adjusted
across the multiple outcomes and weighting schemes.
The unit is a participant-side Activity API BUY record rather than a unique
matched market transaction; one taker transaction can map to multiple maker
fill records.

The equal-game trade-count gap is +2.72 pp (95% CI +0.83 to +4.67). High-prior-
activity accounts contribute +1.75 pp (64.3%; CI +0.31 to +3.22), while their
own group gap is +2.62 pp. Their 74.3% record share explains why their
accounting component is largest; this is not evidence their behavior caused
the gap. Under equal-game share weighting, their component is +1.59 pp (CI
−0.02 to +3.19); under pooled share weighting, their own group gap is −0.17
pp and their contribution is −0.14 pp. The pooled share-weighted total is
only +0.21 pp (CI −4.98 to +4.11). Equal-game dollar-notional weighting gives
+3.11 pp total, with +2.28 pp (73.2%; CI +0.63 to +3.89) from high-activity
accounts; the pooled dollar-notional estimate is +0.11 pp (CI −5.59 to +4.52).
Conclusions depend on weighting: high activity accounts for most
of the equal-game gap because it dominates activity, but its own gap is not
unusually large, and the pooled volume-weighted result is near zero.

Interpretation: descriptive accounting within a selected longshot-buyer
cohort, not a causal decomposition of the market price or proof that profile
types caused mispricing. The result uses realized single-season payoffs, an
estimated P* selection rule, and behavior-proxy profiles. No historical
2025–26 midpoint quotes or Kalshi wallet identifiers are assembled in this
panel. Reproduce with `make phase6-wallet-gap-decomposition`; outputs are in
`data/interim/phase6/prior_game_behavior/gap_decomposition/`.

### Transaction cadence and ticket-size profiles

The follow-up directly operationalizes the proposed “bot-like” versus
“fewer, larger trades” distinction without claiming to observe account
identity. `src/phase6_wallet_execution_style.py` collapses participant fill
rows to a unique wallet × transaction hash × game event before computing
distinct transactions per active day, within-day transaction gaps, and median
transaction notional. Each wallet's features are frozen before the target
game's first ESPN play, with all target-game events excluded. This reduces the
risk that one on-chain execution split across many maker fills is mistakenly
counted as many rapid trades.

The descriptive “rapid-cycle proxy” requires at least 20 prior transactions
per active day and a median within-day gap no longer than 30 seconds. The
“large-ticket/low-frequency proxy” requires a median transaction notional of
at least $100 and no more than five transactions per active day, after the
rapid-cycle rule. In the selected longshot-buy cohort, rapid-cycle accounts
contribute 67.5% of buy records (92,719/137,343; 965 wallets). Across their
13,077 wallet-game histories, median cadence is 225.8 transactions per active
day and median within-day gap is 8 seconds. Their own equal-game
record-weighted price-minus-payoff gap is +2.62 pp, versus +3.65 pp
for other adequately observed styles. Their additive contribution is +1.54 pp
(95% exploratory two-way bootstrap CI +0.23 to +2.89) of the +2.72 pp total.
This is an accounting result: the rapid-cycle group dominates the sample
volume, but does not exhibit a larger own-group gap than the other-style
group.

The large-ticket/low-frequency group contains only 336 selected buy records
and 162 wallets under the $100/five-per-day rule. It cannot support a precise
account-style conclusion. In threshold checks, the wallet-game pair count
ranges from 979 at a $25 ticket threshold to 278 at $100 and 46 at $500 (all
using the five-per-day rule). Rapid-cycle pair counts also change materially
with cadence and gap cutoffs; the full grid is
`execution_style_threshold_sensitivity.csv`.

To reduce reliance on these cutoffs, the analysis compares highest versus
lowest quartiles of prior cadence and median ticket size within matched game ×
minute × P* band × participant role cells. The cadence contrast in
price-minus-payoff is −0.03 pp (95% CI −0.22 to +0.16); the ticket-size
contrast is +0.03 pp (95% CI −0.17 to +0.23). Both include zero. Thus the
available data show that rapid-cycle proxies account for much of the
selected-buyer accounting gap because they are numerous, but do not show that
high-cadence or high-ticket accounts have a distinct conditional realized
overpayment. Neither proxy verifies bots, retail status, professional status,
causality, or price impact. These are exploratory comparisons without a
multiplicity adjustment. Reproduce with `make
phase6-wallet-execution-style-analysis` and `make
phase6-wallet-execution-style-decomposition`.
Polymarket's public API documents current order-book reads and bucketed
historical prices, with finer retained history limited to 7–90 days by
resolution ([API documentation](https://docs.polymarket.com/market-data/prices-order-books)).
A third-party vendor advertises full L2 history from August 2025 at one-minute
resolution, potentially covering this season, but NBA-market coverage,
completeness, timestamp semantics, and licensing have not been audited
([coverage](https://www.polymarketdata.co/polymarket-order-book-data),
[pricing](https://www.polymarketdata.co/pricing)).
The vendor says it offers specialized academic access, but the discount amount
is not public ([academic research page](https://www.polymarketdata.co/polymarket-academic-research-data)).
