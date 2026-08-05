import csv
import logging
import pkgutil
import socket
import subprocess
from io import StringIO
from pathlib import Path

from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.webdriver import WebDriver as EdgeWebDriver
from selenium.webdriver.remote.webdriver import WebDriver

from auto_searcher.utils.path_utils import default_edge_user_data_dir

from .base_browser import SearchBrowser

logger = logging.getLogger(__name__)


class EdgeBrowser(SearchBrowser):
    DEFAULT_DEBUGGER_PORT = 9222
    REQUIRED_SELENIUM_RESOURCES = (
        "findElements.js",
        "getAttribute.js",
        "isDisplayed.js",
    )

    def open(self) -> None:
        self.validate_runtime()
        logger.info("使用浏览器: Edge")
        super().open()

    @classmethod
    def validate_runtime(cls) -> None:
        for resource_name in cls.REQUIRED_SELENIUM_RESOURCES:
            try:
                content = pkgutil.get_data(
                    "selenium.webdriver.remote",
                    resource_name,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"Selenium 运行资源缺失: {resource_name}"
                ) from exc
            if not content:
                raise RuntimeError(f"Selenium 运行资源缺失: {resource_name}")

    def _create_options(self) -> ChromiumOptions:
        return Options()

    def _create_driver(self, options: ChromiumOptions) -> WebDriver:
        service = Service(log_output=subprocess.DEVNULL)
        return EdgeWebDriver(options=options, service=service)

    def _automatic_debugger_port(self) -> int:
        if self._port_is_available(self.DEFAULT_DEBUGGER_PORT):
            logger.info("使用默认远程调试端口: %d", self.DEFAULT_DEBUGGER_PORT)
            return self.DEFAULT_DEBUGGER_PORT
        logger.info("端口 %d 已被占用，改用随机空闲端口", self.DEFAULT_DEBUGGER_PORT)
        return 0

    @staticmethod
    def _port_is_available(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    listener.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_EXCLUSIVEADDRUSE,
                        1,
                    )
                listener.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True

    @classmethod
    def detect_debugger_address(cls, user_data_dir: str) -> str | None:
        for address in cls._listening_edge_addresses():
            logger.info("验证远程调试地址: %s", address)
            product = cls._get_debugger_product(address)
            if product and product.startswith("Edg/"):
                return address
        return None

    @staticmethod
    def _listening_edge_addresses() -> tuple[str, ...]:
        edge_process_ids = EdgeBrowser._edge_process_ids()
        if not edge_process_ids:
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
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("无法读取 TCP 监听端口: %s", exc)
            return ()

        ports: set[int] = set()
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 5 or fields[-1] not in edge_process_ids:
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
    def _edge_process_ids() -> set[str]:
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    "IMAGENAME eq msedge.exe",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("无法读取 Edge 进程: %s", exc)
            return set()

        process_ids: set[str] = set()
        for row in csv.reader(StringIO(result.stdout)):
            if len(row) >= 2 and row[0].casefold() == "msedge.exe":
                process_ids.add(row[1])
        return process_ids

    def _before_launch(self) -> None:
        user_data_dir = self._browser_config.user_data_dir
        if not user_data_dir:
            return
        try:
            uses_default_directory = (
                Path(user_data_dir).resolve() == default_edge_user_data_dir()
            )
        except OSError:
            return
        if uses_default_directory and self._edge_process_is_running():
            raise RuntimeError(
                "无法启动新的 Edge：默认用户目录仍被 Edge 进程占用。"
                "Default 和 Profile 1 共用同一个 User Data 根目录。"
                "请完全退出 Edge（包括启动增强和后台扩展进程）后重试，"
                "或者先启用远程调试再由程序接管。"
            )

    @staticmethod
    def _edge_process_is_running() -> bool:
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    "IMAGENAME eq msedge.exe",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("无法检查 Edge 后台进程: %s", exc)
            return False
        return "msedge.exe" in result.stdout.casefold()

    def _supports_debugger(self, product: str) -> bool:
        return product.startswith("Edg/")
