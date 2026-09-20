"""Workspace-safe guardrail policy and draft-binding services."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Agent,
    AgentDraft,
    AgentDraftGuardrail,
    GuardrailHook,
    GuardrailPolicy,
    GuardrailVersion,
    ToolVersion,
)
from .contracts import GuardrailConfiguration
from .engine import GuardrailConfigurationError, validate_configuration
from .schemas import (
    DraftGuardrailAttachRequest,
    GuardrailPolicyCreateRequest,
    GuardrailVersionCreateRequest,
)


class GuardrailServiceError(Exception):
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


async def create_policy(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: GuardrailPolicyCreateRequest,
) -> GuardrailPolicy:
    existing = await session.scalar(
        select(GuardrailPolicy).where(
            GuardrailPolicy.workspace_id == workspace_id,
            GuardrailPolicy.name == payload.name.strip(),
        )
    )
    if existing is not None:
        raise GuardrailServiceError(
            "GUARDRAIL_POLICY_CONFLICT",
            "A guardrail policy with this name already exists in the workspace.",
            409,
        )
    policy = GuardrailPolicy(
        workspace_id=workspace_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        created_by=user_id,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return policy


async def create_version(
    session: AsyncSession,
    policy: GuardrailPolicy,
    user_id: UUID,
    payload: GuardrailVersionCreateRequest,
) -> GuardrailVersion:
    if payload.type != "RULE_SET":
        raise GuardrailServiceError(
            "GUARDRAIL_TYPE_UNSUPPORTED",
            "Only RULE_SET guardrails are supported in this phase.",
            422,
        )
    try:
        configuration = validate_configuration(
            payload.configuration.model_dump(mode="json")
        )
    except (GuardrailConfigurationError, ValueError) as exc:
        raise GuardrailServiceError(
            "GUARDRAIL_CONFIGURATION_INVALID",
            str(exc),
            422,
        ) from exc
    referenced_tool_ids = {
        tool_id
        for rule in configuration.rules
        for tool_id in (
            *rule.allowed_tool_version_ids,
            *rule.denied_tool_version_ids,
        )
    }
    if referenced_tool_ids:
        owned_tool_ids = set(
            (
                await session.scalars(
                    select(ToolVersion.id).where(
                        ToolVersion.workspace_id == policy.workspace_id,
                        ToolVersion.id.in_(referenced_tool_ids),
                    )
                )
            ).all()
        )
        if owned_tool_ids != referenced_tool_ids:
            raise GuardrailServiceError(
                "GUARDRAIL_TOOL_WORKSPACE_MISMATCH",
                "Tool policy references a tool version outside this workspace.",
                422,
            )
    locked = await session.scalar(
        select(GuardrailPolicy)
        .where(
            GuardrailPolicy.id == policy.id,
            GuardrailPolicy.workspace_id == policy.workspace_id,
        )
        .with_for_update()
    )
    if locked is None:
        raise GuardrailServiceError(
            "RESOURCE_NOT_FOUND", "The policy was not found.", 404
        )
    version = GuardrailVersion(
        guardrail_policy_id=locked.id,
        version_number=locked.latest_version_number + 1,
        guardrail_type=payload.type,
        configuration=configuration.model_dump(mode="json"),
        created_by=user_id,
    )
    locked.latest_version_number += 1
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def get_policy(
    session: AsyncSession, policy_id: UUID, workspace_id: UUID | None = None
) -> GuardrailPolicy:
    statement = select(GuardrailPolicy).where(GuardrailPolicy.id == policy_id)
    if workspace_id is not None:
        statement = statement.where(GuardrailPolicy.workspace_id == workspace_id)
    policy = await session.scalar(statement)
    if policy is None:
        raise GuardrailServiceError(
            "RESOURCE_NOT_FOUND", "The guardrail policy was not found.", 404
        )
    return policy


async def get_version(
    session: AsyncSession, version_id: UUID, workspace_id: UUID | None = None
) -> tuple[GuardrailVersion, GuardrailPolicy]:
    statement: Select[tuple[GuardrailVersion, GuardrailPolicy]] = (
        select(GuardrailVersion, GuardrailPolicy)
        .join(
            GuardrailPolicy, GuardrailPolicy.id == GuardrailVersion.guardrail_policy_id
        )
        .where(GuardrailVersion.id == version_id)
    )
    if workspace_id is not None:
        statement = statement.where(GuardrailPolicy.workspace_id == workspace_id)
    row = (await session.execute(statement)).tuples().one_or_none()
    if row is None:
        raise GuardrailServiceError(
            "RESOURCE_NOT_FOUND", "The guardrail version was not found.", 404
        )
    return row


async def list_versions(
    session: AsyncSession, policy: GuardrailPolicy
) -> Sequence[GuardrailVersion]:
    return (
        await session.scalars(
            select(GuardrailVersion)
            .where(GuardrailVersion.guardrail_policy_id == policy.id)
            .order_by(GuardrailVersion.version_number.desc())
        )
    ).all()


async def policy_usage_count(session: AsyncSession, policy_id: UUID) -> int:
    """Count draft and published agent bindings for the policy."""

    draft_count = await session.scalar(
        select(func.count())
        .select_from(AgentDraftGuardrail)
        .join(
            GuardrailVersion,
            GuardrailVersion.id == AgentDraftGuardrail.guardrail_version_id,
        )
        .where(GuardrailVersion.guardrail_policy_id == policy_id)
    )
    from ..models import AgentVersionGuardrail

    version_count = await session.scalar(
        select(func.count())
        .select_from(AgentVersionGuardrail)
        .join(
            GuardrailVersion,
            GuardrailVersion.id == AgentVersionGuardrail.guardrail_version_id,
        )
        .where(GuardrailVersion.guardrail_policy_id == policy_id)
    )
    return int(draft_count or 0) + int(version_count or 0)


async def set_enabled(
    session: AsyncSession, agent: Agent, user_id: UUID, enabled: bool
) -> AgentDraft:
    draft = await session.scalar(
        select(AgentDraft).where(AgentDraft.agent_id == agent.id)
    )
    if draft is None:
        raise GuardrailServiceError(
            "RESOURCE_NOT_FOUND", "The agent draft was not found.", 404
        )
    draft.guardrails_enabled = enabled
    draft.updated_by = user_id
    await session.commit()
    await session.refresh(draft)
    return draft


async def list_draft_bindings(
    session: AsyncSession, agent: Agent
) -> Sequence[tuple[AgentDraftGuardrail, GuardrailVersion, GuardrailPolicy]]:
    statement = (
        select(AgentDraftGuardrail, GuardrailVersion, GuardrailPolicy)
        .join(
            GuardrailVersion,
            GuardrailVersion.id == AgentDraftGuardrail.guardrail_version_id,
        )
        .join(
            GuardrailPolicy, GuardrailPolicy.id == GuardrailVersion.guardrail_policy_id
        )
        .where(
            AgentDraftGuardrail.agent_id == agent.id,
            GuardrailPolicy.workspace_id == agent.workspace_id,
        )
        .order_by(AgentDraftGuardrail.priority, GuardrailPolicy.name)
    )
    return (await session.execute(statement)).tuples().all()


async def attach_binding(
    session: AsyncSession, agent: Agent, payload: DraftGuardrailAttachRequest
) -> AgentDraftGuardrail:
    version, policy = await get_version(
        session, payload.guardrail_version_id, agent.workspace_id
    )
    config = GuardrailConfiguration.model_validate(version.configuration)
    for rule in config.rules:
        if (
            rule.type.value == "TOOL_POLICY"
            and payload.hook != GuardrailHook.TOOL_INPUT
        ):
            raise GuardrailServiceError(
                "GUARDRAIL_HOOK_INVALID",
                "Tool policies may only be attached to TOOL_INPUT.",
                422,
            )
    existing = await session.get(
        AgentDraftGuardrail,
        (agent.id, payload.guardrail_version_id, payload.hook),
    )
    if existing is not None:
        raise GuardrailServiceError(
            "GUARDRAIL_BINDING_CONFLICT",
            "This guardrail version is already attached to the hook.",
            409,
        )
    binding = AgentDraftGuardrail(
        agent_id=agent.id,
        guardrail_version_id=version.id,
        hook=payload.hook,
        priority=payload.priority,
    )
    session.add(binding)
    await session.commit()
    await session.refresh(binding)
    del policy
    return binding


async def remove_binding(
    session: AsyncSession, agent: Agent, version_id: UUID, hook: GuardrailHook
) -> None:
    existing = await session.scalar(
        select(AgentDraftGuardrail).where(
            AgentDraftGuardrail.agent_id == agent.id,
            AgentDraftGuardrail.guardrail_version_id == version_id,
            AgentDraftGuardrail.hook == hook,
        )
    )
    if existing is None:
        raise GuardrailServiceError(
            "RESOURCE_NOT_FOUND", "The guardrail binding was not found.", 404
        )
    await session.delete(existing)
    await session.commit()
