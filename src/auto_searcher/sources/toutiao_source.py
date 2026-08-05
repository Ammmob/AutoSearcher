from collections.abc import Sequence
from typing import Any

from .base_source import HttpSource


class ToutiaoSource(HttpSource):
    url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"

    @property
    def name(self) -> str:
        return "toutiao"

    def parse(self, data: Any) -> Sequence[str]:
        items = data.get("data", []) if isinstance(data, dict) else []
        return [
            item["Title"]
            for item in items
            if isinstance(item, dict) and item.get("Title")
        ]
