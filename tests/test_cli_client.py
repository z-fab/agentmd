"""Tests for the CLI HTTP client."""

from agent_md.cli.client import BackendClient, get_socket_path


def test_get_socket_path():
    path = get_socket_path()
    assert path.name == "agentmd.sock"
    assert "agentmd" in str(path)


def test_client_default_socket():
    client = BackendClient()
    assert client.base_url.startswith("http+unix://")


def test_client_tcp():
    client = BackendClient(host="127.0.0.1", port=4100, api_key="secret")
    assert client.base_url == "http://127.0.0.1:4100"
    assert client._api_key == "secret"
