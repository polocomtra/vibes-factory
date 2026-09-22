"""Application services for workflow identity, drafts and immutable versions."""

from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Workflow,
    WorkflowDraft,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowStatus,
    WorkflowVersion,
)
from .schemas import (
    WorkflowCreateRequest,
    WorkflowDefinition,
    WorkflowDraftUpdateRequest,
    WorkflowEdgeDefinition,
    WorkflowNodeDefinition,
    WorkflowUpdateRequest,
)
from .validation import validate_definition


class WorkflowServiceError(Exception):
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


def default_definition() -> WorkflowDefinition:
    return WorkflowDefinition(
        nodes=[
            WorkflowNodeDefinition(
                key="start",
                type=WorkflowNodeType.START,
                name="Start",
                position={"x": 80, "y": 160},
            ),
            WorkflowNodeDefinition(
                key="end",
                type=WorkflowNodeType.END,
                name="End",
                position={"x": 480, "y": 160},
            ),
        ],
        edges=[WorkflowEdgeDefinition(source="start", target="end")],
    )


async def create_workflow(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    payload: WorkflowCreateRequest,
) -> Workflow:
    existing = await session.scalar(
        select(Workflow).where(
            Workflow.workspace_id == workspace_id, Workflow.slug == payload.slug
        )
    )
    if existing is not None:
        raise WorkflowServiceError(
            "WORKFLOW_SLUG_CONFLICT",
            "A workflow with this slug already exists in the workspace.",
            409,
        )
    workflow = Workflow(
        workspace_id=workspace_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        created_by=user_id,
    )
    session.add(workflow)
    await session.flush()
    session.add(
        WorkflowDraft(
            workflow_id=workflow.id,
            definition=default_definition().model_dump(mode="json"),
            updated_by=user_id,
        )
    )
    await session.commit()
    await session.refresh(workflow)
    return workflow


async def get_draft(session: AsyncSession, workflow: Workflow) -> WorkflowDraft:
    draft = await session.scalar(
        select(WorkflowDraft).where(WorkflowDraft.workflow_id == workflow.id)
    )
    if draft is None:
        raise WorkflowServiceError(
            "RESOURCE_NOT_FOUND", "Workflow draft was not found.", 404
        )
    return draft


async def update_workflow(
    session: AsyncSession, workflow: Workflow, payload: WorkflowUpdateRequest
) -> Workflow:
    if workflow.status == WorkflowStatus.ARCHIVED:
        raise WorkflowServiceError(
            "RESOURCE_ARCHIVED", "The workflow is archived.", 409
        )
    if payload.name is not None:
        workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    await session.commit()
    await session.refresh(workflow)
    return workflow


async def archive_workflow(session: AsyncSession, workflow: Workflow) -> None:
    """Archive a workflow without removing its immutable versions or run history."""
    if workflow.status == WorkflowStatus.ARCHIVED:
        return
    workflow.status = WorkflowStatus.ARCHIVED
    await session.commit()


async def update_draft(
    session: AsyncSession,
    workflow: Workflow,
    user_id: UUID,
    payload: WorkflowDraftUpdateRequest,
) -> WorkflowDraft:
    if workflow.status == WorkflowStatus.ARCHIVED:
        raise WorkflowServiceError(
            "RESOURCE_ARCHIVED", "The workflow is archived.", 409
        )
    draft = await get_draft(session, workflow)
    if draft.revision != payload.expected_revision:
        raise WorkflowServiceError(
            "DRAFT_VERSION_CONFLICT",
            "The workflow draft changed in another tab. Reload before saving.",
            409,
            {"revision": draft.revision},
        )
    issues = await validate_definition(
        session, workflow.workspace_id, payload.definition
    )
    # Drafts may be temporarily incomplete, but malformed expressions and resource
    # references are rejected so the editor never stores an unparseable contract.
    hard_errors = [
        item
        for item in issues
        if item.code
        not in {
            "START_COUNT_INVALID",
            "END_REQUIRED",
            "START_SHAPE_INVALID",
            "END_SHAPE_INVALID",
            "NODE_OUTGOING_INVALID",
            "CONDITION_BRANCH_INVALID",
            "UNREACHABLE_NODE",
            "CYCLE_UNSUPPORTED",
        }
    ]
    if hard_errors:
        raise WorkflowServiceError(
            "DRAFT_INVALID",
            "The workflow draft contains invalid node configuration.",
            422,
            {"errors": [item.model_dump() for item in hard_errors]},
        )
    draft.definition = payload.definition.model_dump(mode="json")
    draft.revision += 1
    draft.updated_by = user_id
    await session.commit()
    await session.refresh(draft)
    return draft


async def publish_version(
    session: AsyncSession, workflow: Workflow, user_id: UUID
) -> WorkflowVersion:
    locked = await session.scalar(
        select(Workflow)
        .where(
            Workflow.id == workflow.id, Workflow.workspace_id == workflow.workspace_id
        )
        .with_for_update()
    )
    if locked is None:
        raise WorkflowServiceError("RESOURCE_NOT_FOUND", "Workflow was not found.", 404)
    draft = await get_draft(session, locked)
    definition = WorkflowDefinition.model_validate(draft.definition)
    issues = await validate_definition(session, locked.workspace_id, definition)
    if issues:
        raise WorkflowServiceError(
            "DRAFT_INVALID",
            "The workflow draft is not valid and cannot be published.",
            422,
            {"errors": [item.model_dump() for item in issues]},
        )
    version_number = locked.latest_version_number + 1
    version = WorkflowVersion(
        workspace_id=locked.workspace_id,
        workflow_id=locked.id,
        version_number=version_number,
        configuration=definition.configuration
        | {
            "schema_version": definition.schema_version,
            "viewport": definition.viewport,
            "budget": definition.configuration.get("budget", {}),
        },
        created_by=user_id,
    )
    session.add(version)
    await session.flush()
    node_ids: dict[str, UUID] = {}
    for node in definition.nodes:
        row = WorkflowNode(
            workflow_version_id=version.id,
            node_key=node.key,
            node_type=node.type,
            name=node.name,
            configuration=node.config,
            position=node.position,
        )
        session.add(row)
        await session.flush()
        node_ids[node.key] = row.id
    for edge in definition.edges:
        session.add(
            WorkflowEdge(
                workflow_version_id=version.id,
                source_node_id=node_ids[edge.source],
                target_node_id=node_ids[edge.target],
                source_handle=edge.source_handle,
                priority=edge.priority,
            )
        )
    locked.latest_version_number = version_number
    await session.commit()
    await session.refresh(version)
    return version


def workflow_definition_from_version(
    nodes: list[WorkflowNode], edges: list[WorkflowEdge], version: WorkflowVersion
) -> WorkflowDefinition:
    node_by_id = {node.id: node for node in nodes}
    return WorkflowDefinition(
        schema_version=cast(Literal[1], 1),
        configuration={
            key: value
            for key, value in version.configuration.items()
            if key not in {"schema_version", "viewport"}
        },
        viewport=version.configuration.get("viewport"),
        nodes=[
            WorkflowNodeDefinition(
                key=node.node_key,
                type=node.node_type,
                name=node.name,
                config=node.configuration,
                position=node.position,
            )
            for node in nodes
        ],
        edges=[
            WorkflowEdgeDefinition(
                source=node_by_id[edge.source_node_id].node_key,
                target=node_by_id[edge.target_node_id].node_key,
                source_handle=edge.source_handle,
                priority=edge.priority,
            )
            for edge in edges
        ],
    )
