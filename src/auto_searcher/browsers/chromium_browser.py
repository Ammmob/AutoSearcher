"""Shared Chromium browser implementation."""

import logging
import random
import subprocess
import time
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path

from auto_searcher.schemas import BrowserConfig, SearchConfig

from .browser import Browser
from .cdp import (
    CdpConnection,
    CdpError,
    CdpSession,
    Endpoint,
    read_active_endpoint,
    read_http_endpoint,
)

logger = logging.getLogger(__name__)


class ChromiumBrowser(Browser):
    def __init__(
        self,
        browser_config: BrowserConfig,
        search_config: SearchConfig,
        session: CdpSession | None = None,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._browser_config = browser_config
        self._search_config = search_config
        self._session = session
        self._rng = rng
        self._sleep = sleeper

    def open(self) -> None:
        logger.info("使用浏览器: %s", self.name)
        if self._session is None:
            endpoint = self.detect_endpoint(self._browser_config)
            owns_browser = endpoint is None
            if endpoint is None:
                endpoint = self._launch()
            self._session = CdpSession(
                endpoint,
                self._search_config,
                self._browser_config.page_timeout_seconds,
                owns_browser=owns_browser,
                rng=self._rng,
                sleeper=self._sleep,
            )
        self._session.open()

    def search(self, keyword: str) -> None:
        self._require_session().search(keyword)

    def browse_results(self) -> None:
        self._require_session().browse_results()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def _require_session(self) -> CdpSession:
        if self._session is None:
            raise RuntimeError("CDP 会话尚未初始化")
        return self._session

    @classmethod
    def detect_endpoint(cls, browser_config: BrowserConfig) -> Endpoint | None:
        should_attach = browser_config.auto_detect_debugger or bool(
            browser_config.debugger_address
        )
        if not should_attach:
            return None

        candidates: list[Endpoint] = []
        if browser_config.user_data_dir:
            file_endpoint = read_active_endpoint(
                browser_config.user_data_dir,
                browser_config.debugger_address,
            )
            if file_endpoint is not None:
                candidates.append(file_endpoint)

        if browser_config.debugger_address:
            http_endpoint = read_http_endpoint(browser_config.debugger_address)
            if http_endpoint is not None:
                candidates.append(http_endpoint)
        elif browser_config.auto_detect_debugger:
            for address in cls._listening_addresses():
                http_endpoint = read_http_endpoint(address)
                if http_endpoint is not None:
                    candidates.append(http_endpoint)

        checked: set[str] = set()
        for endpoint in candidates:
            if endpoint.websocket_url in checked:
                continue
            checked.add(endpoint.websocket_url)
            if cls._is_supported_endpoint(
                endpoint,
                browser_config.page_timeout_seconds,
            ):
                logger.info(
                    "发现可接管的 %s CDP 端点: %s",
                    cls._name(),
                    endpoint.address,
                )
                return endpoint
        return None

    @classmethod
    def _is_supported_endpoint(cls, endpoint: Endpoint, timeout: float) -> bool:
        connection = CdpConnection(endpoint.websocket_url, timeout)
        try:
            connection.open()
            version = connection.command("Browser.getVersion")
        except CdpError:
            return False
        finally:
            connection.close()
        product = version.get("product")
        return isinstance(product, str) and cls._supports_product(product)

    def _launch(self) -> Endpoint:
        executable = self._find_executable()
        if executable is None:
            raise RuntimeError(f"没有找到 {self.name}")
        if self._process_is_running():
            raise RuntimeError(
                f"{self.name} 正在运行，但没有发现可用的 CDP WebSocket。"
                f"请完全退出 {self.name}，或启用远程调试后重试。"
            )

        user_data_dir = self._browser_config.user_data_dir
        command = [str(executable)]
        logger.info("启动 %s，等待浏览器开放 CDP WebSocket", self.name)
        logger.debug("浏览器启动参数: %s", subprocess.list2cmdline(command))

        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(f"无法启动 {self.name}: {exc}") from exc

        deadline = time.monotonic() + min(
            self._browser_config.page_timeout_seconds,
            10,
        )
        endpoint_dir = user_data_dir or self._default_user_data_dir()
        while time.monotonic() < deadline:
            endpoint = read_active_endpoint(endpoint_dir)
            if endpoint is not None and self._is_supported_endpoint(
                endpoint,
                self._browser_config.page_timeout_seconds,
            ):
                return endpoint
            self._sleep(0.2)
        raise RuntimeError(
            f"{self.name} 已启动，但没有开放可用的 CDP WebSocket。"
            f"{self._remote_debugging_hint()}"
        )

    @classmethod
    @abstractmethod
    def _name(cls) -> str:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _find_executable() -> Path | None:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _process_is_running() -> bool:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _listening_addresses() -> tuple[str, ...]:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _default_user_data_dir() -> Path:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _supports_product(product: str) -> bool:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _remote_debugging_hint() -> str:
        raise NotImplementedError
