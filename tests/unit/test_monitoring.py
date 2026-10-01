from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.api.app.main import app
from apps.api.app.monitoring.pricing import pricing_payload
from apps.api.app.monitoring.service import _base_query


def pricing_entry(**overrides: object) -> dict[str, object]:
    return {
        "provider": " Azure_OpenAI ",
        "model": " GPT-6-LUNA ",
        "effective_from": "2026-09-30T00:00:00Z",
        "input_price_per_million": "1.25000000",
        "output_price_per_million": "10",
        "cached_input_price_per_million": "0.125",
        "metadata": {"source": "operator import"},
        **overrides,
    }


def test_pricing_payload_normalizes_ids_and_keeps_decimal_rates() -> None:
    parsed = pricing_payload(pricing_entry())

    assert parsed["provider"] == "azure_openai"
    assert parsed["model"] == "gpt-6-luna"
    assert parsed["effective_from"] == datetime(2026, 9, 30, tzinfo=UTC)
    assert parsed["input_price_per_million"] == Decimal("1.25000000")
    assert parsed["metadata_json"] == {
        "source": "operator import",
        "currency": "USD",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"effective_from": "2026-09-30T00:00:00"},
        {"input_price_per_million": "-1"},
        {"output_price_per_million": "NaN"},
        {"metadata": {"currency": "EUR", "source": "operator"}},
        {"metadata": {"currency": "USD"}},
    ],
)
def test_pricing_payload_rejects_invalid_ranges_and_metadata(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        pricing_payload(pricing_entry(**overrides))


def test_monitoring_query_scopes_workspace_period_and_excludes_evaluation() -> None:
    workspace_id = uuid4()
    start = datetime(2026, 9, 24, tzinfo=UTC)
    end = datetime(2026, 10, 1, tzinfo=UTC)

    statement = _base_query(
        workspace_id,
        start,
        end,
        {
            "agent_id": None,
            "agent_version_id": None,
            "provider": None,
            "model": None,
            "status": None,
        },
    )
    compiled = statement.compile()

    assert workspace_id in compiled.params.values()
    assert start in compiled.params.values()
    assert end in compiled.params.values()
    assert "runs.metadata" in str(compiled)
    assert "evaluation_results" in str(compiled)


def test_monitoring_api_routes_are_exposed_in_openapi() -> None:
    paths = app.openapi()["paths"]

    assert "/v1/workspaces/{workspace_id}/monitoring/summary" in paths
    assert "/v1/workspaces/{workspace_id}/monitoring/timeseries" in paths
    assert "/v1/workspaces/{workspace_id}/monitoring/options" in paths
