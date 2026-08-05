"""Browser-independent CDP session and search workflow."""

import logging
import random
import time
from collections.abc import Callable

from auto_searcher.schemas import SearchConfig

from .connection import CdpConnection, CdpError
from .endpoint import Endpoint
from .interaction import CdpInteraction
from .page import CdpPage

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


class CdpSession:
    def __init__(
        self,
        endpoint: Endpoint,
        search_config: SearchConfig,
        page_timeout_seconds: float,
        owns_browser: bool = False,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        connection: CdpConnection | None = None,
        interaction: CdpInteraction | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._search_config = search_config
        self._page_timeout_seconds = page_timeout_seconds
        self._owns_browser = owns_browser
        self._rng = rng or random.Random()
        self._sleep = sleeper
        self._connection = connection or CdpConnection(
            endpoint.websocket_url,
            page_timeout_seconds,
        )
        self._interaction = interaction
        self._page: CdpPage | None = None

    def open(self) -> None:
        if self._page is not None:
            return
        self._connection.open()
        version = self._connection.command("Browser.getVersion")
        product = version.get("product")
        if not isinstance(product, str):
            self._connection.close()
            raise CdpError("CDP 端点没有返回有效的浏览器版本")

        target = self._connection.command(
            "Target.createTarget",
            {"url": "about:blank", "newWindow": False},
        )
        target_id = target.get("targetId")
        if not isinstance(target_id, str):
            self._connection.close()
            raise CdpError("浏览器未返回新标签页 targetId")
        attached = self._connection.command(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str):
            self._connection.close()
            raise CdpError("浏览器未返回标签页 sessionId")

        page = CdpPage(
            self._connection,
            target_id,
            session_id,
            self._page_timeout_seconds,
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
        logger.info("已连接 CDP WebSocket: %s", self._endpoint.address)

    def search(self, keyword: str) -> None:
        self._require_page().activate()
        self._require_interaction().search(keyword)
        logger.info("搜索结果已加载: %s", keyword)

    def browse_results(self) -> None:
        self._require_page().activate()
        self._require_interaction().browse_results()

    def close(self) -> None:
        page = self._page
        self._page = None
        try:
            if self._owns_browser and page is not None:
                self._connection.command("Browser.close")
            elif page is not None:
                page.close()
        except CdpError as exc:
            logger.debug("关闭 CDP 标签页失败: %s", exc)
        finally:
            self._connection.close()

    def _require_page(self) -> CdpPage:
        if self._page is None:
            raise RuntimeError("浏览器尚未打开")
        return self._page

    def _require_interaction(self) -> CdpInteraction:
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
