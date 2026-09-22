"use client";

import { Check, ChevronDown, Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

export type PrimarySelectOption = {
  value: string;
  label: string;
  secondary?: string;
};

type PrimarySelectProps = {
  value: string;
  options: PrimarySelectOption[];
  placeholder: string;
  ariaLabel: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  searchable?: boolean;
  searchPlaceholder?: string;
  emptyMessage?: string;
};

/** Shared themed combobox for app-owned selects. Never fall back to a native select. */
export function PrimarySelect({
  value,
  options,
  placeholder,
  ariaLabel,
  onChange,
  disabled = false,
  searchable = false,
  searchPlaceholder,
  emptyMessage = "No options found.",
}: PrimarySelectProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selectedIndex = options.findIndex((option) => option.value === value);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : null;
  const visibleOptions = searchable && query.trim()
    ? options.filter((option) =>
        `${option.label} ${option.secondary ?? ""}`
          .toLowerCase()
          .includes(query.trim().toLowerCase()),
      )
    : options;
  const selectedVisibleIndex = visibleOptions.findIndex(
    (option) => option.value === value,
  );
  const [highlightedIndex, setHighlightedIndex] = useState(
    Math.max(selectedVisibleIndex, 0),
  );

  useEffect(() => {
    setHighlightedIndex(Math.max(selectedVisibleIndex, 0));
  }, [selectedVisibleIndex]);

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (
        rootRef.current &&
        !rootRef.current.contains(event.target as globalThis.Node)
      ) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  function chooseOption(option?: PrimarySelectOption) {
    if (!option) return;
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  function moveHighlight(direction: 1 | -1) {
    if (visibleOptions.length === 0) return;
    setHighlightedIndex(
      (index) => (index + direction + visibleOptions.length) % visibleOptions.length,
    );
  }

  function handleTriggerKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (disabled || options.length === 0) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      moveHighlight(event.key === "ArrowDown" ? 1 : -1);
    } else if ((event.key === "Enter" || event.key === " ") && open) {
      event.preventDefault();
      chooseOption(visibleOptions[highlightedIndex]);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      setQuery("");
    }
  }

  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveHighlight(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveHighlight(-1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      chooseOption(visibleOptions[highlightedIndex]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className="model-select primary-select" ref={rootRef}>
      <button
        className="model-select-trigger"
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        disabled={disabled || options.length === 0}
        onClick={() => {
          setOpen((current) => !current);
          if (open) setQuery("");
        }}
        onKeyDown={handleTriggerKeyDown}
      >
        <span
          className={
            selectedOption ? "model-select-value" : "model-select-placeholder"
          }
        >
          {selectedOption?.label || placeholder}
        </span>
        <ChevronDown
          className={open ? "model-select-chevron open" : "model-select-chevron"}
          size={17}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div
          className="model-select-menu"
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel}
        >
          {searchable ? (
            <label className="model-select-search">
              <Search size={15} aria-hidden="true" />
              <span className="sr-only">Search {ariaLabel.toLowerCase()}</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder={searchPlaceholder ?? `Search ${ariaLabel.toLowerCase()}…`}
                autoComplete="off"
              />
            </label>
          ) : null}
          {visibleOptions.length > 0 ? (
            visibleOptions.map((option, index) => (
              <button
                className={
                  index === highlightedIndex
                    ? "model-select-option highlighted"
                    : "model-select-option"
                }
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                onMouseEnter={() => setHighlightedIndex(index)}
                onClick={() => chooseOption(option)}
              >
                <span>
                  <strong>{option.label}</strong>
                  {option.secondary ? <small>{option.secondary}</small> : null}
                </span>
                {option.value === value ? (
                  <Check size={16} aria-hidden="true" />
                ) : null}
              </button>
            ))
          ) : (
            <div className="model-select-empty">{emptyMessage}</div>
          )}
        </div>
      ) : null}
    </div>
  );
}
