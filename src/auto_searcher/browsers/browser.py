"""High-level browser abstractions and shared Chromium implementation."""

import logging
import random
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from auto_searcher.schemas import BrowserConfig, SearchConfig
from .cdp import (
    CdpConnection,
    CdpError,
    CdpSession,
    Endpoint,
    port_is_available,
    read_active_endpoint,
    read_http_endpoint,
)

logger = logging.getLogger(__name__)


class Browser(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def open(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, keyword: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def browse_results(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> "Browser":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

class ChromiumBrowser(Browser):
    DEFAULT_DEBUGGER_PORT = 9222

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
                logger.info("发现可接管的 %s CDP 端点: %s", cls._name(), endpoint.address)
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
        command = [
            str(executable),
            f"--profile-directory={self._browser_config.profile_name}",
        ]
        if user_data_dir:
            command.append(f"--user-data-dir={user_data_dir}")

        debugger_address = self._browser_config.debugger_address
        if debugger_address:
            try:
                port = int(debugger_address.rsplit(":", maxsplit=1)[-1])
            except ValueError as exc:
                raise RuntimeError("远程调试地址端口无效") from exc
            expected_address: str | None = debugger_address
        elif port_is_available(self.DEFAULT_DEBUGGER_PORT):
            port = self.DEFAULT_DEBUGGER_PORT
            expected_address = f"127.0.0.1:{port}"
        else:
            port = 0
            expected_address = None
        command.append(f"--remote-debugging-port={port}")
        logger.info("启动 %s，通过 CDP WebSocket 连接", self.name)

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
            endpoint = read_active_endpoint(endpoint_dir, expected_address)
            if endpoint is None and expected_address:
                endpoint = read_http_endpoint(expected_address)
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
