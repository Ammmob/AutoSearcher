"""Microsoft Edge browser implementation and runtime helpers."""

import csv
import os
import subprocess
from io import StringIO
from pathlib import Path

from auto_searcher.utils.path_utils import default_edge_user_data_dir

from .browser import ChromiumBrowser


def find_edge_executable() -> Path | None:
    roots = (
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LOCALAPPDATA"),
    )
    for root in roots:
        if not root:
            continue
        executable = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if executable.is_file():
            return executable.resolve()
    return None


def edge_process_ids() -> set[str]:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {
        row[1]
        for row in csv.reader(StringIO(result.stdout))
        if len(row) >= 2 and row[0].casefold() == "msedge.exe"
    }


def edge_process_is_running() -> bool:
    return bool(edge_process_ids())


def listening_edge_addresses() -> tuple[str, ...]:
    process_ids = edge_process_ids()
    if not process_ids:
        return ()
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()

    ports: set[int] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[-1] not in process_ids:
            continue
        if fields[-2].upper() != "LISTENING":
            continue
        try:
            port = int(fields[1].rsplit(":", maxsplit=1)[-1])
        except ValueError:
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return tuple(f"127.0.0.1:{port}" for port in sorted(ports))


class EdgeBrowser(ChromiumBrowser):
    @property
    def name(self) -> str:
        return self._name()

    @classmethod
    def _name(cls) -> str:
        return "Edge"

    @staticmethod
    def _find_executable() -> Path | None:
        return find_edge_executable()

    @staticmethod
    def _process_is_running() -> bool:
        return edge_process_is_running()

    @staticmethod
    def _listening_addresses() -> tuple[str, ...]:
        return listening_edge_addresses()

    @staticmethod
    def _default_user_data_dir() -> Path:
        return default_edge_user_data_dir()

    @staticmethod
    def _supports_product(product: str) -> bool:
        return product.startswith("Edg/")

    @staticmethod
    def _remote_debugging_hint() -> str:
        return "Edge 151 请在 edge://inspect 中启用远程调试。"
