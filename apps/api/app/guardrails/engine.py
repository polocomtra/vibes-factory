"""Bounded deterministic guardrail evaluation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import regex  # type: ignore[import-untyped]

from ..models import GuardrailHook, ToolRiskLevel
from .contracts import (
    GuardrailConfiguration,
    GuardrailContext,
    GuardrailDecision,
    GuardrailEvaluation,
    GuardrailRule,
    GuardrailRuleType,
    PIIEntity,
)

MAX_REGEX_COUNT = 100
MAX_REGEX_PATTERN_LENGTH = 2_000
REGEX_TIMEOUT_SECONDS = 0.05

_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|authorization|cookie|credential|password|secret|token)"
    r"(?:[_-]?(?:value|text|header))?$",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    regex.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    regex.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    regex.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    regex.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b", regex.IGNORECASE),
)
_EMAIL_RE = regex.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", regex.I)
_PHONE_RE = regex.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")
_CARD_RE = regex.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


@dataclass(frozen=True, slots=True)
class GuardrailPolicyInput:
    """An immutable policy snapshot consumed by the engine."""

    configuration: dict[str, Any]
    hooks: tuple[GuardrailHook, ...]
    priority: int = 100
    version_id: UUID | None = None
    source: str = "CUSTOM"


def _json_bytes(value: Any) -> int:
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    try:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError):
        return len(str(value).encode("utf-8"))


def _luhn(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _replace_pattern(
    value: str, pattern: regex.Pattern, replacement: str
) -> tuple[str, int]:
    try:
        return pattern.subn(replacement, value, timeout=REGEX_TIMEOUT_SECONDS)
    except regex.TimeoutError:
        return value, 0


def _walk_strings(value: Any, transform: Any) -> tuple[Any, int]:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        list_output: list[Any] = []
        count = 0
        for item in value:
            next_value, item_count = _walk_strings(item, transform)
            list_output.append(next_value)
            count += item_count
        return list_output, count
    if isinstance(value, tuple):
        output, count = _walk_strings(list(value), transform)
        return tuple(output), count
    if isinstance(value, Mapping):
        mapping_output: dict[Any, Any] = {}
        count = 0
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key):
                mapping_output[key] = "[REDACTED_SECRET]"
                count += 1
                continue
            next_value, item_count = _walk_strings(item, transform)
            mapping_output[key] = next_value
            count += item_count
        return mapping_output, count
    return value, 0


def _secret_transform(value: str, replacement: str) -> tuple[str, int]:
    result = value
    count = 0
    for pattern in _SECRET_VALUE_PATTERNS:
        result, found = _replace_pattern(result, pattern, replacement)
        count += found
    return result, count


def _pii_transform(
    value: str, entities: tuple[PIIEntity, ...], replacement: str
) -> tuple[str, int]:
    result = value
    count = 0
    if PIIEntity.EMAIL in entities:
        result, found = _replace_pattern(result, _EMAIL_RE, replacement)
        count += found
    if PIIEntity.PHONE in entities:
        result, found = _replace_pattern(result, _PHONE_RE, replacement)
        count += found
    if PIIEntity.PAYMENT_CARD in entities:

        def card_sub(match: regex.Match[str]) -> str:
            nonlocal count
            if _luhn(match.group(0)):
                count += 1
                return replacement
            return match.group(0)

        try:
            result = _CARD_RE.sub(card_sub, result, timeout=REGEX_TIMEOUT_SECONDS)
        except regex.TimeoutError:
            pass
    return result, count


def _tool_policy_matches(rule: GuardrailRule, context: GuardrailContext) -> bool:
    if context.hook != GuardrailHook.TOOL_INPUT:
        return False
    if rule.side_effect_only and not context.tool_side_effect:
        return False
    if rule.minimum_risk is not None:
        order = {
            ToolRiskLevel.LOW: 0,
            ToolRiskLevel.MEDIUM: 1,
            ToolRiskLevel.HIGH: 2,
        }
        if (
            context.tool_risk is None
            or order[context.tool_risk] < order[rule.minimum_risk]
        ):
            return False
    tool_id = str(context.tool_version_id) if context.tool_version_id else None
    if (
        rule.denied_tool_version_ids
        and context.tool_version_id in rule.denied_tool_version_ids
    ):
        return True
    if rule.denied_tool_names and context.tool_name in rule.denied_tool_names:
        return True
    if (
        rule.allowed_tool_version_ids
        and context.tool_version_id not in rule.allowed_tool_version_ids
    ):
        return True
    if rule.allowed_tool_names and context.tool_name not in rule.allowed_tool_names:
        return True
    return bool(
        rule.minimum_risk is not None or rule.side_effect_only or tool_id is None
    )


class GuardrailConfigurationError(ValueError):
    pass


def validate_configuration(configuration: dict[str, Any]) -> GuardrailConfiguration:
    parsed = GuardrailConfiguration.model_validate(configuration)
    regex_count = 0
    for rule in parsed.rules:
        if rule.type == GuardrailRuleType.REGEX:
            regex_count += 1
            if not rule.pattern:
                raise GuardrailConfigurationError(
                    f"Regex rule {rule.id} requires pattern."
                )
            if len(rule.pattern) > MAX_REGEX_PATTERN_LENGTH:
                raise GuardrailConfigurationError(f"Regex rule {rule.id} is too long.")
            try:
                regex.compile(rule.pattern)
            except (regex.error, ValueError) as exc:
                raise GuardrailConfigurationError(
                    f"Regex rule {rule.id} is invalid."
                ) from exc
        elif rule.type == GuardrailRuleType.MAX_PAYLOAD_SIZE and rule.max_bytes is None:
            raise GuardrailConfigurationError(
                f"Payload rule {rule.id} requires max_bytes."
            )
        elif rule.type == GuardrailRuleType.TOOL_POLICY and rule.hooks != (
            GuardrailHook.TOOL_INPUT,
        ):
            raise GuardrailConfigurationError(
                "Tool policies may only run at TOOL_INPUT."
            )
    if regex_count > MAX_REGEX_COUNT:
        raise GuardrailConfigurationError(
            "A policy may contain at most 100 regex rules."
        )
    return parsed


class GuardrailEngine:
    def evaluate(
        self,
        context: GuardrailContext,
        policies: tuple[GuardrailPolicyInput, ...],
    ) -> GuardrailEvaluation:
        value = context.payload
        initial_bytes = _json_bytes(value)
        decision = GuardrailDecision.ALLOW
        triggered = False
        policy_id: UUID | None = None
        source: str | None = None
        rule_id: str | None = None
        reason: str | None = None
        matches = 0

        for policy in sorted(policies, key=lambda item: item.priority):
            parsed = validate_configuration(policy.configuration)
            if context.hook not in policy.hooks:
                continue
            for rule in parsed.rules:
                if context.hook not in rule.hooks:
                    continue
                if rule.type == GuardrailRuleType.MAX_PAYLOAD_SIZE:
                    if initial_bytes > (rule.max_bytes or 0):
                        decision = rule.action
                        triggered = True
                        policy_id, source, rule_id = (
                            policy.version_id,
                            policy.source,
                            rule.id,
                        )
                        reason = "PAYLOAD_TOO_LARGE"
                elif rule.type == GuardrailRuleType.TOOL_POLICY:
                    if _tool_policy_matches(rule, context):
                        decision = rule.action
                        triggered = True
                        policy_id, source, rule_id = (
                            policy.version_id,
                            policy.source,
                            rule.id,
                        )
                        reason = "TOOL_POLICY_BLOCKED"
                elif rule.type == GuardrailRuleType.REGEX and rule.pattern:
                    try:
                        pattern = regex.compile(rule.pattern)

                        def redact_regex(
                            item: str,
                            compiled: regex.Pattern = pattern,
                            replacement: str = rule.replacement,
                        ) -> tuple[str, int]:
                            return _replace_pattern(item, compiled, replacement)

                        value, found = _walk_strings(
                            value,
                            redact_regex,
                        )
                    except (regex.error, TypeError, ValueError):
                        found = 0
                    if found:
                        matches += found
                        triggered = True
                        policy_id, source, rule_id = (
                            policy.version_id,
                            policy.source,
                            rule.id,
                        )
                        reason = "REGEX_MATCH"
                        if rule.action != GuardrailDecision.REDACT:
                            decision = rule.action
                elif rule.type == GuardrailRuleType.SECRET_DETECTION:
                    value, found = _walk_strings(
                        value,
                        lambda item, replacement=rule.replacement: _secret_transform(
                            item, replacement
                        ),
                    )
                    if found:
                        matches += found
                        triggered = True
                        policy_id, source, rule_id = (
                            policy.version_id,
                            policy.source,
                            rule.id,
                        )
                        reason = "SECRET_DETECTED"
                        if rule.action != GuardrailDecision.REDACT:
                            decision = rule.action
                elif rule.type == GuardrailRuleType.PII_REDACTION:

                    def redact_pii(
                        item: str,
                        entities=rule.entities,
                        replacement: str = rule.replacement,
                    ) -> tuple[str, int]:
                        return _pii_transform(item, entities, replacement)

                    value, found = _walk_strings(
                        value,
                        redact_pii,
                    )
                    if found:
                        matches += found
                        triggered = True
                        policy_id, source, rule_id = (
                            policy.version_id,
                            policy.source,
                            rule.id,
                        )
                        reason = "PII_DETECTED"
                        if rule.action != GuardrailDecision.REDACT:
                            decision = rule.action

                if decision in {
                    GuardrailDecision.BLOCK,
                    GuardrailDecision.REQUIRE_APPROVAL,
                }:
                    break
            if decision in {
                GuardrailDecision.BLOCK,
                GuardrailDecision.REQUIRE_APPROVAL,
            }:
                break

        if triggered and decision == GuardrailDecision.ALLOW:
            decision = GuardrailDecision.REDACT
        return GuardrailEvaluation(
            decision=decision,
            value=value,
            triggered=triggered,
            policy_version_id=policy_id,
            policy_source=source,
            rule_id=rule_id,
            reason_code=reason,
            match_count=matches,
            input_bytes=initial_bytes,
            output_bytes=_json_bytes(value),
        )


def default_baseline() -> GuardrailPolicyInput:
    return GuardrailPolicyInput(
        source="PLATFORM_DEFAULT",
        priority=0,
        hooks=tuple(GuardrailHook),
        configuration={
            "rules": [
                {
                    "id": "default-max-input",
                    "type": "MAX_PAYLOAD_SIZE",
                    "action": "BLOCK",
                    "hooks": ["INPUT", "TOOL_INPUT"],
                    "max_bytes": 100_000,
                },
                {
                    "id": "default-max-output",
                    "type": "MAX_PAYLOAD_SIZE",
                    "action": "BLOCK",
                    "hooks": ["MODEL_OUTPUT", "TOOL_OUTPUT"],
                    "max_bytes": 256_000,
                },
                {
                    "id": "default-secrets",
                    "type": "SECRET_DETECTION",
                    "action": "REDACT",
                },
                {
                    "id": "default-pii",
                    "type": "PII_REDACTION",
                    "action": "REDACT",
                },
                {
                    "id": "default-high-risk-tool",
                    "type": "TOOL_POLICY",
                    "action": "BLOCK",
                    "hooks": ["TOOL_INPUT"],
                    "minimum_risk": "HIGH",
                    "side_effect_only": True,
                },
            ]
        },
    )
