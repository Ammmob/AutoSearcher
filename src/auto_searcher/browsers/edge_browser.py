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
    @property
    def name(self) -> str:
        return self._name()

    @classmethod
    def _name(cls) -> str:
        return "Edge"

    def _launch_command(self, executable: Path) -> tuple[list[str], str | None]:
        arguments, configured_port = self._extract_debugging_port(
            self._browser_config.args
        )
        command = [str(executable), *arguments]

        if self._browser_manages_remote_debugging():
            if configured_port is not None:
                logger.warning(
                    "Edge 使用浏览器内置远程调试，忽略启动参数中的调试端口 %s",
                    configured_port or "（未指定值）",
                )
            else:
                logger.info("检测到 Edge 内置远程调试已启用，不传入调试端口")
            return command, None

        port_value = "9222" if configured_port is None else configured_port
        port = self._validated_debugging_port(port_value)
        if configured_port is None:
            logger.info("未检测到 Edge 内置远程调试，使用默认调试端口 9222")
        else:
            logger.info("未检测到 Edge 内置远程调试，使用配置的调试端口 %d", port)
        command.append(f"--remote-debugging-port={port}")
        return command, f"127.0.0.1:{port}"

    @staticmethod
    def _extract_debugging_port(arguments: tuple[str, ...]) -> tuple[list[str], str | None]:
        option = "--remote-debugging-port"
        remaining: list[str] = []
        configured_port: str | None = None
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            normalized = argument.casefold()
            if normalized.startswith(f"{option}="):
                configured_port = argument.split("=", maxsplit=1)[1]
            elif normalized == option:
                configured_port = ""
                if index + 1 < len(arguments) and not arguments[index + 1].startswith("--"):
                    configured_port = arguments[index + 1]
                    index += 1
            else:
                remaining.append(argument)
            index += 1
        return remaining, configured_port

    @staticmethod
    def _validated_debugging_port(value: str) -> int:
        try:
            port = int(value)
        except ValueError as exc:
            raise RuntimeError("远程调试端口必须是有效整数") from exc
        if not 1 <= port <= 65535:
            raise RuntimeError("远程调试端口必须在 1 到 65535 之间")
        return port

    def _browser_manages_remote_debugging(self) -> bool:
        user_data_dir = self._configured_user_data_dir(self._browser_config)
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
