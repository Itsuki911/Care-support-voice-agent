"""Add TEST-Secretary mode tables (secretary_employees, secretary_events, secretary_tasks).

Revision ID: 0003_secretary_schema
Revises: 0002_rag_schema
Create Date: 2026-11-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_secretary_schema"
down_revision = "0002_rag_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secretary_employees",
        sa.Column("employee_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("department", sa.String(length=128), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("employee_id"),
    )

    op.create_table(
        "secretary_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seed_key", sa.String(length=128), nullable=True),
        sa.Column("employee_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["secretary_employees.employee_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seed_key"),
    )
    op.create_index(
        "ix_secretary_events_emp_start", "secretary_events", ["employee_id", "start_at"]
    )

    op.create_table(
        "secretary_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seed_key", sa.String(length=128), nullable=True),
        sa.Column("employee_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["secretary_employees.employee_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seed_key"),
    )
    op.create_index(
        "ix_secretary_tasks_emp_due", "secretary_tasks", ["employee_id", "due_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_secretary_tasks_emp_due", table_name="secretary_tasks")
    op.drop_table("secretary_tasks")
    op.drop_index("ix_secretary_events_emp_start", table_name="secretary_events")
    op.drop_table("secretary_events")
    op.drop_table("secretary_employees")
