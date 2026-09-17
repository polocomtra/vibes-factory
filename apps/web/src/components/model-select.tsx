"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { ModelDefinition } from "../lib/agents";

type ModelSelectProps = {
  models: ModelDefinition[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
};

export function ModelSelect({ models, value, onChange, disabled = false }: ModelSelectProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const selectedIndex = models.findIndex((model) => `${model.provider}:${model.name}` === value);
  const [highlightedIndex, setHighlightedIndex] = useState(Math.max(selectedIndex, 0));
  const selectedModel = selectedIndex >= 0 ? models[selectedIndex] : null;

  useEffect(() => {
    if (selectedIndex >= 0) setHighlightedIndex(selectedIndex);
  }, [selectedIndex]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  function selectModel(model: ModelDefinition) {
    onChange(`${model.provider}:${model.name}`);
    setOpen(false);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled || models.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setHighlightedIndex((index) => (index + direction + models.length) % models.length);
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && open) {
      event.preventDefault();
      const model = models[highlightedIndex];
      if (model) selectModel(model);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    }
  }

  return <div className="model-select" ref={rootRef}>
    <button
      className="model-select-trigger"
      type="button"
      aria-label="Model"
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={listboxId}
      disabled={disabled || models.length === 0}
      onClick={() => setOpen((current) => !current)}
      onKeyDown={handleKeyDown}
    >
      <span className={selectedModel ? "model-select-value" : "model-select-placeholder"}>{selectedModel ? `${selectedModel.display_name} · ${selectedModel.provider}` : "Select a model"}</span>
      <ChevronDown className={open ? "model-select-chevron open" : "model-select-chevron"} size={17} aria-hidden="true" />
    </button>
    {open ? <div className="model-select-menu" id={listboxId} role="listbox" aria-label="Available models">
      {models.map((model, index) => {
        const modelKey = `${model.provider}:${model.name}`;
        const isSelected = modelKey === value;
        const isHighlighted = index === highlightedIndex;
        return <button
          className={isHighlighted ? "model-select-option highlighted" : "model-select-option"}
          id={`${listboxId}-${index}`}
          key={modelKey}
          type="button"
          role="option"
          aria-selected={isSelected}
          onMouseEnter={() => setHighlightedIndex(index)}
          onClick={() => selectModel(model)}
        >
          <span><strong>{model.display_name}</strong><small>{model.provider} · {model.name}</small></span>
          {isSelected ? <Check size={16} aria-hidden="true" /> : null}
        </button>;
      })}
    </div> : null}
  </div>;
}
