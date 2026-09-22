"use client";

import { CircleAlert, CheckCircle2, Info, LoaderCircle, X } from "lucide-react";
import { useEffect } from "react";

export type FeedbackToastState = {
    kind: "success" | "error" | "info" | "loading";
    message: string;
};

export function FeedbackToast({
    toast,
    onDismiss,
}: {
    toast: FeedbackToastState | null;
    onDismiss: () => void;
}) {
    useEffect(() => {
        if (!toast || toast.kind === "loading") return;
        const timeout = window.setTimeout(onDismiss, 4200);
        return () => window.clearTimeout(timeout);
    }, [onDismiss, toast]);

    if (!toast) return null;
    const Icon = toast.kind === "success"
        ? CheckCircle2
        : toast.kind === "error"
            ? CircleAlert
            : toast.kind === "loading"
                ? LoaderCircle
                : Info;

    return (
        <div className={`feedback-toast ${toast.kind}`} role={toast.kind === "error" ? "alert" : "status"} aria-live="polite">
            <Icon size={16} aria-hidden="true" className={toast.kind === "loading" ? "spin" : undefined} />
            <span>{toast.message}</span>
            <button className="feedback-toast-dismiss" type="button" onClick={onDismiss} aria-label="Dismiss notification">
                <X size={15} aria-hidden="true" />
            </button>
        </div>
    );
}
