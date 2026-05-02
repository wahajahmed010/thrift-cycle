#!/usr/bin/env python3
"""Daily quota tracker for eBay APIs.

Tracks API call counts per day to avoid hitting rate limits.
Resets at midnight PST (eBay's reset time).
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

QUOTA_PATH = Path(__file__).parent / ".quota_state.json"

# eBay Finding API limits (per App ID per day)
FINDING_DAILY_LIMIT = 5000  # Conservative estimate


def _get_pst_date():
    """Get current date in PST (eBay's timezone)."""
    from datetime import timedelta
    pst_offset = timedelta(hours=-7)  # PDT (summer) - adjust to -8 for PST
    pst_now = datetime.now(timezone.utc) + pst_offset
    return pst_now.strftime("%Y-%m-%d")


def load_quota():
    """Load quota state from file."""
    if not QUOTA_PATH.exists():
        return {}
    try:
        with open(QUOTA_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_quota(state):
    """Save quota state to file."""
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUOTA_PATH, "w") as f:
        json.dump(state, f, indent=2)
    os.chmod(QUOTA_PATH, 0o600)


def get_daily_calls(api_name="finding"):
    """Get number of calls made today for an API."""
    state = load_quota()
    pst_date = _get_pst_date()
    return state.get(pst_date, {}).get(api_name, 0)


def increment_calls(api_name="finding", count=1):
    """Increment call count for today."""
    state = load_quota()
    pst_date = _get_pst_date()
    if pst_date not in state:
        state[pst_date] = {}
    state[pst_date][api_name] = state[pst_date].get(api_name, 0) + count
    save_quota(state)


def is_quota_exceeded(api_name="finding", limit=None):
    """Check if daily quota is exceeded."""
    if limit is None:
        limit = FINDING_DAILY_LIMIT
    return get_daily_calls(api_name) >= limit


def get_remaining_calls(api_name="finding", limit=None):
    """Get remaining calls for today."""
    if limit is None:
        limit = FINDING_DAILY_LIMIT
    return max(0, limit - get_daily_calls(api_name))


def reset_if_new_day():
    """Reset quota if it's a new day."""
    state = load_quota()
    pst_date = _get_pst_date()
    old_dates = [d for d in state.keys() if d != pst_date]
    if old_dates:
        for d in old_dates:
            del state[d]
        save_quota(state)
        return True
    return False


if __name__ == "__main__":
    print(f"PST Date: {_get_pst_date()}")
    print(f"Finding API calls today: {get_daily_calls('finding')}")
    print(f"Remaining: {get_remaining_calls('finding')}")
    print(f"Quota exceeded: {is_quota_exceeded('finding')}")
