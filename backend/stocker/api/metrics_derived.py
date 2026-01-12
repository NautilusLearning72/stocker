from datetime import date, datetime
from decimal import Decimal
import math
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.core.database import get_db
from stocker.models.derived_metric_definition import DerivedMetricDefinition
from stocker.models.derived_metric_value import DerivedMetricValue
from stocker.models.derived_metric_rule_set import DerivedMetricRuleSet
from stocker.models.derived_metric_rule import DerivedMetricRule
from stocker.models.derived_metric_score import DerivedMetricScore
from stocker.models.instrument_info import InstrumentInfo
from stocker.models.instrument_universe_member import InstrumentUniverseMember
from stocker.services.derived_metric_seed_service import DerivedMetricSeedService

router = APIRouter()


def _to_finite_number(value: Decimal | float | int | None) -> Decimal | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


class DerivedMetricDefinitionResponse(BaseModel):
    id: int
    metric_key: str
    name: str
    category: str
    unit: Optional[str] = None
    direction: str
    lookback_days: Optional[int] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    source_table: Optional[str] = None
    source_field: Optional[str] = None
    version: str
    is_active: bool

    class Config:
        from_attributes = True


class DerivedMetricValueResponse(BaseModel):
    symbol: str
    as_of_date: date
    metric_id: int
    metric_key: str
    value: Optional[Decimal] = None
    zscore: Optional[Decimal] = None
    percentile: Optional[Decimal] = None
    rank: Optional[int] = None
    source: str
    calc_version: str


class RuleSetBase(BaseModel):
    name: str = Field(..., max_length=120)
    description: Optional[str] = None
    universe_id: Optional[int] = None
    is_active: bool = True


class RuleSetCreate(RuleSetBase):
    pass


class RuleSetUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    universe_id: Optional[int] = None
    is_active: Optional[bool] = None


class RuleSetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    universe_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RuleBase(BaseModel):
    metric_id: Optional[int] = None
    metric_key: Optional[str] = Field(None, max_length=64)
    operator: str = Field(..., max_length=10)
    threshold_low: Optional[Decimal] = None
    threshold_high: Optional[Decimal] = None
    weight: Decimal = Decimal("1.0")
    is_required: bool = False
    normalize: Optional[str] = None


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    metric_id: Optional[int] = None
    metric_key: Optional[str] = Field(None, max_length=64)
    operator: Optional[str] = Field(None, max_length=10)
    threshold_low: Optional[Decimal] = None
    threshold_high: Optional[Decimal] = None
    weight: Optional[Decimal] = None
    is_required: Optional[bool] = None
    normalize: Optional[str] = None


class RuleResponse(BaseModel):
    id: int
    rule_set_id: int
    metric_id: int
    operator: str
    threshold_low: Optional[Decimal] = None
    threshold_high: Optional[Decimal] = None
    weight: Decimal
    is_required: bool
    normalize: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScoreRow(BaseModel):
    symbol: str
    score: Optional[Decimal] = None
    rank: Optional[int] = None
    percentile: Optional[Decimal] = None
    passes_required: bool
    metrics: dict[str, Optional[Decimal]] = Field(default_factory=dict)
    holdings: Optional[dict[str, Any]] = None


class ScoresResponse(BaseModel):
    items: list[ScoreRow]
    total: int
    page: int
    page_size: int


class DerivedMetricsStatus(BaseModel):
    latest_values_date: Optional[date] = None
    latest_scores_date: Optional[date] = None
    latest_values_updated_at: Optional[datetime] = None
    latest_scores_updated_at: Optional[datetime] = None


class FilterClause(BaseModel):
    field: str
    op: str
    value: Optional[Any] = None
    metric_key: Optional[str] = None


class SortSpec(BaseModel):
    field: str
    order: str = "desc"


class ScoresQuery(BaseModel):
    rule_set_id: int = Field(..., ge=1)
    as_of_date: Optional[date] = None
    search: Optional[str] = None
    universe_id: Optional[int] = None
    filters: list[FilterClause] = Field(default_factory=list)
    sort: Optional[SortSpec] = None
    columns: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


async def _resolve_metric_id(
    db: AsyncSession,
    metric_id: Optional[int],
    metric_key: Optional[str],
) -> int:
    if metric_id is not None:
        return metric_id
    if not metric_key:
        raise HTTPException(status_code=400, detail="metric_id or metric_key is required")
    key = metric_key.strip().lower()
    stmt = select(DerivedMetricDefinition.id).where(DerivedMetricDefinition.metric_key == key)
    result = await db.execute(stmt)
    resolved = result.scalar_one_or_none()
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Metric definition not found: {key}")
    return resolved


async def _build_scores_response(
    db: AsyncSession,
    rule_set_id: int,
    as_of_date: Optional[date],
    search: Optional[str],
    universe_id: Optional[int],
    sector: Optional[str],
    industry: Optional[str],
    min_score: Optional[Decimal],
    max_score: Optional[Decimal],
    sort: Optional[str],
    order: Optional[str],
    page: int,
    page_size: int,
    columns: list[str],
) -> ScoresResponse:
    if as_of_date is None:
        latest_stmt = select(func.max(DerivedMetricScore.as_of_date)).where(
            DerivedMetricScore.rule_set_id == rule_set_id
        )
        latest_result = await db.execute(latest_stmt)
        as_of_date = latest_result.scalar_one_or_none()
        if as_of_date is None:
            return ScoresResponse(items=[], total=0, page=page, page_size=page_size)

    stmt = select(DerivedMetricScore).where(DerivedMetricScore.rule_set_id == rule_set_id)

    if as_of_date:
        stmt = stmt.where(DerivedMetricScore.as_of_date == as_of_date)
    if search:
        search_value = search.strip().upper()
        if search_value:
            stmt = stmt.where(DerivedMetricScore.symbol.ilike(f"%{search_value}%"))
    if min_score is not None:
        stmt = stmt.where(DerivedMetricScore.score >= min_score)
    if max_score is not None:
        stmt = stmt.where(DerivedMetricScore.score <= max_score)
    if universe_id:
        stmt = stmt.join(
            InstrumentUniverseMember,
            (InstrumentUniverseMember.symbol == DerivedMetricScore.symbol)
            & (InstrumentUniverseMember.universe_id == universe_id)
            & (InstrumentUniverseMember.is_deleted.is_(False)),
        )
    if sector or industry:
        stmt = stmt.join(InstrumentInfo, InstrumentInfo.symbol == DerivedMetricScore.symbol)
        if sector:
            stmt = stmt.where(InstrumentInfo.sector == sector)
        if industry:
            stmt = stmt.where(InstrumentInfo.industry == industry)

    sort_col = DerivedMetricScore.score
    if sort == "rank":
        sort_col = DerivedMetricScore.rank
    elif sort == "symbol":
        sort_col = DerivedMetricScore.symbol
    elif sort and sort.startswith("metric:"):
        metric_key = sort.split(":", 1)[1].strip().lower()
        if not metric_key:
            raise HTTPException(status_code=400, detail="Metric sort requires a metric key")
        if as_of_date is None:
            raise HTTPException(status_code=400, detail="as_of_date is required for metric sorting")
        metric_stmt = select(DerivedMetricDefinition.id).where(
            DerivedMetricDefinition.metric_key == metric_key
        )
        metric_result = await db.execute(metric_stmt)
        metric_id = metric_result.scalar_one_or_none()
        if metric_id is None:
            raise HTTPException(status_code=404, detail=f"Metric definition not found: {metric_key}")
        stmt = stmt.join(
            DerivedMetricValue,
            (DerivedMetricValue.symbol == DerivedMetricScore.symbol)
            & (DerivedMetricValue.metric_id == metric_id)
            & (DerivedMetricValue.as_of_date == as_of_date),
        )
        sort_col = DerivedMetricValue.value

    sort_order = (order or "desc").lower()
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="order must be asc or desc")

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    if sort_order == "asc":
        stmt = stmt.order_by(sort_col.asc(), DerivedMetricScore.symbol.asc())
    else:
        stmt = stmt.order_by(sort_col.desc(), DerivedMetricScore.symbol.asc())

    offset = (page - 1) * page_size
    rows_result = await db.execute(stmt.offset(offset).limit(page_size))
    scores = rows_result.scalars().all()

    metrics_by_symbol: dict[str, dict[str, Optional[Decimal]]] = {}
    if columns and as_of_date and scores:
        normalized_columns = [column.strip().lower() for column in columns if column.strip()]
        if normalized_columns:
            metric_stmt = select(
                DerivedMetricDefinition.id,
                DerivedMetricDefinition.metric_key,
            ).where(DerivedMetricDefinition.metric_key.in_(normalized_columns))
            metric_result = await db.execute(metric_stmt)
            metric_rows = metric_result.all()
            metric_ids = {row[0]: row[1] for row in metric_rows}
            if metric_ids:
                symbols = [score.symbol for score in scores]
                values_stmt = select(DerivedMetricValue).where(
                    DerivedMetricValue.as_of_date == as_of_date,
                    DerivedMetricValue.symbol.in_(symbols),
                    DerivedMetricValue.metric_id.in_(metric_ids.keys()),
                )
                values_result = await db.execute(values_stmt)
                for value in values_result.scalars().all():
                    metrics_by_symbol.setdefault(value.symbol, {})[
                        metric_ids[value.metric_id]
                    ] = _to_finite_number(value.value)

    items = [
        ScoreRow(
            symbol=score.symbol,
            score=_to_finite_number(score.score),
            rank=score.rank,
            percentile=_to_finite_number(score.percentile),
            passes_required=score.passes_required,
            metrics=metrics_by_symbol.get(score.symbol, {}),
            holdings=None,
        )
        for score in scores
    ]

    return ScoresResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/definitions", response_model=list[DerivedMetricDefinitionResponse])
async def list_metric_definitions(
    category: Optional[str] = Query(default=None),
    active: Optional[bool] = Query(default=True),
    version: Optional[str] = Query(default="v1"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DerivedMetricDefinition)
    if category:
        stmt = stmt.where(DerivedMetricDefinition.category == category)
    if active is not None:
        stmt = stmt.where(DerivedMetricDefinition.is_active.is_(active))
    if version:
        stmt = stmt.where(DerivedMetricDefinition.version == version)
    stmt = stmt.order_by(DerivedMetricDefinition.category.asc(), DerivedMetricDefinition.metric_key.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/values", response_model=list[DerivedMetricValueResponse])
async def list_metric_values(
    as_of_date: Optional[date] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    metric_keys: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(DerivedMetricValue, DerivedMetricDefinition.metric_key)
        .join(
            DerivedMetricDefinition,
            DerivedMetricValue.metric_id == DerivedMetricDefinition.id,
        )
    )
    if as_of_date:
        stmt = stmt.where(DerivedMetricValue.as_of_date == as_of_date)
    if symbol:
        symbol_value = symbol.strip().upper()
        if symbol_value:
            stmt = stmt.where(DerivedMetricValue.symbol == symbol_value)
    if metric_keys:
        keys = [key.strip().lower() for key in metric_keys if key.strip()]
        if keys:
            stmt = stmt.where(DerivedMetricDefinition.metric_key.in_(keys))
    stmt = stmt.order_by(DerivedMetricValue.symbol.asc(), DerivedMetricDefinition.metric_key.asc())
    result = await db.execute(stmt)
    return [
        DerivedMetricValueResponse(
            symbol=value.symbol,
            as_of_date=value.as_of_date,
            metric_id=value.metric_id,
            metric_key=metric_key,
            value=value.value,
            zscore=value.zscore,
            percentile=value.percentile,
            rank=value.rank,
            source=value.source,
            calc_version=value.calc_version,
        )
        for value, metric_key in result.all()
    ]


@router.get("/status", response_model=DerivedMetricsStatus)
async def get_metrics_status(
    db: AsyncSession = Depends(get_db),
):
    values_date_stmt = select(func.max(DerivedMetricValue.as_of_date))
    scores_date_stmt = select(func.max(DerivedMetricScore.as_of_date))
    values_updated_stmt = select(func.max(DerivedMetricValue.updated_at))
    scores_updated_stmt = select(func.max(DerivedMetricScore.updated_at))

    values_date_result = await db.execute(values_date_stmt)
    scores_date_result = await db.execute(scores_date_stmt)
    values_updated_result = await db.execute(values_updated_stmt)
    scores_updated_result = await db.execute(scores_updated_stmt)

    return DerivedMetricsStatus(
        latest_values_date=values_date_result.scalar_one_or_none(),
        latest_scores_date=scores_date_result.scalar_one_or_none(),
        latest_values_updated_at=values_updated_result.scalar_one_or_none(),
        latest_scores_updated_at=scores_updated_result.scalar_one_or_none(),
    )


@router.get("/rule-sets", response_model=list[RuleSetResponse])
async def list_rule_sets(
    active: Optional[bool] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DerivedMetricRuleSet)
    if active is not None:
        stmt = stmt.where(DerivedMetricRuleSet.is_active.is_(active))
    result = await db.execute(stmt.order_by(DerivedMetricRuleSet.name.asc()))
    rule_sets = result.scalars().all()
    if not rule_sets:
        seeded = await DerivedMetricSeedService().seed_defaults(db)
        if seeded > 0:
            result = await db.execute(stmt.order_by(DerivedMetricRuleSet.name.asc()))
            rule_sets = result.scalars().all()
    return rule_sets


@router.post("/rule-sets", response_model=RuleSetResponse, status_code=status.HTTP_201_CREATED)
async def create_rule_set(
    payload: RuleSetCreate,
    db: AsyncSession = Depends(get_db),
):
    rule_set = DerivedMetricRuleSet(
        name=payload.name,
        description=payload.description,
        universe_id=payload.universe_id,
        is_active=payload.is_active,
    )
    db.add(rule_set)
    await db.flush()
    await db.refresh(rule_set)
    return rule_set


@router.patch("/rule-sets/{rule_set_id}", response_model=RuleSetResponse)
async def update_rule_set(
    rule_set_id: int,
    payload: RuleSetUpdate,
    db: AsyncSession = Depends(get_db),
):
    rule_set = await db.get(DerivedMetricRuleSet, rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="Rule set not found")
    if payload.name is not None:
        rule_set.name = payload.name
    if payload.description is not None:
        rule_set.description = payload.description
    if payload.universe_id is not None:
        rule_set.universe_id = payload.universe_id
    if payload.is_active is not None:
        rule_set.is_active = payload.is_active
    await db.flush()
    await db.refresh(rule_set)
    return rule_set


@router.delete("/rule-sets/{rule_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_set(
    rule_set_id: int,
    db: AsyncSession = Depends(get_db),
):
    rule_set = await db.get(DerivedMetricRuleSet, rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="Rule set not found")
    await db.delete(rule_set)
    return None


@router.get("/rule-sets/{rule_set_id}/rules", response_model=list[RuleResponse])
async def list_rules(
    rule_set_id: int,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(DerivedMetricRule)
        .where(DerivedMetricRule.rule_set_id == rule_set_id)
        .order_by(DerivedMetricRule.id.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/rule-sets/{rule_set_id}/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule(
    rule_set_id: int,
    payload: RuleCreate,
    db: AsyncSession = Depends(get_db),
):
    rule_set = await db.get(DerivedMetricRuleSet, rule_set_id)
    if not rule_set:
        raise HTTPException(status_code=404, detail="Rule set not found")
    metric_id = await _resolve_metric_id(db, payload.metric_id, payload.metric_key)
    rule = DerivedMetricRule(
        rule_set_id=rule_set_id,
        metric_id=metric_id,
        operator=payload.operator,
        threshold_low=payload.threshold_low,
        threshold_high=payload.threshold_high,
        weight=payload.weight,
        is_required=payload.is_required,
        normalize=payload.normalize,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    payload: RuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(DerivedMetricRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if payload.metric_id is not None or payload.metric_key:
        rule.metric_id = await _resolve_metric_id(db, payload.metric_id, payload.metric_key)
    if payload.operator is not None:
        rule.operator = payload.operator
    if payload.threshold_low is not None:
        rule.threshold_low = payload.threshold_low
    if payload.threshold_high is not None:
        rule.threshold_high = payload.threshold_high
    if payload.weight is not None:
        rule.weight = payload.weight
    if payload.is_required is not None:
        rule.is_required = payload.is_required
    if payload.normalize is not None:
        rule.normalize = payload.normalize
    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    rule = await db.get(DerivedMetricRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    return None


@router.get("/scores", response_model=ScoresResponse)
async def get_scores(
    rule_set_id: int = Query(..., ge=1),
    as_of_date: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    universe_id: Optional[int] = Query(default=None),
    sector: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    min_score: Optional[Decimal] = Query(default=None),
    max_score: Optional[Decimal] = Query(default=None),
    sort: Optional[str] = Query(default="score"),
    order: Optional[str] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    columns: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    return await _build_scores_response(
        db=db,
        rule_set_id=rule_set_id,
        as_of_date=as_of_date,
        search=search,
        universe_id=universe_id,
        sector=sector,
        industry=industry,
        min_score=min_score,
        max_score=max_score,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
        columns=columns,
    )


@router.post("/scores/query", response_model=ScoresResponse)
async def query_scores(
    body: ScoresQuery,
    db: AsyncSession = Depends(get_db),
):
    sector = None
    industry = None
    for clause in body.filters:
        if clause.field == "sector" and clause.op == "=":
            sector = str(clause.value) if clause.value is not None else None
        if clause.field == "industry" and clause.op == "=":
            industry = str(clause.value) if clause.value is not None else None

    sort_field = body.sort.field if body.sort else "score"
    sort_order = body.sort.order if body.sort else "desc"

    return await _build_scores_response(
        db=db,
        rule_set_id=body.rule_set_id,
        as_of_date=body.as_of_date,
        search=body.search,
        universe_id=body.universe_id,
        sector=sector,
        industry=industry,
        min_score=None,
        max_score=None,
        sort=sort_field,
        order=sort_order,
        page=body.page,
        page_size=body.page_size,
        columns=body.columns,
    )
