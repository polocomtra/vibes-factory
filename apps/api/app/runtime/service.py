"""Public facade for agent runtime execution."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..credentials.service import DatabaseCredentialResolver
from ..guardrails.contracts import (
    GuardrailContext,
    GuardrailDecision,
    GuardrailEvaluation,
)
from ..guardrails.engine import GuardrailEngine, GuardrailPolicyInput
from ..knowledge.embedding import (
    EmbeddingProvider,
    HttpEmbeddingProvider,
)
from ..mcp.executor import DatabaseMCPServerResolver
from ..mcp.manager import MCPManager
from ..model_providers.contracts import (
    ModelProvider,
    StreamingModelProvider,
)
from ..model_providers.registry import ModelProviderRegistry
from ..models import (
    GuardrailHook,
    Message,
    Run,
    Span,
    SpanStatus,
    SpanType,
    ToolRiskLevel,
    Trace,
    WorkflowEventType,
    WorkflowRun,
    WorkflowRunEvent,
)
from ..tools.pipeline import SecretRedactor, ToolExecutionPipeline
from .accounting import RuntimeAccounting
from .budget import (
    ExecutionContext,
)
from .context import ContextBuilder
from .contracts import (
    AgentRunRequest,
    AgentRunResult,
    RuntimeStreamEvent,
    TextInput,
)
from .errors import RuntimeExecutionError
from .lifecycle import RunLifecycle
from .model_access import ModelAccessResolver
from .retrieval import RuntimeRetrieval
from .run_execution import RunExecution
from .state import RunState
from .stream_execution import StreamExecution
from .tool_execution import ToolBatchExecutor

logger = structlog.get_logger(__name__)


class AgentRuntime:
    """Coordinate runtime execution and its focused collaborators."""

    def __init__(
        self,
        session: AsyncSession,
        registry: ModelProviderRegistry,
        *,
        context_builder: ContextBuilder | None = None,
        tool_pipeline: ToolExecutionPipeline | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.model_access = ModelAccessResolver(session, registry)
        self.context_builder = context_builder or ContextBuilder()
        self.tool_pipeline = tool_pipeline or ToolExecutionPipeline(
            credential_resolver=DatabaseCredentialResolver(session),
            mcp_manager=MCPManager(),
            mcp_server_resolver=DatabaseMCPServerResolver(session),
        )
        self.secret_redactor = SecretRedactor()
        self.embedding_provider = embedding_provider or HttpEmbeddingProvider(
            get_settings()
        )
        self.retrieval = RuntimeRetrieval(session, self.embedding_provider)
        self.accounting = RuntimeAccounting(session)
        self.lifecycle = RunLifecycle(session, self.accounting)
        self.run_execution = RunExecution(self)
        self.stream_execution = StreamExecution(self)
        self.tool_executor = ToolBatchExecutor(self)
        self.guardrail_engine = GuardrailEngine()

    async def _model_provider_and_key(
        self, request: AgentRunRequest, *, streaming: bool = False
    ) -> tuple[ModelProvider | StreamingModelProvider, str]:
        return await self.model_access.resolve(request, streaming=streaming)

    def _guardrail_policies(
        self, request: AgentRunRequest, hook: GuardrailHook
    ) -> tuple[GuardrailPolicyInput, ...]:
        if not request.agent_version.guardrails_enabled:
            return ()
        policies: list[GuardrailPolicyInput] = []
        for item in request.agent_version.guardrails:
            try:
                hooks = (
                    tuple(GuardrailHook(value) for value in item.hooks)
                    if item.hooks
                    else tuple(GuardrailHook)
                )
            except ValueError:
                continue
            if hook not in hooks:
                continue
            policies.append(
                GuardrailPolicyInput(
                    configuration=item.configuration,
                    hooks=hooks,
                    priority=item.priority,
                    version_id=item.version_id,
                    source=item.source,
                )
            )
        return tuple(policies)

    async def _workflow_child_event(
        self,
        run: Run,
        event_type: WorkflowEventType,
        data: dict[str, object],
    ) -> None:
        if run.workflow_run_id is None:
            return
        workflow_run = await self.session.get(WorkflowRun, run.workflow_run_id)
        if workflow_run is None:
            return
        sequence = workflow_run.next_event_sequence
        workflow_run.next_event_sequence += 1
        self.session.add(
            WorkflowRunEvent(
                workflow_run_id=workflow_run.id,
                sequence=sequence,
                event_type=event_type,
                data=data,
            )
        )

    async def _evaluate_guardrail(
        self,
        request: AgentRunRequest,
        run: Run,
        trace: Trace,
        parent_span: Span,
        hook: GuardrailHook,
        payload: object,
        *,
        tool_version_id: UUID | None = None,
        tool_name: str | None = None,
        tool_risk: ToolRiskLevel | None = None,
        tool_side_effect: bool = False,
        approval_resolved: bool = False,
        state: RunState,
    ) -> GuardrailEvaluation:
        started = datetime.now(UTC)
        try:
            context = GuardrailContext(
                hook=hook,
                workspace_id=request.workspace_id,
                run_id=run.id,
                trace_id=trace.id,
                tool_version_id=tool_version_id,
                tool_name=tool_name,
                tool_risk=tool_risk,
                tool_side_effect=tool_side_effect,
                payload=payload,
            )
            evaluation = self.guardrail_engine.evaluate(
                context, self._guardrail_policies(request, hook)
            )
        except Exception as exc:
            raise RuntimeExecutionError(
                "GUARDRAIL_CONFIGURATION_INVALID",
                "The published guardrail configuration is invalid.",
                status_code=422,
            ) from exc
        span = Span(
            id=uuid4(),
            trace_id=trace.id,
            parent_span_id=parent_span.id,
            run_id=run.id,
            span_type=SpanType.GUARDRAIL,
            name=f"guardrail.{hook.value.lower()}",
            status=(
                SpanStatus.FAILED
                if evaluation.decision == GuardrailDecision.BLOCK
                or (
                    evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL
                    and not approval_resolved
                )
                else SpanStatus.COMPLETED
            ),
            input={"hook": hook.value, "bytes": evaluation.input_bytes},
            output={"hook": hook.value, "bytes": evaluation.output_bytes},
            attributes={
                "hook": hook.value,
                "decision": evaluation.decision.value,
                "policy_version_id": (
                    str(evaluation.policy_version_id)
                    if evaluation.policy_version_id
                    else None
                ),
                "policy_source": evaluation.policy_source,
                "rule_id": evaluation.rule_id,
                "reason_code": evaluation.reason_code,
                "match_count": evaluation.match_count,
                "approval_resolved": approval_resolved,
                "duration_ms": max(
                    0, int((datetime.now(UTC) - started).total_seconds() * 1000)
                ),
            },
            error_json=(
                {
                    "code": (
                        "GUARDRAIL_APPROVAL_REQUIRED"
                        if evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL
                        else "GUARDRAIL_BLOCKED"
                    ),
                    "message": "The guardrail blocked this operation.",
                }
                if evaluation.decision == GuardrailDecision.BLOCK
                or (
                    evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL
                    and not approval_resolved
                )
                else None
            ),
            started_at=started,
            completed_at=datetime.now(UTC),
        )
        self.session.add(span)
        await self.session.commit()
        if evaluation.triggered and not (
            approval_resolved
            and evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL
        ):
            state.guardrail_events.append(
                {
                    "run_id": str(run.id),
                    "hook": hook.value,
                    "decision": evaluation.decision.value,
                    "rule_id": evaluation.rule_id,
                    "reason_code": evaluation.reason_code,
                    "match_count": evaluation.match_count,
                }
            )
            logger.info(
                {
                    GuardrailDecision.REDACT: "guardrail.redacted",
                    GuardrailDecision.BLOCK: "guardrail.blocked",
                    GuardrailDecision.REQUIRE_APPROVAL: "guardrail.approval_required",
                }.get(evaluation.decision, "guardrail.triggered"),
                outcome=(
                    "redacted"
                    if evaluation.decision == GuardrailDecision.REDACT
                    else "blocked"
                    if evaluation.decision == GuardrailDecision.BLOCK
                    else "approval_required"
                ),
                run_id=str(run.id),
                trace_id=str(trace.id),
                hook=hook.value,
                decision=evaluation.decision.value,
                reason_code=evaluation.reason_code,
                match_count=evaluation.match_count,
            )
        return evaluation

    async def _apply_input_guardrail(
        self,
        request: AgentRunRequest,
        run: Run,
        root_span: Span,
        user_message: Message,
        trace: Trace,
        state: RunState,
    ) -> AgentRunRequest:
        evaluation = await self._evaluate_guardrail(
            request,
            run,
            trace,
            root_span,
            GuardrailHook.INPUT,
            request.input.text,
            state=state,
        )
        if evaluation.decision == GuardrailDecision.BLOCK:
            raise RuntimeExecutionError(
                "GUARDRAIL_BLOCKED",
                "The input was blocked by a guardrail.",
                status_code=422,
            )
        if evaluation.decision == GuardrailDecision.REQUIRE_APPROVAL:
            raise RuntimeExecutionError(
                "GUARDRAIL_APPROVAL_REQUIRED",
                "This input requires approval before it can be processed.",
                status_code=422,
            )
        text = str(evaluation.value)
        request = request.model_copy(update={"input": TextInput(text=text)})
        safe_input = request.input.model_dump()
        run.input = safe_input
        run.metadata_json = {
            **run.metadata_json,
            "input_bytes": len(text.encode("utf-8")),
            "guardrail_pending": False,
        }
        root_span.input = safe_input
        root_span.attributes = {
            **root_span.attributes,
            "input_bytes": len(text.encode("utf-8")),
            "guardrail_pending": False,
        }
        user_message.content = safe_input
        user_message.token_count = max(1, (len(text) + 3) // 4)
        await self.session.commit()
        return request

    async def run(
        self,
        request: AgentRunRequest,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> AgentRunResult:
        return await self.run_execution.execute(
            request, execution_context=execution_context
        )

    async def stream(
        self,
        request: AgentRunRequest,
        *,
        execution_context: ExecutionContext | None = None,
    ) -> AsyncIterator[RuntimeStreamEvent]:
        async for event in self.stream_execution.execute(
            request, execution_context=execution_context
        ):
            yield event

    @staticmethod
    def _validate_request(request: AgentRunRequest) -> None:
        if not (
            request.workspace_id
            == request.agent_version.workspace_id
            == request.session.workspace_id
        ):
            raise RuntimeExecutionError(
                "ACCESS_DENIED",
                "Runtime resources belong to different workspaces.",
                status_code=403,
            )
        if request.agent_version.agent_id != request.session.agent_id:
            raise RuntimeExecutionError(
                "RESOURCE_NOT_FOUND",
                "The session does not belong to this agent.",
                status_code=404,
            )
        if (request.session.user_id is None) == (
            request.session.public_api_key_id is None
        ):
            raise RuntimeExecutionError(
                "AUTHENTICATION_REQUIRED",
                "A runtime session must have exactly one authenticated principal.",
                status_code=401,
            )
