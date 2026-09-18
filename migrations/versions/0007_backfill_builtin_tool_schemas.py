"""Backfill canonical schemas for built-in tool versions.

Revision ID: 0007_builtin_schema_backfill
Revises: 0006_tool_platform
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0007_builtin_schema_backfill"
down_revision = "0006_tool_platform"
branch_labels = None
depends_on = None


def _schemas() -> dict[str, tuple[dict[str, object], dict[str, object]]]:
    return {
        "calculator": (
            {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    }
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"result": {}},
                "required": ["result"],
                "additionalProperties": False,
            },
        ),
        "current_datetime": (
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"datetime": {"type": "string"}},
                "required": ["datetime"],
                "additionalProperties": False,
            },
        ),
        "echo": (
            {
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"value": {}},
                "required": ["value"],
                "additionalProperties": False,
            },
        ),
        "web_search": (
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "num_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 10,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "published_date": {"type": ["string", "null"]},
                                "highlights": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title", "url", "highlights"],
                        },
                    },
                    "request_id": {"type": ["string", "null"]},
                },
                "required": ["query", "results"],
                "additionalProperties": False,
            },
        ),
    }


def upgrade() -> None:
    connection = op.get_bind()
    for slug, (input_schema, output_schema) in _schemas().items():
        connection.execute(
            sa.text(
                """
                UPDATE tool_versions AS versions
                SET input_schema = CAST(:input_schema AS jsonb),
                    output_schema = CAST(:output_schema AS jsonb)
                FROM tools
                WHERE tools.id = versions.tool_id
                  AND tools.slug = :slug
                  AND versions.version_number = 1
                  AND versions.executor_type = 'FUNCTION'
                """
            ),
            {
                "slug": slug,
                "input_schema": json.dumps(input_schema),
                "output_schema": json.dumps(output_schema),
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    for slug in _schemas():
        connection.execute(
            sa.text(
                """
                UPDATE tool_versions AS versions
                SET input_schema = '{"type": "object", "additionalProperties": true}'::jsonb,
                    output_schema = NULL
                FROM tools
                WHERE tools.id = versions.tool_id
                  AND tools.slug = :slug
                  AND versions.version_number = 1
                  AND versions.executor_type = 'FUNCTION'
                """
            ),
            {"slug": slug},
        )
