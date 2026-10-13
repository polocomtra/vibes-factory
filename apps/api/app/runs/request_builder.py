"""Build provider-independent runtime requests from published records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.schemas import MemoryConfiguration
from ..models import (
    Agent,
    AgentVersion,
    AgentVersionKnowledgeBase,
    AgentVersionTool,
    KnowledgeBase,
    Message,
    Session,
    Tool,
    ToolVersion,
    User,
)
from ..runtime.contracts import (
    AgentRunRequest,
    AgentVersionRuntimeConfig,
    ExecutionBudget,
    RuntimeGuardrail,
    RuntimeKnowledgeBinding,
    RuntimeMemoryBinding,
    RuntimeSession,
    RuntimeTool,
    SessionMessage,
)
from ..runtime.errors import RuntimeExecutionError
from ..tools.naming import model_tool_name
from .schemas import RunCreateRequest


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "RESOURCE_NOT_FOUND", "message": message, "details": {}},
    )


async def build_runtime_request(
    payload: RunCreateRequest,
    agent: Agent,
    user: User | None,
    session: AsyncSession,
    *,
    evaluation_mode: bool = False,
    public_api_key_id: UUID | None = None,
    deployment_id: UUID | None = None,
    public_invocation_id: UUID | None = None,
    request_metadata: dict[str, str] | None = None,
) -> AgentRunRequest:
    version = await load_version(session, agent, payload.agent_version_id)
    conversation = await load_owned_session(
        session,
        agent,
        payload.session_id,
        user,
        public_api_key_id=public_api_key_id,
    )
    messages = await session.scalars(
        select(Message)
        .where(Message.session_id == conversation.id)
        .order_by(Message.sequence_no.asc())
    )
    history = tuple(
        SessionMessage(
            role=item.role.value,
            content=str(item.content.get("text", "")),
            tool_calls=tuple(item.content.get("tool_calls", [])),
            tool_call_id=item.content.get("tool_call_id"),
            name=item.content.get("name"),
        )
        for item in messages.all()
        if item.content.get("text")
        or item.content.get("tool_calls")
        or item.role.value == "TOOL"
    )
    tool_rows = await session.execute(
        select(AgentVersionTool, ToolVersion, Tool)
        .join(ToolVersion, ToolVersion.id == AgentVersionTool.tool_version_id)
        .join(Tool, Tool.id == ToolVersion.tool_id)
        .where(AgentVersionTool.agent_version_id == version.id)
    )
    published_tools = tool_rows.all()
    if any(
        tool_version.workspace_id != agent.workspace_id
        or catalog_tool.workspace_id != agent.workspace_id
        for _, tool_version, catalog_tool in published_tools
    ):
        raise RuntimeExecutionError(
            "TOOL_WORKSPACE_MISMATCH",
            "A published tool does not belong to the agent workspace.",
            status_code=422,
        )
    knowledge_rows = await session.execute(
        select(AgentVersionKnowledgeBase, KnowledgeBase)
        .join(
            KnowledgeBase,
            KnowledgeBase.id == AgentVersionKnowledgeBase.knowledge_base_id,
        )
        .where(AgentVersionKnowledgeBase.agent_version_id == version.id)
    )
    published_knowledge = knowledge_rows.all()
    if any(kb.workspace_id != agent.workspace_id for _, kb in published_knowledge):
        raise RuntimeExecutionError(
            "KNOWLEDGE_WORKSPACE_MISMATCH",
            "A published knowledge base does not belong to the agent workspace.",
            status_code=422,
        )
    budget = ExecutionBudget.model_validate(version.runtime_config)
    memory_config = MemoryConfiguration.model_validate(version.memory_config)
    snapshot_guardrails = version.snapshot.get("guardrails", {})
    guardrail_items = (
        snapshot_guardrails.get("policies", [])
        if isinstance(snapshot_guardrails, dict)
        else []
    )
    runtime_guardrails = tuple(
        RuntimeGuardrail(
            version_id=item.get("id"),
            source=item.get("source", "CUSTOM"),
            configuration=item.get("configuration", {}),
            hooks=(cast(str, item["hook"]),)
            if isinstance(item.get("hook"), str) and item["hook"] != "ALL"
            else (),
            priority=int(item.get("priority", 100)),
        )
        for item in guardrail_items
        if isinstance(item, dict)
    )
    snapshot_model = version.snapshot.get("model")
    model_snapshot = snapshot_model if isinstance(snapshot_model, dict) else {}
    snapshot_provider = model_snapshot.get("provider")
    snapshot_name = model_snapshot.get("name")
    model_provider = (
        snapshot_provider
        if isinstance(snapshot_provider, str)
        else version.model_provider
    )
    model_name = snapshot_name if isinstance(snapshot_name, str) else version.model_name
    return AgentRunRequest(
        workspace_id=agent.workspace_id,
        agent_version=AgentVersionRuntimeConfig(
            id=version.id,
            agent_id=version.agent_id,
            workspace_id=version.workspace_id,
            instructions=version.instructions,
            model_provider=model_provider,
            model_name=model_name,
            model_options=(
                cast(dict[str, object], model_snapshot)
                if model_snapshot
                else version.model_config
            ),
            tools=tuple(
                RuntimeTool(
                    tool_id=catalog_tool.id,
                    tool_version_id=tool_version.id,
                    name=model_tool_name(binding.alias or catalog_tool.slug),
                    description=tool_version.description,
                    parameters=tool_version.input_schema,
                )
                for binding, tool_version, catalog_tool in published_tools
            )
            + tuple(
                RuntimeTool(
                    name=str(binding.get("alias", "child_agent")),
                    description=str(
                        binding.get("description", "Delegates work to a child agent.")
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "maxLength": 100_000}
                        },
                        "required": ["task"],
                        "additionalProperties": False,
                    },
                    kind="child_agent",
                    child_agent_id=UUID(str(binding["agent_id"])),
                    child_agent_version_id=UUID(str(binding["agent_version_id"])),
                )
                for binding in version.workflow_child_bindings
                if isinstance(binding, dict)
                and binding.get("alias")
                and binding.get("agent_version_id")
            ),
            knowledge_bases=tuple(
                RuntimeKnowledgeBinding(
                    knowledge_base_id=kb.id,
                    name=kb.name,
                    mode=cast(
                        Literal["auto", "always"],
                        str(binding.retrieval_config.get("mode", "auto"))
                        if binding.retrieval_config.get("mode", "auto")
                        in {"auto", "always"}
                        else "auto",
                    ),
                    top_k=int(binding.retrieval_config.get("top_k", 5)),
                    score_threshold=binding.retrieval_config.get("score_threshold"),
                    filters=binding.retrieval_config.get("filters", {}),
                )
                for binding, kb in published_knowledge
            ),
            memory=(
                RuntimeMemoryBinding(
                    memory_store_id=memory_config.memory_store_id,
                    top_k=memory_config.retrieve.top_k,
                    write_enabled=memory_config.write.enabled,
                    write_types=tuple(item.value for item in memory_config.write.types),
                )
                if memory_config.enabled and memory_config.memory_store_id is not None
                else None
            ),
            guardrails_enabled=version.guardrails_enabled,
            guardrails=runtime_guardrails,
        ),
        session=RuntimeSession(
            id=conversation.id,
            agent_id=conversation.agent_id,
            workspace_id=conversation.workspace_id,
            user_id=user.id if user is not None else None,
            public_api_key_id=public_api_key_id,
            messages=history,
        ),
        input=payload.input,
        execution_budget=budget,
        deployment_id=deployment_id,
        public_invocation_id=public_invocation_id,
        evaluation_mode=evaluation_mode,
        metadata=request_metadata or {},
    )


async def load_version(
    session: AsyncSession, agent: Agent, version_id: UUID
) -> AgentVersion:
    version = await session.scalar(
        select(AgentVersion).where(
            AgentVersion.id == version_id,
            AgentVersion.agent_id == agent.id,
            AgentVersion.workspace_id == agent.workspace_id,
        )
    )
    if version is None:
        raise _not_found("The published agent version was not found.")
    return version


async def load_owned_session(
    session: AsyncSession,
    agent: Agent,
    session_id: UUID,
    user: User | None,
    *,
    public_api_key_id: UUID | None = None,
) -> Session:
    statement = select(Session).where(
        Session.id == session_id,
        Session.agent_id == agent.id,
        Session.workspace_id == agent.workspace_id,
    )
    if user is not None:
        statement = statement.where(Session.user_id == user.id)
    elif public_api_key_id is not None:
        statement = statement.where(Session.public_api_key_id == public_api_key_id)
    else:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "AUTHENTICATION_REQUIRED",
                "message": "A session principal is required.",
                "details": {},
            },
        )
    conversation = await session.scalar(statement)
    if conversation is None:
        raise _not_found("The session was not found.")
    return conversation


def serialize_sse(event: str, data: Mapping[str, object], sequence: int) -> str:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {sequence}\nevent: {event}\ndata: {encoded}\n\n"
