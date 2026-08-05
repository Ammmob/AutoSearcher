import csv
import logging
import pkgutil
import random
import socket
import subprocess
import time
from collections.abc import Callable
from io import StringIO
from pathlib import Path

from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.webdriver import WebDriver as EdgeWebDriver
from selenium.webdriver.remote.webdriver import WebDriver

from auto_searcher.schemas import BrowserConfig, SearchConfig
from auto_searcher.utils.path_utils import default_edge_user_data_dir

from .base_browser import SearchBrowser
from .cdp import (
    CdpConnection,
    CdpEdgeBrowser,
    CdpError,
    EdgeEndpoint,
    read_edge_endpoint,
)
from .edge_runtime import find_edge_executable, read_edge_major_version
from .search_interaction import SearchInteraction

logger = logging.getLogger(__name__)


class EdgeBrowser(SearchBrowser):
    DEFAULT_DEBUGGER_PORT = 9222
    REQUIRED_SELENIUM_RESOURCES = (
        "findElements.js",
        "getAttribute.js",
        "isDisplayed.js",
    )

    def __init__(
        self,
        browser_config: BrowserConfig,
        search_config: SearchConfig,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        interaction: SearchInteraction | None = None,
    ) -> None:
        super().__init__(
            browser_config,
            search_config,
            rng,
            sleeper,
            interaction,
        )
        self._cdp_browser: CdpEdgeBrowser | None = None
        self._sleep = sleeper

    def open(self) -> None:
        self.validate_runtime()
        logger.info("使用浏览器: Edge")
        if self._open_cdp_if_available():
            return
        if self._launch_cdp_for_modern_edge():
            return
        super().open()

    def search(self, keyword: str) -> None:
        if self._cdp_browser is not None:
            self._cdp_browser.search(keyword)
            return
        super().search(keyword)

    def browse_results(self) -> None:
        if self._cdp_browser is not None:
            self._cdp_browser.browse_results()
            return
        super().browse_results()

    def close(self) -> None:
        if self._cdp_browser is not None:
            try:
                self._cdp_browser.close()
            finally:
                self._cdp_browser = None
            return
        super().close()

    def _open_cdp_if_available(self) -> bool:
        user_data_dir = self._browser_config.user_data_dir
        configured_address = self._browser_config.debugger_address
        should_attach = self._browser_config.auto_detect_debugger or bool(
            configured_address
        )
        if not should_attach or not user_data_dir:
            return False
        endpoint = read_edge_endpoint(user_data_dir, configured_address)
        if endpoint is None:
            return False
        if self._get_debugger_product(endpoint.address):
            return False

        cdp_browser = CdpEdgeBrowser(
            endpoint,
            self._browser_config,
            self._search_config,
        )
        try:
            cdp_browser.open()
        except CdpError as exc:
            logger.info("CDP WebSocket 接管失败: %s", exc)
            return False
        self._cdp_browser = cdp_browser
        return True

    @classmethod
    def detect_cdp_endpoint(
        cls,
        browser_config: BrowserConfig,
    ) -> EdgeEndpoint | None:
        configured_address = browser_config.debugger_address
        should_attach = browser_config.auto_detect_debugger or bool(
            configured_address
        )
        if not should_attach or not browser_config.user_data_dir:
            return None
        endpoint = read_edge_endpoint(
            browser_config.user_data_dir,
            configured_address,
        )
        if endpoint is None or cls._get_debugger_product(endpoint.address):
            return None

        connection = CdpConnection(
            endpoint.websocket_url,
            browser_config.page_timeout_seconds,
        )
        try:
            connection.open()
            version = connection.command("Browser.getVersion")
        except CdpError:
            return None
        finally:
            connection.close()
        product = version.get("product")
        if isinstance(product, str) and product.startswith("Edg/"):
            return endpoint
        return None

    def _launch_cdp_for_modern_edge(self) -> bool:
        executable = find_edge_executable()
        major_version = (
            read_edge_major_version(executable) if executable is not None else None
        )
        if major_version is None or major_version < 151:
            return False
        if self._edge_process_is_running():
            raise RuntimeError(
                "Edge 151 正在运行，但没有发现可用的 CDP WebSocket。"
                "请在 edge://inspect 中启用远程调试后重试。"
            )

        command = [
            str(executable),
            f"--profile-directory={self._browser_config.profile_name}",
        ]
        user_data_dir = self._browser_config.user_data_dir
        if user_data_dir:
            try:
                uses_default_directory = (
                    Path(user_data_dir).resolve() == default_edge_user_data_dir()
                )
            except OSError:
                uses_default_directory = True
            if not uses_default_directory:
                command.extend(
                    [
                        f"--user-data-dir={user_data_dir}",
                        "--remote-debugging-port=0",
                    ]
                )

        logger.info("启动 Edge 151，等待 CDP WebSocket")
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(f"无法启动 Edge 151: {exc}") from exc

        deadline = time.monotonic() + min(
            self._browser_config.page_timeout_seconds,
            10,
        )
        while time.monotonic() < deadline:
            endpoint = read_edge_endpoint(user_data_dir or default_edge_user_data_dir())
            if endpoint is not None:
                cdp_browser = CdpEdgeBrowser(
                    endpoint,
                    self._browser_config,
                    self._search_config,
                    owns_browser=True,
                )
                try:
                    cdp_browser.open()
                except CdpError:
                    cdp_browser.close()
                else:
                    self._cdp_browser = cdp_browser
                    return True
            self._sleep(0.2)
        raise RuntimeError(
            "Edge 151 已启动，但没有开放 CDP WebSocket。"
            "请打开 edge://inspect，启用远程调试后重新运行。"
        )

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
