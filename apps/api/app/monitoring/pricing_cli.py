"""Validate, import and inspect operator-supplied model pricing JSON."""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionFactory, dispose_engine
from ..models import ModelPricing
from .pricing import import_pricing, pricing_payload


def _file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise ValueError("pricing JSON must be an object or a list of objects")
    return payload


async def _run(args: argparse.Namespace) -> None:
    if args.action == "validate":
        entries = _file(args.file)
        parsed = [pricing_payload(item) for item in entries]
        keys = [
            (item["provider"], item["model"], item["effective_from"]) for item in parsed
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("pricing file contains duplicate effective dates")
        print(f"Validated {len(parsed)} pricing entries")
    elif args.action == "import":
        entries = _file(args.file)
        async with SessionFactory() as session:
            count = await import_pricing(session, entries, dry_run=args.dry_run)
        print(f"Imported {count} pricing entries")
    elif args.action == "list":
        async with SessionFactory() as session:
            rows = (
                await session.scalars(
                    select(ModelPricing).order_by(
                        ModelPricing.provider,
                        ModelPricing.model,
                        ModelPricing.effective_from,
                    )
                )
            ).all()
            print(
                json.dumps(
                    [
                        {
                            "provider": row.provider,
                            "model": row.model,
                            "effective_from": row.effective_from.isoformat(),
                            "effective_to": row.effective_to.isoformat()
                            if row.effective_to
                            else None,
                            "input_price_per_million": str(row.input_price_per_million),
                            "output_price_per_million": str(
                                row.output_price_per_million
                            ),
                            "cached_input_price_per_million": str(
                                row.cached_input_price_per_million
                            )
                            if row.cached_input_price_per_million is not None
                            else None,
                            "metadata": row.metadata_json,
                        }
                        for row in rows
                    ],
                    indent=2,
                )
            )
    else:
        settings = get_settings()
        if (
            settings.azure_openai_input_price_per_million is None
            or settings.azure_openai_output_price_per_million is None
        ):
            raise ValueError(
                "Azure input and output rates must be configured before bootstrap"
            )
        entry = {
            "provider": "azure_openai",
            "model": settings.azure_openai_deployment_name,
            "effective_from": args.effective_from,
            "input_price_per_million": str(
                settings.azure_openai_input_price_per_million
            ),
            "output_price_per_million": str(
                settings.azure_openai_output_price_per_million
            ),
            "cached_input_price_per_million": str(
                settings.azure_openai_cached_input_price_per_million
            )
            if settings.azure_openai_cached_input_price_per_million is not None
            else None,
            "metadata": {"currency": "USD", "source": "operator settings bootstrap"},
        }
        async with SessionFactory() as session:
            count = await import_pricing(session, [entry], dry_run=args.dry_run)
        print(
            f"Bootstrapped {count} Azure pricing entry"
            + (" (dry run)" if args.dry_run else "")
        )


async def _main(args: argparse.Namespace) -> None:
    try:
        await _run(args)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate")
    validate.add_argument("file", type=Path)
    importer = actions.add_parser("import")
    importer.add_argument("file", type=Path)
    importer.add_argument("--dry-run", action="store_true")
    actions.add_parser("list")
    bootstrap = actions.add_parser("bootstrap-azure")
    bootstrap.add_argument(
        "--effective-from",
        required=True,
        type=lambda value: datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).isoformat(),
    )
    bootstrap.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
