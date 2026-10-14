"""
Supabase keeps one HTTP/2 connection open; after a quiet spell the server closes it and the next request on it
fails with "Server disconnected". This retries such a request once on a fresh connection (the failed one is
dropped from the pool), only for requests to our Supabase host.
"""

import httpx

_RETRYABLE = (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError, httpx.ConnectError)
_original_send = httpx.Client.send


def install(supabase_url: str | None):
    if not supabase_url:
        return
    host = httpx.URL(supabase_url).host

    def send(self, request, *args, **kwargs):
        try:
            return _original_send(self, request, *args, **kwargs)
        except _RETRYABLE:
            if request.url.host != host:
                raise
            return _original_send(self, request, *args, **kwargs)

    httpx.Client.send = send
