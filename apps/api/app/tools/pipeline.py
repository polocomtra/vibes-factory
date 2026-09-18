"""The single tool execution boundary shared by tests and AgentRuntime."""

from collections.abc import Mapping
from typing import Any

from ..config import get_settings
from ..models import ToolType, ToolVersion
from .contracts import (
    CredentialResolver,
    NoopToolGuardrailHook,
    ToolExecutionContext,
    ToolGuardrailHook,
    ToolResult,
    UnavailableCredentialResolver,
)
from .executors import FunctionToolRegistry, HttpToolExecutor
from .validation import SchemaDefinitionError, SchemaValidationError, validate

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "proxy-authorization",
        "secret",
        "set-cookie",
        "token",
        "x-api-key",
    }
)


class SecretRedactor:
    """Remove secret-shaped data before persistence, tracing or model context."""

    def redact(self, value: Any, secret_values: tuple[str, ...] = ()) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): self.redact(child, secret_values)
                for key, child in value.items()
                if str(key).lower() not in _SECRET_KEYS
            }
        if isinstance(value, list):
            return [self.redact(child, secret_values) for child in value]
        if isinstance(value, tuple):
            return [self.redact(child, secret_values) for child in value]
        if isinstance(value, str):
            redacted = value
            for secret in secret_values:
                if secret:
                    redacted = redacted.replace(secret, "[REDACTED]")
            return redacted
        return value


class ToolExecutionPipeline:
    def __init__(
        self,
        *,
        function_registry: FunctionToolRegistry | None = None,
        guardrail_hook: ToolGuardrailHook | None = None,
        secret_redactor: SecretRedactor | None = None,
        credential_resolver: CredentialResolver | None = None,
    ) -> None:
        self.function_registry = function_registry or FunctionToolRegistry(
            exa_api_key=get_settings().exa_api_key
        )
        self.guardrail_hook = guardrail_hook or NoopToolGuardrailHook()
        self.secret_redactor = secret_redactor or SecretRedactor()
        self.credential_resolver = (
            credential_resolver or UnavailableCredentialResolver()
        )

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        return ToolResult(ok=False, error_code=code, error_message=message)

    async def execute(
        self,
        version: ToolVersion,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        try:
            validate(dict(arguments), version.input_schema)
        except SchemaDefinitionError:
            return self._failure(
                "TOOL_SCHEMA_INVALID", "The tool schema definition is invalid."
            )
        except SchemaValidationError:
            return self._failure(
                "TOOL_ARGUMENTS_INVALID",
                "Tool arguments do not match the input schema.",
            )

        executor_type = version.executor_config.get("type", version.executor_type.value)
        if executor_type != version.executor_type.value:
            return self._failure(
                "EXECUTOR_TYPE_MISMATCH", "The executor type must match the tool type."
            )

        try:
            await self.guardrail_hook.validate(arguments, context)
        except Exception:
            return self._failure(
                "TOOL_GUARDRAIL_BLOCKED", "The tool call was blocked by a guardrail."
            )

        credential_ref = version.executor_config.get("credential_ref")
        if credential_ref is not None:
            try:
                self.credential_resolver.resolve(str(credential_ref))
            except Exception:
                return self._failure(
                    "CREDENTIAL_VAULT_UNAVAILABLE",
                    "Credential-backed tools are not available until Phase 7.",
                )

        try:
            if version.executor_type == ToolType.FUNCTION:
                result = await self.function_registry.execute(
                    str(version.executor_config.get("function_name", version.name)),
                    arguments,
                    context,
                )
            elif version.executor_type == ToolType.HTTP:
                result = await HttpToolExecutor(
                    version.executor_config,
                    retry_policy=version.retry_policy,
                    idempotent=version.idempotent,
                ).execute(arguments, context)
            else:
                return self._failure(
                    "EXECUTOR_TYPE_MISMATCH", "The executor type is unsupported."
                )
        except Exception:
            return self._failure("TOOL_EXECUTION_FAILED", "The tool execution failed.")

        if not result.ok:
            return result.model_copy(
                update={
                    "output": None,
                    "error_message": result.error_message or "The tool failed.",
                }
            )
        output = self.secret_redactor.redact(result.output or {})
        if version.output_schema is not None:
            try:
                validate(output, version.output_schema)
            except SchemaDefinitionError:
                return self._failure(
                    "TOOL_SCHEMA_INVALID", "The tool schema definition is invalid."
                )
            except SchemaValidationError:
                return self._failure(
                    "TOOL_OUTPUT_INVALID", "The tool returned an invalid output."
                )
        return result.model_copy(update={"output": output})
