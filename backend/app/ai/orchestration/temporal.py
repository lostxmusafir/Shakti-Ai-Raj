import re
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo


def resolve_temporal_window(question: str, as_of: Optional[date] = None):
    text = (question or "").lower()
    today = as_of or datetime.now(ZoneInfo("Asia/Kolkata")).date()

    if re.search(r"\b(last|previous|prior) month\b|\bpichh?le mahine\b", text):
        first_current = today.replace(day=1)
        last_previous = first_current - timedelta(days=1)
        return {
            "period": "last_month",
            "start": last_previous.replace(day=1).isoformat(),
            "end": first_current.isoformat(),
        }
    if re.search(r"\b(this|current) month\b|\b(is|iss) mahine\b", text):
        first_current = today.replace(day=1)
        if first_current.month == 12:
            first_next = first_current.replace(year=first_current.year + 1, month=1)
        else:
            first_next = first_current.replace(month=first_current.month + 1)
        return {"period": "this_month", "start": first_current.isoformat(), "end": first_next.isoformat()}
    if re.search(r"\byesterday\b", text):
        start = today - timedelta(days=1)
        return {"period": "yesterday", "start": start.isoformat(), "end": today.isoformat()}
    if re.search(r"\btoday\b|\baaj\b", text):
        return {"period": "today", "start": today.isoformat(), "end": (today + timedelta(days=1)).isoformat()}
    return None
