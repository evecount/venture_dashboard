import re
import unittest
from datetime import timezone

from timeparse import normalize, parse_ts

# What Python 3.10's datetime.fromisoformat (the VM) accepts: no "Z", and a fraction of exactly 3 or 6 digits.
PY310_SAFE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?([+-]\d{2}:\d{2})?$")


class TimeparseTest(unittest.TestCase):
    def test_supabase_trimmed_fraction(self):
        s = "2026-10-19T01:35:03.79174+00:00"  # the stamp that broke the bot on 2026-10-19
        self.assertEqual(normalize(s), "2026-10-19T01:35:03.791740+00:00")
        self.assertEqual(parse_ts(s).microsecond, 791740)

    def test_formats_all_become_py310_safe(self):
        for s in ("2026-10-19T01:35:03Z", "2026-10-19T01:35:03.1+00:00", "2026-10-19T01:35:03.123456789Z",
                  "2026-10-19T09:35:03+08:00", "2026-10-19 01:35:03.5+00:00", "2026-10-19T01:35:03"):
            self.assertRegex(normalize(s), PY310_SAFE, s)

    def test_timezone_kept(self):
        self.assertEqual(parse_ts("2026-10-19T01:35:03Z").tzinfo, timezone.utc)
        self.assertEqual(parse_ts("2026-10-19T09:35:03+08:00").utcoffset().total_seconds(), 8 * 3600)


if __name__ == "__main__":
    unittest.main()
