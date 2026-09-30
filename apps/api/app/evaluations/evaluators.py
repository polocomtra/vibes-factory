"""Deterministic evaluator primitives and shared scoring contracts."""

import json
from dataclasses import dataclass
from typing import Any, Protocol

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class EvaluationScore:
    score: float | None
    passed: bool | None
    details: dict[str, Any]


class Evaluator(Protocol):
    evaluator_type: str

    async def evaluate(self, case: dict[str, Any], run: Any) -> EvaluationScore: ...


def _output_text(run: Any) -> str:
    output = run.output if isinstance(run.output, dict) else {}
    return str(output.get("text", ""))


def _expected_text(case: dict[str, Any]) -> str:
    expected = case.get("expected_output")
    if isinstance(expected, dict):
        return str(expected.get("text", ""))
    return ""


class ExactMatchEvaluator:
    evaluator_type = "EXACT_MATCH"

    async def evaluate(self, case: dict[str, Any], run: Any) -> EvaluationScore:
        expected, actual = _expected_text(case).strip(), _output_text(run).strip()
        if not expected:
            return EvaluationScore(None, None, {"reason": "EXPECTED_OUTPUT_MISSING"})
        passed = actual == expected
        return EvaluationScore(
            float(passed), passed, {"expected": expected, "actual": actual}
        )


class ContainsEvaluator:
    evaluator_type = "CONTAINS"

    async def evaluate(self, case: dict[str, Any], run: Any) -> EvaluationScore:
        expected, actual = _expected_text(case).strip(), _output_text(run)
        if not expected:
            return EvaluationScore(None, None, {"reason": "EXPECTED_OUTPUT_MISSING"})
        passed = expected.casefold() in actual.casefold()
        return EvaluationScore(
            float(passed), passed, {"expected": expected, "matched": passed}
        )


class JSONSchemaEvaluator:
    evaluator_type = "JSON_SCHEMA"

    async def evaluate(self, case: dict[str, Any], run: Any) -> EvaluationScore:
        schema = case.get("expected_schema")
        if not isinstance(schema, dict):
            return EvaluationScore(None, None, {"reason": "EXPECTED_SCHEMA_MISSING"})
        text = _output_text(run)
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return EvaluationScore(0.0, False, {"reason": "OUTPUT_NOT_JSON"})
        errors = list(Draft202012Validator(schema).iter_errors(value))
        issues = [error.message[:300] for error in errors[:5]]
        passed = not errors
        return EvaluationScore(float(passed), passed, {"errors": issues})


class ToolCallEvaluator:
    evaluator_type = "TOOL_CALL"

    async def evaluate(self, case: dict[str, Any], run: Any) -> EvaluationScore:
        expected = case.get("expected_tool")
        if not expected:
            return EvaluationScore(None, None, {"reason": "EXPECTED_TOOL_MISSING"})
        tool_names = getattr(run, "metadata_json", {}).get("evaluation_tool_calls", [])
        called = expected in tool_names
        return EvaluationScore(
            float(called), called, {"expected_tool": expected, "tool_calls": tool_names}
        )


class LatencyEvaluator:
    evaluator_type = "LATENCY"

    async def evaluate(
        self, case: dict[str, Any], run: Any, config: dict[str, Any]
    ) -> EvaluationScore:
        maximum = int(config.get("max_ms", 10_000))
        if maximum < 1 or maximum > 3_600_000:
            return EvaluationScore(None, None, {"reason": "INVALID_LATENCY_LIMIT"})
        if run.started_at is None or run.completed_at is None:
            return EvaluationScore(None, None, {"reason": "RUN_TIMING_MISSING"})
        elapsed_ms = max(
            0, round((run.completed_at - run.started_at).total_seconds() * 1000)
        )
        passed = elapsed_ms <= maximum
        return EvaluationScore(
            float(passed), passed, {"latency_ms": elapsed_ms, "max_ms": maximum}
        )


class GroundednessEvaluator:
    evaluator_type = "GROUNDEDNESS"

    async def evaluate(self, case: dict[str, Any], run: Any) -> EvaluationScore:
        output = run.output if isinstance(run.output, dict) else {}
        citations = output.get("citations")
        if not isinstance(citations, list) or not citations:
            return EvaluationScore(None, None, {"reason": "CITATION_EVIDENCE_MISSING"})
        snippets = " ".join(
            str(item.get("excerpt", "")) for item in citations if isinstance(item, dict)
        )
        if not _output_text(run).strip() or not snippets.strip():
            return EvaluationScore(None, None, {"reason": "GROUNDING_TEXT_MISSING"})
        return EvaluationScore(
            None,
            None,
            {"reason": "SEMANTIC_JUDGE_REQUIRED", "citation_count": len(citations)},
        )


DETERMINISTIC_EVALUATORS: dict[str, type[Evaluator]] = {
    "EXACT_MATCH": ExactMatchEvaluator,
    "CONTAINS": ContainsEvaluator,
    "JSON_SCHEMA": JSONSchemaEvaluator,
    "TOOL_CALL": ToolCallEvaluator,
    "GROUNDEDNESS": GroundednessEvaluator,
}
