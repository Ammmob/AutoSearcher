"""Resolve Edge's browser-level CDP WebSocket endpoint."""

import http.client
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EdgeEndpoint:
    address: str
    websocket_url: str


def read_http_endpoint(address: str) -> EdgeEndpoint | None:
    connection: http.client.HTTPConnection | None = None
    try:
        host, port_text = address.rsplit(":", maxsplit=1)
        port = int(port_text)
        connection = http.client.HTTPConnection(host, port, timeout=0.5)
        connection.request("GET", "/json/version")
        response = connection.getresponse()
        if response.status != 200:
            return None
        data = json.loads(response.read().decode("utf-8"))
        product = data.get("Browser")
        websocket_url = data.get("webSocketDebuggerUrl")
        if not isinstance(product, str) or not product.startswith("Edg/"):
            return None
        if not isinstance(websocket_url, str) or not websocket_url.startswith("ws"):
            return None
        return EdgeEndpoint(address, websocket_url)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    finally:
        if connection is not None:
            connection.close()


def read_edge_endpoint(
    user_data_dir: str | Path,
    expected_address: str | None = None,
) -> EdgeEndpoint | None:
    active_port_file = Path(user_data_dir) / "DevToolsActivePort"
    try:
        lines = active_port_file.read_text(encoding="utf-8").splitlines()
        port = int(lines[0].strip())
        websocket_path = lines[1].strip()
    except (OSError, UnicodeError, ValueError, IndexError):
        return None

    if not 1 <= port <= 65535:
        return None
    if not websocket_path.startswith("/devtools/browser/"):
        return None

    host = "127.0.0.1"
    if expected_address:
        try:
            expected_host, expected_port = expected_address.rsplit(":", maxsplit=1)
            if int(expected_port) != port:
                return None
        except ValueError:
            return None
        host = expected_host

    address = f"{host}:{port}"
    return EdgeEndpoint(address, f"ws://{address}{websocket_path}")
