"""CLI-specific exceptions."""


class BackendAlreadyRunning(Exception):
    """Raised when ``agentmd start`` finds a healthy backend already bound to the socket."""


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
