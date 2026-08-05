"""Browser backend contract and CDP implementation."""

import logging
import random
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from auto_searcher.schemas import BrowserConfig, SearchConfig
from auto_searcher.utils.path_utils import default_edge_user_data_dir

from .cdp import (
    CdpConnection,
    CdpError,
    CdpPage,
    EdgeEndpoint,
    read_edge_endpoint,
    read_http_endpoint,
)
from .edge_runtime import (
    edge_process_is_running,
    find_edge_executable,
    listening_edge_addresses,
    port_is_available,
)
from .interaction import CdpInteraction, Interaction

logger = logging.getLogger(__name__)

NAVIGATOR_OVERRIDE_SCRIPT = """
    if (navigator.webdriver === true) {
        const prototype = Navigator.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(
            prototype,
            'webdriver'
        );
        Object.defineProperty(prototype, 'webdriver', {
            ...descriptor,
            get: () => false
        });
    }
"""


class Backend(ABC):
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


class CdpBackend(Backend):
    DEFAULT_DEBUGGER_PORT = 9222

    def __init__(
        self,
        browser_config: BrowserConfig,
        search_config: SearchConfig,
        endpoint: EdgeEndpoint | None = None,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        connection: CdpConnection | None = None,
        interaction: Interaction | None = None,
    ) -> None:
        self._browser_config = browser_config
        self._search_config = search_config
        self._endpoint = endpoint
        self._rng = rng or random.Random()
        self._sleep = sleeper
        self._connection = connection
        self._interaction = interaction
        self._page: CdpPage | None = None
        self._owns_browser = False

    def open(self) -> None:
        if self._page is not None:
            return
        endpoint = self._endpoint or self.detect_endpoint(self._browser_config)
        if endpoint is None:
            endpoint = self._launch_edge()
            self._owns_browser = True
        self._endpoint = endpoint
        connection = self._connection or CdpConnection(
            endpoint.websocket_url,
            self._browser_config.page_timeout_seconds,
        )
        self._connection = connection
        connection.open()
        version = connection.command("Browser.getVersion")
        product = version.get("product")
        if not isinstance(product, str) or not product.startswith("Edg/"):
            connection.close()
            raise CdpError(f"CDP 端点不是 Microsoft Edge: {product!r}")

        target = connection.command(
            "Target.createTarget",
            {"url": "about:blank", "newWindow": False},
        )
        target_id = target.get("targetId")
        if not isinstance(target_id, str):
            connection.close()
            raise CdpError("Edge 未返回新标签页 targetId")
        attached = connection.command(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str):
            connection.close()
            raise CdpError("Edge 未返回标签页 sessionId")

        page = CdpPage(
            connection,
            target_id,
            session_id,
            self._browser_config.page_timeout_seconds,
        )
        self._page = page
        self._interaction = self._interaction or CdpInteraction(
            page,
            self._search_config,
            self._rng,
            self._sleep,
        )
        try:
            page.prepare(NAVIGATOR_OVERRIDE_SCRIPT)
            page.navigate(self._search_config.url)
            page.activate()
            self._interaction.wait_after_open()
            self._log_browser_environment(product)
        except Exception:
            self.close()
            raise
        logger.info("已通过 CDP WebSocket 接管 Edge: %s", endpoint.address)

    def search(self, keyword: str) -> None:
        self._require_page().activate()
        self._require_interaction().search(keyword)
        logger.info("搜索结果已加载: %s", keyword)

    def browse_results(self) -> None:
        self._require_page().activate()
        self._require_interaction().browse_results()

    def close(self) -> None:
        page = self._page
        connection = self._connection
        self._page = None
        try:
            if connection is not None and self._owns_browser and page is not None:
                connection.command("Browser.close")
            elif page is not None:
                page.close()
        except CdpError as exc:
            logger.debug("关闭 CDP 标签页失败: %s", exc)
        finally:
            if connection is not None:
                connection.close()

    @classmethod
    def detect_endpoint(
        cls,
        browser_config: BrowserConfig,
    ) -> EdgeEndpoint | None:
        should_attach = browser_config.auto_detect_debugger or bool(
            browser_config.debugger_address
        )
        if not should_attach:
            return None

        candidates: list[EdgeEndpoint] = []
        if browser_config.user_data_dir:
            file_endpoint = read_edge_endpoint(
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
            for address in listening_edge_addresses():
                http_endpoint = read_http_endpoint(address)
                if http_endpoint is not None:
                    candidates.append(http_endpoint)

        checked: set[str] = set()
        for endpoint in candidates:
            if endpoint.websocket_url in checked:
                continue
            checked.add(endpoint.websocket_url)
            if cls._is_edge_endpoint(endpoint, browser_config.page_timeout_seconds):
                logger.info("发现可接管的 Edge CDP 端点: %s", endpoint.address)
                return endpoint
        return None

    @staticmethod
    def _is_edge_endpoint(endpoint: EdgeEndpoint, timeout: float) -> bool:
        connection = CdpConnection(endpoint.websocket_url, timeout)
        try:
            connection.open()
            version = connection.command("Browser.getVersion")
        except CdpError:
            return False
        finally:
            connection.close()
        product = version.get("product")
        return isinstance(product, str) and product.startswith("Edg/")

    def _launch_edge(self) -> EdgeEndpoint:
        executable = find_edge_executable()
        if executable is None:
            raise RuntimeError("没有找到 Microsoft Edge")
        if edge_process_is_running():
            raise RuntimeError(
                "Edge 正在运行，但没有发现可用的 CDP WebSocket。"
                "请完全退出 Edge，或启用远程调试后重试。"
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
        logger.info("启动 Edge，通过 CDP WebSocket 连接")

        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(f"无法启动 Edge: {exc}") from exc

        deadline = time.monotonic() + min(
            self._browser_config.page_timeout_seconds,
            10,
        )
        endpoint_dir = user_data_dir or default_edge_user_data_dir()
        while time.monotonic() < deadline:
            endpoint = read_edge_endpoint(endpoint_dir, expected_address)
            if endpoint is None and expected_address:
                endpoint = read_http_endpoint(expected_address)
            if endpoint is not None and self._is_edge_endpoint(
                endpoint,
                self._browser_config.page_timeout_seconds,
            ):
                return endpoint
            self._sleep(0.2)
        raise RuntimeError(
            "Edge 已启动，但没有开放可用的 CDP WebSocket。"
            "Edge 151 请在 edge://inspect 中启用远程调试。"
        )

    def _require_page(self) -> CdpPage:
        if self._page is None:
            raise RuntimeError("浏览器尚未打开")
        return self._page

    def _require_interaction(self) -> Interaction:
        if self._interaction is None:
            raise RuntimeError("搜索交互尚未初始化")
        return self._interaction

    def _log_browser_environment(self, product: str) -> None:
        environment = self._require_page().evaluate(
            """
            ({
                webdriver: navigator.webdriver,
                language: navigator.language,
                languages: navigator.languages,
                platform: navigator.platform,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                screen: `${screen.width}x${screen.height}`,
                viewport: `${innerWidth}x${innerHeight}`,
                pixelRatio: devicePixelRatio
            })
            """
        )
        logger.debug("CDP 浏览器版本: %s", product)
        logger.debug("浏览器页面环境: %s", environment)
