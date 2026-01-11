"""add_derived_metrics_tables

Revision ID: k1a2b3c4d5e6
Revises: j2c3d4e5f6g7
Create Date: 2026-01-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "k1a2b3c4d5e6"
down_revision = "j2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "derived_metric_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("unit", sa.String(length=20)),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("lookback_days", sa.Integer()),
        sa.Column("description", sa.Text()),
        sa.Column("tags", sa.String(length=200)),
        sa.Column("source_table", sa.String(length=50)),
        sa.Column("source_field", sa.String(length=64)),
        sa.Column("version", sa.String(length=20), nullable=False, server_default="v1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("metric_key", name="uq_derived_metric_definitions_key"),
    )
    op.create_index(
        "ix_derived_metric_definitions_category_key",
        "derived_metric_definitions",
        ["category", "metric_key"],
    )

    op.create_table(
        "derived_metric_rule_sets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("universe_id", sa.Integer(), sa.ForeignKey("instrument_universe.id")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("name", name="uq_derived_metric_rule_sets_name"),
    )
    op.create_index(
        "ix_derived_metric_rule_sets_active",
        "derived_metric_rule_sets",
        ["is_active"],
    )

    op.create_table(
        "derived_metric_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "rule_set_id",
            sa.Integer(),
            sa.ForeignKey("derived_metric_rule_sets.id"),
            nullable=False,
        ),
        sa.Column(
            "metric_id",
            sa.Integer(),
            sa.ForeignKey("derived_metric_definitions.id"),
            nullable=False,
        ),
        sa.Column("operator", sa.String(length=10), nullable=False),
        sa.Column("threshold_low", sa.Numeric(20, 8)),
        sa.Column("threshold_high", sa.Numeric(20, 8)),
        sa.Column("weight", sa.Numeric(10, 6), nullable=False, server_default="1.0"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("normalize", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index(
        "ix_derived_metric_rules_rule_set",
        "derived_metric_rules",
        ["rule_set_id"],
    )
    op.create_index(
        "ix_derived_metric_rules_metric",
        "derived_metric_rules",
        ["metric_id"],
    )

    op.create_table(
        "derived_metric_values",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "metric_id",
            sa.Integer(),
            sa.ForeignKey("derived_metric_definitions.id"),
            nullable=False,
        ),
        sa.Column("value", sa.Numeric(20, 8)),
        sa.Column("zscore", sa.Numeric(12, 6)),
        sa.Column("percentile", sa.Numeric(6, 4)),
        sa.Column("rank", sa.Integer()),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("calc_version", sa.String(length=20), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint(
            "symbol",
            "as_of_date",
            "metric_id",
            name="uq_derived_metric_values_symbol_date_metric",
        ),
    )
    op.create_index(
        "ix_derived_metric_values_metric_date",
        "derived_metric_values",
        ["metric_id", "as_of_date"],
    )
    op.create_index(
        "ix_derived_metric_values_symbol_date",
        "derived_metric_values",
        ["symbol", "as_of_date"],
    )

    op.create_table(
        "derived_metric_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "rule_set_id",
            sa.Integer(),
            sa.ForeignKey("derived_metric_rule_sets.id"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("score", sa.Numeric(20, 8)),
        sa.Column("rank", sa.Integer()),
        sa.Column("percentile", sa.Numeric(6, 4)),
        sa.Column("passes_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint(
            "rule_set_id",
            "symbol",
            "as_of_date",
            name="uq_derived_metric_scores_rule_set_symbol_date",
        ),
    )
    op.create_index(
        "ix_derived_metric_scores_rule_set_date",
        "derived_metric_scores",
        ["rule_set_id", "as_of_date"],
    )
    op.create_index(
        "ix_derived_metric_scores_symbol_date",
        "derived_metric_scores",
        ["symbol", "as_of_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_derived_metric_scores_symbol_date", table_name="derived_metric_scores")
    op.drop_index("ix_derived_metric_scores_rule_set_date", table_name="derived_metric_scores")
    op.drop_table("derived_metric_scores")

    op.drop_index("ix_derived_metric_values_symbol_date", table_name="derived_metric_values")
    op.drop_index("ix_derived_metric_values_metric_date", table_name="derived_metric_values")
    op.drop_table("derived_metric_values")

    op.drop_index("ix_derived_metric_rules_metric", table_name="derived_metric_rules")
    op.drop_index("ix_derived_metric_rules_rule_set", table_name="derived_metric_rules")
    op.drop_table("derived_metric_rules")

    op.drop_index("ix_derived_metric_rule_sets_active", table_name="derived_metric_rule_sets")
    op.drop_table("derived_metric_rule_sets")

    op.drop_index("ix_derived_metric_definitions_category_key", table_name="derived_metric_definitions")
    op.drop_table("derived_metric_definitions")
