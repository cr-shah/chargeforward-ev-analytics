"""Small dependency-free HTTP client for public-data adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
import ssl
import time
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


class PublicDataError(RuntimeError):
    """Raised when an upstream public-data request cannot be completed."""


class HttpTransport(Protocol):
    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes: ...

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any: ...


@dataclass
class UrllibTransport:
    timeout_seconds: float = 45.0
    retries: int = 2
    user_agent: str = "ChargeForward/0.2 (+https://github.com/cr-shah/chargeforward-ev-analytics)"

    def _url(self, url: str, params: Mapping[str, object] | None) -> str:
        if not params:
            return url
        query = urlencode([(key, value) for key, value in params.items() if value is not None])
        return f"{url}{'&' if '?' in url else '?'}{query}"

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes:
        request_headers = {"Accept": "application/json", "User-Agent": self.user_agent, **(headers or {})}
        request = Request(self._url(url, params), headers=request_headers)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                context = ssl.create_default_context(cafile=certifi.where())
                with urlopen(request, timeout=self.timeout_seconds, context=context) as response:
                    return response.read()
            except HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except URLError as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.35 * (2**attempt))
        detail = f"HTTP {last_error.code}" if isinstance(last_error, HTTPError) else str(last_error)
        raise PublicDataError(f"Unable to fetch {url}: {detail}") from last_error

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        payload = self.get_bytes(url, params=params, headers=headers)
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PublicDataError(f"Invalid JSON returned by {url}") from exc
