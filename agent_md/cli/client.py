"""HTTP client for communicating with the agentmd backend.

Supports Unix domain socket (default) and TCP connections.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import httpx


def get_state_dir() -> Path:
    """Return the XDG state directory for agentmd."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "agentmd"


def get_socket_path() -> Path:
    """Return the path to the Unix domain socket."""
    return get_state_dir() / "agentmd.sock"


def get_log_path() -> Path:
    """Return the path to the backend log file."""
    return get_state_dir() / "backend.log"


class BackendClient:
    """Thin HTTP client for the agentmd backend."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        socket_path: Path | None = None,
    ) -> None:
        self._api_key = api_key

        if host and port:
            self.base_url = f"http://{host}:{port}"
            self._transport = None
            self._socket_path: Path | None = None
        else:
            sock = socket_path or get_socket_path()
            self._socket_path = sock
            # httpx needs a normal http:// base_url — the UDS transport
            # handles routing to the socket file transparently
            self.base_url = "http://agentmd-backend"
            self._transport = httpx.HTTPTransport(uds=str(sock))

    def _client(self, **kwargs) -> httpx.Client:
        headers = kwargs.pop("headers", {})
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        transport = self._transport
        return httpx.Client(
            base_url=self.base_url,
            transport=transport,
            headers=headers,
            timeout=10.0,
            **kwargs,
        )

    def _async_client(self, **kwargs) -> httpx.AsyncClient:
        headers = kwargs.pop("headers", {})
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        transport = httpx.AsyncHTTPTransport(uds=str(self._socket_path)) if self._socket_path else None
        return httpx.AsyncClient(
            base_url=self.base_url,
            transport=transport,
            headers=headers,
            timeout=10.0,
            **kwargs,
        )

    def health_check(self) -> bool:
        """Return True if the backend is alive."""
        try:
            with self._client() as c:
                resp = c.get("/health")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    def get(self, path: str, **kwargs) -> httpx.Response:
        with self._client() as c:
            return c.get(path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        with self._client() as c:
            return c.post(path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        with self._client() as c:
            return c.delete(path, **kwargs)

    @contextmanager
    def stream_sse(self, path: str):
        """Open an SSE stream. Yields an httpx response to iterate over.

        Usage::

            with client.stream_sse("/executions/1/stream") as response:
                for line in response.iter_lines():
                    ...
        """
        client = self._client(timeout=httpx.Timeout(None))
        with client:
            with client.stream("GET", path) as response:
                yield response
