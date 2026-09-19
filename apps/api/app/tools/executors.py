"""Safe built-in and HTTP tool executors."""

import ast
import asyncio
import hashlib
import ipaddress
import socket
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import httpx
import structlog
from pydantic import SecretStr

from .contracts import ToolExecutionContext, ToolResult

if TYPE_CHECKING:
    from ..credentials.service import ResolvedCredential

HTTP_RESPONSE_LIMIT = 100_000
_EXA_MAX_RESULTS = 10
_EXA_MAX_HIGHLIGHTS = 5
_EXA_MAX_HIGHLIGHT_CHARS = 2_000
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
_SENSITIVE_KEYS = frozenset(
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
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)
logger = structlog.get_logger(__name__)


class HttpToolConfigError(ValueError):
    code = "HTTP_CONFIG_INVALID"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class _HttpStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _HttpResponseTooLarge(Exception):
    pass


def _value(item: object, name: str, alternate: str | None = None) -> Any:
    if isinstance(item, Mapping):
        return (
            item.get(name) if alternate is None else item.get(name, item.get(alternate))
        )
    return getattr(item, name, getattr(item, alternate, None) if alternate else None)


def _redact_config_keys(value: object, *, in_headers: bool = False) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized == "credential_ref":
                continue
            credential_template = (
                isinstance(child, str)
                and "{{credential." in child
                and child.endswith("}}")
            )
            if (
                normalized in _SENSITIVE_KEYS
                or in_headers
                and normalized in _SENSITIVE_KEYS
            ) and not credential_template:
                raise HttpToolConfigError("HTTP tool config cannot contain secrets.")
            _redact_config_keys(child, in_headers=in_headers or normalized == "headers")
    elif isinstance(value, (list, tuple)):
        for child in value:
            _redact_config_keys(child, in_headers=in_headers)


def _contains_credential_template(value: object) -> bool:
    if isinstance(value, str):
        return "{{credential." in value
    if isinstance(value, Mapping):
        return any(_contains_credential_template(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_credential_template(child) for child in value)
    return False


def canonical_http_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a new or legacy HTTP executor config without storing secrets."""
    if not isinstance(config, Mapping):
        raise HttpToolConfigError("HTTP executor config must be an object.")
    _redact_config_keys(config)
    method = str(config.get("method", "GET")).upper()
    if method not in _HTTP_METHODS:
        raise HttpToolConfigError("HTTP method is not supported.")
    legacy_url = config.get("url")
    base_url = config.get("base_url") or legacy_url
    if not isinstance(base_url, str) or not base_url.strip():
        raise HttpToolConfigError("HTTP tools require a base_url.")
    try:
        parsed = urlparse(base_url.strip())
        _ = parsed.port
    except ValueError as exc:
        raise HttpToolConfigError(
            "HTTP tools require a valid public HTTP URL.", code="HTTP_URL_INVALID"
        ) from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HttpToolConfigError(
            "HTTP tools require a valid public HTTP URL.", code="HTTP_URL_INVALID"
        )
    if parsed.username is not None or parsed.password is not None:
        raise HttpToolConfigError("HTTP URLs cannot contain embedded credentials.")
    if "credential_ref" in config and (
        not isinstance(config["credential_ref"], str)
        or not config["credential_ref"].strip()
    ):
        raise HttpToolConfigError("credential_ref must be a non-empty reference.")
    credential_binding = config.get("credential_binding")
    if "credential_ref" in config and credential_binding is None:
        credential_binding = {
            "location": "HEADER",
            "name": "Authorization",
            "prefix": "Bearer",
            "secret_key": "token",
        }
    if credential_binding is not None:
        if not isinstance(credential_binding, Mapping):
            raise HttpToolConfigError("credential_binding must be an object.")
        if credential_binding.get("location", "HEADER") != "HEADER":
            raise HttpToolConfigError(
                "Credential injection only supports HTTP headers."
            )
        header_name = credential_binding.get("name", "Authorization")
        secret_key = credential_binding.get("secret_key", "token")
        prefix = credential_binding.get("prefix", "Bearer")
        if (
            not isinstance(header_name, str)
            or not header_name.strip()
            or not isinstance(secret_key, str)
            or not secret_key.strip()
            or not isinstance(prefix, str)
        ):
            raise HttpToolConfigError("credential_binding contains invalid values.")
        if "credential_ref" not in config:
            raise HttpToolConfigError("credential_binding requires credential_ref.")
    if legacy_url and not config.get("base_url"):
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        base_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    else:
        path = config.get("path", "/")
    if not isinstance(path, str) or not path.startswith("/"):
        raise HttpToolConfigError("HTTP path must start with '/'.")
    headers = config.get("headers", {})
    query_mapping = config.get("query_mapping", {})
    body_mapping = config.get("body_mapping", {})
    for name, value in (
        ("headers", headers),
        ("query_mapping", query_mapping),
        ("body_mapping", body_mapping),
    ):
        if not isinstance(value, Mapping):
            raise HttpToolConfigError(f"HTTP {name} must be an object.")
    if (
        _contains_credential_template(path)
        or _contains_credential_template(query_mapping)
        or _contains_credential_template(body_mapping)
    ):
        raise HttpToolConfigError("Credential injection only supports HTTP headers.")
    normalized_headers = dict(headers)
    if credential_binding is not None:
        header_name = str(credential_binding.get("name", "Authorization"))
        secret_key = str(credential_binding.get("secret_key", "token"))
        prefix = str(credential_binding.get("prefix", "Bearer"))
        generated_header = (
            f"{prefix} {{{{credential.{secret_key}}}}}"
            if prefix
            else f"{{{{credential.{secret_key}}}}}"
        )
        if (
            header_name in normalized_headers
            and normalized_headers[header_name] != generated_header
        ):
            raise HttpToolConfigError(
                "credential_binding cannot overwrite a configured header."
            )
        normalized_headers[header_name] = generated_header
    return {
        "method": method,
        "base_url": base_url,
        "path": path,
        "headers": normalized_headers,
        "query_mapping": dict(query_mapping),
        "body_mapping": dict(body_mapping),
        **(
            {"credential_ref": config["credential_ref"]}
            if "credential_ref" in config
            else {}
        ),
        **(
            {"credential_binding": dict(credential_binding)}
            if credential_binding is not None
            else {}
        ),
    }


def _resolve_template(
    value: Any,
    arguments: Mapping[str, Any],
    credential: "ResolvedCredential | None" = None,
) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _resolve_template(child, arguments, credential)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_resolve_template(child, arguments, credential) for child in value]
    if not isinstance(value, str):
        return value
    start = 0
    pieces: list[str] = []
    while True:
        opening = value.find("{{", start)
        if opening < 0:
            pieces.append(value[start:])
            break
        closing = value.find("}}", opening + 2)
        if closing < 0:
            raise HttpToolConfigError("HTTP mapping contains an invalid placeholder.")
        pieces.append(value[start:opening])
        name = value[opening + 2 : closing].strip()
        if name.startswith("credential."):
            if credential is None:
                raise HttpToolConfigError(
                    "HTTP mapping requires a configured credential."
                )
            credential_key = name.removeprefix("credential.")
            replacement = credential.values.get(credential_key)
            if not isinstance(replacement, (str, int, float, bool)):
                raise HttpToolConfigError(
                    "The credential mapping references an unavailable value."
                )
        elif not name or name not in arguments:
            raise HttpToolConfigError(
                "HTTP mapping contains an unresolved placeholder."
            )
        else:
            replacement = arguments[name]
        if opening == 0 and closing == len(value) - 2:
            return replacement
        pieces.append(str(replacement))
        start = closing + 2
    return "".join(pieces)


def _blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    )


async def _assert_public_destination(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise HttpToolConfigError(
            "Private and local HTTP destinations are blocked.",
            code="HTTP_PRIVATE_DESTINATION",
        )
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise HttpToolConfigError(
            "The HTTP destination could not be resolved.", code="HTTP_URL_INVALID"
        ) from exc
    if not addresses:
        raise HttpToolConfigError(
            "The HTTP destination could not be resolved.", code="HTTP_URL_INVALID"
        )
    for address in addresses:
        resolved = address[4][0]
        if not isinstance(resolved, str) or _blocked_ip(resolved):
            raise HttpToolConfigError(
                "Private and local HTTP destinations are blocked.",
                code="HTTP_PRIVATE_DESTINATION",
            )


def _safe_calculate(expression: str) -> float | int:
    def walk(node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left**right
        raise ValueError("Unsupported expression")

    return walk(ast.parse(expression, mode="eval").body)


class ExaWebSearchExecutor:
    def __init__(
        self,
        api_key: SecretStr | None,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.client_factory = client_factory or self._default_factory

    @staticmethod
    def _default_factory(api_key: str) -> Any:
        from exa_py import Exa

        return Exa(api_key)

    @staticmethod
    def _query_fingerprint(query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

    def _safe_error_detail(self, error: BaseException) -> str:
        detail = str(error).strip() or type(error).__name__
        if self.api_key is not None:
            secret = self.api_key.get_secret_value()
            if secret:
                detail = detail.replace(secret, "[REDACTED]")
        return detail[:500]

    def _failure(
        self,
        *,
        code: str,
        message: str,
        query: str,
        context: ToolExecutionContext,
        started: float,
        error: BaseException | None = None,
        status_code: int | None = None,
    ) -> ToolResult:
        logger.warning(
            "external_tool_call_failed",
            provider="exa",
            tool="web_search",
            run_id=str(context.run_id) if context.run_id else None,
            trace_id=str(context.trace_id) if context.trace_id else None,
            workspace_id=str(context.workspace_id),
            query_sha256=self._query_fingerprint(query),
            query_length=len(query),
            error_code=code,
            error_type=type(error).__name__ if error else None,
            error_detail=self._safe_error_detail(error) if error else None,
            status_code=status_code,
            duration_ms=max(0, int((monotonic() - started) * 1000)),
        )
        return ToolResult(ok=False, error_code=code, error_message=message)

    async def execute(
        self, arguments: Mapping[str, Any], context: ToolExecutionContext
    ) -> ToolResult:
        started = monotonic()
        query = arguments.get("query")
        num_results = arguments.get("num_results", 10)
        if not isinstance(query, str) or not 1 <= len(query) <= 2_000:
            return self._failure(
                code="EXA_INVALID_ARGUMENT",
                message="The search query is invalid.",
                query=str(query) if isinstance(query, str) else "",
                context=context,
                started=started,
            )
        if (
            isinstance(num_results, bool)
            or not isinstance(num_results, int)
            or not 1 <= num_results <= 10
        ):
            return self._failure(
                code="EXA_INVALID_ARGUMENT",
                message="The result count must be an integer from 1 to 10.",
                query=query if isinstance(query, str) else "",
                context=context,
                started=started,
            )
        if self.api_key is None or not self.api_key.get_secret_value():
            return self._failure(
                code="EXA_API_KEY_MISSING",
                message="Web search is not configured.",
                query=query,
                context=context,
                started=started,
            )
        try:
            logger.info(
                "external_tool_call_started",
                provider="exa",
                tool="web_search",
                run_id=str(context.run_id) if context.run_id else None,
                trace_id=str(context.trace_id) if context.trace_id else None,
                workspace_id=str(context.workspace_id),
                query_sha256=self._query_fingerprint(query),
                query_length=len(query),
                num_results=num_results,
            )
            client = self.client_factory(self.api_key.get_secret_value())
            search_and_contents = getattr(client, "search_and_contents", None)
            search_method = (
                search_and_contents if callable(search_and_contents) else client.search
            )
            search_kwargs: dict[str, Any] = {
                "num_results": num_results,
                "type": "auto",
            }
            # Current exa-py exposes highlights on search_and_contents. Older
            # clients accepted the legacy search call with a contents mapping.
            if callable(search_and_contents):
                search_kwargs["highlights"] = True
            else:
                search_kwargs["contents"] = {"highlights": True}
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    search_method,
                    query,
                    **search_kwargs,
                ),
                timeout=context.timeout_seconds,
            )
            raw_items = _value(response, "results")
            if not isinstance(raw_items, list):
                raise ValueError("results")
            normalized: list[dict[str, Any]] = []
            for item in raw_items[:_EXA_MAX_RESULTS]:
                title, url = _value(item, "title"), _value(item, "url")
                published = _value(item, "published_date", "publishedDate")
                highlights = _value(item, "highlights")
                if not isinstance(item, Mapping) and not hasattr(item, "title"):
                    raise ValueError("result shape")
                if not isinstance(title, str) or not isinstance(url, str):
                    raise ValueError("result field")
                if published is not None and not isinstance(published, str):
                    raise ValueError("published_date")
                if highlights is None:
                    highlights = []
                if not isinstance(highlights, list) or not all(
                    isinstance(value, str) for value in highlights
                ):
                    raise ValueError("highlights")
                normalized.append(
                    {
                        "title": title,
                        "url": url,
                        "published_date": published,
                        "highlights": [
                            value[:_EXA_MAX_HIGHLIGHT_CHARS]
                            for value in highlights[:_EXA_MAX_HIGHLIGHTS]
                        ],
                    }
                )
            request_id = _value(response, "request_id")
            if request_id is not None and not isinstance(request_id, str):
                raise ValueError("request_id")
            logger.info(
                "external_tool_call_completed",
                provider="exa",
                tool="web_search",
                run_id=str(context.run_id) if context.run_id else None,
                trace_id=str(context.trace_id) if context.trace_id else None,
                workspace_id=str(context.workspace_id),
                query_sha256=self._query_fingerprint(query),
                result_count=len(normalized),
                provider_request_id=request_id,
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            return ToolResult(
                ok=True,
                output={
                    "query": query,
                    "results": normalized,
                    "request_id": request_id,
                },
            )
        except (TimeoutError, httpx.TimeoutException) as exc:
            return self._failure(
                code="EXA_TIMEOUT",
                message="Web search timed out.",
                query=query,
                context=context,
                started=started,
                error=exc,
            )
        except Exception as exc:
            name = type(exc).__name__.lower()
            status_code = getattr(exc, "status_code", None)
            if status_code == 429 or "rate" in name or "429" in str(exc):
                return self._failure(
                    code="EXA_RATE_LIMITED",
                    message="Web search is temporarily rate limited.",
                    query=query,
                    context=context,
                    started=started,
                    error=exc,
                    status_code=status_code,
                )
            if isinstance(exc, ValueError):
                return self._failure(
                    code="EXA_INVALID_RESPONSE",
                    message="The web search provider returned an invalid response.",
                    query=query,
                    context=context,
                    started=started,
                    error=exc,
                    status_code=status_code,
                )
            return self._failure(
                code="EXA_PROVIDER_ERROR",
                message="The web search provider failed.",
                query=query,
                context=context,
                started=started,
                error=exc,
                status_code=status_code,
            )


class FunctionToolRegistry:
    def __init__(
        self,
        *,
        exa_api_key: SecretStr | None = None,
        exa_client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._web_search = ExaWebSearchExecutor(exa_api_key, exa_client_factory)

    async def execute(
        self, name: str, arguments: Mapping[str, Any], context: ToolExecutionContext
    ) -> ToolResult:
        if name == "web_search":
            return await self._web_search.execute(arguments, context)
        if name == "echo":
            return ToolResult(ok=True, output={"value": arguments.get("value")})
        if name == "current_datetime":
            return ToolResult(
                ok=True, output={"datetime": datetime.now(UTC).isoformat()}
            )
        if name == "calculator":
            try:
                return ToolResult(
                    ok=True,
                    output={"result": _safe_calculate(str(arguments["expression"]))},
                )
            except Exception:
                return ToolResult(
                    ok=False,
                    error_code="FUNCTION_INVALID_ARGUMENT",
                    error_message="The expression could not be evaluated safely.",
                )
        return ToolResult(
            ok=False,
            error_code="TOOL_NOT_FOUND",
            error_message="The requested function tool is unavailable.",
        )


class HttpToolExecutor:
    """Credential-free HTTP adapter with SSRF and bounded-response protection."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        retry_policy: Mapping[str, Any] | None = None,
        idempotent: bool = False,
        credential: "ResolvedCredential | None" = None,
    ) -> None:
        self.config = canonical_http_config(config)
        self.retry_policy = retry_policy or {}
        self.idempotent = idempotent
        self.credential = credential

    async def _request_once(
        self,
        method: str,
        url: str,
        headers: Mapping[str, Any],
        params: Mapping[str, Any],
        body: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> ToolResult:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=timeout_seconds, trust_env=False
        ) as client:
            request_kwargs: dict[str, Any] = {"headers": headers, "params": params}
            if method not in {"GET", "HEAD"}:
                request_kwargs["json"] = body
            async with client.stream(method, url, **request_kwargs) as response:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > HTTP_RESPONSE_LIMIT:
                        raise _HttpResponseTooLarge
                    chunks.append(chunk)
                if not 200 <= response.status_code < 300:
                    raise _HttpStatusError(response.status_code)
                status_code = response.status_code
                raw_body = b"".join(chunks)
        try:
            decoded: Any = httpx.Response(status_code, content=raw_body).json()
        except ValueError:
            decoded = {"text": raw_body.decode("utf-8", errors="replace")}
        if not isinstance(decoded, dict):
            decoded = {"data": decoded}
        return ToolResult(ok=True, output={"status_code": status_code, "body": decoded})

    async def execute(
        self, arguments: Mapping[str, Any], context: ToolExecutionContext
    ) -> ToolResult:
        try:
            method = self.config["method"]
            path = _resolve_template(self.config["path"], arguments)
            if not isinstance(path, str):
                raise HttpToolConfigError("HTTP path mapping must resolve to text.")
            url = self.config["base_url"].rstrip("/") + "/" + path.lstrip("/")
            await _assert_public_destination(url)
            headers = _resolve_template(
                self.config["headers"], arguments, self.credential
            )
            params = _resolve_template(
                self.config["query_mapping"] or arguments, arguments, self.credential
            )
            body = _resolve_template(
                self.config["body_mapping"] or arguments, arguments, self.credential
            )
            if not isinstance(headers, Mapping) or not isinstance(params, Mapping):
                raise HttpToolConfigError("HTTP mappings must resolve to objects.")
            if body is not None and not isinstance(body, Mapping):
                raise HttpToolConfigError(
                    "HTTP body mapping must resolve to an object."
                )
            attempts = self.retry_policy.get("max_attempts", 1)
            if (
                isinstance(attempts, bool)
                or not isinstance(attempts, int)
                or not 1 <= attempts <= 5
            ):
                raise HttpToolConfigError(
                    "retry_policy.max_attempts must be from 1 to 5."
                )
            deadline = monotonic() + context.timeout_seconds
            for attempt in range(attempts):
                try:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        return ToolResult(
                            ok=False,
                            error_code="HTTP_TIMEOUT",
                            error_message="The HTTP tool timed out.",
                        )
                    return await self._request_once(
                        method, url, headers, params, body, remaining
                    )
                except _HttpStatusError as exc:
                    transient = (
                        exc.status_code in {408, 425, 429} or exc.status_code >= 500
                    )
                    if not transient or not self.idempotent or attempt + 1 >= attempts:
                        return ToolResult(
                            ok=False,
                            error_code="HTTP_PROVIDER_ERROR",
                            error_message="The HTTP tool returned an error.",
                        )
                except _HttpResponseTooLarge:
                    return ToolResult(
                        ok=False,
                        error_code="HTTP_RESPONSE_TOO_LARGE",
                        error_message="The HTTP response exceeded the platform limit.",
                    )
                except (TimeoutError, httpx.TimeoutException):
                    if not self.idempotent or attempt + 1 >= attempts:
                        return ToolResult(
                            ok=False,
                            error_code="HTTP_TIMEOUT",
                            error_message="The HTTP tool timed out.",
                        )
                except httpx.HTTPError:
                    if not self.idempotent or attempt + 1 >= attempts:
                        return ToolResult(
                            ok=False,
                            error_code="HTTP_PROVIDER_ERROR",
                            error_message="The HTTP tool failed.",
                        )
            return ToolResult(
                ok=False,
                error_code="HTTP_PROVIDER_ERROR",
                error_message="The HTTP tool failed.",
            )
        except HttpToolConfigError as exc:
            return ToolResult(ok=False, error_code=exc.code, error_message=exc.message)
        except ValueError:
            return ToolResult(
                ok=False,
                error_code="HTTP_URL_INVALID",
                error_message="The HTTP destination is invalid.",
            )
        except OSError:
            return ToolResult(
                ok=False,
                error_code="HTTP_URL_INVALID",
                error_message="The HTTP destination could not be resolved.",
            )
