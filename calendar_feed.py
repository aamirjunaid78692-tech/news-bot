"""
ForexFactory calendar feed.

Pulls the public weekly JSON, filters to the USD red-folder (High-impact)
events we care about, and returns them as normalised Event objects with a
timezone-aware release timestamp.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

import requests
from dateutil import parser as dateparser  # provided by python-dateutil (dep of pandas/alpaca)

import config


@dataclass
class Event:
    title: str
    currency: str
    impact: str
    when: dt.datetime          # timezone-aware (UTC)
    forecast: str
    previous: str

    @property
    def is_fomc(self) -> bool:
        return "FOMC" in self.title.upper()

    def __str__(self) -> str:
        local = self.when.astimezone()
        return (f"[{self.currency} {self.impact}] {self.title} @ "
                f"{self.when.isoformat()} (local {local:%Y-%m-%d %H:%M %Z}) "
                f"fc={self.forecast or '-'} prev={self.previous or '-'}")


def _matches_keywords(title: str) -> bool:
    if config.TRADE_ALL_HIGH_IMPACT:
        return True
    up = title.upper()
    return any(k.upper() in up for k in config.EVENT_KEYWORDS)


def fetch_events(url: str = None) -> List[Event]:
    """Fetch and filter this week's high-impact USD events."""
    url = url or config.FF_CALENDAR_URL
    resp = requests.get(url, timeout=20, headers={"User-Agent": "news-gld-bot/1.0"})
    resp.raise_for_status()
    raw = resp.json()

    events: List[Event] = []
    for row in raw:
        currency = (row.get("country") or row.get("currency") or "").upper()
        impact = (row.get("impact") or "").capitalize()
        title = row.get("title") or row.get("event") or ""

        if currency != config.TRADE_CURRENCY:
            continue
        allowed = config.TRADE_IMPACT
        allowed = (allowed,) if isinstance(allowed, str) else tuple(allowed)
        if impact not in allowed:
            continue
        if not _matches_keywords(title):
            continue

        when = _parse_when(row.get("date"))
        if when is None:
            continue

        ev = Event(
            title=title,
            currency=currency,
            impact=impact,
            when=when,
            forecast=str(row.get("forecast") or ""),
            previous=str(row.get("previous") or ""),
        )
        if config.SKIP_FOMC and ev.is_fomc:
            continue
        events.append(ev)

    events.sort(key=lambda e: e.when)
    return events


def _parse_when(date_str: Optional[str]) -> Optional[dt.datetime]:
    """ForexFactory dates are ISO8601 with an offset, e.g. 2026-07-29T14:00:00-04:00."""
    if not date_str:
        return None
    try:
        d = dateparser.parse(date_str)
    except (ValueError, TypeError):
        return None
    if d.tzinfo is None:
        # Assume the feed's local (ET) if naive; safest is to treat as UTC and warn.
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def upcoming_events(lead_seconds: int = 0) -> List[Event]:
    """Events whose release time is still in the future (minus lead)."""
    now = dt.datetime.now(dt.timezone.utc)
    horizon = now - dt.timedelta(seconds=lead_seconds)
    return [e for e in fetch_events() if e.when >= horizon]


if __name__ == "__main__":
    for e in fetch_events():
        print(e)
