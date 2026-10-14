import unittest

import httpx

import db_retry


class DbRetryTest(unittest.TestCase):
    def tearDown(self):
        httpx.Client.send = db_retry._original_send

    def client(self, failures):
        calls = []

        def handler(request):
            calls.append(request.url.host)
            if len(calls) <= failures:
                raise httpx.RemoteProtocolError("Server disconnected", request=request)
            return httpx.Response(200, json=[])
        return httpx.Client(transport=httpx.MockTransport(handler)), calls

    def test_retries_once_for_supabase(self):
        db_retry.install("https://abc.supabase.co")
        c, calls = self.client(failures=1)
        self.assertEqual(c.get("https://abc.supabase.co/rest/v1/x").status_code, 200)
        self.assertEqual(len(calls), 2)

    def test_gives_up_after_one_retry(self):
        db_retry.install("https://abc.supabase.co")
        c, _ = self.client(failures=2)
        with self.assertRaises(httpx.RemoteProtocolError):
            c.get("https://abc.supabase.co/rest/v1/x")

    def test_other_hosts_untouched(self):
        db_retry.install("https://abc.supabase.co")
        c, calls = self.client(failures=1)
        with self.assertRaises(httpx.RemoteProtocolError):
            c.get("https://api.example.com/")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
