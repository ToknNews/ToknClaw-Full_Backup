"""Small bounded JSON client. Never propagate response bodies or secret URLs."""

import json
import socket
from urllib import error, request


class RemoteError(Exception):
    def __init__(self, code, *, retry_after=60, ambiguous=False):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after
        self.ambiguous = ambiguous


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class JsonClient:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.opener = request.build_opener(NoRedirect())

    def call(self, url, payload=None):
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        req = request.Request(url, data=data, headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "User-Agent": "ToknMarketWatch/0.1",
        })
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                content_type = response.headers.get_content_type()
                if content_type != "application/json" and not content_type.endswith("+json"):
                    raise RemoteError("unexpected_content_type", ambiguous=True)
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise RemoteError("response_too_large", ambiguous=True)
                return json.loads(raw)
        except error.HTTPError as exc:
            retry = 60
            if exc.code == 429:
                try:
                    body = json.loads(exc.read(16384))
                    retry = float(body.get("retry_after", body.get("parameters", {}).get("retry_after", 60)))
                    if not 0 < retry <= 86400:
                        retry = 60
                except (ValueError, TypeError, AttributeError):
                    pass
            raise RemoteError("http_" + str(exc.code), retry_after=retry,
                              ambiguous=exc.code >= 500) from None
        except (error.URLError, socket.timeout, TimeoutError, OSError):
            raise RemoteError("network_failure", ambiguous=True) from None
        except (ValueError, UnicodeError):
            raise RemoteError("invalid_json", ambiguous=True) from None
