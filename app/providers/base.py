from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface for interchangeable model providers."""

    @abstractmethod
    def generate(self, system_prompt: str, user_message: str) -> str:
        raise NotImplementedError
