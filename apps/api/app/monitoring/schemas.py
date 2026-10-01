"""Public workspace monitoring response contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class MonitoringPeriod(BaseModel):
    from_: datetime
    to: datetime


class MonitoringSummary(BaseModel):
    period: dict[str, datetime]
    filters: dict[str, Any]
    runs: dict[str, int | float | None]
    latency: dict[str, float | None]
    model_latency: dict[str, float | None]
    usage: dict[str, int]
    estimated_cost: str | None
    currency: Literal["USD"]
    tool_failures: dict[str, int | float | None]
    data_quality: dict[str, int | bool | str | None]


class TimeseriesPoint(BaseModel):
    timestamp: datetime
    value: float | int | None
    complete: bool


class MonitoringTimeseries(BaseModel):
    metric: str
    interval: Literal["1h", "1d"]
    points: list[TimeseriesPoint]


class MonitoringOptions(BaseModel):
    agents: list[dict[str, Any]]
    models: list[dict[str, str]]
