"""Application services for Agent identity, drafts and immutable versions."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..guardrails.contracts import GuardrailConfiguration
from ..guardrails.engine import default_baseline
from ..models import (
    Agent,
    AgentDraft,
    AgentDraftGuardrail,
    AgentDraftKnowledgeBase,
    AgentDraftTool,
    AgentStatus,
    AgentVersion,
    AgentVersionGuardrail,
    AgentVersionKnowledgeBase,
    AgentVersionTool,
    GuardrailPolicy,
    GuardrailVersion,
    KnowledgeBase,
    KnowledgeBaseStatus,
    MemoryStore,
    Tool,
    ToolVersion,
)
from ..tools.naming import model_tool_name
from .catalog import find_model, get_default_model
from .schemas import (
    AgentCreateRequest,
    AgentDraftUpdateRequest,
    AgentUpdateRequest,
    DraftValidationIssue,
    MemoryConfiguration,
    ModelConfiguration,
    RuntimeConfiguration,
)


class AgentServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def validate_draft(draft: AgentDraft) -> list[DraftValidationIssue]:
    issues: list[DraftValidationIssue] = []
    if find_model(draft.model_provider, draft.model_name) is None:
        issues.append(
            DraftValidationIssue(
                code="MODEL_NOT_FOUND",
                field="model.name",
                message="The selected model is not available in the platform catalog.",
            )
        )
    try:
        RuntimeConfiguration.model_validate(draft.runtime_config)
    except ValueError as exc:
        issues.append(
            DraftValidationIssue(
                code="RUNTIME_CONFIG_INVALID",
                field="runtime_config",
                message=str(exc),
            )
        )
    if not draft.instructions.strip():
        issues.append(
            DraftValidationIssue(
                code="INSTRUCTIONS_REQUIRED",
                field="instructions",
                message="Instructions must not be blank.",
            )
        )
    try:
        MemoryConfiguration.model_validate(draft.memory_config)
    except ValueError as exc:
        issues.append(
            DraftValidationIssue(
                code="MEMORY_CONFIG_INVALID",
                field="memory_config",
                message=str(exc),
            )
        )
    return issues


async def validate_memory_configuration(
    session: AsyncSession,
    workspace_id: UUID,
    value: MemoryConfiguration | dict[str, Any],
) -> MemoryConfiguration:
    """Validate the shared memory contract and its workspace binding."""

    try:
        config = MemoryConfiguration.model_validate(value)
    except ValueError as error:
        raise AgentServiceError(
            "MEMORY_CONFIG_INVALID",
            str(error),
            422,
            {"field": "memory_config"},
        ) from error
    if config.enabled and config.memory_store_id is not None:
        store = await session.scalar(
            select(MemoryStore).where(
                MemoryStore.id == config.memory_store_id,
                MemoryStore.workspace_id == workspace_id,
            )
        )
        if store is None:
            raise AgentServiceError(
                "MEMORY_STORE_NOT_FOUND",
                "The configured memory store does not belong to the agent workspace.",
                422,
                {"field": "memory_config.memory_store_id"},
            )
    return config


def _normalized_model_config(stored_config: dict[str, Any]) -> dict[str, object]:
    if any(
        key in stored_config
        for key in ("config", "reasoning_options", "provider_options")
    ):
        return {
            "config": stored_config.get("config", {}),
            "reasoning_options": stored_config.get("reasoning_options", {}),
            "provider_options": stored_config.get("provider_options", {}),
        }
    return {
        "config": stored_config,
        "reasoning_options": {},
        "provider_options": {},
    }


def _memory_config_data(
    value: MemoryConfiguration | dict[str, Any],
) -> dict[str, Any]:
    """Return a JSON-safe memory configuration for JSONB persistence."""

    return MemoryConfiguration.model_validate(value).model_dump(mode="json")


def build_snapshot(
    draft: AgentDraft,
    tools: list[dict[str, object]] | None = None,
    knowledge_bases: list[dict[str, object]] | None = None,
    guardrails: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    guardrail_snapshot: object = []
    if guardrails is not None:
        guardrail_snapshot = {
            "enabled": draft.guardrails_enabled,
            "baseline_version": 1,
            "policies": guardrails,
        }
    return {
        "schema_version": 1,
        "instructions": draft.instructions,
        "model": {
            "provider": draft.model_provider,
            "name": draft.model_name,
            **_normalized_model_config(draft.model_config),
        },
        "runtime_config": draft.runtime_config,
        "memory_config": _memory_config_data(draft.memory_config),
        "tools": tools or [],
        "knowledge_bases": knowledge_bases or [],
        "guardrails": guardrail_snapshot,
        "child_agents": [],
    }


async def create_agent(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: AgentCreateRequest,
) -> Agent:
    selected_model = payload.model or ModelConfiguration(
        provider=get_default_model().provider,
        name=get_default_model().name,
    )
    if find_model(selected_model.provider, selected_model.name) is None:
        raise AgentServiceError(
            "MODEL_NOT_FOUND",
            "The selected model is not available in the platform catalog.",
            422,
            {"field": "model.name"},
        )
    memory_config = await validate_memory_configuration(
        session, workspace_id, payload.memory_config
    )
    existing = await session.scalar(
        select(Agent).where(
            Agent.workspace_id == workspace_id,
            Agent.slug == payload.slug,
        )
    )
    if existing is not None:
        raise AgentServiceError(
            "AGENT_SLUG_CONFLICT",
            "An agent with this slug already exists in the workspace.",
            409,
        )

    agent = Agent(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        created_by=user_id,
    )
    session.add(agent)
    await session.flush()
    session.add(
        AgentDraft(
            agent_id=agent.id,
            instructions=payload.instructions,
            model_provider=selected_model.provider,
            model_name=selected_model.name,
            model_config=selected_model.model_dump(exclude={"provider", "name"}),
            runtime_config=payload.runtime_config.model_dump(),
            memory_config=_memory_config_data(memory_config),
            updated_by=user_id,
        )
    )
    await session.commit()
    await session.refresh(agent)
    return agent


async def update_agent(
    session: AsyncSession,
    agent: Agent,
    user_id: UUID,
    payload: AgentUpdateRequest,
) -> Agent:
    if agent.status == AgentStatus.ARCHIVED:
        raise AgentServiceError("RESOURCE_ARCHIVED", "The agent is archived.", 409)
    if "name" in payload.model_fields_set and payload.name is not None:
        agent.name = payload.name
    if "description" in payload.model_fields_set:
        agent.description = payload.description
    del user_id  # Kept in the service signature for a future audit event.
    await session.commit()
    await session.refresh(agent)
    return agent


async def archive_agent(session: AsyncSession, agent: Agent) -> None:
    if agent.status == AgentStatus.ARCHIVED:
        return
    agent.status = AgentStatus.ARCHIVED
    agent.archived_at = datetime.now(UTC)
    await session.commit()


async def update_draft(
    session: AsyncSession,
    agent: Agent,
    user_id: UUID,
    payload: AgentDraftUpdateRequest,
) -> AgentDraft:
    if agent.status == AgentStatus.ARCHIVED:
        raise AgentServiceError("RESOURCE_ARCHIVED", "The agent is archived.", 409)
    draft = await session.scalar(
        select(AgentDraft).where(AgentDraft.agent_id == agent.id)
    )
    if draft is None:
        raise AgentServiceError("RESOURCE_NOT_FOUND", "Agent draft was not found.", 404)
    if "instructions" in payload.model_fields_set and payload.instructions is not None:
        draft.instructions = payload.instructions
    if "model" in payload.model_fields_set and payload.model is not None:
        if find_model(payload.model.provider, payload.model.name) is None:
            raise AgentServiceError(
                "MODEL_NOT_FOUND",
                "The selected model is not available in the platform catalog.",
                422,
                {"field": "model.name"},
            )
        draft.model_provider = payload.model.provider
        draft.model_name = payload.model.name
        draft.model_config = payload.model.model_dump(exclude={"provider", "name"})
    if (
        "runtime_config" in payload.model_fields_set
        and payload.runtime_config is not None
    ):
        draft.runtime_config = payload.runtime_config.model_dump()
    if (
        "memory_config" in payload.model_fields_set
        and payload.memory_config is not None
    ):
        memory_config = await validate_memory_configuration(
            session, agent.workspace_id, payload.memory_config
        )
        draft.memory_config = _memory_config_data(memory_config)
    draft.updated_by = user_id
    await session.commit()
    await session.refresh(draft)
    return draft


async def publish_version(
    session: AsyncSession,
    agent: Agent,
    user_id: UUID,
    change_note: str | None,
) -> AgentVersion:
    locked_agent = await session.scalar(
        select(Agent)
        .where(Agent.id == agent.id, Agent.workspace_id == agent.workspace_id)
        .with_for_update()
    )
    if locked_agent is None:
        raise AgentServiceError("RESOURCE_NOT_FOUND", "Agent was not found.", 404)
    if locked_agent.status == AgentStatus.ARCHIVED:
        raise AgentServiceError("RESOURCE_ARCHIVED", "The agent is archived.", 409)
    draft = await session.scalar(
        select(AgentDraft).where(AgentDraft.agent_id == agent.id)
    )
    if draft is None:
        raise AgentServiceError("RESOURCE_NOT_FOUND", "Agent draft was not found.", 404)
    issues = validate_draft(draft)
    if issues:
        raise AgentServiceError(
            "DRAFT_INVALID",
            "The agent draft is not valid and cannot be published.",
            422,
            {"errors": [issue.model_dump() for issue in issues]},
        )

    await validate_memory_configuration(
        session, locked_agent.workspace_id, draft.memory_config
    )

    bindings = await session.execute(
        select(AgentDraftTool, ToolVersion, Tool)
        .join(ToolVersion, ToolVersion.id == AgentDraftTool.tool_version_id)
        .join(Tool, Tool.id == ToolVersion.tool_id)
        .where(
            AgentDraftTool.agent_id == locked_agent.id, AgentDraftTool.enabled.is_(True)
        )
        .order_by(ToolVersion.name.asc())
    )
    tool_snapshots: list[dict[str, object]] = []
    binding_rows = bindings.all()
    for binding, tool_version, tool in binding_rows:
        if (
            tool_version.workspace_id != locked_agent.workspace_id
            or tool.workspace_id != locked_agent.workspace_id
        ):
            raise AgentServiceError(
                "TOOL_WORKSPACE_MISMATCH",
                "A bound tool does not belong to the agent workspace.",
                422,
            )
        tool_snapshots.append(
            {
                "id": str(tool_version.id),
                "name": model_tool_name(binding.alias or tool.slug),
                "description": tool_version.description,
                "type": tool_version.executor_type.value,
                "input_schema": tool_version.input_schema,
                "output_schema": tool_version.output_schema,
                "executor": {
                    "type": tool_version.executor_type.value,
                    "config": tool_version.executor_config,
                },
                "version_number": tool_version.version_number,
                "risk_level": tool_version.risk_level.value,
            }
        )

    knowledge_rows = (
        await session.execute(
            select(AgentDraftKnowledgeBase, KnowledgeBase)
            .join(
                KnowledgeBase,
                KnowledgeBase.id == AgentDraftKnowledgeBase.knowledge_base_id,
            )
            .where(AgentDraftKnowledgeBase.agent_id == locked_agent.id)
        )
    ).all()
    knowledge_snapshots: list[dict[str, object]] = []
    for binding, knowledge_base in knowledge_rows:
        if knowledge_base.workspace_id != locked_agent.workspace_id:
            raise AgentServiceError(
                "KNOWLEDGE_WORKSPACE_MISMATCH",
                "A bound knowledge base does not belong to the agent workspace.",
                422,
            )
        if knowledge_base.status != KnowledgeBaseStatus.ACTIVE:
            raise AgentServiceError(
                "KNOWLEDGE_BASE_ARCHIVED",
                "Archived knowledge bases cannot be published.",
                409,
            )
        knowledge_snapshots.append(
            {
                "id": str(knowledge_base.id),
                "name": knowledge_base.name,
                "model": knowledge_base.embedding_model,
                "revision": knowledge_base.embedding_revision,
                "dimensions": knowledge_base.embedding_dimensions,
                "retrieval_config": binding.retrieval_config,
            }
        )

    next_version = locked_agent.latest_version_number + 1
    guardrail_rows = (
        await session.execute(
            select(AgentDraftGuardrail, GuardrailVersion, GuardrailPolicy)
            .join(
                GuardrailVersion,
                GuardrailVersion.id == AgentDraftGuardrail.guardrail_version_id,
            )
            .join(
                GuardrailPolicy,
                GuardrailPolicy.id == GuardrailVersion.guardrail_policy_id,
            )
            .where(
                AgentDraftGuardrail.agent_id == locked_agent.id,
                GuardrailPolicy.workspace_id == locked_agent.workspace_id,
            )
            .order_by(AgentDraftGuardrail.priority, GuardrailPolicy.name)
        )
    ).all()
    guardrail_snapshots: list[dict[str, object]] = [
        {
            "id": str(version_row.id),
            "policy_id": str(policy.id),
            "policy_name": policy.name,
            "version_number": version_row.version_number,
            "hook": binding.hook.value,
            "priority": binding.priority,
            "type": version_row.guardrail_type,
            "configuration": version_row.configuration,
            "source": "CUSTOM",
        }
        for binding, version_row, policy in guardrail_rows
    ]
    baseline_configuration = GuardrailConfiguration.model_validate(
        default_baseline().configuration
    ).model_dump(mode="json")
    guardrail_snapshots.insert(
        0,
        {
            "id": None,
            "policy_id": None,
            "policy_name": "Platform Default",
            "version_number": 1,
            "hook": "ALL",
            "priority": 0,
            "type": "RULE_SET",
            "configuration": baseline_configuration,
            "source": "PLATFORM_DEFAULT",
        },
    )
    version = AgentVersion(
        workspace_id=locked_agent.workspace_id,
        agent_id=locked_agent.id,
        version_number=next_version,
        instructions=draft.instructions,
        model_provider=draft.model_provider,
        model_name=draft.model_name,
        model_config=draft.model_config,
        runtime_config=draft.runtime_config,
        memory_config=_memory_config_data(draft.memory_config),
        guardrails_enabled=draft.guardrails_enabled,
        snapshot=build_snapshot(
            draft, tool_snapshots, knowledge_snapshots, guardrail_snapshots
        ),
        change_note=change_note,
        created_by=user_id,
    )
    locked_agent.latest_version_number = next_version
    session.add(version)
    await session.flush()
    for binding, _, _ in binding_rows:
        session.add(
            AgentVersionTool(
                agent_version_id=version.id,
                tool_version_id=binding.tool_version_id,
                alias=binding.alias,
                configuration=binding.configuration,
            )
        )
    for binding, _ in knowledge_rows:
        session.add(
            AgentVersionKnowledgeBase(
                agent_version_id=version.id,
                knowledge_base_id=binding.knowledge_base_id,
                retrieval_config=binding.retrieval_config,
            )
        )
    for binding, _, _ in guardrail_rows:
        session.add(
            AgentVersionGuardrail(
                agent_version_id=version.id,
                guardrail_version_id=binding.guardrail_version_id,
                hook=binding.hook,
                priority=binding.priority,
            )
        )
    await session.commit()
    await session.refresh(version)
    return version


def make_agent_select(workspace_id: UUID) -> Select[tuple[Agent]]:
    return select(Agent).where(Agent.workspace_id == workspace_id)
