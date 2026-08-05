"""Search interaction contract and CDP implementation."""

import json
import math
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from auto_searcher.schemas import SearchConfig

from .cdp import CdpPage


class Interaction(ABC):
    @abstractmethod
    def wait_after_open(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, keyword: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def browse_results(self) -> None:
        raise NotImplementedError


class CdpInteraction(Interaction):
    WORD_BOUNDARIES = frozenset(" \t-_/,.;:!?，。；：！？、")
    SEARCH_BOX_EXPRESSION = """
        (() => {
            const element = document.querySelector('[name="q"]');
            if (!element || element.disabled) return null;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            if (
                style.visibility === 'hidden' ||
                style.display === 'none' ||
                rect.width <= 0 ||
                rect.height <= 0
            ) return null;
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2
            };
        })()
    """
    PAGE_METRICS_EXPRESSION = """
        (() => {
            const body = document.body;
            const root = document.documentElement;
            return {
                height: Math.max(
                    body ? body.scrollHeight : 0,
                    root ? root.scrollHeight : 0
                ),
                viewport: window.innerHeight,
                width: window.innerWidth,
                y: window.scrollY
            };
        })()
    """

    def __init__(
        self,
        page: CdpPage,
        config: SearchConfig,
        rng: random.Random | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._page = page
        self._config = config
        self._rng = rng or random.Random()
        self._sleep = sleeper

    def wait_after_open(self) -> None:
        self._sleep(self._page_dwell_seconds((2.0, 3.0)))

    def search(self, keyword: str) -> None:
        previous_url = str(self._page.evaluate("location.href"))
        position = self._page.wait_for_value(
            self.SEARCH_BOX_EXPRESSION,
            "等待搜索框超时",
        )
        if not isinstance(position, dict):
            raise RuntimeError("搜索框位置无效")
        x = float(position["x"])
        y = float(position["y"])
        self._move_and_click(x, y)
        self._select_all()
        self._press_key("Backspace", "Backspace", 8)

        for index, character in enumerate(keyword):
            self._page.command("Input.insertText", {"text": character})
            self._sleep(self._typing_delay(keyword, index, character))

        self._sleep(self._rng.uniform(0.5, 1.0))
        self._press_key("Enter", "Enter", 13)
        expected_previous_url = json.dumps(previous_url, ensure_ascii=False)
        self._page.wait_for_value(
            "location.pathname.includes('/search') && "
            f"location.href !== {expected_previous_url} ? location.href : null",
            "等待搜索结果页超时",
        )
        self._sleep(self._page_dwell_seconds((2.0, 3.0), keyword))

    def browse_results(self) -> None:
        metrics = self._page_metrics()
        scrollable = max(metrics["height"] - metrics["viewport"], 0)
        if scrollable <= 0:
            self._sleep(self._rng.uniform(1.0, 2.0))
            return

        requested = self._rng.randint(*self._config.scroll_count)
        useful_steps = max(1, math.ceil(scrollable / 500))
        for _ in range(min(requested, useful_steps)):
            metrics = self._page_metrics()
            remaining = max(
                metrics["height"] - metrics["viewport"] - metrics["y"],
                0,
            )
            if remaining <= 0:
                break
            distance = min(self._rng.randint(300, 800), round(remaining))
            self._scroll(metrics, distance)
            self._sleep(self._rng.uniform(*self._config.scroll_pause_seconds))
            if self._rng.random() < 0.2 and metrics["y"] + distance > 200:
                self._scroll(metrics, -self._rng.randint(120, 240))
                self._sleep(self._rng.uniform(1.0, 2.0))

    def _move_and_click(self, x: float, y: float) -> None:
        steps = self._rng.randint(8, 14)
        start_x = max(0.0, x + self._rng.uniform(-180, 180))
        start_y = max(0.0, y + self._rng.uniform(-120, 120))
        for step in range(1, steps + 1):
            progress = step / steps
            eased = progress * progress * (3 - 2 * progress)
            current_x = start_x + (x - start_x) * eased
            current_y = start_y + (y - start_y) * eased
            self._page.command(
                "Input.dispatchMouseEvent",
                {"type": "mouseMoved", "x": current_x, "y": current_y},
            )
            self._sleep(self._rng.uniform(0.008, 0.025))
        self._sleep(self._rng.uniform(0.15, 0.45))
        for event_type in ("mousePressed", "mouseReleased"):
            self._page.command(
                "Input.dispatchMouseEvent",
                {
                    "type": event_type,
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                },
            )

    def _select_all(self) -> None:
        self._page.command(
            "Input.dispatchKeyEvent",
            {
                "type": "rawKeyDown",
                "key": "a",
                "code": "KeyA",
                "windowsVirtualKeyCode": 65,
                "modifiers": 2,
                "commands": ["SelectAll"],
            },
        )
        self._page.command(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "a",
                "code": "KeyA",
                "windowsVirtualKeyCode": 65,
                "modifiers": 2,
            },
        )

    def _press_key(self, key: str, code: str, virtual_key: int) -> None:
        for event_type in ("rawKeyDown", "keyUp"):
            self._page.command(
                "Input.dispatchKeyEvent",
                {
                    "type": event_type,
                    "key": key,
                    "code": code,
                    "windowsVirtualKeyCode": virtual_key,
                },
            )

    def _scroll(self, metrics: dict[str, float], distance: int) -> None:
        self._page.command(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": metrics["width"] / 2,
                "y": metrics["viewport"] / 2,
                "deltaX": 0,
                "deltaY": distance,
            },
        )

    def _typing_delay(self, keyword: str, index: int, character: str) -> float:
        low, high = self._config.typing_delay_seconds
        delay = self._rng.triangular(low, high, low + (high - low) * 0.4)
        if character in self.WORD_BOUNDARIES:
            delay += self._rng.uniform(0.08, 0.22)
        elif index and index % 6 == 0 and index < len(keyword) - 1:
            delay += self._rng.uniform(0.03, 0.12)
        return delay

    def _page_dwell_seconds(
        self,
        base_range: tuple[float, float],
        keyword: str = "",
    ) -> float:
        metrics = self._page_metrics()
        scrollable = max(metrics["height"] - metrics["viewport"], 0)
        content_bonus = min(scrollable / 3000, 1.5)
        keyword_bonus = min(len(keyword) / 50, 0.6)
        return self._rng.uniform(*base_range) + content_bonus + keyword_bonus

    def _page_metrics(self) -> dict[str, float]:
        raw = self._page.evaluate(self.PAGE_METRICS_EXPRESSION)
        if not isinstance(raw, dict):
            return {"height": 0.0, "viewport": 0.0, "width": 0.0, "y": 0.0}
        return {
            key: float(raw.get(key) or 0)
            for key in ("height", "viewport", "width", "y")
        }
