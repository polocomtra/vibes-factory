"""Build model context without coupling the runtime to provider SDKs."""

from dataclasses import dataclass
from typing import Literal, cast

from ..model_providers.contracts import ModelMessage, ModelRequest
from .contracts import AgentRunRequest, SessionMessage


@dataclass(frozen=True, slots=True)
class ContextBuildResult:
    request: ModelRequest
    input_token_estimate: int


def _model_config(stored: dict[str, object]) -> dict[str, object]:
    nested = stored.get("config")
    return cast(dict[str, object], nested) if isinstance(nested, dict) else stored


def _message_content(message: SessionMessage) -> str:
    return message.content


def _provider_role(message: SessionMessage) -> Literal["user", "assistant", "tool"]:
    return cast(Literal["user", "assistant", "tool"], message.role.lower())


class ContextBuilder:
    """Create the Phase 4 text-only ModelRequest and approximate token count."""

    def build(self, request: AgentRunRequest) -> ContextBuildResult:
        messages = [
            ModelMessage(
                role=_provider_role(message),
                content=_message_content(message),
            )
            for message in request.session.messages
            if message.role != "SYSTEM"
        ]
        messages.append(
            ModelMessage(role="user", content=request.input.text.strip())
        )
        config = _model_config(request.agent_version.model_options)
        provider = request.agent_version.model_provider.strip().lower()
        model_name = request.agent_version.model_name.strip().lower()
        # Azure OpenAI reasoning models and Gemini 3.8 Flash reject the legacy
        # temperature sampling parameter. Keep reading old agent configs for
        # compatibility, but omit the field from the actual model request.
        temperature = (
            None
            if provider == "azure_openai"
            or (provider == "google" and model_name == "gemini-3.8-flash")
            else config.get("temperature")
        )
        max_output_tokens = config.get("max_output_tokens", 1024)
        model_request = ModelRequest(
            provider=provider,
            model=request.agent_version.model_name,
            messages=tuple(messages),
            system_instruction=request.agent_version.instructions,
            temperature=temperature if isinstance(temperature, (int, float)) else None,
            max_output_tokens=(
                max_output_tokens if isinstance(max_output_tokens, int) else 1024
            ),
            stream=False,
        )
        input_text = request.agent_version.instructions + "\n" + "\n".join(
            message.content for message in messages
        )
        return ContextBuildResult(
            request=model_request,
            input_token_estimate=max(1, (len(input_text) + 3) // 4),
        )
