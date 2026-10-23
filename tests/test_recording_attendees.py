import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import slack_bot as b  # noqa: E402


class FakeDB:
    rows = {"founders": [{"email": "Adrian@x.com", "slack_user_id": "UF1"}, {"email": "no@x.com", "slack_user_id": None}],
            "mentors": [{"email": "ben@x.com", "slack_user_id": "UM1"}, {"email": "gwen@x.com", "slack_user_id": "UM2"}],
            "startups": [{"name": "GRC Nexus"}]}

    def table(self, name):
        self.name = name
        return self

    def select(self, *_):
        return self

    def execute(self):
        return mock.Mock(data=self.rows[self.name])


EVENT = {"summary": "Agents advice", "extendedProperties": {"private": {"requester": "UF1"}},
         "attendees": [{"email": "adrian@x.com"}, {"email": "ben@x.com"}, {"email": "gwen@x.com", "responseStatus": "declined"},
                       {"email": "outsider@y.com"}],
         "location": "https://meet.google.com/abc-defg-hij"}


class RecordingAttendeeTests(unittest.TestCase):
    def test_attendees_are_program_members_by_email_minus_declines(self):
        with mock.patch.object(b, "supabase", FakeDB()):
            self.assertEqual(b.meeting_attendees(EVENT), ["UF1", "UM1"])
            self.assertEqual(b.meeting_attendees({"attendees": []}), [])

    def test_every_attendee_gets_the_same_notes_written_once(self):
        gcal = mock.Mock()
        gcal.events.return_value = [EVENT]
        gcal.download_drive_file.return_value = 10 * 1024 * 1024
        sent = []
        with mock.patch.object(b, "supabase", FakeDB()), mock.patch.object(b, "gcal", gcal), \
                mock.patch.object(b, "SPEECHMATICS_API_KEY", "k"), mock.patch.object(b, "_DM", lambda uid: (lambda *a, **k: None)), \
                mock.patch.object(b.meeting_capture, "transcribe_speechmatics", return_value="[00:01] S1: lots of words " * 10), \
                mock.patch.object(b.meeting_capture, "summarize", return_value="*Summary*") as summarize, \
                mock.patch.object(b, "get_role", side_effect=lambda u: "founder" if u == "UF1" else "mentor"), \
                mock.patch.object(b, "deliver_notes", side_effect=lambda uid, role, title, t, say, notes: sent.append((uid, role, notes))):
            b._process_recording({"meeting_code": "abc-defg-hij", "start": "2026-10-23T06:30:00Z", "file_id": "f"},
                                 {"refresh_token": "h"}, {"refresh_token": "s"})
        self.assertEqual(sent, [("UF1", "founder", "*Summary*"), ("UM1", "mentor", "*Summary*")])
        summarize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
