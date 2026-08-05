import http.client
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType

from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.remote.webdriver import WebDriver

from auto_searcher.schemas import BrowserConfig, SearchConfig

from .search_interaction import SearchInteraction

logger = logging.getLogger(__name__)


class Browser(ABC):
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


class SearchBrowser(Browser, ABC):
    SEARCH_BOX_LOCATOR = SearchInteraction.SEARCH_BOX_LOCATOR
    WEBDRIVER_OVERRIDE_SCRIPT = """
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

    def __init__(
        self,
        browser_config: BrowserConfig,
        search_config: SearchConfig,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        interaction: SearchInteraction | None = None,
    ) -> None:
        self._browser_config = browser_config
        self._search_config = search_config
        interaction_rng = rng or random.Random()
        self._interaction = interaction or SearchInteraction(
            search_config,
            browser_config.page_timeout_seconds,
            interaction_rng,
            sleeper,
        )
        self._driver: WebDriver | None = None
        self._owns_driver = True
        self._created_tab: str | None = None

    @property
    def driver(self) -> WebDriver:
        if self._driver is None:
            raise RuntimeError("浏览器尚未打开")
        return self._driver

    def open(self) -> None:
        if self._driver is not None:
            return
        configured_debugger = self._browser_config.debugger_address
        debugger_address = configured_debugger
        debugger_product: str | None = None
        debugger_is_verified = False
        if self._browser_config.auto_detect_debugger:
            user_data_dir = self._browser_config.user_data_dir
            if user_data_dir:
                debugger_address = self.detect_debugger_address(user_data_dir)
            if debugger_address:
                logger.info("自动识别远程调试地址: %s", debugger_address)
                debugger_is_verified = True
            else:
                logger.info("未检测到 Edge 远程调试端口")

        if debugger_address:
            if not debugger_is_verified:
                logger.info("检查是否存在可接管的浏览器: %s", debugger_address)
                debugger_product = self._get_debugger_product(debugger_address)
            if (
                debugger_product
                and not self._supports_debugger(debugger_product)
            ):
                raise RuntimeError(
                    "调试地址对应的浏览器与 browser.type 不匹配："
                    f"{debugger_product}"
                )
            if debugger_is_verified or debugger_product:
                try:
                    self._driver = self._attach(debugger_address)
                    self._owns_driver = False
                    logger.info("已接管浏览器: %s", debugger_address)
                except WebDriverException:
                    logger.info("接管失败，准备启动新浏览器")
            else:
                logger.info("未发现可接管的浏览器，准备启动新浏览器")

        if self._driver is None:
            try:
                self._before_launch()
                self._driver = self._launch(configured_debugger)
                self._owns_driver = True
            except SessionNotCreatedException as exc:
                profile = self._browser_config.user_data_dir or "临时配置目录"
                raise RuntimeError(
                    f"浏览器启动失败，请确认配置目录未被占用：{profile}"
                ) from exc

        self.driver.set_page_load_timeout(self._browser_config.page_timeout_seconds)
        if self._owns_driver:
            self._created_tab = self.driver.current_window_handle
        else:
            self.driver.switch_to.new_window("tab")
            self._created_tab = self.driver.current_window_handle
        self._prepare_page_context()
        self.driver.get(self._search_config.url)
        self._activate_tab()
        self._interaction.wait_after_open(self.driver)
        self._log_browser_environment()

    def search(self, keyword: str) -> None:
        self._activate_tab()
        self._interaction.search(self.driver, keyword)
        logger.info("搜索结果已加载: %s", keyword)

    def browse_results(self) -> None:
        self._activate_tab()
        self._interaction.browse_results(self.driver)

    def close(self) -> None:
        if self._driver is None:
            return
        try:
            if self._owns_driver:
                self._driver.quit()
            elif self._created_tab in self._driver.window_handles:
                self._driver.switch_to.window(self._created_tab)
                self._driver.close()
        finally:
            self._driver = None
            self._created_tab = None

    def _attach(self, debugger_address: str) -> WebDriver:
        options = self._create_options()
        options.add_experimental_option("debuggerAddress", debugger_address)
        return self._create_driver(options)

    def _launch(self, debugger_address: str | None) -> WebDriver:
        logger.info("启动新浏览器")
        options = self._create_options()
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation", "enable-logging"],
        )
        options.add_experimental_option("useAutomationExtension", False)
        if self._browser_config.user_data_dir:
            options.add_argument(
                f"--user-data-dir={self._browser_config.user_data_dir}"
            )
        options.add_argument(f"--profile-directory={self._browser_config.profile_name}")
        if debugger_address:
            port = debugger_address.rsplit(":", maxsplit=1)[-1]
        else:
            port = str(self._automatic_debugger_port())
        options.add_argument(f"--remote-debugging-port={port}")
        return self._create_driver(options)

    def _before_launch(self) -> None:
        """Validate conditions that are specific to a browser implementation."""

    def _automatic_debugger_port(self) -> int:
        return 0

    @classmethod
    def detect_debugger_address(cls, user_data_dir: str) -> str | None:
        """Find a live debugger endpoint for this browser implementation."""
        return None

    def _prepare_page_context(self) -> None:
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": self.WEBDRIVER_OVERRIDE_SCRIPT},
        )

    def _activate_tab(self) -> None:
        if self._created_tab in self.driver.window_handles:
            self.driver.switch_to.window(self._created_tab)
        self.driver.execute_cdp_cmd("Page.bringToFront", {})
        self.driver.execute_script("window.focus();")

    def _log_browser_environment(self) -> None:
        environment = self.driver.execute_script(
            """
            return {
                webdriver: navigator.webdriver,
                language: navigator.language,
                languages: navigator.languages,
                platform: navigator.platform,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                screen: `${screen.width}x${screen.height}`,
                viewport: `${window.innerWidth}x${window.innerHeight}`,
                pixelRatio: window.devicePixelRatio
            };
            """
        )
        if not isinstance(environment, dict):
            return
        if environment.get("webdriver") is not False:
            logger.warning(
                "浏览器自动化属性与普通 Edge 不一致: navigator.webdriver=%r",
                environment.get("webdriver"),
            )
        logger.debug("浏览器页面环境: %s", environment)

    @staticmethod
    def _get_debugger_product(debugger_address: str) -> str | None:
        connection: http.client.HTTPConnection | None = None
        try:
            host, port_text = debugger_address.rsplit(":", maxsplit=1)
            connection = http.client.HTTPConnection(host, int(port_text), timeout=0.5)
            connection.request("GET", "/json/version")
            response = connection.getresponse()
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
            product = data.get("Browser")
            return product if isinstance(product, str) else None
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        finally:
            if connection is not None:
                connection.close()

    @abstractmethod
    def _create_options(self) -> ChromiumOptions:
        raise NotImplementedError

    @abstractmethod
    def _create_driver(self, options: ChromiumOptions) -> WebDriver:
        raise NotImplementedError

    @abstractmethod
    def _supports_debugger(self, product: str) -> bool:
        raise NotImplementedError
