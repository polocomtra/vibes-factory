"""At-least-once continuation worker for resolved approvals."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select

from ..config import get_settings
from ..credentials.service import DatabaseCredentialResolver
from ..db import SessionFactory
from ..mcp.executor import DatabaseMCPServerResolver
from ..mcp.manager import MCPManager
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    Agent,
    ApprovalKind,
    ApprovalRequest,
    ApprovalStatus,
    Job,
    JobStatus,
    JobType,
    Run,
    RunStatus,
    Session,
    Span,
    SpanStatus,
    ToolVersion,
    Trace,
    TraceStatus,
    User,
    WorkflowEdge,
    WorkflowEventType,
    WorkflowNode,
    WorkflowNodeRun,
    WorkflowNodeStatus,
    WorkflowRun,
    WorkflowRunEvent,
    WorkflowRunStatus,
)
from ..runs.routes import _build_runtime_request, _load_version
from ..runs.schemas import RunCreateRequest
from ..runtime.contracts import TextInput
from ..runtime.service import AgentRuntime
from ..tools.contracts import ToolExecutionContext
from ..tools.pipeline import ToolExecutionPipeline

logger = structlog.get_logger(__name__)


async def _finish_job(
    session, job: Job, *, failed: bool = False, error: dict[str, str] | None = None
) -> None:
    job.status = JobStatus.FAILED if failed else JobStatus.COMPLETED
    job.error = error
    job.lease_owner = None
    job.lease_expires_at = None
    await session.commit()


async def _fail_run(session, run: Run, code: str, message: str) -> None:
    now = datetime.now(UTC)
    run.status = RunStatus.FAILED
    run.error_code = code
    run.error_message = message
    run.completed_at = now
    trace = await session.get(Trace, run.trace_id)
    if trace is not None:
        trace.status = TraceStatus.FAILED
        trace.completed_at = now
    spans = list(
        (
            await session.scalars(
                select(Span).where(
                    Span.run_id == run.id, Span.status == SpanStatus.RUNNING
                )
            )
        ).all()
    )
    for span in spans:
        span.status = SpanStatus.FAILED
        span.error_json = {"code": code, "message": message}
        span.completed_at = now


async def _fail_workflow_for_child(session, run: Run, code: str, message: str) -> None:
    if run.workflow_run_id is None:
        return
    workflow_run = await session.get(WorkflowRun, run.workflow_run_id)
    if workflow_run is None or workflow_run.status in {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.CANCELLED,
    }:
        return
    workflow_run.status = WorkflowRunStatus.FAILED
    workflow_run.error_code = code
    workflow_run.error_message = message
    workflow_run.completed_at = datetime.now(UTC)
    await _append_workflow_event(
        session,
        workflow_run,
        WorkflowEventType.WORKFLOW_FAILED,
        {"code": code, "message": message},
    )


async def _enqueue_workflow(session, workflow_run: WorkflowRun) -> None:
    generation = (
        int(
            await session.scalar(
                select(func.coalesce(func.max(Job.generation), 0)).where(
                    Job.job_type == JobType.WORKFLOW_EXECUTION,
                    Job.resource_id == workflow_run.id,
                )
            )
            or 0
        )
        + 1
    )
    session.add(
        Job(
            workspace_id=workflow_run.workspace_id,
            job_type=JobType.WORKFLOW_EXECUTION,
            status=JobStatus.QUEUED,
            resource_type="workflow",
            resource_id=workflow_run.id,
            generation=generation,
            payload={"workflow_run_id": str(workflow_run.id), "generation": generation},
        )
    )


async def _append_workflow_event(
    session,
    workflow_run: WorkflowRun,
    event: WorkflowEventType,
    data: dict[str, object],
    node_run_id: UUID | None = None,
) -> None:
    sequence = workflow_run.next_event_sequence
    workflow_run.next_event_sequence += 1
    session.add(
        WorkflowRunEvent(
            workflow_run_id=workflow_run.id,
            sequence=sequence,
            event_type=event,
            node_run_id=node_run_id,
            data=data,
        )
    )


async def _resume_workflow_node_approval(session, request: ApprovalRequest) -> None:
    workflow_run = await session.get(WorkflowRun, request.workflow_run_id)
    node_run = await session.get(WorkflowNodeRun, request.workflow_node_run_id)
    if workflow_run is None or node_run is None:
        request.continuation_status = "FAILED"
        request.continuation_error = {
            "code": "WORKFLOW_APPROVAL_STATE_INVALID",
            "message": "The workflow approval state is incomplete.",
        }
        return
    if workflow_run.status == WorkflowRunStatus.CANCELLED:
        request.continuation_status = "COMPLETED"
        request.continuation_completed_at = datetime.now(UTC)
        return
    node = await session.get(WorkflowNode, node_run.workflow_node_id)
    if node is None:
        request.continuation_status = "FAILED"
        return
    decision = (
        "APPROVED"
        if request.status == ApprovalStatus.APPROVED
        else "EXPIRED"
        if request.status == ApprovalStatus.EXPIRED
        else "REJECTED"
    )
    # A risky TOOL node uses the same approval record but must execute the
    # persisted arguments before the node can advance.  Rejections/expiry
    # follow the rejected branch without dispatching the external action.
    workflow_tool = bool(request.metadata_json.get("workflow_tool"))
    tool_output: dict[str, object] | None = None
    if workflow_tool and decision == "APPROVED":
        if request.tool_version_id is None:
            request.continuation_error = {
                "code": "APPROVAL_TOOL_VERSION_MISSING",
                "message": "The approved workflow tool version is missing.",
            }
            return
        version = await session.get(ToolVersion, request.tool_version_id)
        if version is None:
            request.continuation_error = {
                "code": "TOOL_VERSION_NOT_FOUND",
                "message": "The approved workflow tool version was not found.",
            }
            return
        pipeline = ToolExecutionPipeline(
            credential_resolver=DatabaseCredentialResolver(session),
            mcp_manager=MCPManager(),
            mcp_server_resolver=DatabaseMCPServerResolver(session),
        )
        result = await pipeline.execute(
            version,
            request.arguments,
            ToolExecutionContext(
                workspace_id=workflow_run.workspace_id,
                run_id=workflow_run.id,
                trace_id=workflow_run.trace_id,
                timeout_seconds=min(version.timeout_seconds, 300),
            ),
        )
        if not result.ok:
            request.continuation_error = {
                "code": result.error_code or "TOOL_FAILED",
                "message": result.error_message or "The approved workflow tool failed.",
            }
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.error_code = request.continuation_error["code"]
            workflow_run.error_message = request.continuation_error["message"]
            workflow_run.completed_at = datetime.now(UTC)
            return
        tool_output = {"output": result.output or {}, "metadata": result.metadata}
    node_run.status = WorkflowNodeStatus.COMPLETED
    node_run.output = {
        "decision": decision,
        "resolved_by": str(request.resolved_by) if request.resolved_by else None,
        "resolved_at": request.resolved_at.isoformat() if request.resolved_at else None,
        **({"tool": tool_output} if tool_output is not None else {}),
    }
    node_run.completed_at = datetime.now(UTC)
    if node_run.span_id:
        node_span = await session.get(Span, node_run.span_id)
        if node_span is not None:
            node_span.status = SpanStatus.COMPLETED
            node_span.output = node_run.output
            node_span.completed_at = node_run.completed_at
    workflow_run.status = WorkflowRunStatus.RUNNING
    workflow_run.waiting_reason = None
    outgoing = list(
        (
            await session.scalars(
                select(WorkflowEdge).where(WorkflowEdge.source_node_id == node.id)
            )
        ).all()
    )
    handle = "approved" if decision == "APPROVED" else "rejected"
    target = next(
        (edge.target_node_id for edge in outgoing if edge.source_handle == handle), None
    )
    if target is None:
        workflow_run.status = WorkflowRunStatus.FAILED
        workflow_run.error_code = "WORKFLOW_APPROVAL_ROUTE_INVALID"
        workflow_run.error_message = (
            "The approval decision has no matching workflow edge."
        )
        workflow_run.completed_at = datetime.now(UTC)
    else:
        workflow_run.current_node_id = target
        await _enqueue_workflow(session, workflow_run)
    await _append_workflow_event(
        session,
        workflow_run,
        WorkflowEventType.WORKFLOW_NODE_COMPLETED,
        {
            "node_key": node.node_key,
            "status": node_run.status.value,
            "output": node_run.output,
        },
        node_run.id,
    )
    await _append_workflow_event(
        session,
        workflow_run,
        WorkflowEventType.APPROVAL_RESOLVED,
        {
            "approval_request_id": str(request.id),
            "decision": decision,
            "node_key": node.node_key,
        },
        node_run.id,
    )
    if request.approval_span_id:
        approval_span = await session.get(Span, request.approval_span_id)
        if approval_span is not None:
            approval_span.status = (
                SpanStatus.COMPLETED if decision == "APPROVED" else SpanStatus.FAILED
            )
            approval_span.completed_at = datetime.now(UTC)


async def _resume_completed_agent_node(session, run: Run) -> None:
    if run.workflow_run_id is None or run.status != RunStatus.COMPLETED:
        return
    workflow_run = await session.get(WorkflowRun, run.workflow_run_id)
    node_run = await session.scalar(
        select(WorkflowNodeRun).where(WorkflowNodeRun.agent_run_id == run.id)
    )
    if workflow_run is None or node_run is None:
        return
    node = await session.get(WorkflowNode, node_run.workflow_node_id)
    if node is None:
        return
    if run.session_id:
        hidden_session = await session.get(Session, run.session_id)
        run.session_id = None
        if hidden_session is not None and hidden_session.metadata_json.get("hidden"):
            await session.delete(hidden_session)
    node_run.status = WorkflowNodeStatus.COMPLETED
    node_run.output = run.output or {}
    node_run.completed_at = datetime.now(UTC)
    if node_run.span_id:
        node_span = await session.get(Span, node_run.span_id)
        if node_span is not None:
            node_span.status = SpanStatus.COMPLETED
            node_span.output = node_run.output
            node_span.completed_at = node_run.completed_at
    edge = await session.scalar(
        select(WorkflowEdge).where(WorkflowEdge.source_node_id == node.id).limit(1)
    )
    if edge is not None:
        workflow_run.current_node_id = edge.target_node_id
        workflow_run.status = WorkflowRunStatus.RUNNING
        workflow_run.waiting_reason = None
        await _enqueue_workflow(session, workflow_run)


async def process_approval_resume(job: Job, worker_id: str) -> None:
    async with SessionFactory() as session:
        request = await session.get(
            ApprovalRequest, job.resource_id, with_for_update=True
        )
        if request is None:
            await _finish_job(session, job)
            return
        if request.continuation_status == "COMPLETED":
            await _finish_job(session, job)
            return
        request.continuation_status = "RUNNING"
        request.continuation_started_at = datetime.now(UTC)
        await session.flush()
        if request.kind == ApprovalKind.WORKFLOW_NODE:
            await _resume_workflow_node_approval(session, request)
            request.continuation_status = (
                "COMPLETED" if request.continuation_error is None else "FAILED"
            )
            request.continuation_completed_at = datetime.now(UTC)
            await _finish_job(
                session,
                job,
                failed=request.continuation_error is not None,
                error=request.continuation_error,
            )
            return
        if request.kind != ApprovalKind.TOOL_CALL or request.run_id is None:
            request.continuation_status = "FAILED"
            request.continuation_error = {
                "code": "APPROVAL_WORKFLOW_RESUME_UNSUPPORTED",
                "message": (
                    "This approval target is not supported by the runtime worker."
                ),
            }
            await _finish_job(
                session, job, failed=True, error=request.continuation_error
            )
            return
        run = await session.get(Run, request.run_id)
        if run is None:
            request.continuation_status = "FAILED"
            await _finish_job(
                session,
                job,
                failed=True,
                error={
                    "code": "RUN_NOT_FOUND",
                    "message": "The waiting run was not found.",
                },
            )
            return
        if request.status in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
            code = (
                "APPROVAL_REJECTED"
                if request.status == ApprovalStatus.REJECTED
                else "APPROVAL_EXPIRED"
            )
            await _fail_run(
                session, run, code, "The approval request was not approved."
            )
            await _fail_workflow_for_child(
                session, run, code, "The child agent approval was not approved."
            )
            request.continuation_status = "COMPLETED"
            request.continuation_completed_at = datetime.now(UTC)
            await _finish_job(session, job)
            return
        if request.status != ApprovalStatus.APPROVED:
            request.continuation_status = "FAILED"
            await _finish_job(
                session,
                job,
                failed=True,
                error={
                    "code": "APPROVAL_STATE_INVALID",
                    "message": "The approval is not resolved.",
                },
            )
            return
        agent = await session.get(Agent, run.agent_id)
        conversation = (
            await session.get(Session, run.session_id) if run.session_id else None
        )
        user = (
            await session.get(User, conversation.user_id)
            if conversation is not None
            else None
        )
        if agent is None or conversation is None or user is None:
            await _fail_run(
                session,
                run,
                "APPROVAL_RESUME_STATE_INVALID",
                "The waiting run is missing its session state.",
            )
            request.continuation_status = "FAILED"
            await _finish_job(
                session,
                job,
                failed=True,
                error={
                    "code": "APPROVAL_RESUME_STATE_INVALID",
                    "message": "The waiting run is missing its session state.",
                },
            )
            return
        version = await _load_version(session, agent, run.agent_version_id)
        payload = RunCreateRequest(
            input=TextInput.model_validate(run.input),
            session_id=conversation.id,
            agent_version_id=version.id,
        )
        runtime_request = await _build_runtime_request(payload, agent, user, session)
        runtime_request = runtime_request.model_copy(
            update={"resume_run_id": run.id, "resume_approval_id": request.id}
        )
        try:
            await AgentRuntime(
                session, ModelProviderRegistry.from_settings(get_settings())
            ).run(runtime_request)
            await session.refresh(run)
            await _resume_completed_agent_node(session, run)
            request.continuation_status = "COMPLETED"
            request.continuation_completed_at = datetime.now(UTC)
            await _finish_job(session, job)
        except Exception:
            logger.exception(
                "approval_resume_failed",
                approval_request_id=str(request.id),
                run_id=str(run.id),
                worker_id=worker_id,
            )
            request.continuation_status = "FAILED"
            request.continuation_error = {
                "code": "APPROVAL_RESUME_FAILED",
                "message": "The approved action could not be resumed.",
            }
            await _finish_job(
                session, job, failed=True, error=request.continuation_error
            )
