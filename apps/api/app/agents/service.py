"""Application services for Agent identity, drafts and immutable versions."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Agent, AgentDraft, AgentStatus, AgentVersion
from .catalog import find_model, get_default_model
from .schemas import (
    AgentCreateRequest,
    AgentDraftUpdateRequest,
    AgentUpdateRequest,
    DraftValidationIssue,
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
    return issues


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


def build_snapshot(draft: AgentDraft) -> dict[str, object]:
    return {
        "schema_version": 1,
        "instructions": draft.instructions,
        "model": {
            "provider": draft.model_provider,
            "name": draft.model_name,
            **_normalized_model_config(draft.model_config),
        },
        "runtime_config": draft.runtime_config,
        "memory_config": draft.memory_config,
        "tools": [],
        "knowledge_bases": [],
        "guardrails": [],
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
            memory_config=payload.memory_config.model_dump(),
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
        draft.memory_config = payload.memory_config.model_dump()
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

    next_version = locked_agent.latest_version_number + 1
    version = AgentVersion(
        workspace_id=locked_agent.workspace_id,
        agent_id=locked_agent.id,
        version_number=next_version,
        instructions=draft.instructions,
        model_provider=draft.model_provider,
        model_name=draft.model_name,
        model_config=draft.model_config,
        runtime_config=draft.runtime_config,
        memory_config=draft.memory_config,
        snapshot=build_snapshot(draft),
        change_note=change_note,
        created_by=user_id,
    )
    locked_agent.latest_version_number = next_version
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


def make_agent_select(workspace_id: UUID) -> Select[tuple[Agent]]:
    return select(Agent).where(Agent.workspace_id == workspace_id)
