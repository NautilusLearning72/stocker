from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.models.derived_metric_definition import DerivedMetricDefinition
from stocker.models.derived_metric_rule_set import DerivedMetricRuleSet
from stocker.models.derived_metric_rule import DerivedMetricRule
from stocker.models.instrument_universe import InstrumentUniverse
from stocker.services.derived_metrics_service import DerivedMetricsService

logger = logging.getLogger(__name__)


DEFAULT_RULE_SETS: list[dict[str, Any]] = [
    {
        "name": "Quality + Momentum",
        "description": "Blend quality (ROIC) with intermediate momentum.",
        "rules": [
            {
                "metric_key": "mom_6m",
                "operator": ">",
                "threshold_low": 0,
                "weight": 0.0,
                "is_required": True,
                "normalize": None,
            },
            {
                "metric_key": "roic",
                "operator": "any",
                "weight": 0.6,
                "normalize": "zscore",
            },
            {
                "metric_key": "mom_6m",
                "operator": "any",
                "weight": 0.4,
                "normalize": "zscore",
            },
        ],
    },
    {
        "name": "Value + Low Volatility",
        "description": "High earnings yield with lower realized volatility.",
        "rules": [
            {
                "metric_key": "earnings_yield",
                "operator": ">",
                "threshold_low": 0,
                "weight": 0.0,
                "is_required": True,
                "normalize": None,
            },
            {
                "metric_key": "earnings_yield",
                "operator": "any",
                "weight": 0.6,
                "normalize": "percentile",
            },
            {
                "metric_key": "vol_20d",
                "operator": "any",
                "weight": 0.4,
                "normalize": "percentile",
            },
        ],
    },
    {
        "name": "Sentiment Breakout",
        "description": "Positive sentiment momentum with price confirmation.",
        "rules": [
            {
                "metric_key": "sentiment_mom",
                "operator": ">",
                "threshold_low": 0,
                "weight": 0.0,
                "is_required": True,
                "normalize": None,
            },
            {
                "metric_key": "sentiment_mom",
                "operator": "any",
                "weight": 0.5,
                "normalize": "percentile",
            },
            {
                "metric_key": "mom_3m",
                "operator": "any",
                "weight": 0.5,
                "normalize": "percentile",
            },
        ],
    },
    {
        "name": "Defensive Quality",
        "description": "Balance quality with low beta and low volatility.",
        "rules": [
            {
                "metric_key": "debt_to_equity",
                "operator": "<",
                "threshold_low": 1,
                "weight": 0.0,
                "is_required": True,
                "normalize": None,
            },
            {
                "metric_key": "roic",
                "operator": "any",
                "weight": 0.4,
                "normalize": "zscore",
            },
            {
                "metric_key": "vol_20d",
                "operator": "any",
                "weight": 0.3,
                "normalize": "percentile",
            },
            {
                "metric_key": "beta",
                "operator": "any",
                "weight": 0.3,
                "normalize": "percentile",
            },
        ],
    },
]


class DerivedMetricSeedService:
    """Seed default derived metric rule sets and rules if none exist."""

    async def seed_defaults(self, session: AsyncSession) -> int:
        count_stmt = select(func.count()).select_from(DerivedMetricRuleSet)
        result = await session.execute(count_stmt)
        if (result.scalar() or 0) > 0:
            return 0

        await DerivedMetricsService()._ensure_metric_definitions(session)

        metric_keys = {
            rule["metric_key"]
            for rule_set in DEFAULT_RULE_SETS
            for rule in rule_set["rules"]
            if rule.get("metric_key")
        }
        definitions_stmt = select(DerivedMetricDefinition).where(
            DerivedMetricDefinition.metric_key.in_(metric_keys)
        )
        definitions_result = await session.execute(definitions_stmt)
        definitions = {row.metric_key: row for row in definitions_result.scalars().all()}

        global_universe_stmt = (
            select(InstrumentUniverse)
            .where(
                InstrumentUniverse.is_global.is_(True),
                InstrumentUniverse.is_deleted.is_(False),
            )
            .order_by(InstrumentUniverse.id.asc())
            .limit(1)
        )
        global_universe_result = await session.execute(global_universe_stmt)
        global_universe = global_universe_result.scalar_one_or_none()
        universe_id = global_universe.id if global_universe else None

        created = 0
        for rule_set in DEFAULT_RULE_SETS:
            rules = []
            for rule in rule_set["rules"]:
                definition = definitions.get(rule["metric_key"])
                if not definition:
                    logger.warning(
                        "Skipping rule %s in %s: missing metric definition",
                        rule["metric_key"],
                        rule_set["name"],
                    )
                    continue
                rules.append(
                    DerivedMetricRule(
                        metric_id=definition.id,
                        operator=rule["operator"],
                        threshold_low=rule.get("threshold_low"),
                        threshold_high=rule.get("threshold_high"),
                        weight=rule.get("weight", 1.0),
                        is_required=rule.get("is_required", False),
                        normalize=rule.get("normalize"),
                    )
                )

            if not rules:
                continue

            model = DerivedMetricRuleSet(
                name=rule_set["name"],
                description=rule_set.get("description"),
                universe_id=universe_id,
                is_active=True,
            )
            session.add(model)
            await session.flush()

            for rule in rules:
                rule.rule_set_id = model.id
                session.add(rule)

            created += 1

        await session.commit()
        return created
