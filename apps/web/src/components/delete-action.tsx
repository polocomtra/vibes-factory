import { LoaderCircle, Trash2 } from "lucide-react";

type DeleteActionProps = {
    label: string;
    confirming: boolean;
    busy: boolean;
    onRequest: () => void;
    onCancel: () => void;
    onConfirm: () => void;
};

export function DeleteAction({
    label,
    confirming,
    busy,
    onRequest,
    onCancel,
    onConfirm,
}: DeleteActionProps) {
    if (confirming) {
        return (
            <div className="resource-delete-confirm" role="group" aria-label={`Confirm delete ${label}`}>
                <span className="resource-delete-prompt">Delete?</span>
                <button className="text-button" type="button" onClick={onCancel} disabled={busy}>
                    Cancel
                </button>
                <button className="button danger-button" type="button" onClick={onConfirm} disabled={busy}>
                    {busy ? <LoaderCircle className="spin" size={13} aria-hidden="true" /> : null}
                    {busy ? "Deleting…" : "Delete"}
                </button>
            </div>
        );
    }

    return (
        <button className="icon-button danger-icon resource-delete-button" type="button" aria-label={`Delete ${label}`} onClick={onRequest}>
            <Trash2 size={15} aria-hidden="true" />
        </button>
    );
}
