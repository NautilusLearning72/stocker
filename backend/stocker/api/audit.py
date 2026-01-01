"""
Order Audit API Router.

Provides comprehensive order lifecycle tracking, decision explanations,
and discrepancy detection for order audit and investigation.
"""
from datetime import date, datetime, timezone
from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
from sqlalchemy.orm import joinedload
from pydantic import BaseModel

from stocker.core.database import get_db
from stocker.core.metrics import metrics, MetricEvent
from stocker.models.order import Order
from stocker.models.fill import Fill
from stocker.models.signal import Signal
from stocker.models.target_exposure import TargetExposure

router = APIRouter()


# ---------- Pydantic Schemas ----------

class SignalSnapshot(BaseModel):
    """Signal data at time of order."""
    strategy_version: str
    symbol: str
    date: date
    direction: int
    target_weight: Decimal
    lookback_return: Optional[Decimal] = None
    ewma_vol: Optional[Decimal] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TargetSnapshot(BaseModel):
    """Target exposure data."""
    symbol: str
    date: date
    target_exposure: Decimal
    scaling_factor: Decimal
    is_capped: bool
    reason: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FillSnapshot(BaseModel):
    """Execution fill data."""
    fill_id: str
    date: datetime
    qty: Decimal
    price: Decimal
    commission: Decimal
    exchange: Optional[str] = None

    class Config:
        from_attributes = True


class OrderSnapshot(BaseModel):
    """Order data."""
    order_id: UUID
    portfolio_id: str
    date: date
    symbol: str
    side: Optional[str]
    qty: Decimal
    type: Optional[str]
    status: Optional[str]
    broker_order_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DecisionEvent(BaseModel):
    """A decision point in the order lifecycle."""
    timestamp: datetime
    stage: str  # signal, target, sizing, execution
    event_type: str
    description: str
    metadata: dict = {}


class DiscrepancyInfo(BaseModel):
    """Detected discrepancy in order execution."""
    type: str  # qty_mismatch, partial_fill, rejected, slippage
    expected: Optional[Decimal] = None
    actual: Optional[Decimal] = None
    difference: Optional[Decimal] = None
    severity: str  # info, warning, error
    description: str


class OrderAuditRecord(BaseModel):
    """Complete audit record for an order."""
    # Core entities
    order: OrderSnapshot
    signal: Optional[SignalSnapshot] = None
    target: Optional[TargetSnapshot] = None
    fills: List[FillSnapshot] = []

    # Reconstructed timeline
    timeline: List[DecisionEvent] = []

    # Analysis
    discrepancies: List[DiscrepancyInfo] = []

    # Computed metrics
    expected_qty: Optional[Decimal] = None
    filled_qty: Decimal = Decimal("0")
    fill_rate: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    slippage_bps: Optional[Decimal] = None
    total_commission: Decimal = Decimal("0")


class AuditSummary(BaseModel):
    """Summary statistics for audit period."""
    total_orders: int
    filled_count: int
    failed_count: int
    pending_count: int
    discrepancy_count: int
    avg_fill_rate: Optional[float] = None
    total_commission: Decimal
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class AuditListResponse(BaseModel):
    """Paginated audit list response."""
    items: List[OrderAuditRecord]
    total: int
    limit: int
    offset: int


# ---------- Helper Functions ----------

def format_metric_event(event: MetricEvent) -> str:
    """Format a metric event into human-readable description."""
    descriptions = {
        "sizing": lambda e: f"Order sized: target={e.metadata.get('target_qty', 'N/A')}, actual={e.metadata.get('actual_qty', 'N/A')}",
        "skipped": lambda e: f"Order skipped: {e.metadata.get('reason', 'unknown reason')}",
        "created": lambda e: f"Order created: {e.metadata.get('side', '?')} {e.metadata.get('qty', '?')} shares",
        "single_cap_applied": lambda e: f"Single cap applied: {e.metadata.get('weight_before', 'N/A')} → {e.metadata.get('cap', 'N/A')}",
        "gross_exposure_scaled": lambda e: f"Gross exposure scaled by {e.metadata.get('scale_factor', 'N/A')}",
        "drawdown_scaling": lambda e: f"Drawdown scaling: {e.metadata.get('drawdown', 0)*100:.1f}% drawdown, scale={e.metadata.get('scale_factor', 'N/A')}",
        "sector_cap_applied": lambda e: f"Sector cap ({e.metadata.get('sector', '?')}): {e.metadata.get('exposure_before', 'N/A')} → {e.metadata.get('cap', 'N/A')}",
        "confirmation_check": lambda e: f"Confirmation {'passed' if e.metadata.get('passed') else 'failed'}: {e.metadata.get('type', 'N/A')}",
        "trailing_stop_triggered": lambda e: f"Trailing stop triggered: {e.metadata.get('drawdown_pct', 0)*100:.1f}% from peak",
        "generated": lambda e: f"Signal generated: direction={e.metadata.get('direction', '?')}, weight={e.value:.2%}",
    }
    formatter = descriptions.get(event.event_type, lambda e: event.event_type)
    return formatter(event)


def detect_discrepancies(
    order: Order,
    signal: Optional[Signal],
    target: Optional[TargetExposure],
    fills: List[Fill],
    expected_qty: Optional[Decimal] = None
) -> List[DiscrepancyInfo]:
    """Detect discrepancies between expected and actual execution."""
    discrepancies = []

    # Calculate filled quantity
    filled_qty = sum(Decimal(str(f.qty)) for f in fills) if fills else Decimal("0")
    order_qty = Decimal(str(order.qty))

    # 1. Quantity mismatch (expected vs ordered)
    if expected_qty is not None:
        diff = abs(order_qty - expected_qty)
        tolerance = Decimal("0.01") * expected_qty if expected_qty > 0 else Decimal("1")
        if diff > tolerance:
            discrepancies.append(DiscrepancyInfo(
                type="qty_mismatch",
                expected=expected_qty,
                actual=order_qty,
                difference=order_qty - expected_qty,
                severity="warning",
                description=f"Ordered {order_qty} vs expected {expected_qty}"
            ))

    # 2. Partial fill
    if order.status == "FILLED" and filled_qty < order_qty:
        fill_rate = filled_qty / order_qty if order_qty > 0 else Decimal("0")
        severity = "warning" if fill_rate > Decimal("0.9") else "error"
        discrepancies.append(DiscrepancyInfo(
            type="partial_fill",
            expected=order_qty,
            actual=filled_qty,
            difference=order_qty - filled_qty,
            severity=severity,
            description=f"Only {filled_qty}/{order_qty} filled ({float(fill_rate)*100:.1f}%)"
        ))

    # 3. Rejected order
    if order.status == "FAILED":
        discrepancies.append(DiscrepancyInfo(
            type="rejected",
            severity="error",
            description="Order was rejected by broker"
        ))

    # 4. Slippage detection (would need market price at order time)
    # For now, we skip this since we don't have expected price in the order

    return discrepancies


async def build_timeline(
    signal: Optional[Signal],
    target: Optional[TargetExposure],
    order: Order,
    fills: List[Fill],
    metric_events: List[MetricEvent]
) -> List[DecisionEvent]:
    """Build chronological timeline of decision events."""
    events = []

    # Signal generated
    if signal and signal.created_at:
        events.append(DecisionEvent(
            timestamp=signal.created_at,
            stage="signal",
            event_type="signal_generated",
            description=f"Signal: direction={signal.direction}, weight={float(signal.target_weight or 0):.2%}",
            metadata={
                "direction": signal.direction,
                "target_weight": float(signal.target_weight) if signal.target_weight else None,
                "lookback_return": float(signal.lookback_return) if signal.lookback_return else None,
                "ewma_vol": float(signal.ewma_vol) if signal.ewma_vol else None,
            }
        ))

    # Target computed
    if target and target.created_at:
        desc = f"Target: {float(target.target_exposure):.2%}"
        if target.is_capped:
            desc += f" (capped: {target.reason or 'risk limit'})"
        events.append(DecisionEvent(
            timestamp=target.created_at,
            stage="target",
            event_type="target_computed",
            description=desc,
            metadata={
                "target_exposure": float(target.target_exposure),
                "is_capped": target.is_capped,
                "scaling_factor": float(target.scaling_factor) if target.scaling_factor else 1.0,
                "reason": target.reason,
            }
        ))

    # Add relevant metrics events (filter by symbol and timeframe)
    order_symbol = order.symbol
    for me in metric_events:
        if me.symbol == order_symbol and me.category in ["order", "risk", "diversification"]:
            events.append(DecisionEvent(
                timestamp=me.timestamp,
                stage=me.category,
                event_type=me.event_type,
                description=format_metric_event(me),
                metadata=me.metadata
            ))

    # Order created
    if order.created_at:
        events.append(DecisionEvent(
            timestamp=order.created_at,
            stage="execution",
            event_type="order_created",
            description=f"Order: {order.side} {order.qty} @ {order.type}",
            metadata={"status": order.status, "broker_order_id": order.broker_order_id}
        ))

    # Fills
    for fill in fills:
        events.append(DecisionEvent(
            timestamp=fill.date,
            stage="execution",
            event_type="fill",
            description=f"Fill: {fill.qty} @ ${fill.price}",
            metadata={
                "fill_id": fill.fill_id,
                "exchange": fill.exchange,
                "commission": float(fill.commission) if fill.commission else 0,
            }
        ))

    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    return events


async def build_audit_record(
    order: Order,
    db: AsyncSession
) -> OrderAuditRecord:
    """Build complete audit record for an order."""

    # 1. Find matching signal by date + symbol
    signal_result = await db.execute(
        select(Signal).where(
            and_(
                Signal.date == order.date,
                Signal.symbol == order.symbol
            )
        ).order_by(desc(Signal.created_at)).limit(1)
    )
    signal = signal_result.scalar_one_or_none()

    # 2. Find matching target_exposure
    target_result = await db.execute(
        select(TargetExposure).where(
            and_(
                TargetExposure.portfolio_id == order.portfolio_id,
                TargetExposure.date == order.date,
                TargetExposure.symbol == order.symbol
            )
        ).limit(1)
    )
    target = target_result.scalar_one_or_none()

    # 3. Get fills (via eager loading, already available)
    fills = order.fills or []

    # 4. Get metrics events from buffer (filter by symbol)
    metric_events = [
        e for e in metrics.get_buffer()
        if e.symbol == order.symbol
    ]

    # 5. Build timeline
    timeline = await build_timeline(signal, target, order, fills, metric_events)

    # 6. Calculate computed metrics
    filled_qty = sum(Decimal(str(f.qty)) for f in fills) if fills else Decimal("0")
    order_qty = Decimal(str(order.qty))
    fill_rate = filled_qty / order_qty if order_qty > 0 else Decimal("0")

    avg_fill_price = None
    if fills and filled_qty > 0:
        total_value = sum(Decimal(str(f.qty)) * Decimal(str(f.price)) for f in fills)
        avg_fill_price = total_value / filled_qty

    total_commission = sum(Decimal(str(f.commission or 0)) for f in fills)

    # 7. Detect discrepancies
    discrepancies = detect_discrepancies(order, signal, target, fills)

    # Build snapshots
    signal_snapshot = SignalSnapshot(
        strategy_version=signal.strategy_version,
        symbol=signal.symbol,
        date=signal.date,
        direction=signal.direction,
        target_weight=signal.target_weight,
        lookback_return=signal.lookback_return,
        ewma_vol=signal.ewma_vol,
        created_at=signal.created_at,
    ) if signal else None

    target_snapshot = TargetSnapshot(
        symbol=target.symbol,
        date=target.date,
        target_exposure=target.target_exposure,
        scaling_factor=target.scaling_factor or Decimal("1.0"),
        is_capped=target.is_capped or False,
        reason=target.reason,
        created_at=target.created_at,
    ) if target else None

    fill_snapshots = [
        FillSnapshot(
            fill_id=f.fill_id,
            date=f.date,
            qty=f.qty,
            price=f.price,
            commission=f.commission or Decimal("0"),
            exchange=f.exchange,
        ) for f in fills
    ]

    order_snapshot = OrderSnapshot(
        order_id=order.order_id,
        portfolio_id=order.portfolio_id,
        date=order.date,
        symbol=order.symbol,
        side=order.side,
        qty=order.qty,
        type=order.type,
        status=order.status,
        broker_order_id=order.broker_order_id,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )

    return OrderAuditRecord(
        order=order_snapshot,
        signal=signal_snapshot,
        target=target_snapshot,
        fills=fill_snapshots,
        timeline=timeline,
        discrepancies=discrepancies,
        filled_qty=filled_qty,
        fill_rate=fill_rate,
        avg_fill_price=avg_fill_price,
        total_commission=total_commission,
    )


# ---------- Endpoints ----------

@router.get("/orders", response_model=AuditListResponse)
async def get_audit_orders(
    portfolio_id: str = "main",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    side: Optional[str] = None,
    strategy_version: Optional[str] = None,
    min_qty: Optional[float] = None,
    max_qty: Optional[float] = None,
    has_discrepancy: Optional[bool] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Get paginated list of order audit records with filters.
    """
    # Build base query
    query = select(Order).options(joinedload(Order.fills)).where(
        Order.portfolio_id == portfolio_id
    )

    # Apply filters
    if date_from:
        query = query.where(Order.date >= date_from)
    if date_to:
        query = query.where(Order.date <= date_to)
    if symbol:
        query = query.where(Order.symbol == symbol.upper())
    if status:
        query = query.where(Order.status == status.upper())
    if side:
        query = query.where(Order.side == side.upper())
    if min_qty is not None:
        query = query.where(Order.qty >= min_qty)
    if max_qty is not None:
        query = query.where(Order.qty <= max_qty)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination and ordering
    query = query.order_by(desc(Order.date), desc(Order.created_at))
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    orders = result.unique().scalars().all()

    # Build audit records
    items = []
    for order in orders:
        record = await build_audit_record(order, db)

        # Filter by has_discrepancy if specified
        if has_discrepancy is not None:
            has_issues = len(record.discrepancies) > 0
            if has_discrepancy != has_issues:
                continue

        items.append(record)

    return AuditListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/orders/{order_id}", response_model=OrderAuditRecord)
async def get_audit_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get full audit record for a specific order."""
    query = select(Order).options(joinedload(Order.fills)).where(
        Order.order_id == order_id
    )
    result = await db.execute(query)
    order = result.unique().scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return await build_audit_record(order, db)


@router.get("/summary", response_model=AuditSummary)
async def get_audit_summary(
    portfolio_id: str = "main",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get summary statistics for order audit."""
    query = select(Order).options(joinedload(Order.fills)).where(
        Order.portfolio_id == portfolio_id
    )

    if date_from:
        query = query.where(Order.date >= date_from)
    if date_to:
        query = query.where(Order.date <= date_to)

    result = await db.execute(query)
    orders = result.unique().scalars().all()

    total_orders = len(orders)
    filled_count = sum(1 for o in orders if o.status == "FILLED")
    failed_count = sum(1 for o in orders if o.status == "FAILED")
    pending_count = sum(1 for o in orders if o.status in ("NEW", "PENDING", "PENDING_EXECUTION"))

    # Calculate fill rates and discrepancies
    discrepancy_count = 0
    fill_rates = []
    total_commission = Decimal("0")

    for order in orders:
        record = await build_audit_record(order, db)
        if record.discrepancies:
            discrepancy_count += 1
        if record.fill_rate:
            fill_rates.append(float(record.fill_rate))
        total_commission += record.total_commission

    avg_fill_rate = sum(fill_rates) / len(fill_rates) if fill_rates else None

    return AuditSummary(
        total_orders=total_orders,
        filled_count=filled_count,
        failed_count=failed_count,
        pending_count=pending_count,
        discrepancy_count=discrepancy_count,
        avg_fill_rate=avg_fill_rate,
        total_commission=total_commission,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/discrepancies", response_model=List[OrderAuditRecord])
async def get_discrepancies(
    portfolio_id: str = "main",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get orders with detected discrepancies."""
    query = select(Order).options(joinedload(Order.fills)).where(
        Order.portfolio_id == portfolio_id
    )

    if date_from:
        query = query.where(Order.date >= date_from)
    if date_to:
        query = query.where(Order.date <= date_to)

    query = query.order_by(desc(Order.date), desc(Order.created_at))

    result = await db.execute(query)
    orders = result.unique().scalars().all()

    # Build audit records and filter to those with discrepancies
    records_with_discrepancies = []
    for order in orders:
        record = await build_audit_record(order, db)
        if record.discrepancies:
            # Filter by severity if specified
            if severity:
                matching = [d for d in record.discrepancies if d.severity == severity]
                if not matching:
                    continue
            records_with_discrepancies.append(record)
            if len(records_with_discrepancies) >= limit:
                break

    return records_with_discrepancies
