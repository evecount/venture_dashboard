import os
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import google_calendar as g  # noqa: E402

ME = "founder@startup.io"


def ev(day, attendees, status="confirmed", summary="x"):
    return {"summary": summary, "status": status, "start": {"dateTime": f"{day}T09:00:00+08:00"},
            "attendees": [{"email": e, **({"self": True} if e == ME else {})} for e in attendees]}


class Q:
    def __init__(self, store):
        self.store, self.op, self.payload = store, "select", None

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def delete(self):
        self.op = "delete"
        return self

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        if self.op == "insert":
            self.store.setdefault("inserted", []).extend(self.payload)
        if self.op == "delete":
            self.store["deleted"] = self.store.get("deleted", 0) + 1
        return NS(data=self.store.get("existing", []) if self.op == "select" else None)


class SB:
    def __init__(self, existing=None):
        self.store = {"existing": existing or []}

    def table(self, _):
        return Q(self.store)


class CalendarTests(unittest.TestCase):
    TEAM = {"cofounder@startup.io", "mentor@studio.com"}

    def test_counts_meetings_and_external_ones(self):
        events = [
            ev("2026-10-12", [ME, "cofounder@startup.io"]),             # internal
            ev("2026-10-12", [ME, "customer@bigco.com"]),               # external
            ev("2026-10-12", [ME]),                                      # solo block: not a meeting
            ev("2026-10-12", [ME, "customer@bigco.com"], status="cancelled"),
            ev("2026-10-13", [ME, "mentor@studio.com"]),                # mentor session: not external
            ev("2026-10-13", [ME, "friend@gmail.com"]),                 # public mail domain = outside
            ev("2026-10-13", [ME, "colleague@startup.io"]),             # same company domain = team
        ]
        days = g.classify(events, self.TEAM, ME)
        self.assertEqual(days["2026-10-12"], {"meetings": 2, "external": 1})
        self.assertEqual(days["2026-10-13"], {"meetings": 3, "external": 1})

    def test_declined_events_are_ignored(self):
        e = ev("2026-10-12", [ME, "customer@bigco.com"])
        e["attendees"][0]["responseStatus"] = "declined"
        self.assertEqual(g.classify([e], self.TEAM, ME), {})

    def test_token_encryption_roundtrip_and_wrong_key(self):
        blob = g.encrypt_token("refresh-123", "secret-a")
        self.assertNotIn("refresh-123", blob)
        self.assertEqual(g.decrypt_token(blob, "secret-a"), "refresh-123")
        self.assertIsNone(g.decrypt_token(blob, "secret-b"))
        self.assertIsNone(g.decrypt_token("garbage", "secret-a"))

    def test_connect_url_is_read_only_offline_and_signed(self):
        url = g.connect_url("cid", "https://x/cb", "s", "f1", "s1")
        self.assertIn("calendar.events.readonly", url)
        self.assertIn("access_type=offline", url)
        self.assertIn("state=", url)
        self.assertNotIn("calendar%20", url.replace("calendar.events", ""))  # no full-calendar write scope
        self.assertIsNone(g.connect_url(None, "https://x/cb", "s", "f1", "s1"))

    def test_sync_stores_counts_only_and_replaces_its_own_old_rows(self):
        enc = g.encrypt_token("r", "s")

        def http(method, url, headers=None, data=None, params=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            return {"items": [ev("2026-10-12", [ME, "customer@bigco.com"], summary="SECRET TITLE")]}

        gc = g.GoogleCalendar("cid", "cs", "https://x/cb", "s", http=http)
        sb = SB(existing=[{"id": "old", "meta": {"source": "google", "founder_id": "f1"}},
                          {"id": "other", "meta": {"source": "google", "founder_id": "f2"}}])
        integ = {"startup_id": "s1", "founder_id": "f1", "account": ME, "refresh_token": enc}
        n = g.sync_signals(gc, sb, integ, self.TEAM, now=datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
        row = sb.store["inserted"][0]
        self.assertEqual((n, row["meta"]["meetings"], row["meta"]["external"]), (1, 1, 1))
        self.assertNotIn("SECRET TITLE", str(row))
        self.assertEqual(sb.store["deleted"], 1)  # only this founder's earlier rows


    def test_studio_listing_is_limited_to_events_the_bot_created(self):
        seen = {}

        def http(method, url, headers=None, data=None, params=None, json=None):
            if url == g.TOKEN_URL:
                return {"access_token": "at"}
            seen.update(params or {})
            return {"items": []}

        gc = g.GoogleCalendar("cid", "cs", "https://x/cb", "s", http=http)
        gc.events(g.encrypt_token("r", "s"), datetime(2026, 10, 13, tzinfo=timezone.utc), datetime(2026, 10, 20, tzinfo=timezone.utc), only_ours=True)
        self.assertEqual(seen.get("privateExtendedProperty"), "ventureos=1")
        import meetings
        body = meetings.build_event_body("T", datetime(2026, 10, 16, 15, tzinfo=meetings.SGT), datetime(2026, 10, 16, 16, tzinfo=meetings.SGT), "x", [], "d")
        self.assertEqual(body["extendedProperties"]["private"], {"ventureos": "1"})


if __name__ == "__main__":
    unittest.main()
