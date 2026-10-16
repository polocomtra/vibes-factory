"use client";

type PrimarySwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
};

/** Shared semantic switch using the app's existing token-driven toggle treatment. */
export function PrimarySwitch({
  checked,
  onChange,
  label,
  description,
  disabled = false,
}: PrimarySwitchProps) {
  return (
    <label className="toggle-row primary-switch">
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-control" aria-hidden="true"><span /></span>
      <span className="toggle-copy">
        <strong>{label}</strong>
        {description ? <small>{description}</small> : null}
      </span>
    </label>
  );
}
