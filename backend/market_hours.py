"""NSE cash equity session (IST + exchange calendar) — blocks paper trades when the exchange is closed."""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)

_INDIA_CAL = None
_CALENDAR_FAILED = False


def _get_india_equity_calendar():
    """
    Lazy-load Mumbai (XBOM) calendar from exchange_calendars.

    XNSE was removed in newer exchange_calendars releases; XBOM tracks Indian cash
    session closely for session times and most holidays (NSE-only exceptions exist).
    """
    global _INDIA_CAL, _CALENDAR_FAILED
    if _CALENDAR_FAILED:
        return None
    if _INDIA_CAL is not None:
        return _INDIA_CAL
    try:
        import exchange_calendars as ecals  # noqa: PLC0415

        _INDIA_CAL = ecals.get_calendar("XBOM")
        return _INDIA_CAL
    except Exception as exc:
        _CALENDAR_FAILED = True
        logger.warning("India equity calendar unavailable (%s); using IST clock only.", exc)
        return None


def _calendar_minute_is_open(cal, now_utc: datetime) -> bool:
    """Return True if this UTC minute is an open regular-session minute on the exchange calendar."""
    minute = pd.Timestamp(now_utc).tz_convert("UTC").floor("1min")
    if hasattr(cal, "is_open_on_minute"):
        return bool(cal.is_open_on_minute(minute))
    if hasattr(cal, "is_open_at_minute"):
        return bool(cal.is_open_at_minute(minute))
    return True


def nse_regular_session_status(now: datetime | None = None) -> tuple[bool, str]:
    """
    Return (is_open, human_reason).

    Prefer exchange_calendars XBOM (weekends, holidays, session minutes). If the
    library is unavailable, fall back to Mon–Fri 09:15–15:30 IST.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    local = now.astimezone(IST)
    cal = _get_india_equity_calendar()
    if cal is not None:
        if not _calendar_minute_is_open(cal, now):
            return (
                False,
                f"Indian equity calendar closed ({local.strftime('%a %Y-%m-%d %H:%M')} IST) — weekend, holiday, or outside session.",
            )
        return True, "Indian cash session open (XBOM calendar)."

    if local.weekday() >= 5:
        return False, "Weekend — NSE cash market is closed (IST, fallback clock)."

    t = local.time()
    if t < NSE_OPEN:
        return False, f"Before NSE open (session 09:15–15:30 IST; now {local.strftime('%H:%M')} IST, fallback clock)."
    if t >= NSE_CLOSE:
        return False, f"After NSE close (15:30 IST; now {local.strftime('%H:%M')} IST, fallback clock)."

    return True, "NSE regular session (IST clock; install exchange-calendars for holidays)."
