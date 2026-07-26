"""
USD news-straddle bot for GLD on Alpaca (paper).

Modes (config.STRATEGY_MODE):
  breakout_straddle  -> the MARKET picks the side. Just before the release the
                        bot records a baseline GLD price, then watches live:
                        break UP  past +BREAKOUT_TRIGGER_PCT  -> go long
                        break DOWN past -BREAKOUT_TRIGGER_PCT -> go short
                        Then it manages a take-profit / stop-loss / time exit.
  directional / bracket_straddle -> always take config.BIAS_SIDE (legacy).

Run:  python bot.py            (respects DRY_RUN)
      python bot.py --today    (only today's events, then exit; used by cloud)
      python bot.py --list     (print this week's events, no trading)

SAFETY: high-risk news trading. Paper only until you've watched a full cycle.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

import pytz

import config
import calendar_feed
from calendar_feed import Event

MARKET_TZ = pytz.timezone(config.MARKET_TZ)


def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).astimezone(MARKET_TZ)
    print(f"{ts:%Y-%m-%d %H:%M:%S %Z}  {msg}", flush=True)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------- session help
def is_regular_hours(when_utc: dt.datetime) -> bool:
    et = when_utc.astimezone(MARKET_TZ)
    if et.weekday() >= 5:
        return False
    open_t = et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = et.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= et <= close_t


def is_extended_hours(when_utc: dt.datetime) -> bool:
    et = when_utc.astimezone(MARKET_TZ)
    if et.weekday() >= 5:
        return False
    pre = et.replace(hour=4, minute=0, second=0, microsecond=0)
    ro = et.replace(hour=9, minute=30, second=0, microsecond=0)
    rc = et.replace(hour=16, minute=0, second=0, microsecond=0)
    post = et.replace(hour=20, minute=0, second=0, microsecond=0)
    return (pre <= et < ro) or (rc < et <= post)


def _sleep_until(target_utc: dt.datetime) -> None:
    while True:
        remaining = (target_utc - now_utc()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


# --------------------------------------------------------- planning / listing
def build_plan(events):
    plan = []
    for ev in events:
        plan.append({
            "event": ev,
            "arm_at": ev.when - dt.timedelta(minutes=config.ENTRY_LEAD_MINUTES),
            "flatten_at": ev.when + dt.timedelta(minutes=config.FLATTEN_AFTER_MINUTES),
        })
    return plan


def print_plan(plan) -> None:
    if not plan:
        log("No matching USD red-folder events.")
        return
    log(f"Scheduled {len(plan)} event(s):")
    for item in plan:
        ev = item["event"]
        arm_et = item["arm_at"].astimezone(MARKET_TZ)
        sess = ("regular" if is_regular_hours(item["arm_at"])
                else "extended" if is_extended_hours(item["arm_at"]) else "CLOSED")
        log(f"  - {ev.title:32s} release {ev.when.astimezone(MARKET_TZ):%a %m-%d %H:%M %Z} "
            f"| arm {arm_et:%H:%M} ({sess}) | fc={ev.forecast or '-'} prev={ev.previous or '-'}")


def _todays_events(events):
    today_et = now_utc().astimezone(MARKET_TZ).date()
    return [e for e in events if e.when.astimezone(MARKET_TZ).date() == today_et]


# ------------------------------------------------------------- BREAKOUT FLOW
def manage_breakout_event(broker, event: Event) -> None:
    """
    Blocking, per-event: wait to arm, record baseline, watch for a break,
    enter the side that breaks, then manage take-profit / stop-loss / time exit.
    """
    sym = config.SYMBOL
    arm_at = event.when - dt.timedelta(minutes=config.ENTRY_LEAD_MINUTES)
    watch_deadline = event.when + dt.timedelta(minutes=config.BREAKOUT_WATCH_MINUTES)
    flat_deadline = event.when + dt.timedelta(minutes=config.FLATTEN_AFTER_MINUTES)
    trig = config.BREAKOUT_TRIGGER_PCT

    log(f">>> Arming breakout for '{event.title}' (release "
        f"{event.when.astimezone(MARKET_TZ):%H:%M %Z})")
    _sleep_until(arm_at)

    if config.DRY_RUN or broker is None:
        log(f"DRY_RUN: would record GLD baseline now and watch for a "
            f"±{trig*100:.2f}% break, then trade ~${config.NOTIONAL_PER_TRADE:.0f} "
            f"the breakout direction for '{event.title}'")
        return

    baseline = broker.last_price(sym)
    upper = round(baseline * (1 + trig), 2)
    lower = round(baseline * (1 - trig), 2)
    log(f"Baseline {sym}={baseline:.2f} | long if >= {upper} | short if <= {lower}")

    # --- watch for a break ---------------------------------------------------
    side = None
    while now_utc() < watch_deadline:
        px = broker.last_price(sym)
        if px >= upper:
            side = "buy"
            break
        if px <= lower:
            side = "sell"
            break
        time.sleep(config.BREAKOUT_POLL_SECONDS)

    if side is None:
        log(f"No ±{trig*100:.2f}% break within {config.BREAKOUT_WATCH_MINUTES} min "
            f"for '{event.title}'. No trade.")
        return

    # --- enter the breakout direction ---------------------------------------
    qty = broker.qty_for_notional(sym, config.NOTIONAL_PER_TRADE)
    regular = is_regular_hours(now_utc())
    broker.simple_entry(sym, side, qty, regular)
    time.sleep(2)
    entry_px = broker.avg_entry_price(sym) or broker.last_price(sym)
    log(f"ENTERED {side.upper()} {qty} {sym} @ ~{entry_px:.2f} "
        f"({'regular' if regular else 'extended'} hours) on breakout")

    # --- manage exit: take-profit / stop-loss / hard time exit --------------
    if side == "buy":
        tp = entry_px * (1 + config.TAKE_PROFIT_PCT)
        sl = entry_px * (1 - config.STOP_LOSS_PCT)
    else:
        tp = entry_px * (1 - config.TAKE_PROFIT_PCT)
        sl = entry_px * (1 + config.STOP_LOSS_PCT)
    log(f"Exit targets -> TP={tp:.2f} SL={sl:.2f} time={flat_deadline.astimezone(MARKET_TZ):%H:%M %Z}")

    reason = "time"
    while now_utc() < flat_deadline:
        px = broker.last_price(sym)
        if side == "buy" and (px >= tp or px <= sl):
            reason = "take-profit" if px >= tp else "stop-loss"
            break
        if side == "sell" and (px <= tp or px >= sl):
            reason = "take-profit" if px <= tp else "stop-loss"
            break
        time.sleep(config.BREAKOUT_POLL_SECONDS)

    broker.cancel_open_orders(sym)
    broker.flatten(sym)
    log(f"FLATTENED {sym} after '{event.title}' (exit: {reason})")


# ---------------------------------------------- LEGACY DIRECTIONAL FLOW
def manage_directional_event(broker, event: Event) -> None:
    sym = config.SYMBOL
    side = config.BIAS_SIDE
    arm_at = event.when - dt.timedelta(minutes=config.ENTRY_LEAD_MINUTES)
    flat_deadline = event.when + dt.timedelta(minutes=config.FLATTEN_AFTER_MINUTES)

    log(f">>> Directional entry for '{event.title}' side={side}")
    _sleep_until(arm_at)
    if config.DRY_RUN or broker is None:
        log(f"DRY_RUN: would take {side.upper()} {sym} (~${config.NOTIONAL_PER_TRADE:.0f}) "
            f"for '{event.title}'")
        return
    qty = broker.qty_for_notional(sym, config.NOTIONAL_PER_TRADE)
    regular = is_regular_hours(now_utc())
    if regular:
        broker.bracket_market(sym, side, qty, config.TAKE_PROFIT_PCT, config.STOP_LOSS_PCT)
    else:
        broker.extended_hours_limit(sym, side, qty)
    log(f"ENTERED {side.upper()} {qty} {sym} for '{event.title}'")
    _sleep_until(flat_deadline)
    broker.cancel_open_orders(sym)
    broker.flatten(sym)
    log(f"FLATTENED {sym} after '{event.title}'")


# ------------------------------------------------------------------------ run
def run(list_only: bool = False, today_only: bool = False) -> None:
    log(f"Bot start | symbol={config.SYMBOL} mode={config.STRATEGY_MODE} "
        f"DRY_RUN={config.DRY_RUN} PAPER={config.ALPACA_PAPER} today_only={today_only}")

    events = calendar_feed.fetch_events()
    if today_only:
        events = _todays_events(events)
    plan = build_plan(events)
    print_plan(plan)
    if list_only:
        return

    broker = None
    if not config.DRY_RUN:
        from alpaca_client import Broker
        broker = Broker()
        acct = broker.account_summary()
        log(f"Alpaca account: status={acct['status']} equity=${acct['equity']:.0f} "
            f"buying_power=${acct['buying_power']:.0f}")
        if str(acct["status"]) not in ("ACTIVE", "AccountStatus.ACTIVE"):
            log("Account not ACTIVE — aborting.")
            return

    handler = (manage_breakout_event
               if config.STRATEGY_MODE == "breakout_straddle"
               else manage_directional_event)

    for item in plan:
        ev = item["event"]
        if config.SKIP_FOMC and ev.is_fomc:
            log(f"Skipping FOMC '{ev.title}' (SKIP_FOMC=True)")
            continue
        # if this event's flatten time already passed, skip it
        if now_utc() >= item["flatten_at"]:
            log(f"Skipping past event '{ev.title}'")
            continue
        try:
            handler(broker, ev)
        except Exception as e:  # never let one event kill the whole run
            log(f"ERROR handling '{ev.title}': {e}")
            if broker is not None:
                try:
                    broker.cancel_open_orders(config.SYMBOL)
                    broker.flatten(config.SYMBOL)
                except Exception:
                    pass

    log("All events processed. Exiting.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="USD news breakout-straddle bot for GLD on Alpaca")
    ap.add_argument("--list", action="store_true", help="print events and exit")
    ap.add_argument("--today", action="store_true", help="only handle today's events, then exit")
    args = ap.parse_args()
    try:
        run(list_only=args.list, today_only=args.today)
    except KeyboardInterrupt:
        log("Interrupted by user. Bye.")
        sys.exit(0)
