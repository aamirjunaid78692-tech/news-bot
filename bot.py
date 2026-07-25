"""
USD news-straddle bot for GLD on Alpaca (paper).

Flow
----
1. Pull this week's high-impact USD red-folder events from ForexFactory.
2. For each event, schedule an ENTRY at (release - ENTRY_LEAD_MINUTES) and a
   FLATTEN at (release + FLATTEN_AFTER_MINUTES).
3. At entry time:
     - inside regular hours (09:30-16:00 ET, e.g. the 14:00 FOMC) -> bracket
       market order with TP/SL.
     - in pre-/post-market (e.g. the 08:30 prints) -> extended-hours
       marketable-limit order (no bracket allowed there), risk handled by the
       time-based flatten.
4. At flatten time, close the position and cancel any leftover orders.

Run:  python bot.py            (respects DRY_RUN in config.py)
Test: python bot.py --list     (just print the scheduled events, no trading)

SAFETY: keep DRY_RUN=True and ALPACA_PAPER=True until you have watched it run
through a full event cycle. See STRATEGY.md section 5.
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


# --------------------------------------------------------------------- logging
def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).astimezone(MARKET_TZ)
    print(f"{ts:%Y-%m-%d %H:%M:%S %Z}  {msg}", flush=True)


# ---------------------------------------------------------------- session help
def is_regular_hours(when_utc: dt.datetime) -> bool:
    """True if `when` falls inside 09:30-16:00 ET on a weekday."""
    et = when_utc.astimezone(MARKET_TZ)
    if et.weekday() >= 5:                      # Sat/Sun
        return False
    open_t = et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = et.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= et <= close_t


def is_extended_hours(when_utc: dt.datetime) -> bool:
    """True if `when` falls inside 04:00-09:30 or 16:00-20:00 ET on a weekday."""
    et = when_utc.astimezone(MARKET_TZ)
    if et.weekday() >= 5:
        return False
    pre_open = et.replace(hour=4, minute=0, second=0, microsecond=0)
    reg_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
    reg_close = et.replace(hour=16, minute=0, second=0, microsecond=0)
    post_close = et.replace(hour=20, minute=0, second=0, microsecond=0)
    return (pre_open <= et < reg_open) or (reg_close < et <= post_close)


# ------------------------------------------------------------------- the trade
def enter_trade(broker, event: Event) -> dict | None:
    entry_time = dt.datetime.now(dt.timezone.utc)
    side = config.BIAS_SIDE

    if config.DRY_RUN or broker is None:
        log(f"DRY_RUN: would enter {side.upper()} {config.SYMBOL} "
            f"(~${config.NOTIONAL_PER_TRADE:.0f}) for '{event.title}'")
        return {"dry_run": True}

    qty = broker.qty_for_notional(config.SYMBOL, config.NOTIONAL_PER_TRADE)

    if is_regular_hours(entry_time):
        res = broker.bracket_market(
            config.SYMBOL, side, qty,
            config.TAKE_PROFIT_PCT, config.STOP_LOSS_PCT,
        )
        log(f"ENTERED (regular-hours bracket) {side.upper()} {qty} {config.SYMBOL} "
            f"entry~{res['entry']:.2f} TP={res['tp']} SL={res['sl']} id={res['id']}")
    elif is_extended_hours(entry_time):
        res = broker.extended_hours_limit(config.SYMBOL, side, qty)
        log(f"ENTERED (extended-hours limit) {side.upper()} {qty} {config.SYMBOL} "
            f"limit={res['limit']} id={res['id']} "
            f"(no bracket in ext-hours; time-exit protects)")
    else:
        log(f"SKIP '{event.title}': market fully closed at entry time "
            f"{entry_time.astimezone(MARKET_TZ):%H:%M %Z}")
        return None
    return res


def flatten_trade(broker, event: Event) -> None:
    if config.DRY_RUN or broker is None:
        log(f"DRY_RUN: would flatten {config.SYMBOL} after '{event.title}'")
        return
    broker.cancel_open_orders(config.SYMBOL)
    oid = broker.flatten(config.SYMBOL)
    if oid:
        log(f"FLATTENED {config.SYMBOL} after '{event.title}' close_id={oid}")
    else:
        log(f"No open {config.SYMBOL} position to flatten after '{event.title}'")


# --------------------------------------------------------------------- planner
def build_plan(events: list[Event]) -> list[dict]:
    plan = []
    for ev in events:
        plan.append({
            "event": ev,
            "entry_at": ev.when - dt.timedelta(minutes=config.ENTRY_LEAD_MINUTES),
            "flatten_at": ev.when + dt.timedelta(minutes=config.FLATTEN_AFTER_MINUTES),
            "entered": False,
            "flattened": False,
        })
    return plan


def print_plan(plan: list[dict]) -> None:
    if not plan:
        log("No matching USD red-folder events this week.")
        return
    log(f"Scheduled {len(plan)} event(s):")
    for item in plan:
        ev = item["event"]
        entry_et = item["entry_at"].astimezone(MARKET_TZ)
        sess = ("regular" if is_regular_hours(item["entry_at"])
                else "extended" if is_extended_hours(item["entry_at"])
                else "CLOSED")
        log(f"  - {ev.title:32s} release {ev.when.astimezone(MARKET_TZ):%a %m-%d %H:%M %Z} "
            f"| entry {entry_et:%H:%M} ({sess}) | fc={ev.forecast or '-'} prev={ev.previous or '-'}")


# ------------------------------------------------------------------------ loop
def _todays_events(events: list[Event]) -> list[Event]:
    """Keep only events whose release date is today in US-Eastern time."""
    today_et = dt.datetime.now(dt.timezone.utc).astimezone(MARKET_TZ).date()
    return [e for e in events if e.when.astimezone(MARKET_TZ).date() == today_et]


def run(list_only: bool = False, today_only: bool = False) -> None:
    log(f"Bot start | symbol={config.SYMBOL} mode={config.STRATEGY_MODE} "
        f"bias={config.BIAS_SIDE} DRY_RUN={config.DRY_RUN} PAPER={config.ALPACA_PAPER} "
        f"today_only={today_only}")

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
        if acct["status"] != "ACTIVE":
            log("Account not ACTIVE — aborting.")
            return

    log("Entering scheduler loop. Ctrl-C to stop.")
    while True:
        now = dt.datetime.now(dt.timezone.utc)

        pending = [p for p in plan if not p["flattened"]]
        if not pending:
            log("All events processed. Exiting.")
            return

        for item in plan:
            ev = item["event"]
            if not item["entered"] and now >= item["entry_at"]:
                if now <= ev.when + dt.timedelta(minutes=config.FLATTEN_AFTER_MINUTES):
                    log(f">>> ENTRY window for '{ev.title}' (release {ev.when.astimezone(MARKET_TZ):%H:%M %Z})")
                    enter_trade(broker, ev)
                item["entered"] = True

            if item["entered"] and not item["flattened"] and now >= item["flatten_at"]:
                log(f">>> EXIT window for '{ev.title}'")
                flatten_trade(broker, ev)
                item["flattened"] = True

        time.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="USD news-straddle bot for GLD on Alpaca")
    ap.add_argument("--list", action="store_true",
                    help="print the week's scheduled events and exit (no trading)")
    ap.add_argument("--today", action="store_true",
                    help="only handle events that occur TODAY, then exit "
                         "(use this for the daily auto-start job)")
    args = ap.parse_args()
    try:
        run(list_only=args.list, today_only=args.today)
    except KeyboardInterrupt:
        log("Interrupted by user. Bye.")
        sys.exit(0)
