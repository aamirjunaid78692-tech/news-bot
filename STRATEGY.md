# USD News-Straddle Strategy on Gold (GLD) via Alpaca

**Instrument:** GLD (SPDR Gold Shares ETF) — proxy for USD-direction news, since Alpaca does not trade forex.
**Mode:** Paper trading first (Alpaca paper API).
**Data as of:** 26 July 2026. Figures below are the most recent prints. Re-verify before trading — this is a moving target.

---

## 1. Why gold, and the core logic

Alpaca cannot trade EUR/USD or any FX pair. It trades US stocks, ETFs, options and crypto. Gold is the cleanest liquid Alpaca instrument that trades *USD direction*, because gold is priced in dollars and is highly sensitive to the same drivers as the dollar:

- **Weak US data / dovish Fed → lower real yields → weaker USD → gold UP.**
- **Strong US data / hawkish Fed → higher real yields → stronger USD → gold DOWN.**

So for gold the mapping is inverted vs. the dollar: a *disappointing* red-folder USD number is generally *bullish* for GLD, and a *strong* number is *bearish*.

> **The single most important practical constraint:** GLD is a stock ETF. Regular hours are 09:30–16:00 ET. Three of the four key releases print at **08:30 ET — before the open.** That means you cannot trade GLD at the exact release instant during regular hours; you either use Alpaca **extended-hours limit orders** (pre-market from 04:00 ET, limit only) or you trade the **09:30 opening gap**. Only the **FOMC decision (14:00 ET)** lands inside regular hours. The bot is built to handle both cases.

---

## 2. The four most important USD red-folder events

These are the four highest-impact recurring USD events on the ForexFactory calendar, with the latest prints and the directional read for gold.

### A. Non-Farm Payrolls (NFP) — release 08:30 ET, first Friday
| | Value |
|---|---|
| Latest actual (Jun 2026) | **57K** |
| Forecast | 110K |
| Previous (May, revised) | 129K |

**Read:** A large miss (57K vs 110K) plus a downward revision signals a cooling labor market. **Dovish → bullish gold.** Previous two prints show a clear deceleration (129K → 57K), reinforcing the softening trend. Fundamentally, a weak jobs market pulls forward rate-cut expectations, lowers real yields, and supports gold. NFP is the single biggest FX/gold mover of the month by realized volatility.

### B. Consumer Price Index (CPI) — release 08:30 ET, mid-month
| | Value |
|---|---|
| Latest actual (Jun 2026, YoY) | **3.5%** |
| Forecast | 3.8% |
| Previous (May) | 4.2% |
| Core CPI | 2.6% vs 2.8% exp (prev 2.9%) |

**Read:** Inflation fell for the first time in five months and came in *below* forecast on both headline and core. **Dovish → bullish gold.** The key driver was energy: the US–Iran ceasefire cooled energy costs (energy +15.7% vs +23.5% prior), removing an inflation tail-risk. Cooling inflation lowers the odds of further Fed tightening → supportive for gold. Caveat: if geopolitics re-escalate and energy spikes, CPI can surprise *hot* → bearish gold.

### C. FOMC Rate Decision & Statement — release 14:00 ET, 28–29 July 2026
| | Value |
|---|---|
| Current target range | **3.50%–3.75%** |
| Market-implied: hold | ~79.5% |
| Market-implied: +25bp hike | ~19.4% |
| Dot plot | 9 officials see ≥1 more hike in 2026 |

**Read:** This is the **wildcard and the biggest single-event risk** — and it is only 3 days out (Wed 29 July). Base case is a hold, which is broadly neutral-to-mildly-bullish for gold given the soft NFP/CPI. **But the hawkish dot plot and ~19% hike pricing mean an upside (hawkish) surprise is a real tail — a hike or hawkish statement would be sharply bearish gold.** The market reaction is driven by the *statement tone and the press conference*, not just the rate number. Because this prints at 14:00 ET, GLD is fully tradeable at the release — the only one of the four that is.

### D. Advance Retail Sales — release 08:30 ET, mid-month
| | Value |
|---|---|
| Latest actual (Jun 2026, MoM) | **+0.2%** |
| Forecast | +0.3% |
| Previous (May, revised) | +1.0% |

**Read:** A modest miss and a sharp deceleration from +1.0% to +0.2% points to a softening consumer. **Mildly dovish → mildly bullish gold.** Ex-gas the number was firmer (+0.7%), so the signal is weaker than NFP/CPI. Retail Sales is the lowest-conviction of the four but still a high-impact red-folder event.

---

## 3. Net directional bias (late July 2026)

The macro tape is **net dovish / net bullish for gold**: weak jobs, cooling inflation, softening consumer. The three data prints all lean the same way.

**The offsetting risk is the FOMC on 29 July** — a hawkish dot plot and live hike pricing mean the single scheduled event most likely to *reverse* the bullish tape is the one landing this week. Layer on the **US–Iran geopolitical situation**: a ceasefire has been the disinflationary tailwind; any re-escalation flips energy/inflation hot (bearish gold via hawkish Fed) *and* simultaneously boosts gold's safe-haven bid — a genuinely two-sided, high-variance setup.

Context: gold is ~\$4,000–4,200/oz (GLD ≈ 1/10th of spot, so ~\$370–390/share range), down sharply from the January 2026 high near \$5,595. Major banks (JPM \$4,500 Q4, HSBC \$4,560, StoneX \$4,000) straddle current levels — no consensus, which is exactly why event-driven trading is being considered rather than a directional hold.

**This is why the strategy is a *straddle*, not a directional bet:** given the two-sided risk, the bot is designed to be positioned for a move either way and to cut losers fast, rather than to predict each print.

---

## 4. Trade mechanics the bot implements

**Entry:** A configurable number of minutes before each high-impact USD red-folder event (default 2 min), the bot enters a position in GLD. Two selectable modes:

- **`directional`** — take a single side based on the pre-computed bias in this doc (default: long GLD, reflecting the net-dovish tape). Simplest; you carry direction risk into the print.
- **`bracket_straddle`** — enter and immediately attach a bracket (take-profit + stop-loss) so the position is risk-defined regardless of which way the spike goes. Recommended.

**Exit:** Bracket order — take-profit and stop-loss as percentages of entry price (defaults: TP +0.8%, SL −0.5%), plus a hard time-based exit N minutes after the event (default 15 min) to avoid holding through the whole post-news drift.

**Sizing:** Fixed notional per trade (default \$2,000 of a \$100k paper account = 2% risk budget per event). Never scales into losers.

**Session handling:** For 08:30 ET events the bot places **extended-hours limit orders** (marketable limit, pre-market). For the 14:00 FOMC it uses regular-hours orders. It skips any event when the market/extended session is closed.

---

## 5. Risk warnings (read before going live)

This is a deliberately high-risk strategy. Be clear-eyed:

1. **Entering *before* a red-folder release is trading into maximum uncertainty.** Spreads widen, slippage spikes, and a stop can be jumped straight through on a gap. The realized fill can be far from your intended price.
2. **GLD is not the dollar and not gold futures.** It tracks spot gold at ~1/10th, has its own liquidity, and pre-market GLD is thin — extended-hours fills on an 08:30 print can be poor.
3. **The 08:30 events cannot be traded at the instant of release in regular hours.** You are either trading thin pre-market or the 09:30 gap, both of which change the risk profile materially.
4. **FOMC (29 July) is a coin-flip tail.** A hawkish surprise against the current bullish tape is the most likely single event to hand you a fast loss. Consider sitting it out or halving size.
5. **Paper-trade for at least a full event cycle** (one NFP, one CPI, one FOMC, one Retail Sales) before risking real capital. Measure slippage vs. your intended entries.
6. This document is analysis, not investment advice. I am not a financial adviser. Markets can and do move opposite to any fundamental read, especially around news.

---

*Sources: ForexFactory economic calendar; Trading Economics; FactSet; CNBC; Federal Reserve; US Census (retail sales); World Gold Council / JPMorgan / HSBC gold outlooks — all July 2026 prints.*
