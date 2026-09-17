import json

from apps.api.app.runs.routes import _sse
from apps.api.app.runtime.contracts import RuntimeStreamEvent


def test_runtime_stream_event_accepts_only_core_sse_events() -> None:
    event = RuntimeStreamEvent(
        event="message.delta",
        data={"run_id": "run-1", "delta": "hello"},
    )

    assert event.event == "message.delta"
    assert event.data["delta"] == "hello"


def test_sse_serialization_has_sequence_event_and_json_data() -> None:
    payload = {"run_id": "run-1", "status": "COMPLETED"}

    serialized = _sse("run.completed", payload, 4)

    assert serialized.startswith("id: 4\nevent: run.completed\ndata: ")
    assert serialized.endswith("\n\n")
    data_line = serialized.splitlines()[2].removeprefix("data: ")
    assert json.loads(data_line) == payload
