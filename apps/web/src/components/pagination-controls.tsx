import { ChevronLeft, ChevronRight } from "lucide-react";

export const PAGE_SIZE_OPTIONS = [6, 12, 18, 24, 30, 48] as const;

type PaginationControlsProps = {
    page: number;
    pageSize: number;
    totalItems?: number;
    hasNextPage?: boolean;
    hasPreviousPage?: boolean;
    disabled?: boolean;
    resetPageOnSizeChange?: boolean;
    onPageChange: (page: number) => void;
    onPageSizeChange: (pageSize: number) => void;
    ariaLabel: string;
};

export function PaginationControls({
    page,
    pageSize,
    totalItems,
    hasNextPage,
    hasPreviousPage,
    disabled = false,
    resetPageOnSizeChange = true,
    onPageChange,
    onPageSizeChange,
    ariaLabel,
}: PaginationControlsProps) {
    if (totalItems === 0) return null;

    const totalPages = totalItems
        ? Math.max(1, Math.ceil(totalItems / pageSize))
        : null;
    const currentPage = totalPages
        ? Math.min(Math.max(page, 1), totalPages)
        : Math.max(page, 1);
    const firstItem = totalItems
        ? (currentPage - 1) * pageSize + 1
        : null;
    const lastItem = totalItems
        ? Math.min(currentPage * pageSize, totalItems)
        : null;
    const previousDisabled = disabled ||
        (hasPreviousPage !== undefined
            ? !hasPreviousPage
            : currentPage === 1);
    const nextDisabled = disabled ||
        (hasNextPage !== undefined
            ? !hasNextPage
            : currentPage === totalPages);

    return (
        <div className="pagination-footer">
            <nav className="pagination-controls" aria-label={ariaLabel}>
                <label className="pagination-page-size">
                    <span>Items per page</span>
                    <select
                        value={pageSize}
                        aria-label="Items per page"
                        disabled={disabled}
                        onChange={(event) => {
                            onPageSizeChange(Number(event.target.value));
                            if (resetPageOnSizeChange) onPageChange(1);
                        }}
                    >
                        {PAGE_SIZE_OPTIONS.map((option) => (
                            <option value={option} key={option}>
                                {option}
                            </option>
                        ))}
                    </select>
                </label>
                <span className="pagination-summary" aria-live="polite">
                    {totalItems
                        ? `Showing ${firstItem}–${lastItem} of ${totalItems}`
                        : `Page ${currentPage}`}
                </span>
                <div className="pagination-actions">
                    <button
                        className="button secondary-button pagination-button"
                        type="button"
                        onClick={() => onPageChange(currentPage - 1)}
                        disabled={previousDisabled}
                    >
                        <ChevronLeft size={15} aria-hidden="true" />
                        Previous
                    </button>
                    <button
                        className="button secondary-button pagination-button"
                        type="button"
                        onClick={() => onPageChange(currentPage + 1)}
                        disabled={nextDisabled}
                    >
                        Next
                        <ChevronRight size={15} aria-hidden="true" />
                    </button>
                </div>
            </nav>
        </div>
    );
}
