from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.api.app.credentials.service import ResolvedCredential
from apps.api.app.mcp.client import _headers, schema_fingerprint
from apps.api.app.mcp.contracts import MCPConnectionSnapshot, MCPInvocationResult
from apps.api.app.mcp.executor import MCPToolExecutor
from apps.api.app.mcp.manager import MCPManager
from apps.api.app.mcp.network import MCPNetworkPolicyError, validate_endpoint
from apps.api.app.mcp.schemas import MCPAuthConfig, MCPServerCreateRequest
from apps.api.app.mcp.service import _auth_dict
from apps.api.app.models import MCPServerStatus, ToolType
from apps.api.app.tools.contracts import ToolExecutionContext
from apps.api.app.tools.pipeline import ToolExecutionPipeline


def test_schema_fingerprint_is_canonical() -> None:
    first = schema_fingerprint(
        "lookup", {"type": "object", "properties": {"q": {"type": "string"}}}, None
    )
    second = schema_fingerprint(
        "lookup", {"properties": {"q": {"type": "string"}}, "type": "object"}, None
    )
    assert first == second
    assert first.startswith("sha256:")


def test_custom_headers_resolve_secret_keys_without_exposing_values() -> None:
    credential = ResolvedCredential(
        credential_id=uuid4(),
        provider="test",
        credential_type="API_KEY",
        values={"instance": "acme", "username": "alice", "password": "secret"},
    )
    headers = _headers(
        MCPConnectionSnapshot(
            workspace_id=uuid4(),
            endpoint="https://example.com/mcp",
            auth={
                "mode": "HEADER",
                "custom_headers": [
                    {"header_name": "x-instance", "secret_key": "instance"},
                    {"header_name": "x-username", "secret_key": "username"},
                    {"header_name": "x-password", "secret_key": "password"},
                ],
            },
        ),
        credential,
    )
    assert headers == {
        "x-instance": "acme",
        "x-username": "alice",
        "x-password": "secret",
    }


def test_bearer_and_custom_headers_are_sent_together() -> None:
    credential = ResolvedCredential(
        credential_id=uuid4(),
        provider="test",
        credential_type="API_KEY",
        values={"token": "bearer-secret", "instance": "acme"},
    )
    headers = _headers(
        MCPConnectionSnapshot(
            workspace_id=uuid4(),
            endpoint="https://example.com/mcp",
            auth={
                "mode": "BEARER",
                "header_name": "Authorization",
                "prefix": "Bearer",
                "secret_key": "token",
                "custom_headers": [
                    {"header_name": "x-instance", "secret_key": "instance"},
                ],
            },
        ),
        credential,
    )
    assert headers == {
        "Authorization": "Bearer bearer-secret",
        "x-instance": "acme",
    }


def test_custom_header_can_use_its_own_secret_store_credential_without_authorization() -> (
    None
):
    custom_credential = ResolvedCredential(
        credential_id=uuid4(),
        provider="test",
        credential_type="API_KEY",
        values={"token": "instance-secret"},
    )
    snapshot = MCPConnectionSnapshot(
        workspace_id=uuid4(),
        endpoint="https://example.com/mcp",
        auth={
            "mode": "NONE",
            "custom_headers": [
                {
                    "header_name": "x-instance",
                    "credential_id": str(custom_credential.credential_id),
                }
            ],
        },
    )
    assert _headers(
        snapshot,
        None,
        {str(custom_credential.credential_id): custom_credential},
    ) == {"x-instance": "instance-secret"}


def test_no_authorization_does_not_require_primary_credential() -> None:
    request = MCPServerCreateRequest(
        name="No auth MCP",
        endpoint="https://example.com/mcp",
        auth={"mode": "NONE"},
    )
    assert request.credential_id is None


def test_auth_snapshot_serializes_custom_credential_ids_for_jsonb() -> None:
    credential_id = uuid4()
    snapshot = _auth_dict(
        MCPAuthConfig(
            mode="NONE",
            custom_headers=[
                {"header_name": "x-instance", "credential_id": credential_id}
            ],
        )
    )
    assert snapshot["custom_headers"][0]["credential_id"] == str(credential_id)


@pytest.mark.asyncio
async def test_network_policy_rejects_embedded_credentials() -> None:
    with pytest.raises(MCPNetworkPolicyError) as error:
        await validate_endpoint("https://user:pass@example.com/mcp")
    assert error.value.code == "MCP_ENDPOINT_BLOCKED"


class FakeMCPAdapter:
    def __init__(self, result: MCPInvocationResult | None = None) -> None:
        self.result = result or MCPInvocationResult(
            ok=True,
            output={"answer": 42},
            metadata={"protocol_version": "2026-07-28"},
        )

    async def test(self, snapshot, credential, timeout_seconds):
        del snapshot, credential, timeout_seconds
        return {"protocol_version": "2026-07-28", "server_info": {}, "capabilities": {}}

    async def discover(self, snapshot, credential, timeout_seconds, max_tools):
        del snapshot, credential, timeout_seconds, max_tools
        return [], {
            "protocol_version": "2026-07-28",
            "server_info": {},
            "capabilities": {},
        }

    async def invoke(
        self, snapshot, credential, remote_name, arguments, timeout_seconds
    ):
        del snapshot, credential, remote_name, arguments, timeout_seconds
        return self.result


@pytest.mark.asyncio
async def test_manager_rejects_oversized_result() -> None:
    manager = MCPManager(
        FakeMCPAdapter(MCPInvocationResult(ok=True, output={"text": "x" * 256_001}))
    )
    result = await manager.invoke(
        MCPConnectionSnapshot(workspace_id=uuid4(), endpoint="https://example.com/mcp"),
        None,
        "lookup",
        {},
        1,
    )
    assert result.ok is False
    assert result.error_code == "MCP_RESULT_TOO_LARGE"

    paginated = await manager.invoke(
        MCPConnectionSnapshot(workspace_id=uuid4(), endpoint="https://example.com/mcp"),
        None,
        "lookup",
        {"limit": 10},
        1,
    )
    assert paginated.metadata["suggested_limit"] == 5
    assert paginated.metadata["retryable"] is True
    assert "suggested_limit=5" in (paginated.error_message or "")


class FakeServerResolver:
    def __init__(self, server) -> None:
        self.server = server

    async def get(self, server_id, workspace_id):
        assert server_id == self.server.id
        assert workspace_id == self.server.workspace_id
        return self.server


@pytest.mark.asyncio
async def test_disabled_server_is_a_runtime_kill_switch() -> None:
    server = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        endpoint="https://example.com/mcp",
        transport="STREAMABLE_HTTP",
        credential_id=None,
        configuration={"auth": {"mode": "NONE"}},
        status=MCPServerStatus.DISABLED,
    )
    version = SimpleNamespace(
        mcp_server_id=server.id,
        workspace_id=server.workspace_id,
        name="lookup",
        executor_config={"remote_tool_name": "lookup", "type": "MCP"},
    )
    result = await MCPToolExecutor(
        version,
        MCPManager(FakeMCPAdapter()),
        FakeServerResolver(server),
        None,
    ).execute({}, ToolExecutionContext(workspace_id=server.workspace_id))
    assert result.error_code == "MCP_SERVER_DISABLED"


@pytest.mark.asyncio
async def test_mcp_pipeline_returns_safe_metadata() -> None:
    server = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        endpoint="https://example.com/mcp",
        transport="STREAMABLE_HTTP",
        credential_id=uuid4(),
        configuration={"auth": {"mode": "BEARER", "secret_key": "token"}},
        status=MCPServerStatus.ACTIVE,
    )
    version = SimpleNamespace(
        mcp_server_id=server.id,
        workspace_id=server.workspace_id,
        name="lookup",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"answer": {"type": "integer"}}},
        executor_type=ToolType.MCP,
        executor_config={
            "type": "MCP",
            "remote_tool_name": "lookup",
            "schema_fingerprint": "sha256:abc",
            "credential_ref": str(server.credential_id),
            "auth": {"mode": "BEARER", "secret_key": "token"},
        },
        retry_policy={},
        idempotent=True,
    )
    credential = ResolvedCredential(
        credential_id=server.credential_id,
        provider="test",
        credential_type="API_KEY",
        values={"token": "super-secret"},
    )

    class CredentialResolver:
        async def resolve(self, reference, workspace_id):
            assert reference == str(credential.credential_id)
            assert workspace_id == server.workspace_id
            return credential

    pipeline = ToolExecutionPipeline(
        credential_resolver=CredentialResolver(),
        mcp_manager=MCPManager(FakeMCPAdapter()),
        mcp_server_resolver=FakeServerResolver(server),
    )
    result = await pipeline.execute(
        version,
        {},
        ToolExecutionContext(workspace_id=server.workspace_id),
    )
    assert result.ok is True
    assert result.output == {"answer": 42}
    assert result.metadata["executor_type"] == "MCP"
    assert "super-secret" not in str(result.model_dump())
