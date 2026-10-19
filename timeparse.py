"""
Timestamp parsing that works on the VM's Python 3.10. Supabase/Postgres drop trailing zeros from fractional
seconds ("...03.79174+00:00") and GitHub/Google use "Z"; Python 3.10's fromisoformat accepts neither, so every
datetime string from outside goes through parse_ts.
"""

import re
from datetime import datetime

_FRACTION = re.compile(r"(T\d{2}:\d{2}:\d{2})(?:\.(\d+))?")


def normalize(stamp: str) -> str:
    """'2026-10-19T01:35:03.79174Z' -> '2026-10-19T01:35:03.791740+00:00' (fraction padded or cut to 6 digits)."""
    s = str(stamp).strip().replace(" ", "T", 1) if "T" not in str(stamp) else str(stamp).strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    return _FRACTION.sub(lambda m: m.group(1) + (f".{m.group(2)[:6].ljust(6, '0')}" if m.group(2) else ""), s, count=1)


def parse_ts(stamp: str) -> datetime:
    return datetime.fromisoformat(normalize(stamp))
