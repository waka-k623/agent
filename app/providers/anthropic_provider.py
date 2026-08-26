import os

from anthropic import Anthropic

from app.providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

    def generate(self, system_prompt: str, user_message: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        return "\n".join(text_blocks)
