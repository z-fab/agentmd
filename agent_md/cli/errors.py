"""CLI-specific exceptions."""


class BackendAlreadyRunning(Exception):
    """Raised when ``agentmd start`` finds a healthy backend already bound to the socket."""
