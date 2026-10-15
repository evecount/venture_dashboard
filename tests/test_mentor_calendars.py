import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mentor_calendars as mc  # noqa: E402

SGT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc)


def ev(**over):
    base = {"id": "g1", "summary": "Board call", "status": "confirmed",
            "start": {"dateTime": "2026-10-16T15:00:00+08:00"}, "end": {"dateTime": "2026-10-16T16:00:00+08:00"}}
    base.update(over)
    return base


def block(h1, h2, all_day=False):
    d = date(2026, 10, 16)
    return {"slack_user_id": "UA", "title": "X", "busy_only": False, "all_day": all_day,
            "begin": datetime(d.year, d.month, d.day, h1, 0, tzinfo=SGT), "end": datetime(d.year, d.month, d.day, h2, 0, tzinfo=SGT)}


class MentorCalendarTests(unittest.TestCase):
    def test_connect_link_is_read_only_and_names_the_mentor(self):
        url = mc.connect_url("cid", "https://x/cb", "secret", "UARTHUR")
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["scope"][0], "openid email https://www.googleapis.com/auth/calendar.events.readonly")
        self.assertIsNone(mc.connect_url(None, "https://x/cb", "secret", "UARTHUR"))

    def test_private_events_become_busy_and_free_or_declined_ones_are_skipped(self):
        rows = mc.event_rows("UA", [
            ev(),
            ev(id="g2", visibility="private", summary="Doctor"),
            ev(id="g3", transparency="transparent"),
            ev(id="g4", attendees=[{"self": True, "responseStatus": "declined"}]),
            ev(id="g5", status="cancelled"),
        ], NOW)
        self.assertEqual([(r["event_id"], r["title"], r["busy_only"]) for r in rows],
                         [("g1", "Board call", False), ("g2", "Busy", True)])
        self.assertEqual(rows[0]["id"], "UA:g1")

    def test_all_day_events_are_kept_but_dont_block_suggested_times(self):
        [row] = mc.event_rows("UA", [ev(start={"date": "2026-10-16"}, end={"date": "2026-10-17"})], NOW)
        self.assertTrue(row["all_day"])
        slots = mc.free_slots([block(0, 23, all_day=True)], date(2026, 10, 16), 60)
        self.assertEqual(slots[0].hour, 9)

    def test_free_slots_avoid_busy_blocks(self):
        slots = mc.free_slots([block(9, 12), block(13, 15)], date(2026, 10, 16), 60, limit=3)
        self.assertEqual([(s.hour, s.minute) for s in slots], [(12, 0), (15, 0), (16, 0)])

    def test_clash_lines_hide_titles_from_founders_and_private_events(self):
        b = block(15, 16)
        self.assertEqual(mc.clash_lines([b], {"UA": "Arthur"}, True), ["Arthur: X (3:00 pm–4:00 pm)"])
        self.assertEqual(mc.clash_lines([b], {"UA": "Arthur"}, False), ["Arthur: busy (3:00 pm–4:00 pm)"])
        self.assertEqual(mc.clash_lines([{**b, "busy_only": True}], {"UA": "Arthur"}, True), ["Arthur: busy (3:00 pm–4:00 pm)"])


if __name__ == "__main__":
    unittest.main()
