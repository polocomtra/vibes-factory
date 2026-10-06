"""OpenRouter adapter using its OpenAI-compatible chat API."""

from .deepseek import DeepSeekProvider


class OpenRouterProvider(DeepSeekProvider):
    provider_id = "openrouter"
    default_base_url = "https://openrouter.ai/api/v1"
