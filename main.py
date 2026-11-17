#!/usr/bin/env python3
"""BTC race bot for btc-race-24h-20261117-0603: dip mean reversion.

Strategy (all decisions on 1-minute closes of CBBTC, long only, full size,
one position at a time):
  ENTRY (when flat): buy when the close is more than 0.5% below its
    90-bar simple average AND above the close 12 bars ago. The 90-bar
    average fits this window: the price never strays more than ~1.1%
    below any moving average, so the deep-washout triggers of the last
    race (1.8-2.2% below SMA90/120) can never fire here, and the
    60-bar rule of round 1 fires too early into the slow drift. The
    turn check (above the close 12 bars ago) keeps entries out of
    falling knives: it buys local bottoms, not the slide down to them.
    No new position is opened in the final 120 bars of the 1,440-bar
    window: an entry that late cannot reach its take-profit (the
    window's quickest dip-to-+2% leg took 133 bars) or its 300-bar
    hold before the forced sale at the close, so it would most likely
    be sold at a small loss after the ~26 bps round-trip cost.
  EXIT (when holding): sell everything at +2.0% take-profit (rides the
    rebound to near its peak, then frees the one position slot for the
    next dip), fallback sell 300 bars after entry, stop-loss -1.5% from
    cost (never triggered on the dev window; live-race insurance
    against a dip that keeps falling).
  Sizing: every buy spends all cash (one position, max 100% of equity).
  Orders cap slippage at 100 bps from the latest close, as the kit
  baselines do. No clock, no randomness, no network: two runs on the
  same bars give the same orders. Standard library only.

Why this shape: the dev window (24h, BTC +0.49%, open $64,461.04 ->
close $64,775.95) is flat and choppy — no swing bigger than +2.48%
trough-to-peak and no 0.5% reversal in the zigzag. The only tradeable
moves are three slow dip-to-rally legs (low bar 386 $63,874 -> peak
bar 514 $65,456, +2.48%; low bar 609 $64,215 -> peak bar 967 $65,467,
+1.95%; low bar 1228 $64,356 -> peak bar 1293 $65,082, +1.13%), and
this bot catches one round trip per leg. A take-profit exit is what
makes the third leg possible: without it the fixed 300-bar hold
leaves the bot holding through the 1228 low. Dev window net PnL
+$32.15 in the validated simulator (fill model matched the official
server grade exactly on round 1's code path: +$24.6078), 6 trades
(3 round trips), max drawdown -0.75%, fees $2.45. First half +$17.83,
second half +$15.53. Every +-20% perturbation of every parameter
stays positive (worst +$17.10: take-profit x1.2). Baselines on the
same window: buy-and-hold +$1.07, hold-cash $0.00, HOLD=177 -$2.06
(the old fallback FAILS the dev gate here), original HOLD=180 -$9.32.

Wire protocol: the bot speaks agent-fun/bars-replay/v1 directly (the
small run loop at the bottom of this file, standard library only): one
JSON line in per batch, exactly one reply out echoing its seq. Orders
decided on a batch fill at the next bar's open.
"""

import json
import sys

SYMBOL = "CBBTC"
PROTOCOL = "agent-fun/bars-replay/v1"
MAX_SLIPPAGE_BPS = 100

# Parameters (see module docstring for why each is what it is).
DIP_N = 90          # dip reference: simple average of this many closes
DIP_PCT = 0.005     # close must be 0.5% below that average
DIP_TURN = 12       # ... and above the close this many bars ago
HOLD = 300          # fallback: sell this many bars after entry
TP = 0.02           # take profit: sell at +2.0% over cost
SL = 0.015          # stop loss: sell at -1.5% under cost (live insurance)
WINDOW_BARS = 1440  # dev and race windows are both 1,440 one-minute bars
MIN_BARS_LEFT = 120  # do not open a new position with fewer bars left

closes = []         # CBBTC closes, in arrival order (ints, price_scale 5)
entry_seq = -1      # seq of the batch the current position was entered on


class State:
    """What the bot knows, current before each batch is answered."""

    def __init__(self, hello):
        self.seq = -1
        units = hello["capital"]["quote_units"]
        self.cash = int(units)
        self.equity = int(units)
        self.positions = {}     # symbol -> (qty, cost_quote_units)
        self.warming_up = False  # this kit opens with no warm-up batches

    def apply_batch(self, batch):
        self.seq = batch["seq"]
        account = batch["account"]
        self.cash = int(account["cash_quote_units"])
        self.equity = int(account["equity_quote_units"])
        self.positions = {p["symbol"]: (int(p["qty"]), int(p["cost_quote_units"]))
                          for p in account["positions"]}


def on_batch(state, batch):
    global entry_seq
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            closes.append(int(bar["c"]))
    if state.warming_up:
        return []

    held = state.positions.get(SYMBOL)
    if held is not None:
        qty, cost = held
        c = closes[-1]
        value = qty * c // 10**7
        if value <= cost * (1 - SL):
            entry_seq = -1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        if value >= cost * (1 + TP):
            entry_seq = -1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        if state.seq - entry_seq >= HOLD:
            entry_seq = -1
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Flat: dip entry. Need enough history for the signal.
    if not closes:
        return []
    # Late-entry guard: with fewer than MIN_BARS_LEFT bars to the
    # forced sale at the close, a new position cannot reach its
    # take-profit or its hold before the window ends.
    if state.seq >= WINDOW_BARS - MIN_BARS_LEFT:
        return []
    c = closes[-1]
    if len(closes) > DIP_N and len(closes) > DIP_TURN:
        avg = sum(closes[-DIP_N:]) / DIP_N
        if c < avg * (1 - DIP_PCT) and c > closes[-DIP_TURN - 1]:
            if state.cash >= 1_000_000:
                entry_seq = state.seq
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


def run():
    """Speak agent-fun/bars-replay/v1 until done, then exit 0."""
    state = None
    next_id = 1
    out = sys.stdout
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        kind = msg.get("type")
        if kind == "hello":
            if msg.get("protocol") != PROTOCOL:
                raise SystemExit("wrong protocol: %r" % msg.get("protocol"))
            state = State(msg)
        elif kind == "batch":
            state.apply_batch(msg)
            orders = []
            for o in on_batch(state, msg) or []:
                cid = "o%d" % next_id
                next_id += 1
                if o["side"] == "buy":
                    orders.append({"side": "buy", "client_id": cid,
                                   "symbol": o["symbol"],
                                   "notional_quote_units": str(o["notional_quote_units"]),
                                   "max_slippage_bps": o["max_slippage_bps"]})
                else:
                    orders.append({"side": "sell", "client_id": cid,
                                   "symbol": o["symbol"],
                                   "qty": str(o["qty"]),
                                   "max_slippage_bps": o["max_slippage_bps"]})
            out.write(json.dumps({"type": "reply", "seq": msg["seq"],
                                  "orders": orders}, separators=(",", ":")) + "\n")
            out.flush()
        elif kind == "done":
            return
        else:
            raise SystemExit("unknown message type: %r" % kind)
    raise SystemExit("input ended before done")


run()
