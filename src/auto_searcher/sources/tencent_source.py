from collections.abc import Sequence
from typing import Any

from .base_source import HttpSource


class TencentSource(HttpSource):
    url = "https://r.inews.qq.com/gw/event/hot_ranking_list?page_size=50"

    @property
    def name(self) -> str:
        return "tencent"

    def parse(self, data: Any) -> Sequence[str]:
        id_list = data.get("idlist", []) if isinstance(data, dict) else []
        if not id_list or not isinstance(id_list[0], dict):
            return []
        return [
            item["title"]
            for item in id_list[0].get("newslist", [])
            if isinstance(item, dict) and item.get("title")
        ]
