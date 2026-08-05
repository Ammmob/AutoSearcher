from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import requests

from auto_searcher.schemas import Topic


class Source(ABC):
    """Contract implemented by one online topic provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch(self) -> Sequence[Topic]:
        raise NotImplementedError


class HttpSource(Source):
    """Template-method base class shared by JSON topic APIs."""

    url: str

    def __init__(
        self,
        timeout_seconds: float = 10,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def fetch(self) -> Sequence[Topic]:
        response = self._session.get(
            self.url,
            timeout=self._timeout_seconds,
            headers={"User-Agent": "AutoSearcher/0.1 (+local automation tool)"},
        )
        response.raise_for_status()
        texts = self.parse(response.json())
        return [
            Topic(text=text.strip(), source=self.name, rank=index)
            for index, text in enumerate(texts, start=1)
            if isinstance(text, str) and text.strip()
        ]

    @abstractmethod
    def parse(self, data: Any) -> Sequence[str]:
        raise NotImplementedError
