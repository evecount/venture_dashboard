import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from profile_rules import match_person  # noqa: E402

S = [
    {"name": "Alex Lee", "email": "matt@x.com", "slack_user_id": "U1"},
    {"name": "Priya Rao", "email": None, "slack_user_id": None},  # pre-registered by the coordinator
]


class MatchTests(unittest.TestCase):
    def test_same_name_same_email_is_duplicate(self):
        self.assertEqual(match_person(S, S, "Alex Lee", "matt@x.com", True)[0], "duplicate")

    def test_same_name_extra_spaces_and_case_is_duplicate(self):
        self.assertEqual(match_person(S, S, "  alex   LEE ", "matt@x.com", True)[0], "duplicate")

    def test_same_email_different_name_is_still_duplicate(self):
        self.assertEqual(match_person(S, S, "Matt L", "MATT@x.com", True)[0], "duplicate")

    def test_same_name_different_email_is_allowed(self):
        self.assertEqual(match_person(S, S, "Alex Lee", "other@x.com", True)[0], "new")

    def test_different_surname_is_allowed(self):
        self.assertEqual(match_person(S, S, "Alex Tan", "mt@x.com", True)[0], "new")

    def test_preregistered_invite_is_claimed_not_duplicated(self):
        verdict, row = match_person(S, S, "Priya Rao", "tak@x.com", True)
        self.assertEqual((verdict, row["name"]), ("claim", "Priya Rao"))

    def test_typed_email_cannot_claim_an_existing_record(self):
        rows = [{"name": "Ann", "email": "ann@x.com", "slack_user_id": None}]
        self.assertEqual(match_person(rows, rows, "Someone Else", "ann@x.com", False)[0], "duplicate")
        self.assertEqual(match_person(rows, rows, "Someone Else", "ann@x.com", True)[0], "claim")

    def test_name_match_scoped_to_startup(self):
        # same name in a different startup is not in scope, so it is a new person
        self.assertEqual(match_person(S, [], "Alex Lee", "m2@x.com", True)[0], "new")

    def test_user_scenarios_for_a_second_alex(self):
        # existing: Alex Lee <matt@x.com>, linked
        for typed in ("alex lee", "ALEX LEE", "Alex Lee"):
            self.assertEqual(match_person(S, S, typed, "matt@x.com", True)[0], "duplicate", typed)   # same person
            self.assertEqual(match_person(S, S, typed, "second@x.com", True)[0], "new", typed)       # another Alex Lee
        self.assertEqual(match_person(S, S, "Alex Tan", "tan@x.com", True)[0], "new")             # different surname
        self.assertEqual(match_person(S, S, "Alex", "plain@x.com", True)[0], "new")               # no surname, other email
        self.assertEqual(match_person(S, S, "Alex", "matt@x.com", True)[0], "duplicate")          # no surname, same email


if __name__ == "__main__":
    unittest.main()
