"""Topic source interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from auto_searcher.schemas import Topic


class Source(ABC):
    """Contract implemented by one topic provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def fetch(self) -> Sequence[Topic]:
        raise NotImplementedError
