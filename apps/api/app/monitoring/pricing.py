"""Immutable-by-effective-date model pricing operations."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ModelPricing


def pricing_payload(value: dict[str, Any]) -> dict[str, Any]:
    provider = str(value["provider"]).strip().lower()
    model = str(value["model"]).strip().lower()
    start = datetime.fromisoformat(str(value["effective_from"]).replace("Z", "+00:00"))
    if start.tzinfo is None:
        raise ValueError("effective_from must include a timezone")
    rates = {
        key: (Decimal(str(value[key])) if value.get(key) is not None else None)
        for key in (
            "input_price_per_million",
            "output_price_per_million",
            "cached_input_price_per_million",
        )
    }
    if not provider or len(provider) > 64 or not model or len(model) > 255:
        raise ValueError("provider and model must be non-empty identifiers")
    if (
        rates["input_price_per_million"] is None
        or rates["output_price_per_million"] is None
    ):
        raise ValueError("input and output prices are required")
    if any(
        rate is not None and (not rate.is_finite() or rate < 0)
        for rate in rates.values()
    ):
        raise ValueError("prices must be finite non-negative decimals")
    metadata = dict(value.get("metadata", {}))
    if metadata.get("currency", "USD") != "USD":
        raise ValueError("only USD pricing is supported")
    metadata["currency"] = "USD"
    if not metadata.get("source"):
        raise ValueError("metadata.source is required")
    return {
        "provider": provider,
        "model": model,
        "effective_from": start.astimezone(UTC),
        **rates,
        "metadata_json": metadata,
    }


async def import_pricing(
    session: AsyncSession, payloads: list[dict[str, Any]], *, dry_run: bool
) -> int:
    parsed = [pricing_payload(item) for item in payloads]
    parsed.sort(
        key=lambda item: (item["provider"], item["model"], item["effective_from"])
    )
    keys: set[tuple[str, str, datetime]] = set()
    for item in parsed:
        key = (item["provider"], item["model"], item["effective_from"])
        if key in keys:
            raise ValueError("pricing file contains duplicate effective dates")
        keys.add(key)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in parsed:
        grouped.setdefault((item["provider"], item["model"]), []).append(item)
    for (provider, model), entries in grouped.items():
        existing = list(
            (
                await session.scalars(
                    select(ModelPricing)
                    .where(
                        ModelPricing.provider == provider, ModelPricing.model == model
                    )
                    .order_by(ModelPricing.effective_from)
                    .with_for_update()
                )
            ).all()
        )
        existing_by_start = {row.effective_from: row for row in existing}
        new_entries = [
            item for item in entries if item["effective_from"] not in existing_by_start
        ]
        for item in entries:
            previous = next(
                (
                    row
                    for row in existing
                    if row.effective_from == item["effective_from"]
                ),
                None,
            )
            if previous:
                actual = {
                    **{
                        key: getattr(previous, key)
                        for key in item
                        if key != "metadata_json"
                    },
                    "metadata_json": previous.metadata_json,
                }
                expected = item
                if actual != expected:
                    raise ValueError("an existing effective date cannot be modified")
                continue
            later = [
                row.effective_from
                for row in existing
                if row.effective_from > item["effective_from"]
            ]
            later.extend(
                other["effective_from"]
                for other in new_entries
                if other["effective_from"] > item["effective_from"]
            )
            next_start = min(later) if later else None
            prior = next(
                (
                    row
                    for row in reversed(existing)
                    if row.effective_from < item["effective_from"]
                ),
                None,
            )
            if prior and prior.effective_to not in (None, item["effective_from"]):
                raise ValueError(
                    "pricing effective periods may not overlap or rewrite history"
                )
            if prior and prior.effective_to is None:
                if not dry_run:
                    prior.effective_to = item["effective_from"]
            item_to_add = dict(item)
            item_to_add["effective_to"] = next_start
            if not dry_run:
                session.add(ModelPricing(id=uuid4(), **item_to_add))
            existing.append(ModelPricing(id=uuid4(), **item_to_add))
            existing.sort(key=lambda row: row.effective_from)
    if not dry_run:
        await session.commit()
    return len(parsed)


async def pricing_for_call(
    session: AsyncSession, provider: str, model: str, at: datetime
) -> ModelPricing | None:
    return await session.scalar(
        select(ModelPricing)
        .where(
            ModelPricing.provider == provider.lower(),
            ModelPricing.model == model.lower(),
            ModelPricing.effective_from <= at,
            (ModelPricing.effective_to.is_(None)) | (ModelPricing.effective_to > at),
        )
        .order_by(ModelPricing.effective_from.desc())
        .limit(1)
    )
