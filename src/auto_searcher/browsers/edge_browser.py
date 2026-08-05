"""Microsoft Edge browser implementation and runtime helpers."""

import csv
import json
import logging
import os
import subprocess
from io import StringIO
from pathlib import Path

from auto_searcher.utils.path_utils import default_edge_user_data_dir

from .chromium_browser import ChromiumBrowser

logger = logging.getLogger(__name__)


class EdgeBrowser(ChromiumBrowser):
    _LEGACY_DEBUGGING_ADDRESS = "127.0.0.1:9222"

    @property
    def name(self) -> str:
        return self._name()

    @classmethod
    def _name(cls) -> str:
        return "Edge"

    def _launch_command(self, executable: Path) -> tuple[list[str], str | None]:
        command = [str(executable)]
        if self._browser_config.profile_name:
            command.append(
                f"--profile-directory={self._browser_config.profile_name}"
            )
        if self._browser_config.user_data_dir:
            command.append(f"--user-data-dir={self._browser_config.user_data_dir}")

        if self._browser_manages_remote_debugging():
            logger.info("检测到 Edge 内置远程调试已启用，不传入调试端口")
            return command, None

        logger.info("未检测到 Edge 内置远程调试，使用兼容调试端口 9222")
        command.append("--remote-debugging-port=9222")
        return command, self._LEGACY_DEBUGGING_ADDRESS

    def _browser_manages_remote_debugging(self) -> bool:
        user_data_dir = (
            Path(self._browser_config.user_data_dir)
            if self._browser_config.user_data_dir
            else self._default_user_data_dir()
        )
        local_state = user_data_dir / "Local State"
        try:
            data = json.loads(local_state.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False

        devtools = data.get("devtools")
        if not isinstance(devtools, dict):
            return False
        remote_debugging = devtools.get("remote_debugging")
        if not isinstance(remote_debugging, dict):
            return False
        return remote_debugging.get("user-enabled") is True

    @staticmethod
    def _find_executable() -> Path | None:
        roots = (
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramFiles"),
            os.environ.get("LOCALAPPDATA"),
        )
        for root in roots:
            if not root:
                continue
            executable = (
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            )
            if executable.is_file():
                return executable.resolve()
        return None

    @classmethod
    def _process_is_running(cls) -> bool:
        return bool(cls._process_ids())

    @classmethod
    def _listening_addresses(cls) -> tuple[str, ...]:
        process_ids = cls._process_ids()
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

    @staticmethod
    def _process_ids() -> set[str]:
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

    @staticmethod
    def _default_user_data_dir() -> Path:
        return default_edge_user_data_dir()

    @staticmethod
    def _supports_product(product: str) -> bool:
        return product.startswith("Edg/")

    @staticmethod
    def _remote_debugging_hint() -> str:
        return "请先在 Edge 中启用远程调试，并确认 DevToolsActivePort 已生成。"
