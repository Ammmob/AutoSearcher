"""Edge browser control through a browser-level CDP WebSocket."""

import logging
import random
import time
from collections.abc import Callable

from auto_searcher.schemas import BrowserConfig, SearchConfig

from ..base_browser import Browser, SearchBrowser
from .connection import CdpConnection, CdpError
from .endpoint import EdgeEndpoint
from .page import CdpPage
from .search_interaction import CdpSearchInteraction

logger = logging.getLogger(__name__)


class CdpEdgeBrowser(Browser):
    def __init__(
        self,
        endpoint: EdgeEndpoint,
        browser_config: BrowserConfig,
        search_config: SearchConfig,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        connection: CdpConnection | None = None,
        interaction: CdpSearchInteraction | None = None,
        owns_browser: bool = False,
    ) -> None:
        self._endpoint = endpoint
        self._browser_config = browser_config
        self._search_config = search_config
        interaction_rng = rng or random.Random()
        self._connection = connection or CdpConnection(
            endpoint.websocket_url,
            browser_config.page_timeout_seconds,
        )
        self._interaction = interaction or CdpSearchInteraction(
            search_config,
            interaction_rng,
            sleeper,
        )
        self._owns_browser = owns_browser
        self._page: CdpPage | None = None

    def open(self) -> None:
        if self._page is not None:
            return
        self._connection.open()
        version = self._connection.command("Browser.getVersion")
        product = version.get("product")
        if not isinstance(product, str) or not product.startswith("Edg/"):
            self._connection.close()
            raise CdpError(f"CDP 端点不是 Microsoft Edge: {product!r}")

        target = self._connection.command(
            "Target.createTarget",
            {"url": "about:blank", "newWindow": False},
        )
        target_id = target.get("targetId")
        if not isinstance(target_id, str):
            self._connection.close()
            raise CdpError("Edge 未返回新标签页 targetId")
        attached = self._connection.command(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str):
            self._connection.close()
            raise CdpError("Edge 未返回标签页 sessionId")

        self._page = CdpPage(
            self._connection,
            target_id,
            session_id,
            self._browser_config.page_timeout_seconds,
        )
        try:
            self._page.prepare(SearchBrowser.WEBDRIVER_OVERRIDE_SCRIPT)
            self._page.navigate(self._search_config.url)
            self._page.activate()
            self._interaction.wait_after_open(self._page)
            self._log_browser_environment(product)
        except Exception:
            self.close()
            raise
        logger.info("已通过 CDP WebSocket 接管 Edge: %s", self._endpoint.address)

    def search(self, keyword: str) -> None:
        page = self._require_page()
        page.activate()
        self._interaction.search(page, keyword)
        logger.info("搜索结果已加载: %s", keyword)

    def browse_results(self) -> None:
        page = self._require_page()
        page.activate()
        self._interaction.browse_results(page)

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

    def _log_browser_environment(self, product: str) -> None:
        page = self._require_page()
        environment = page.evaluate(
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
