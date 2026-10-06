"use client";

import { useEffect, useMemo, useState } from "react";

import { PrimarySelect, type PrimarySelectOption } from "./primary-select";
import { PrimaryTextInput } from "./primary-text-field";
import { ModelSelect } from "./model-select";
import { fetchModels, type ModelConfiguration, type ModelDefinition } from "../lib/agents";
import { discoverModels, fetchModelConnections, type DiscoveredModel, type ModelConnection } from "../lib/model-connections";

type Props = {
  workspaceId: string | null;
  value: ModelConfiguration;
  onChange: (value: ModelConfiguration) => void;
};

export function ModelConnectionPicker({ workspaceId, value, onChange }: Props) {
  const [connections, setConnections] = useState<ModelConnection[]>([]);
  const [catalog, setCatalog] = useState<ModelDefinition[]>([]);
  const [models, setModels] = useState<DiscoveredModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true); setError(null);
      try {
        const [availableCatalog, availableConnections] = await Promise.all([
          fetchModels(), workspaceId ? fetchModelConnections(workspaceId) : Promise.resolve([]),
        ]);
        if (active) { setCatalog(availableCatalog); setConnections(availableConnections); }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load model configuration.");
      } finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [workspaceId]);

  useEffect(() => {
    let active = true;
    setModels([]);
    if (!value.connection_id) return () => { active = false; };
    void discoverModels(value.connection_id).then((items) => { if (active) setModels(items); }).catch(() => { if (active) setModels([]); });
    return () => { active = false; };
  }, [value.connection_id]);

  const connectionOptions = useMemo<PrimarySelectOption[]>(() => [
    { value: "", label: "System default · Azure / gpt-6-luna" },
    ...connections.filter((item) => item.status === "ACTIVE" || item.id === value.connection_id).map((item) => ({
      value: item.id,
      label: `${item.name}${item.status === "REVOKED" ? " · Revoked" : ""}`,
      secondary: item.provider,
    })),
    ...(value.connection_id && !connections.some((item) => item.id === value.connection_id)
      ? [{ value: value.connection_id, label: "Unavailable provider · choose another" }]
      : []),
  ], [connections, value.connection_id]);
  const modelOptions = useMemo<PrimarySelectOption[]>(() => models.map((item) => ({
    value: item.name, label: item.display_name, secondary: item.name,
  })), [models]);

  function selectConnection(id: string) {
    const connection = connections.find((item) => item.id === id);
    if (!id) {
      const fallback = catalog.find((item) => item.is_default) ?? catalog[0];
      if (fallback) onChange({ ...value, connection_id: null, deployment_name: null, provider: fallback.provider, name: fallback.name });
      return;
    }
    if (connection) onChange({ ...value, connection_id: id, provider: connection.provider, name: "", deployment_name: null });
  }

  if (loading) return <div className="agent-state">Loading models…</div>;
  return <div className="model-connection-picker">
    {error ? <p className="form-error" role="alert">{error}</p> : null}
    <label htmlFor="model-connection-picker-select">Model provider<PrimarySelect id="model-connection-picker-select" value={value.connection_id ?? ""} options={connectionOptions} placeholder="Choose a model provider" ariaLabel="Model provider" searchable onChange={selectConnection} /><small>{connections.find((item) => item.id === value.connection_id)?.status === "REVOKED" ? "This provider key is revoked. Choose an active provider to publish." : "System default uses the platform Azure model key."}</small></label>
    {!value.connection_id ? <label>System model<ModelSelect models={catalog} value={`${value.provider}:${value.name}`} onChange={(selected) => {
      const [provider, ...modelParts] = selected.split(":");
      onChange({ ...value, provider, name: modelParts.join(":") });
    }} /></label> : <>
      {modelOptions.length ? <label htmlFor="model-connection-model-suggestion">Suggested model<PrimarySelect id="model-connection-model-suggestion" value={models.some((item) => item.name === value.name) ? value.name : ""} options={modelOptions} placeholder="Choose a suggestion" ariaLabel="Suggested model" searchable onChange={(name) => onChange({ ...value, name })} /></label> : null}
      <label htmlFor="model-connection-model-id">Model ID<PrimaryTextInput id="model-connection-model-id" value={value.name} onChange={(event) => onChange({ ...value, name: event.target.value })} placeholder="Enter the provider's model ID" required /><small>Capabilities are unverified for models outside the platform catalog.</small></label>
      {value.provider === "azure_openai" ? <label htmlFor="model-connection-deployment">Azure deployment name<PrimaryTextInput id="model-connection-deployment" value={value.deployment_name ?? ""} onChange={(event) => onChange({ ...value, deployment_name: event.target.value })} required /></label> : null}
    </>}
  </div>;
}
