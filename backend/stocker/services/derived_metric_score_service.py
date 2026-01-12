from __future__ import annotations

from datetime import date
from typing import Any
import math

import pandas as pd
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

from stocker.core.database import AsyncSessionLocal
from stocker.models.derived_metric_rule_set import DerivedMetricRuleSet
from stocker.models.derived_metric_rule import DerivedMetricRule
from stocker.models.derived_metric_definition import DerivedMetricDefinition
from stocker.models.derived_metric_value import DerivedMetricValue
from stocker.models.derived_metric_score import DerivedMetricScore
from stocker.services.universe_service import UniverseService


class DerivedMetricScoreService:
    """Compute consolidated scores for rule sets."""

    _MAX_QUERY_PARAMS = 30000
    _DEFAULT_COLUMN_OVERHEAD = 2

    async def compute_scores(self, as_of_date: date | None = None) -> int:
        target_date = as_of_date or date.today()
        async with AsyncSessionLocal() as session:
            rule_sets = await self._load_rule_sets(session)
            if not rule_sets:
                return 0

            rule_map = await self._load_rules(session, [rs.id for rs in rule_sets])
            rows = []

            universe_service = UniverseService()

            for rule_set in rule_sets:
                rules = rule_map.get(rule_set.id, [])
                if not rules:
                    continue
                if rule_set.universe_id:
                    symbols = await universe_service.get_symbols_for_universe(rule_set.universe_id)
                else:
                    symbols = await universe_service.get_global_symbols()
                if not symbols:
                    continue

                metric_ids = [rule.metric_id for rule, _ in rules]
                values = await self._load_metric_values(
                    session, symbols, metric_ids, target_date
                )
                scores = self._score_symbols(symbols, rules, values)
                rows.extend(
                    self._attach_ranks(rule_set.id, target_date, scores)
                )

            if not rows:
                return 0

            for chunk in self._chunk_rows(rows):
                stmt = insert(DerivedMetricScore).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_derived_metric_scores_rule_set_symbol_date",
                    set_={
                        "score": stmt.excluded.score,
                        "rank": stmt.excluded.rank,
                        "percentile": stmt.excluded.percentile,
                        "passes_required": stmt.excluded.passes_required,
                        "updated_at": func.now(),
                    },
                )
                await session.execute(stmt)
            await session.commit()

        return len(rows)

    async def _load_rule_sets(self, session) -> list[DerivedMetricRuleSet]:
        stmt = select(DerivedMetricRuleSet).where(DerivedMetricRuleSet.is_active.is_(True))
        result = await session.execute(stmt)
        return result.scalars().all()

    async def _load_rules(
        self, session, rule_set_ids: list[int]
    ) -> dict[int, list[tuple[DerivedMetricRule, DerivedMetricDefinition]]]:
        if not rule_set_ids:
            return {}
        stmt = (
            select(DerivedMetricRule, DerivedMetricDefinition)
            .join(DerivedMetricDefinition, DerivedMetricRule.metric_id == DerivedMetricDefinition.id)
            .where(DerivedMetricRule.rule_set_id.in_(rule_set_ids))
        )
        result = await session.execute(stmt)
        rule_map: dict[int, list[tuple[DerivedMetricRule, DerivedMetricDefinition]]] = {}
        for rule, definition in result.all():
            rule_map.setdefault(rule.rule_set_id, []).append((rule, definition))
        return rule_map

    async def _load_metric_values(
        self,
        session,
        symbols: list[str],
        metric_ids: list[int],
        target_date: date,
    ) -> dict[tuple[str, int], DerivedMetricValue]:
        stmt = select(DerivedMetricValue).where(
            DerivedMetricValue.as_of_date == target_date,
            DerivedMetricValue.metric_id.in_(metric_ids),
            DerivedMetricValue.symbol.in_(symbols),
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return {(row.symbol, row.metric_id): row for row in rows}

    def _score_symbols(
        self,
        symbols: list[str],
        rules: list[tuple[DerivedMetricRule, DerivedMetricDefinition]],
        values: dict[tuple[str, int], DerivedMetricValue],
    ) -> list[dict[str, Any]]:
        scored = []
        for symbol in symbols:
            score = 0.0
            passes_required = True
            for rule, _definition in rules:
                value_record = values.get((symbol, rule.metric_id))
                selected = self._select_value(value_record, rule.normalize)
                if selected is None:
                    if rule.is_required:
                        passes_required = False
                        break
                    continue

                if not self._passes_threshold(rule, selected):
                    if rule.is_required:
                        passes_required = False
                        break
                    continue

                weight = float(rule.weight or 1.0)
                score += selected * weight

            scored.append(
                {
                    "symbol": symbol,
                    "score": score if passes_required else None,
                    "passes_required": passes_required,
                }
            )
        return scored

    def _select_value(
        self, record: DerivedMetricValue | None, normalize: str | None
    ) -> float | None:
        if record is None:
            return None
        if normalize == "zscore":
            return self._to_float(record.zscore)
        if normalize == "percentile":
            return self._to_float(record.percentile)
        return self._to_float(record.value)

    def _passes_threshold(self, rule: DerivedMetricRule, value: float) -> bool:
        op = rule.operator
        low = self._to_float(rule.threshold_low)
        high = self._to_float(rule.threshold_high)
        if op == ">":
            return low is not None and value > low
        if op == ">=":
            return low is not None and value >= low
        if op == "<":
            return low is not None and value < low
        if op == "<=":
            return low is not None and value <= low
        if op == "between":
            if low is None or high is None:
                return False
            return low <= value <= high
        if op == "any":
            return True
        return True

    def _attach_ranks(
        self,
        rule_set_id: int,
        target_date: date,
        scores: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        df = pd.DataFrame(scores)
        if df.empty:
            return []

        valid = df[df["score"].notna() & df["passes_required"]]
        if not valid.empty:
            ranks = valid["score"].rank(ascending=False, method="min")
            if len(valid) == 1:
                percentiles = pd.Series([1.0], index=valid.index)
            else:
                percentiles = 1 - (ranks - 1) / (len(valid) - 1)
            df.loc[valid.index, "rank"] = ranks.astype(int)
            df.loc[valid.index, "percentile"] = percentiles

        rows = []
        for row in df.itertuples(index=False):
            score_value = None if pd.isna(row.score) else float(row.score)
            if score_value is not None and not math.isfinite(score_value):
                score_value = None
            percentile_value = None if pd.isna(row.percentile) else float(row.percentile)
            if percentile_value is not None and not math.isfinite(percentile_value):
                percentile_value = None
            rows.append(
                {
                    "rule_set_id": rule_set_id,
                    "symbol": row.symbol,
                    "as_of_date": target_date,
                    "score": score_value,
                    "rank": int(row.rank) if not pd.isna(row.rank) else None,
                    "percentile": percentile_value,
                    "passes_required": bool(row.passes_required),
                }
            )
        return rows

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
        return numeric

    def _chunk_rows(self, rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if not rows:
            return []
        row_size = max(1, len(rows[0]) + self._DEFAULT_COLUMN_OVERHEAD)
        batch_size = max(1, min(2000, self._MAX_QUERY_PARAMS // row_size))
        return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
