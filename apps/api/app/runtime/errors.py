"""Stable errors raised by the synchronous runtime."""

from typing import Any
from uuid import UUID


class RuntimeExecutionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 502,
        run_id: UUID | None = None,
        trace_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.run_id = run_id
        self.trace_id = trace_id
        self.details = details or {}

    @property
    def error_details(self) -> dict[str, Any]:
        details = dict(self.details)
        if self.run_id is not None:
            details["run_id"] = str(self.run_id)
        if self.trace_id is not None:
            details["trace_id"] = str(self.trace_id)
        return details
