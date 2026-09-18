import { ChevronLeft, ChevronRight } from "lucide-react";

export const PAGE_SIZE_OPTIONS = [5, 10, 15, 20, 25, 50] as const;

type PaginationControlsProps = {
    page: number;
    pageSize: number;
    totalItems: number;
    onPageChange: (page: number) => void;
    onPageSizeChange: (pageSize: number) => void;
    ariaLabel: string;
};

export function PaginationControls({
    page,
    pageSize,
    totalItems,
    onPageChange,
    onPageSizeChange,
    ariaLabel,
}: PaginationControlsProps) {
    if (totalItems === 0) return null;

    const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
    const currentPage = Math.min(Math.max(page, 1), totalPages);
    const firstItem = (currentPage - 1) * pageSize + 1;
    const lastItem = Math.min(currentPage * pageSize, totalItems);

    return (
        <div className="pagination-footer">
            <nav className="pagination-controls" aria-label={ariaLabel}>
                <label className="pagination-page-size">
                    <span>Items per page</span>
                    <select
                        value={pageSize}
                        aria-label="Items per page"
                        onChange={(event) => {
                            onPageSizeChange(Number(event.target.value));
                            onPageChange(1);
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
                    Showing {firstItem}–{lastItem} of {totalItems}
                </span>
                <div className="pagination-actions">
                    <button
                        className="button secondary-button pagination-button"
                        type="button"
                        onClick={() => onPageChange(currentPage - 1)}
                        disabled={currentPage === 1}
                    >
                        <ChevronLeft size={15} aria-hidden="true" />
                        Previous
                    </button>
                    <button
                        className="button secondary-button pagination-button"
                        type="button"
                        onClick={() => onPageChange(currentPage + 1)}
                        disabled={currentPage === totalPages}
                    >
                        Next
                        <ChevronRight size={15} aria-hidden="true" />
                    </button>
                </div>
            </nav>
        </div>
    );
}
