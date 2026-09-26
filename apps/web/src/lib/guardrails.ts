import { apiFetch, readApiError } from "./api";

export type GuardrailHook = "INPUT" | "MODEL_OUTPUT" | "TOOL_INPUT" | "TOOL_OUTPUT";
export type GuardrailDecision = "ALLOW" | "BLOCK" | "REDACT" | "REQUIRE_APPROVAL";
export type GuardrailRuleType = "REGEX" | "SECRET_DETECTION" | "PII_REDACTION" | "TOOL_POLICY" | "MAX_PAYLOAD_SIZE";
export type GuardrailRule = {
  id: string;
  type: GuardrailRuleType;
  action: GuardrailDecision;
  hooks?: GuardrailHook[];
  pattern?: string | null;
  replacement?: string;
  entities?: Array<"EMAIL" | "PHONE" | "PAYMENT_CARD">;
  allowed_tool_version_ids?: string[];
  denied_tool_version_ids?: string[];
  allowed_tool_names?: string[];
  denied_tool_names?: string[];
  minimum_risk?: "LOW" | "MEDIUM" | "HIGH" | null;
  side_effect_only?: boolean;
  max_bytes?: number | null;
};
export type GuardrailConfiguration = { rules: GuardrailRule[] };
export type GuardrailPolicy = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  latest_version_number: number;
  usage_count: number;
  created_at: string;
  updated_at: string;
};
export type GuardrailVersion = {
  id: string;
  guardrail_policy_id: string;
  version_number: number;
  type: "RULE_SET";
  configuration: GuardrailConfiguration;
  created_at: string;
};
export type GuardrailBinding = {
  guardrail_version_id: string;
  guardrail_policy_id: string;
  policy_name: string;
  version_number: number;
  hook: GuardrailHook;
  priority: number;
  configuration: GuardrailConfiguration;
};
export type DraftGuardrails = {
  enabled: boolean;
  baseline_version: number;
  baseline_source: "PLATFORM_DEFAULT";
  bindings: GuardrailBinding[];
};

type Collection<T> = { data: T[]; pagination: { next_cursor: string | null; has_more: boolean } };

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(await readApiError(response));
  return await response.json() as T;
}

export async function fetchGuardrails(workspaceId: string): Promise<GuardrailPolicy[]> {
  const response = await apiFetch(`/v1/workspaces/${workspaceId}/guardrails`);
  return (await json<Collection<GuardrailPolicy>>(response)).data;
}

export async function createGuardrailPolicy(workspaceId: string, name: string, description: string): Promise<GuardrailPolicy> {
  return json(await apiFetch(`/v1/workspaces/${workspaceId}/guardrails`, {
    method: "POST",
    body: JSON.stringify({ name, description: description || null }),
  }));
}

export async function createGuardrailVersion(policyId: string, configuration: GuardrailConfiguration): Promise<GuardrailVersion> {
  return json(await apiFetch(`/v1/guardrails/${policyId}/versions`, {
    method: "POST",
    body: JSON.stringify({ type: "RULE_SET", configuration }),
  }));
}

export async function fetchGuardrailVersions(policyId: string): Promise<GuardrailVersion[]> {
  const response = await apiFetch(`/v1/guardrails/${policyId}/versions`);
  return (await json<Collection<GuardrailVersion>>(response)).data;
}

export async function fetchDraftGuardrails(agentId: string): Promise<DraftGuardrails> {
  return json(await apiFetch(`/v1/agents/${agentId}/draft/guardrails`));
}

export async function setDraftGuardrailsEnabled(agentId: string, enabled: boolean): Promise<DraftGuardrails> {
  return json(await apiFetch(`/v1/agents/${agentId}/draft/guardrails/settings`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  }));
}

export async function attachDraftGuardrail(agentId: string, guardrailVersionId: string, hook: GuardrailHook, priority = 100): Promise<GuardrailBinding> {
  return json(await apiFetch(`/v1/agents/${agentId}/draft/guardrails`, {
    method: "POST",
    body: JSON.stringify({ guardrail_version_id: guardrailVersionId, hook, priority }),
  }));
}

export async function detachDraftGuardrail(agentId: string, guardrailVersionId: string, hook: GuardrailHook): Promise<void> {
  const response = await apiFetch(`/v1/agents/${agentId}/draft/guardrails/${guardrailVersionId}/${hook}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}
