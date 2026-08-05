"""Resolve Edge's browser-level CDP WebSocket endpoint."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EdgeEndpoint:
    address: str
    websocket_url: str


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
