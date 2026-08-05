from collections.abc import Sequence
from typing import Any

from .cached_source import CachedSource


class BaiduSource(CachedSource):
    url = "https://top.baidu.com/api/board?tab=realtime"

    @property
    def name(self) -> str:
        return "baidu"

    def parse(self, data: Any) -> Sequence[str]:
        cards = data.get("data", {}).get("cards", []) if isinstance(data, dict) else []
        if not cards or not isinstance(cards[0], dict):
            return []
        return [
            item["word"]
            for item in cards[0].get("content", [])
            if isinstance(item, dict) and item.get("word")
        ]
