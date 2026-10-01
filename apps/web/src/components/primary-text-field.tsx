import {
  forwardRef,
  type InputHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

type PrimaryTextInputProps = InputHTMLAttributes<HTMLInputElement>;
type PrimaryTextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

/** Shared themed input primitive for app-owned text and numeric fields. */
export const PrimaryTextInput = forwardRef<
  HTMLInputElement,
  PrimaryTextInputProps
>(function PrimaryTextInput(props, ref) {
  return (
    <input
      {...props}
      ref={ref}
      className={`primary-text-input ${props.className ?? ""}`.trim()}
    />
  );
});

/** Shared themed textarea primitive for app-owned multi-line fields. */
export function PrimaryTextArea(props: PrimaryTextAreaProps) {
  return <textarea {...props} className={`primary-textarea ${props.className ?? ""}`.trim()} />;
}
