"""
Central configuration for the USD news-straddle bot.

All tunables live here. Edit these, not the logic in the other modules.
"""
import os
from dotenv import load_dotenv

# Load credentials from whichever file exists: ".env" (preferred) or "env.txt"
# (fallback, so you don't have to rename a dot-file on Windows/Mac).
if os.path.exists(".env"):
    load_dotenv(".env")
elif os.path.exists("env.txt"):
    load_dotenv("env.txt")
else:
    load_dotenv()  # search default locations

# ----------------------------------------------------------------------------
# Alpaca credentials (paper by default)
# ----------------------------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True").lower() in ("true", "1", "yes")

# ----------------------------------------------------------------------------
# Instrument
# ----------------------------------------------------------------------------
# Alpaca does NOT trade forex. GLD is our USD-direction proxy (gold ETF).
SYMBOL = "GLD"

# ----------------------------------------------------------------------------
# Which events to trade
# ----------------------------------------------------------------------------
# ForexFactory weekly JSON feed. Public, refreshed weekly.
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Only trade these currencies and impact levels ("red folder" == High).
TRADE_CURRENCY = "USD"
# Impact levels to trade. Claims/PMI can be Medium (orange) on ForexFactory,
# so we accept High AND Medium; the EVENT_KEYWORDS list below still narrows it.
TRADE_IMPACT = ("High", "Medium")   # ForexFactory labels: High | Medium | Low | Holiday

# Restrict to specific event-title keywords. Empty list = all matching impact.
EVENT_KEYWORDS = [
    "FOMC",                          # Rate decision / statement / press conf
    "CPI",                           # Consumer Price Index (inflation)
    "Non-Farm Employment Change",    # NFP (monthly jobs)
    "PMI",                           # ISM / Flash Manufacturing & Services PMI
    "Unemployment Claims",           # weekly jobless claims (often Medium impact)
]
# Set to True to trade ANY High-impact USD event, ignoring EVENT_KEYWORDS.
TRADE_ALL_HIGH_IMPACT = False

# ----------------------------------------------------------------------------
# Timing
# ----------------------------------------------------------------------------
ENTRY_LEAD_MINUTES = 2          # enter this many minutes BEFORE the release
FLATTEN_AFTER_MINUTES = 15      # hard time-exit this many minutes AFTER release
POLL_SECONDS = 20               # scheduler tick

# ----------------------------------------------------------------------------
# Strategy mode
# ----------------------------------------------------------------------------
# "breakout_straddle" -> the MARKET picks the side. The bot records a baseline
#                        price just before the release, then watches live: if
#                        price breaks UP past +BREAKOUT_TRIGGER_PCT it goes long,
#                        if it breaks DOWN it goes short. Whichever way the news
#                        pushes gold, the bot follows. (Software breakout, so it
#                        works pre-market too, where Alpaca blocks stop orders.)
# "directional"       -> ignore the price move, always take BIAS_SIDE.
# "bracket_straddle"  -> take BIAS_SIDE, risk-defined with a bracket.
STRATEGY_MODE = "breakout_straddle"

# Only used by "directional" / "bracket_straddle" modes.
# "buy" = long GLD, "sell" = short GLD.
BIAS_SIDE = "buy"

# ----------------------------------------------------------------------------
# Breakout-straddle settings
# ----------------------------------------------------------------------------
BREAKOUT_TRIGGER_PCT = 0.003    # price must move this far from baseline to fire (0.3%)
BREAKOUT_WATCH_MINUTES = 10     # after release, watch this long for a break, else no trade
BREAKOUT_POLL_SECONDS = 5       # how often to check the price while watching

# ----------------------------------------------------------------------------
# Sizing & risk
# ----------------------------------------------------------------------------
NOTIONAL_PER_TRADE = 1000.0     # USD notional per event (1% of a 100k paper acct)
TAKE_PROFIT_PCT = 0.008         # +0.8% take-profit
STOP_LOSS_PCT = 0.005           # -0.5% stop-loss

# Marketable-limit buffer for extended-hours (pre-market) fills, since GLD
# pre-market can be thin. We cross the spread by this fraction to get filled.
LIMIT_CROSS_PCT = 0.002         # 0.2%

# ----------------------------------------------------------------------------
# Safety switches
# ----------------------------------------------------------------------------
# If True, the bot logs what it WOULD do but places no orders. Use this first.
# Set to False for live paper trading (keys come from .env locally, or from
# GitHub Actions Secrets in the cloud).
DRY_RUN = False

# Skip the FOMC event entirely (it is the highest-variance tail — see STRATEGY.md).
SKIP_FOMC = False

# US market timezone
MARKET_TZ = "America/New_York"
