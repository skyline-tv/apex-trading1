from datetime import datetime, timezone

from market_hours import nse_regular_session_status


def test_weekend_is_closed():
    # Sunday in IST should always be closed.
    dt = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    is_open, reason = nse_regular_session_status(dt)
    assert is_open is False
    assert "closed" in reason.lower()


def test_weekday_morning_before_open_is_closed():
    # Monday 08:00 IST -> 02:30 UTC
    dt = datetime(2026, 4, 27, 2, 30, tzinfo=timezone.utc)
    is_open, reason = nse_regular_session_status(dt)
    assert is_open is False
    assert "open" in reason.lower() or "closed" in reason.lower()
