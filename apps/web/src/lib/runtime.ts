import { apiFetch } from "./api";

export type TextInput = { type: "text"; text: string };
export type Session = {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: string;
  last_activity_at: string;
};
export type Message = {
  id: string;
  session_id: string;
  run_id: string | null;
  role: "USER" | "ASSISTANT" | "SYSTEM" | "TOOL";
  sequence_no: number;
  content: { type: string; text?: string; tool_calls?: Array<{ id?: string | null; name: string; arguments: Record<string, unknown> }>; output?: unknown; tool_call_id?: string | null; [key: string]: unknown };
  token_count: number | null;
  created_at: string;
};
export type Citation = { marker: string; chunk_id: string; document_id: string; knowledge_base_id: string; source_name: string; page: number | null; section: string | null; score: number; generation: number; excerpt: string };
export type Run = {
  id: string;
  agent_id: string;
  agent_version_id: string;
  session_id: string | null;
  workflow_run_id?: string | null;
  parent_run_id: string | null;
  root_run_id: string;
  trace_id: string;
  status: "QUEUED" | "RUNNING" | "WAITING_TOOL" | "WAITING_APPROVAL" | "COMPLETED" | "FAILED" | "CANCELLED";
  input: TextInput;
  output: (TextInput & { citations?: Citation[] }) | null;
  usage: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    cached_input_tokens?: number;
    child_runs?: number;
    agent_runs?: number;
    tool_calls?: number;
    model_calls?: number;
  };
  estimated_cost: string | number | null;
  error: { code: string; message: string } | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type ChildRun = Pick<Run, "id" | "agent_id" | "agent_version_id" | "session_id" | "parent_run_id" | "root_run_id" | "trace_id" | "status" | "usage" | "error" | "started_at" | "completed_at" | "created_at"> & {
  agent_depth: number;
};

export type RunStartedEvent = {
  event: "run.started";
  data: { run_id: string; trace_id: string; agent_version_id: string };
};
export type MessageDeltaEvent = {
  event: "message.delta";
  data: { run_id: string; delta: string };
};
export type MessageCompletedEvent = {
  event: "message.completed";
  data: { run_id: string; message_id: string; citations?: Citation[] };
};
export type RunCompletedEvent = {
  event: "run.completed";
  data: {
    run_id: string;
    status: "COMPLETED";
    usage: Run["usage"];
    estimated_cost: string | null;
  };
};
export type RunFailedEvent = {
  event: "run.failed";
  data: { run_id: string; error: { code: string; message: string } };
};
export type ToolStreamEvent = {
  event: "tool.started" | "tool.completed" | "tool.failed";
  data: { run_id: string; tool: string; status: string; duration_ms?: number };
};
export type ChildAgentStreamEvent = {
  event: "child_agent.started" | "child_agent.completed" | "child_agent.failed";
  data: {
    run_id: string;
    child_agent_id?: string | null;
    child_agent_version_id?: string | null;
    child_run_id?: string | null;
    tool?: string;
    status: string;
    duration_ms?: number;
    error_code?: string | null;
  };
};
export type RetrievalStreamEvent = { event: "retrieval.started" | "retrieval.completed" | "retrieval.failed"; data: { run_id: string; citation_count?: number; error?: { code: string; message: string } } };
export type MemoryStreamEvent = { event: "memory.retrieved"; data: { run_id: string; memory_count?: number; degraded?: boolean } };
export type GuardrailStreamEvent = { event: "guardrail.triggered"; data: { run_id: string; hook: string; decision: string; rule_id?: string | null; reason_code?: string | null; match_count?: number } };
export type ApprovalRequiredStreamEvent = { event: "approval.required"; data: { run_id: string; trace_id?: string; approval_request_id: string; requested_action?: string; risk_reason?: string } };
export type RunStreamEvent =
  | RunStartedEvent
  | MessageDeltaEvent
  | MessageCompletedEvent
  | RunCompletedEvent
  | RunFailedEvent
  | ToolStreamEvent
  | ChildAgentStreamEvent
  | RetrievalStreamEvent
  | MemoryStreamEvent
  | GuardrailStreamEvent
  | ApprovalRequiredStreamEvent;
  
export type Span = {
  id: string;
  parent_span_id: string | null;
  run_id: string | null;
  type: "RUN" | "CONTEXT_BUILD" | "MODEL" | "TOOL" | "CHILD_AGENT" | "RETRIEVAL" | "MEMORY_RETRIEVAL" | "GUARDRAIL";
  name: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  usage: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    cached_input_tokens?: number;
    input_tokens_estimated?: boolean;
  };
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: Record<string, unknown> | null;
  estimated_cost?: string | null;
};
export type RunTrace = {
  trace: { id: string; status: "RUNNING" | "COMPLETED" | "FAILED"; started_at: string; completed_at: string | null };
  root_span: { id: string } | null;
};
export type TraceListItem = {
  id: string;
  agent_id: string | null;
  agent_name: string | null;
  agent_version_id: string | null;
  run_id: string | null;
  session_id: string | null;
  workflow_id: string | null;
  workflow_run_id: string | null;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  input_text: string | null;
  output_text: string | null;
  error_code: string | null;
};
export type TraceDetail = {
  id: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  started_at: string;
  completed_at: string | null;
  agent_name: string | null;
  run_id: string | null;
  session_id: string | null;
  workflow_run_id: string | null;
  duration_ms: number | null;
  span_count: number;
  usage: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    cached_input_tokens?: number;
    input_tokens_estimated?: boolean;
  };
  estimated_cost: string | null;
};

export class RuntimeApiError extends Error {
  status: number;
  code?: string;
  runId?: string;
  traceId?: string;

  constructor(message: string, status: number, details?: { run_id?: string; trace_id?: string }, code?: string) {
    super(message);
    this.name = "RuntimeApiError";
    this.status = status;
    this.code = code;
    this.runId = details?.run_id;
    this.traceId = details?.trace_id;
  }
}

async function assertOk(response: Response): Promise<void> {
  if (response.ok) return;
  let body: { error?: { code?: string; message?: string; details?: { run_id?: string; trace_id?: string } } } = {};
  try { body = await response.json() as typeof body; } catch { /* use status fallback */ }
  throw new RuntimeApiError(
    body.error?.message ?? `Request failed (${response.status}).`,
    response.status,
    body.error?.details,
    body.error?.code,
  );
}

type Collection<T> = { data: T[]; pagination: { next_cursor: string | null; has_more: boolean } };

export type TraceFilters = {
  agent?: string;
  session_id?: string;
  status?: string;
  started_after?: string;
  started_before?: string;
};

export async function fetchSessions(agentId: string): Promise<Session[]> {
  const response = await apiFetch(`/v1/agents/${agentId}/sessions`);
  await assertOk(response);
  return (await response.json() as Collection<Session>).data;
}

export async function createSession(agentId: string): Promise<Session> {
  const response = await apiFetch(`/v1/agents/${agentId}/sessions`, {
    method: "POST",
    body: JSON.stringify({ title: "Playground session" }),
  });
  await assertOk(response);
  return await response.json() as Session;
}

export async function updateSession(sessionId: string, title: string): Promise<Session> {
  const response = await apiFetch(`/v1/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  await assertOk(response);
  return await response.json() as Session;
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const response = await apiFetch(`/v1/sessions/${sessionId}/messages`);
  await assertOk(response);
  return (await response.json() as Collection<Message>).data;
}

export async function createRun(agentId: string, sessionId: string, agentVersionId: string, text: string): Promise<Run> {
  const response = await apiFetch(`/v1/agents/${agentId}/runs`, {
    method: "POST",
    body: JSON.stringify({ input: { type: "text", text }, session_id: sessionId, agent_version_id: agentVersionId }),
  });
  await assertOk(response);
  return await response.json() as Run;
}

function parseSseBlock(block: string): RunStreamEvent | null {
  let eventName = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? "" : line.slice(separator + 1).trimStart();
    if (field === "event") eventName = value;
    if (field === "data") dataLines.push(value);
  }
  if (!eventName || dataLines.length === 0) return null;
  const supported = new Set([
    "run.started",
    "message.delta",
    "message.completed",
    "retrieval.started",
    "retrieval.completed",
    "retrieval.failed",
    "memory.retrieved",
    "run.completed",
    "run.failed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "child_agent.started",
    "child_agent.completed",
    "child_agent.failed",
    "guardrail.triggered",
    "approval.required",
  ]);
  if (!supported.has(eventName)) return null;
  try {
    return { event: eventName, data: JSON.parse(dataLines.join("\n")) } as RunStreamEvent;
  } catch {
    throw new RuntimeApiError("The streaming response was not valid JSON.", 502);
  }
}

export async function* createRunStream(
  agentId: string,
  sessionId: string,
  agentVersionId: string,
  text: string,
  signal?: AbortSignal,
): AsyncGenerator<RunStreamEvent> {
  const response = await apiFetch(`/v1/agents/${agentId}/runs:stream`, {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    body: JSON.stringify({ input: { type: "text", text }, session_id: sessionId, agent_version_id: agentVersionId }),
    signal,
  });
  await assertOk(response);
  if (!response.body) throw new RuntimeApiError("The streaming response had no body.", 502);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      let boundaryMatch = buffer.match(/\r?\n\r?\n/);
      while (boundaryMatch?.index !== undefined) {
        const boundary = boundaryMatch.index;
        const block = buffer.slice(0, boundary).replace(/\r/g, "");
        buffer = buffer.slice(boundary + boundaryMatch[0].length);
        const parsed = parseSseBlock(block);
        if (parsed) yield parsed;
        boundaryMatch = buffer.match(/\r?\n\r?\n/);
      }
      if (done) break;
    }
    const finalBlock = buffer.replace(/\r/g, "").trim();
    if (finalBlock) {
      const parsed = parseSseBlock(finalBlock);
      if (parsed) yield parsed;
    }
  } finally {
    reader.releaseLock();
  }
}

export async function fetchRun(runId: string): Promise<Run> {
  const response = await apiFetch(`/v1/runs/${runId}`);
  await assertOk(response);
  return await response.json() as Run;
}

export async function fetchRunChildren(runId: string): Promise<ChildRun[]> {
  const response = await apiFetch(`/v1/runs/${runId}/children?limit=100`);
  await assertOk(response);
  return (await response.json() as { data: ChildRun[] }).data;
}

export async function fetchRunTrace(runId: string): Promise<RunTrace> {
  const response = await apiFetch(`/v1/runs/${runId}/trace`);
  await assertOk(response);
  return await response.json() as RunTrace;
}

export async function fetchTraces(filters: TraceFilters = {}, cursor?: string): Promise<Collection<TraceListItem>> {
  const params = new URLSearchParams();
  if (filters.agent) params.set("agent", filters.agent);
  if (filters.session_id) params.set("session_id", filters.session_id);
  if (filters.status) params.set("status", filters.status);
  if (filters.started_after) params.set("started_after", filters.started_after);
  if (filters.started_before) params.set("started_before", filters.started_before);
  params.set("limit", "100");
  if (cursor) params.set("cursor", cursor);
  const response = await apiFetch(`/v1/traces?${params.toString()}`);
  await assertOk(response);
  return await response.json() as Collection<TraceListItem>;
}

export async function fetchSessionTraces(sessionId: string): Promise<TraceListItem[]> {
  const traces: TraceListItem[] = [];
  let cursor: string | undefined;
  do {
    const page = await fetchTraces({ session_id: sessionId }, cursor);
    traces.push(...page.data);
    cursor = page.pagination.has_more && page.pagination.next_cursor
      ? page.pagination.next_cursor
      : undefined;
  } while (cursor);
  return traces;
}

export async function fetchTraceSpans(traceId: string): Promise<Span[]> {
  const response = await apiFetch(`/v1/traces/${traceId}/spans`);
  await assertOk(response);
  return (await response.json() as Collection<Span>).data;
}

export async function fetchTraceDetail(traceId: string): Promise<TraceDetail> {
  const response = await apiFetch(`/v1/traces/${traceId}`);
  await assertOk(response);
  return await response.json() as TraceDetail;
}

export async function fetchSpan(spanId: string): Promise<Span> {
  const response = await apiFetch(`/v1/spans/${spanId}`);
  await assertOk(response);
  return await response.json() as Span;
}
