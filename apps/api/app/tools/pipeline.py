"""The single tool execution boundary shared by tests and AgentRuntime."""

from collections.abc import Mapping
from time import monotonic
from typing import Any

import structlog

from ..config import get_settings
from ..credentials.service import CredentialResolutionError
from ..mcp.executor import MCPServerResolver, MCPToolExecutor
from ..mcp.manager import MCPManager
from ..models import MCPServerStatus, ToolType, ToolVersion
from .contracts import (
    CredentialResolver,
    NoopToolGuardrailHook,
    ToolExecutionContext,
    ToolGuardrailHook,
    ToolResult,
    UnavailableCredentialResolver,
)
from .executors import FunctionToolRegistry, HttpToolExecutor
from .validation import (
    SchemaDefinitionError,
    SchemaValidationError,
    is_empty_object_schema,
    validate,
)

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
logger = structlog.get_logger(__name__)


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
        mcp_manager: MCPManager | None = None,
        mcp_server_resolver: MCPServerResolver | None = None,
    ) -> None:
        self.function_registry = function_registry or FunctionToolRegistry(
            exa_api_key=get_settings().exa_api_key
        )
        self.guardrail_hook = guardrail_hook or NoopToolGuardrailHook()
        self.secret_redactor = secret_redactor or SecretRedactor()
        self.credential_resolver = (
            credential_resolver or UnavailableCredentialResolver()
        )
        self.mcp_manager = mcp_manager
        self.mcp_server_resolver = mcp_server_resolver

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        return ToolResult(ok=False, error_code=code, error_message=message)

    async def execute(
        self,
        version: ToolVersion,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        started = monotonic()
        tool_name = getattr(version, "name", "tool")
        external = version.executor_type in {ToolType.HTTP, ToolType.MCP} or (
            tool_name == "web_search"
        )
        execution_fields = {
            "tool": tool_name,
            "tool_version_id": (
                str(version.id) if getattr(version, "id", None) else None
            ),
            "executor_type": version.executor_type.value,
            "workspace_id": str(context.workspace_id),
            "run_id": str(context.run_id) if context.run_id else None,
            "trace_id": str(context.trace_id) if context.trace_id else None,
            "external": external,
        }
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
        if version.executor_type == ToolType.MCP:
            if self.mcp_manager is None or self.mcp_server_resolver is None:
                return self._failure(
                    "MCP_UNAVAILABLE", "MCP integration is not configured."
                )
            mcp_manager = self.mcp_manager
            mcp_server_resolver = self.mcp_server_resolver
            if version.mcp_server_id is None:
                return self._failure(
                    "MCP_SERVER_REFERENCE_INVALID",
                    "The MCP tool is missing its server reference.",
                )
            server = await self.mcp_server_resolver.get(
                version.mcp_server_id, context.workspace_id
            )
            if server is None:
                return self._failure(
                    "MCP_SERVER_NOT_FOUND", "The MCP server was not found."
                )
            if server.status != MCPServerStatus.ACTIVE:
                return self._failure(
                    "MCP_SERVER_DISABLED", "The MCP server is disabled."
                )
        credential = None
        custom_credentials: dict[str, Any] = {}
        if credential_ref is not None:
            try:
                credential = await self.credential_resolver.resolve(
                    str(credential_ref), context.workspace_id
                )
            except CredentialResolutionError as exc:
                return self._failure(exc.code, exc.message)
            except Exception:
                return self._failure(
                    "CREDENTIAL_VAULT_UNAVAILABLE",
                    "The credential vault is unavailable.",
                )
        if version.executor_type == ToolType.MCP:
            auth = version.executor_config.get("auth", {})
            raw_headers = (
                auth.get("custom_headers", []) if isinstance(auth, Mapping) else []
            )
            if isinstance(raw_headers, list):
                for raw_header in raw_headers:
                    if (
                        not isinstance(raw_header, Mapping)
                        or raw_header.get("credential_id") is None
                    ):
                        continue
                    reference = str(raw_header["credential_id"])
                    try:
                        custom_credentials[
                            reference
                        ] = await self.credential_resolver.resolve(
                            reference, context.workspace_id
                        )
                    except CredentialResolutionError as exc:
                        return self._failure(exc.code, exc.message)
                    except Exception:
                        return self._failure(
                            "CREDENTIAL_VAULT_UNAVAILABLE",
                            "The credential vault is unavailable.",
                        )

        try:
            logger.info("tool_execution_started", **execution_fields)
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
                    credential=credential,
                ).execute(arguments, context)
            elif version.executor_type == ToolType.MCP:
                result = await MCPToolExecutor(
                    version,
                    mcp_manager,
                    mcp_server_resolver,
                    credential,
                    custom_credentials,
                ).execute(arguments, context)
            else:
                return self._failure(
                    "EXECUTOR_TYPE_MISMATCH", "The executor type is unsupported."
                )
        except Exception:
            logger.exception(
                "tool_execution_failed",
                **execution_fields,
                error_code="TOOL_EXECUTION_FAILED",
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            return self._failure("TOOL_EXECUTION_FAILED", "The tool execution failed.")

        if not result.ok:
            logger.warning(
                "tool_execution_failed",
                **execution_fields,
                error_code=result.error_code or "TOOL_FAILED",
                error_message=result.error_message or "The tool failed.",
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            return result.model_copy(
                update={
                    "output": None,
                    "error_message": result.error_message or "The tool failed.",
                }
            )
        secret_values = tuple(getattr(credential, "secret_values", ())) + tuple(
            value
            for resolved in custom_credentials.values()
            for value in getattr(resolved, "secret_values", ())
        )
        output = self.secret_redactor.redact(result.output or {}, secret_values)
        if version.output_schema is not None and not is_empty_object_schema(
            version.output_schema
        ):
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
        normalized = result.model_copy(
            update={
                "output": output,
                "metadata": self.secret_redactor.redact(result.metadata, secret_values),
            }
        )
        logger.info(
            "tool_execution_completed",
            **execution_fields,
            duration_ms=max(0, int((monotonic() - started) * 1000)),
        )
        return normalized
