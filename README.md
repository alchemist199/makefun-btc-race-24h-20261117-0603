# makefun-btc-race-24h-20261117-0603

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/alchemist199/makefun-btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/alchemist199/makefun-btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

Dip mean-reversion BTC trading bot: buys CBBTC when it closes more than 0.5% below its 90-bar average and turns up, sells at a +2.0% take-profit or 300 bars later. Dev window net PnL +$32.15.

## Run it

```sh
python3 main.py
```

The bot speaks `agent-fun/bars-replay/v1` on stdin/stdout (a small run loop at the bottom of `main.py`, standard library only). The grader runs it as `python3 -P -s /bot/main.py` with `PYTHONHASHSEED=0`.

## Strategy

Long only, full size (one position, 100% of equity), one entry signal:

- **Entry (when flat):** close more than 0.5% below its 90-bar simple average AND above the close 12 bars ago — buys pullbacks and local bottoms, not falling knives. The 90-bar average fits this flat window: price never strays more than ~1.1% below any moving average, so the deep-washout triggers of the last race (1.8–2.2% below SMA90/120) can never fire here, and the 60-bar rule of round 1 fires too early into the slow drift.
- **Exit (when holding):** sell everything at +2.0% take-profit, fallback sell 300 bars after entry, stop-loss −1.5% from cost (never triggered on the dev window; live-race insurance against a dip that keeps falling). The take-profit is what makes the third leg possible: without it the fixed 300-bar hold leaves the bot holding through the last dip.
- **Late-entry guard:** no new position in the final 120 bars of the 1,440-bar window — an entry that late cannot reach its take-profit (the window's quickest dip-to-+2% leg took 133 bars) or its 300-bar hold before the forced sale at the close, so it would most likely be sold at a small loss after the ~26 bps round-trip cost. Never triggers on the dev window (last entry at bar 1111), so the dev result below is unchanged.
- Orders cap slippage at 100 bps from the latest close, as the kit baselines do. No clock, no randomness, no network: two runs on the same bars give the same orders.

## Dev window results (new window, 1,440 bars, BTC +0.49%, 2026-11-16 13:03 → 2026-11-17 13:03 WIB)

| Metric | Value |
|---|---|
| Net PnL | **+$32.15** |
| Trades | 6 (3 round trips) |
| Fees | $2.45 |
| Max drawdown | −0.75% |
| First half / second half | +$17.83 / +$15.53 |
| Buy-and-hold / hold-cash | +$1.07 / $0.00 |
| HOLD=177 baseline / original HOLD=180 | −$2.06 / −$9.32 |

The three round trips: dip buy $64,112 → sell $65,282 (+$17.83, take-profit); dip buy $64,328 → sell $65,055 (+$11.08, 300-bar hold); dip buy $64,584 → sell $64,890 (+$4.46, 300-bar hold). Every ±20% perturbation of every parameter stays positive (worst +$17.10: take-profit x1.2). The window is flat and choppy — no swing bigger than +2.48% trough-to-peak — so +$32.15 is close to the ceiling: the three legs net about +$22 / +$17 / +$9 before costs, and ~2,500 tuning evals (dip grids, take-profit, trailing exits, two-arm variants, momentum, entry filters) found nothing above it.

## Validation

- Wire test of this exact file on the dev window: 1,440/1,440 replies, exit 0, final cash $1,032.1465 (== simulator), two runs byte-identical (deterministic).
- Simulator calibration: the same simulator reproduces round 1's official server grade exactly (+$24.6078, 6 trades) on the previous race's window before any tuning here.
