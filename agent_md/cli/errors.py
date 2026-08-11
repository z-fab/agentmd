"""CLI-specific exceptions."""


class BackendAlreadyRunning(Exception):
    """Raised when ``agentmd start`` finds a healthy backend already bound to the socket."""


class BackendStartupFailed(Exception):
    """Raised when the backend's lifespan startup failed and the server never served.

    uvicorn logs "Application startup failed. Exiting." and returns from
    ``serve()`` normally, so nothing else distinguishes a backend that ran and
    stopped from one that never came up. Exiting 0 for the latter is what makes
    a lost race for the database look like a successful start.
    """


class TcpRequiresApiKey(Exception):
    """Raised when ``agentmd start --port`` is used without ``--api-key``.

    A TCP listener is reachable by anything that can route to the host, and the
    API can execute arbitrary agents. Refuse to bind it unauthenticated.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "--port requires --api-key: a TCP listener would expose every endpoint "
                "(including POST /agents/{id}/run) without authentication. "
                "Retry with: agentmd start --port <port> --api-key <key>"
            )
        )
