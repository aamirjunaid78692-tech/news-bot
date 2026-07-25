"""
Thin wrapper around alpaca-py for the news bot.

Handles:
  - price snapshot (to size share qty and set bracket levels)
  - regular-hours bracket market orders (used for the 14:00 ET FOMC)
  - extended-hours marketable-limit orders (used for 08:30 ET releases)
  - flatten / cancel helpers for the time-based exit
"""
from __future__ import annotations

import math
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
    GetOrdersRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

import config


class Broker:
    def __init__(self):
        if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
            raise RuntimeError("Missing Alpaca keys. Copy .env.example to .env and fill them in.")
        self.trading = TradingClient(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER,
        )
        self.data = StockHistoricalDataClient(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
        )

    # ------------------------------------------------------------------ price
    def last_price(self, symbol: str) -> float:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quote = self.data.get_stock_latest_quote(req)[symbol]
        # mid-price; fall back to ask/bid if one side is 0
        bid, ask = float(quote.bid_price or 0), float(quote.ask_price or 0)
        if bid and ask:
            return (bid + ask) / 2
        return ask or bid

    def qty_for_notional(self, symbol: str, notional: float) -> int:
        px = self.last_price(symbol)
        if px <= 0:
            raise RuntimeError(f"Could not get a price for {symbol}")
        return max(1, math.floor(notional / px))

    # ----------------------------------------------------------------- orders
    def bracket_market(self, symbol: str, side: str, qty: int,
                       tp_pct: float, sl_pct: float) -> dict:
        """Regular-hours bracket market order. Use inside 09:30-16:00 ET."""
        entry_px = self.last_price(symbol)
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        if order_side == OrderSide.BUY:
            tp = round(entry_px * (1 + tp_pct), 2)
            sl = round(entry_px * (1 - sl_pct), 2)
        else:
            tp = round(entry_px * (1 - tp_pct), 2)
            sl = round(entry_px * (1 + sl_pct), 2)

        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=tp),
            stop_loss=StopLossRequest(stop_price=sl),
        )
        order = self.trading.submit_order(req)
        return {"id": str(order.id), "entry": entry_px, "tp": tp, "sl": sl, "qty": qty}

    def extended_hours_limit(self, symbol: str, side: str, qty: int) -> dict:
        """
        Extended-hours (pre-market) marketable-limit order. Bracket orders are
        NOT allowed in extended hours, so this is a plain limit; the time-based
        exit and a manual protective order handle the risk. Use for 08:30 ET.
        """
        px = self.last_price(symbol)
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        # cross the spread so a thin pre-market book still fills us
        if order_side == OrderSide.BUY:
            limit = round(px * (1 + config.LIMIT_CROSS_PCT), 2)
        else:
            limit = round(px * (1 - config.LIMIT_CROSS_PCT), 2)

        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
            limit_price=limit,
            extended_hours=True,
        )
        order = self.trading.submit_order(req)
        return {"id": str(order.id), "entry": px, "limit": limit, "qty": qty}

    # --------------------------------------------------------------- managing
    def position_qty(self, symbol: str) -> int:
        try:
            pos = self.trading.get_open_position(symbol)
            return int(float(pos.qty))
        except Exception:
            return 0

    def flatten(self, symbol: str) -> Optional[str]:
        """Close any open position in symbol at market (regular hours)."""
        qty = self.position_qty(symbol)
        if qty == 0:
            return None
        order = self.trading.close_position(symbol)
        return str(order.id)

    def cancel_open_orders(self, symbol: str) -> None:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        for o in self.trading.get_orders(req):
            try:
                self.trading.cancel_order_by_id(o.id)
            except Exception:
                pass

    def account_summary(self) -> dict:
        acct = self.trading.get_account()
        return {
            "status": acct.status,
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
        }
