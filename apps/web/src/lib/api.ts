import { supabase } from "./supabase";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const accessToken = supabase ? (await supabase.auth.getSession()).data.session?.access_token : null;
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  // Do not set Content-Type for FormData. The browser adds the multipart
  // boundary, which FastAPI needs in order to parse the uploaded file.
  const isFormDataBody = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isFormDataBody && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  return fetch(`${apiUrl}${path}`, { ...init, headers, cache: "no-store" });
}

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details: Record<string, unknown>;
  readonly summary: string;

  constructor(message: string, status: number, code?: string, details: Record<string, unknown> = {}, summary = message) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.summary = summary;
  }
}

type ApiErrorBody = {
  error?: { code?: string; message?: string; details?: Record<string, unknown> };
  detail?: { code?: string; message?: string; details?: Record<string, unknown> } | string;
};

function formatApiErrorMessage(message: string, details: Record<string, unknown>) {
  const errors = Array.isArray(details.errors) ? details.errors : [];
  const formatted = errors
    .filter((item): item is { message?: string; node_key?: string; field?: string } => Boolean(item && typeof item === "object"))
    .slice(0, 6)
    .map((item) => {
      const location = [item.node_key, item.field].filter(Boolean).join(" · ");
      return `${location ? `${location}: ` : ""}${item.message || "Invalid configuration."}`;
    });
  if (formatted.length === 0) return message;
  const suffix = errors.length > formatted.length ? ` (+${errors.length - formatted.length} more)` : "";
  return `${message} ${formatted.join(" | ")}${suffix}`;
}

export async function readApiErrorDetails(response: Response): Promise<ApiRequestError> {
  try {
    const body = await response.json() as ApiErrorBody;
    const payload = body.error ?? (typeof body.detail === "object" ? body.detail : undefined);
    const message = payload?.message || (typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
    const details = payload?.details ?? {};
    return new ApiRequestError(formatApiErrorMessage(message, details), response.status, payload?.code, details, message);
  } catch {
    return new ApiRequestError(`Request failed (${response.status}).`, response.status);
  }
}

export async function readApiError(response: Response): Promise<string> {
  return (await readApiErrorDetails(response)).message;
}
