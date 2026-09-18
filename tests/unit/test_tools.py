from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from apps.api.app.credentials.service import ResolvedCredential
from apps.api.app.models import ToolType
from apps.api.app.tools.catalog import (
    WEB_SEARCH_INPUT,
    WEB_SEARCH_OUTPUT,
    builtin_definitions,
)
from apps.api.app.tools.contracts import ToolExecutionContext, ToolResult
from apps.api.app.tools.executors import (
    ExaWebSearchExecutor,
    HttpToolConfigError,
    HttpToolExecutor,
    canonical_http_config,
)
from apps.api.app.tools.naming import model_tool_name
from apps.api.app.tools.pipeline import SecretRedactor, ToolExecutionPipeline
from apps.api.app.tools.validation import (
    SchemaValidationError,
    is_empty_object_schema,
    validate,
)


class FakeExaClient:
    def __init__(self, key: str) -> None:
        self.key = key
        self.calls: list[tuple[str, dict[str, object]]] = []

    def search(self, query: str, **kwargs: object) -> object:
        self.calls.append((query, kwargs))
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    title="Example",
                    url="https://example.com",
                    publishedDate="2026-09-17",
                    highlights=["A concise highlight."],
                    raw_text="must not escape",
                )
            ],
            request_id="request-1",
        )


@pytest.mark.asyncio
async def test_exa_search_is_called_with_agent_safe_defaults() -> None:
    client = FakeExaClient("secret")
    executor = ExaWebSearchExecutor(SecretStr("secret"), lambda _: client)

    result = await executor.execute(
        {"query": "Latest news", "num_results": 2},
        ToolExecutionContext(workspace_id=uuid4()),
    )

    assert result.ok is True
    assert client.calls == [
        (
            "Latest news",
            {"num_results": 2, "type": "auto", "contents": {"highlights": True}},
        )
    ]
    assert result.output == {
        "query": "Latest news",
        "results": [
            {
                "title": "Example",
                "url": "https://example.com",
                "published_date": "2026-09-17",
                "highlights": ["A concise highlight."],
            }
        ],
        "request_id": "request-1",
    }
    assert "raw_text" not in str(result.output)


@pytest.mark.asyncio
async def test_exa_missing_key_is_safe() -> None:
    result = await ExaWebSearchExecutor(None).execute(
        {"query": "hello"}, ToolExecutionContext(workspace_id=uuid4())
    )

    assert result.ok is False
    assert result.error_code == "EXA_API_KEY_MISSING"
    assert "secret" not in str(result.model_dump())


@pytest.mark.asyncio
async def test_exa_search_limits_highlight_context() -> None:
    class LargeFakeExaClient(FakeExaClient):
        def search(self, query: str, **kwargs: object) -> object:
            self.calls.append((query, kwargs))
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        title="Example",
                        url="https://example.com",
                        publishedDate=None,
                        highlights=["x" * 2_000] * 5,
                    )
                ],
                request_id="request-1",
            )

    result = await ExaWebSearchExecutor(
        SecretStr("secret"), lambda _: LargeFakeExaClient("secret")
    ).execute(
        {"query": "Latest news", "num_results": 10},
        ToolExecutionContext(workspace_id=uuid4()),
    )

    assert result.ok is True
    assert result.output is not None
    item = result.output["results"][0]
    assert len(item["highlights"]) == 5
    assert all(len(highlight) == 2_000 for highlight in item["highlights"])


def test_web_search_catalog_contract_is_bounded() -> None:
    definition = next(
        item for item in builtin_definitions() if item["name"] == "web_search"
    )

    assert definition["config"] == {
        "function_name": "web_search",
        "provider": "exa",
        "search_type": "auto",
        "contents": {"highlights": True},
    }
    validate({"query": "x", "num_results": 10}, WEB_SEARCH_INPUT)
    with pytest.raises(SchemaValidationError):
        validate({"query": "x", "num_results": 11}, WEB_SEARCH_INPUT)
    validate({"query": "x", "results": []}, WEB_SEARCH_OUTPUT)
    validate({"query": "x", "results": [], "request_id": None}, WEB_SEARCH_OUTPUT)


def test_builtin_catalog_exposes_top_level_input_and_output_fields() -> None:
    definitions = builtin_definitions()

    for definition in definitions:
        input_schema = definition["input_schema"]
        output_schema = definition["output_schema"]
        assert isinstance(input_schema, dict)
        assert isinstance(output_schema, dict)
        assert isinstance(input_schema.get("properties"), dict)
        assert isinstance(output_schema.get("properties"), dict)


def test_http_config_normalizes_legacy_url_without_secrets() -> None:
    assert canonical_http_config(
        {"url": "https://example.com/weather?units=metric", "method": "GET"}
    ) == {
        "method": "GET",
        "base_url": "https://example.com",
        "path": "/weather?units=metric",
        "headers": {},
        "query_mapping": {},
        "body_mapping": {},
    }


def test_http_config_rejects_embedded_credentials_and_sensitive_headers() -> None:
    with pytest.raises(HttpToolConfigError):
        canonical_http_config({"base_url": "https://user:pass@example.com"})
    with pytest.raises(HttpToolConfigError):
        canonical_http_config(
            {"base_url": "https://example.com", "headers": {"Authorization": "x"}}
        )


def test_http_config_normalizes_credential_binding_without_secret() -> None:
    config = canonical_http_config(
        {
            "base_url": "https://example.com",
            "credential_ref": str(uuid4()),
            "credential_binding": {
                "name": "X-API-Key",
                "prefix": "",
                "secret_key": "token",
            },
        }
    )

    assert config["headers"] == {"X-API-Key": "{{credential.token}}"}
    assert "secret-value" not in str(config)
    assert canonical_http_config(config) == config


def test_http_config_rejects_credential_templates_outside_headers() -> None:
    with pytest.raises(HttpToolConfigError):
        canonical_http_config(
            {
                "base_url": "https://example.com",
                "credential_ref": str(uuid4()),
                "query_mapping": {"api_key": "{{credential.token}}"},
            }
        )


@pytest.mark.asyncio
async def test_http_executor_injects_credential_only_at_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CapturingExecutor(HttpToolExecutor):
        async def _request_once(
            self,
            method: str,
            url: str,
            headers: object,
            params: object,
            body: object,
            timeout_seconds: float,
        ) -> ToolResult:
            del method, url, params, body, timeout_seconds
            assert headers == {"Authorization": "Bearer secret-value"}
            return ToolResult(ok=True, output={"echo": "secret-value"})

    credential = ResolvedCredential(
        credential_id=uuid4(),
        provider="github",
        credential_type="API_KEY",
        values={"token": "secret-value"},
    )
    executor = CapturingExecutor(
        {
            "base_url": "https://example.com",
            "credential_ref": str(credential.credential_id),
        },
        credential=credential,
    )

    async def allow_destination(_url: str) -> None:
        return None

    monkeypatch.setattr(
        "apps.api.app.tools.executors._assert_public_destination",
        allow_destination,
    )
    result = await executor.execute(
        {}, ToolExecutionContext(workspace_id=uuid4())
    )
    assert result.output == {"echo": "secret-value"}


def test_secret_redactor_removes_sensitive_keys_and_values() -> None:
    redacted = SecretRedactor().redact(
        {"token": "do-not-store", "message": "key=do-not-store"},
        ("do-not-store",),
    )
    assert redacted == {"message": "key=[REDACTED]"}


def test_empty_object_schema_is_treated_as_omitted_output_contract() -> None:
    assert is_empty_object_schema(
        {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    ) is True
    assert is_empty_object_schema(
        {
            "type": "object",
            "properties": {"status_code": {"type": "integer"}},
            "additionalProperties": False,
        }
    ) is False


@pytest.mark.asyncio
async def test_http_tool_without_output_fields_accepts_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHttpExecutor:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def execute(
            self,
            _arguments: object,
            _context: ToolExecutionContext,
        ) -> ToolResult:
            return ToolResult(
                ok=True,
                output={"status_code": 200, "body": {"ok": True}},
            )

    monkeypatch.setattr(
        "apps.api.app.tools.pipeline.HttpToolExecutor", FakeHttpExecutor
    )
    version = SimpleNamespace(
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        executor_type=ToolType.HTTP,
        executor_config={"type": "HTTP"},
        retry_policy={},
        idempotent=True,
    )

    result = await ToolExecutionPipeline().execute(
        version,
        {},
        ToolExecutionContext(workspace_id=uuid4()),
    )

    assert result.ok is True
    assert result.output == {"status_code": 200, "body": {"ok": True}}


def test_model_tool_name_is_provider_safe() -> None:
    assert model_tool_name("JSONPlaceholder Posts") == "jsonplaceholder_posts"


@pytest.mark.asyncio
async def test_exa_invalid_provider_shape_is_normalized() -> None:
    class InvalidClient:
        def search(self, query: str, **kwargs: object) -> object:
            return SimpleNamespace(results={"not": "a list"})

    result = await ExaWebSearchExecutor(
        SecretStr("secret"), lambda _: InvalidClient()
    ).execute({"query": "hello"}, ToolExecutionContext(workspace_id=uuid4()))
    assert result.error_code == "EXA_INVALID_RESPONSE"
