"""Human-paced browser interactions for a search results workflow."""

import math
import random
import time
from collections.abc import Callable

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as conditions
from selenium.webdriver.support.ui import WebDriverWait

from auto_searcher.schemas import SearchConfig


class SearchInteraction:
    SEARCH_BOX_LOCATOR = (By.NAME, "q")
    WORD_BOUNDARIES = frozenset(" \t-_/,.;:!?，。；：！？、")

    def __init__(
        self,
        config: SearchConfig,
        page_timeout_seconds: float,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._page_timeout_seconds = page_timeout_seconds
        self._rng = rng or random.Random()
        self._sleep = sleeper

    def wait_after_open(self, driver: WebDriver) -> None:
        self._sleep(self._page_dwell_seconds(driver, (2.0, 3.0)))

    def search(self, driver: WebDriver, keyword: str) -> None:
        previous_url = driver.current_url
        search_box = WebDriverWait(driver, self._page_timeout_seconds).until(
            conditions.element_to_be_clickable(self.SEARCH_BOX_LOCATOR)
        )

        ActionChains(driver).move_to_element(search_box).pause(
            self._rng.uniform(0.15, 0.45)
        ).click().perform()
        ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(
            Keys.CONTROL
        ).send_keys(Keys.BACKSPACE).perform()

        typing = ActionChains(driver)
        for index, character in enumerate(keyword):
            typing.send_keys(character).pause(
                self._typing_delay(keyword, index, character)
            )
        typing.perform()

        ActionChains(driver).pause(self._rng.uniform(0.5, 1.0)).send_keys(
            Keys.ENTER
        ).perform()
        WebDriverWait(driver, self._page_timeout_seconds).until(
            lambda current: "/search" in current.current_url
            and current.current_url != previous_url
        )
        self._sleep(self._page_dwell_seconds(driver, (2.0, 3.0), keyword))

    def browse_results(self, driver: WebDriver) -> None:
        metrics = self._page_metrics(driver)
        scrollable = max(metrics["height"] - metrics["viewport"], 0)
        if scrollable <= 0:
            self._sleep(self._rng.uniform(1.0, 2.0))
            return

        requested = self._rng.randint(*self._config.scroll_count)
        useful_steps = max(1, math.ceil(scrollable / 500))
        count = min(requested, useful_steps)
        for _ in range(count):
            metrics = self._page_metrics(driver)
            remaining = max(
                metrics["height"] - metrics["viewport"] - metrics["y"],
                0,
            )
            if remaining <= 0:
                break

            distance = min(self._rng.randint(300, 800), round(remaining))
            ActionChains(driver).scroll_by_amount(0, distance).perform()
            self._sleep(self._rng.uniform(*self._config.scroll_pause_seconds))

            if self._rng.random() < 0.2 and metrics["y"] + distance > 200:
                reverse_distance = self._rng.randint(120, 240)
                ActionChains(driver).scroll_by_amount(
                    0, -reverse_distance
                ).perform()
                self._sleep(self._rng.uniform(1.0, 2.0))

    def _typing_delay(
        self,
        keyword: str,
        index: int,
        character: str,
    ) -> float:
        low, high = self._config.typing_delay_seconds
        delay = self._rng.triangular(low, high, low + (high - low) * 0.4)
        if character in self.WORD_BOUNDARIES:
            delay += self._rng.uniform(0.08, 0.22)
        elif index and index % 6 == 0 and index < len(keyword) - 1:
            delay += self._rng.uniform(0.03, 0.12)
        return delay

    def _page_dwell_seconds(
        self,
        driver: WebDriver,
        base_range: tuple[float, float],
        keyword: str = "",
    ) -> float:
        metrics = self._page_metrics(driver)
        scrollable = max(metrics["height"] - metrics["viewport"], 0)
        content_bonus = min(scrollable / 3000, 1.5)
        keyword_bonus = min(len(keyword) / 50, 0.6)
        return self._rng.uniform(*base_range) + content_bonus + keyword_bonus

    @staticmethod
    def _page_metrics(driver: WebDriver) -> dict[str, float]:
        raw = driver.execute_script(
            """
            const body = document.body;
            const root = document.documentElement;
            return {
                height: Math.max(
                    body ? body.scrollHeight : 0,
                    root ? root.scrollHeight : 0
                ),
                viewport: window.innerHeight,
                y: window.scrollY
            };
            """
        )
        if not isinstance(raw, dict):
            return {"height": 0.0, "viewport": 0.0, "y": 0.0}
        return {
            "height": float(raw.get("height") or 0),
            "viewport": float(raw.get("viewport") or 0),
            "y": float(raw.get("y") or 0),
        }
