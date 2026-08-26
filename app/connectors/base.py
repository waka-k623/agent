from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    """Common interface for external business systems."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> dict[str, Any]:
        raise NotImplementedError
