import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from alpaca.common.enums import Sort
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.models.fill import Fill
from stocker.models.holding import Holding
from stocker.models.order import Order
from stocker.models.portfolio_state import PortfolioState
from stocker.models.position_snapshot import PositionSnapshot

logger = logging.getLogger(__name__)


class PortfolioSyncService:
    def __init__(self) -> None:
        base_url = self._normalize_base_url(settings.ALPACA_BASE_URL)
        self.client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=(settings.BROKER_MODE == "paper"),
            url_override=base_url,
        )

    async def sync_portfolio(self, portfolio_id: str = "main") -> dict[str, Any]:
        if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
            raise ValueError("Alpaca credentials are not configured.")

        lookback_start = datetime.utcnow() - timedelta(days=settings.PORTFOLIO_SYNC_LOOKBACK_DAYS)
        orders = self._fetch_orders(lookback_start)
        positions = self.client.get_all_positions()
        account = self.client.get_account()
        activities = await self._fetch_fill_activities(lookback_start)

        return await self._sync_db(
            portfolio_id=portfolio_id,
            account=account,
            positions=positions,
            orders=orders,
            activities=activities,
        )

    def _fetch_orders(self, after: datetime) -> list[Any]:
        request = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=settings.PORTFOLIO_SYNC_ORDER_LIMIT,
            after=after,
            direction=Sort.DESC,
            nested=True,
        )
        return list(self.client.get_orders(request))

    async def _fetch_fill_activities(self, after: datetime) -> list[dict[str, Any]]:
        base_url = self._normalize_base_url(settings.ALPACA_BASE_URL)
        url = self._build_activities_url(base_url)
        headers = {
            "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
        }
        params: dict[str, Any] = {
            "activity_types": "FILL",
            "after": after.date().isoformat(),
            "direction": "desc",
            "page_size": 100,
        }

        activities: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for _ in range(10):
                response = await client.get(url, headers=headers, params=params)
                if response.status_code == 404:
                    logger.warning("Alpaca activities endpoint not found at %s", url)
                    return []
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list) or not data:
                    break
                activities.extend(data)
                next_token = (
                    response.headers.get("next_page_token")
                    or response.headers.get("Next-Page-Token")
                    or response.headers.get("X-Next-Page-Token")
                )
                if not next_token or len(data) < params["page_size"]:
                    break
                params["page_token"] = next_token
        return activities

    def _build_activities_url(self, base_url: str) -> str:
        if base_url.endswith("/v2"):
            return f"{base_url}/account/activities"
        return f"{base_url}/v2/account/activities"

    def _normalize_base_url(self, base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v2"):
            return normalized[:-3]
        return normalized

    async def _sync_db(
        self,
        portfolio_id: str,
        account: Any,
        positions: list[Any],
        orders: list[Any],
        activities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        orders_created = 0
        orders_updated = 0
        fills_created = 0
        holdings_refreshed = 0
        portfolio_state_updated = False
        today = date.today()

        async with AsyncSessionLocal() as session:
            try:
                broker_ids = [str(order.id) for order in orders if getattr(order, "id", None)]
                existing_orders: dict[str, Order] = {}
                if broker_ids:
                    result = await session.execute(
                        select(Order).where(Order.broker_order_id.in_(broker_ids))
                    )
                    existing_orders = {order.broker_order_id: order for order in result.scalars()}

                for alpaca_order in orders:
                    broker_id = str(alpaca_order.id)
                    order_record = existing_orders.get(broker_id)
                    if order_record:
                        self._apply_alpaca_order(order_record, alpaca_order, portfolio_id)
                        orders_updated += 1
                    else:
                        order_record = self._build_order_from_alpaca(
                            alpaca_order, portfolio_id=portfolio_id
                        )
                        session.add(order_record)
                        existing_orders[broker_id] = order_record
                        orders_created += 1

                await session.execute(
                    delete(Holding).where(
                        Holding.portfolio_id == portfolio_id,
                        Holding.date == today,
                    )
                )
                for position in positions:
                    qty = _signed_qty(position)
                    holding = Holding(
                        portfolio_id=portfolio_id,
                        date=today,
                        symbol=str(position.symbol),
                        qty=qty,
                        cost_basis=_to_float(position.avg_entry_price),
                        market_value=_to_float(position.market_value),
                    )
                    session.add(holding)
                holdings_refreshed = len(positions)

                await session.execute(
                    delete(PositionSnapshot).where(
                        PositionSnapshot.portfolio_id == portfolio_id,
                        PositionSnapshot.date == today,
                        PositionSnapshot.source == "alpaca",
                    )
                )
                snapshot_records: list[dict[str, Any]] = []
                as_of_ts = datetime.utcnow()
                for position in positions:
                    signed_qty = _signed_qty(position)
                    side_value = _enum_value(position.side)
                    if side_value:
                        side_value = side_value.upper()
                    if not side_value or side_value not in {"LONG", "SHORT"}:
                        side_value = "SHORT" if signed_qty < 0 else "LONG"
                    snapshot_records.append(
                        {
                            "portfolio_id": portfolio_id,
                            "date": today,
                            "symbol": str(position.symbol),
                            "side": side_value,
                            "qty": signed_qty,
                            "avg_entry_price": _to_optional_float(position.avg_entry_price),
                            "cost_basis": _to_optional_float(position.cost_basis),
                            "market_value": _to_optional_float(position.market_value),
                            "current_price": _to_optional_float(position.current_price),
                            "lastday_price": _to_optional_float(position.lastday_price),
                            "change_today": _to_optional_float(position.change_today),
                            "unrealized_pl": _to_optional_float(position.unrealized_pl),
                            "unrealized_plpc": _to_optional_float(position.unrealized_plpc),
                            "unrealized_intraday_pl": _to_optional_float(
                                position.unrealized_intraday_pl
                            ),
                            "unrealized_intraday_plpc": _to_optional_float(
                                position.unrealized_intraday_plpc
                            ),
                            "asset_class": _enum_value(position.asset_class),
                            "exchange": _enum_value(position.exchange),
                            "source": "alpaca",
                            "as_of_ts": as_of_ts,
                        }
                    )
                if snapshot_records:
                    stmt = insert(PositionSnapshot).values(snapshot_records)
                    await session.execute(stmt)

                nav = _to_float(getattr(account, "equity", None)) or _to_float(
                    getattr(account, "portfolio_value", None)
                )
                cash = _to_float(getattr(account, "cash", None))
                unrealized_pnl = sum(_to_float(pos.unrealized_pl) for pos in positions)
                realized_pnl = 0.0
                last_equity = _to_float(getattr(account, "last_equity", None))
                if last_equity:
                    realized_pnl = nav - last_equity - unrealized_pnl

                gross_value = sum(abs(_to_float(pos.market_value)) for pos in positions)
                net_value = sum(_to_float(pos.market_value) for pos in positions)
                gross_exposure = gross_value / nav if nav else 0.0
                net_exposure = net_value / nav if nav else 0.0

                latest_state_result = await session.execute(
                    select(PortfolioState)
                    .where(PortfolioState.portfolio_id == portfolio_id)
                    .order_by(PortfolioState.date.desc())
                    .limit(1)
                )
                latest_state = latest_state_result.scalar_one_or_none()
                previous_hwm = _to_float(latest_state.high_water_mark) if latest_state else nav
                high_water_mark = max(previous_hwm, nav)
                drawdown = (high_water_mark - nav) / high_water_mark if high_water_mark else 0.0

                state_result = await session.execute(
                    select(PortfolioState).where(
                        PortfolioState.portfolio_id == portfolio_id,
                        PortfolioState.date == today,
                    )
                )
                state = state_result.scalar_one_or_none()
                if state:
                    state.nav = nav
                    state.cash = cash
                    state.gross_exposure = gross_exposure
                    state.net_exposure = net_exposure
                    state.realized_pnl = realized_pnl
                    state.unrealized_pnl = unrealized_pnl
                    state.drawdown = drawdown
                    state.high_water_mark = high_water_mark
                else:
                    session.add(
                        PortfolioState(
                            portfolio_id=portfolio_id,
                            date=today,
                            nav=nav,
                            cash=cash,
                            gross_exposure=gross_exposure,
                            net_exposure=net_exposure,
                            realized_pnl=realized_pnl,
                            unrealized_pnl=unrealized_pnl,
                            drawdown=drawdown,
                            high_water_mark=high_water_mark,
                        )
                    )
                portfolio_state_updated = True

                fill_ids = [self._activity_fill_id(act) for act in activities]
                fill_ids = [fill_id for fill_id in fill_ids if fill_id]
                existing_fill_ids: set[str] = set()
                if fill_ids:
                    fill_result = await session.execute(
                        select(Fill.fill_id).where(Fill.fill_id.in_(fill_ids))
                    )
                    existing_fill_ids = set(fill_result.scalars())

                order_ids_to_check = [
                    order.order_id
                    for order in existing_orders.values()
                    if order.order_id is not None
                ]
                existing_fill_orders: set[uuid.UUID] = set()
                if order_ids_to_check:
                    order_fill_result = await session.execute(
                        select(Fill.order_id).where(Fill.order_id.in_(order_ids_to_check))
                    )
                    existing_fill_orders = set(order_fill_result.scalars())

                for activity in activities:
                    fill_id = self._activity_fill_id(activity)
                    if not fill_id or fill_id in existing_fill_ids:
                        continue
                    broker_order_id = activity.get("order_id")
                    if not broker_order_id:
                        continue
                    order_record = existing_orders.get(broker_order_id)
                    if not order_record:
                        order_record = self._build_order_from_activity(
                            activity, portfolio_id=portfolio_id
                        )
                        session.add(order_record)
                        existing_orders[broker_order_id] = order_record
                        orders_created += 1

                    if order_record.order_id in existing_fill_orders:
                        continue

                    fill = Fill(
                        fill_id=fill_id,
                        order_id=order_record.order_id,
                        date=self._activity_timestamp(activity),
                        symbol=str(activity.get("symbol") or order_record.symbol or ""),
                        side=str(activity.get("side") or order_record.side or "").upper(),
                        qty=_to_float(activity.get("qty")),
                        price=_to_float(activity.get("price")),
                        commission=0.0,
                        exchange="ALPACA",
                    )
                    session.add(fill)
                    existing_fill_ids.add(fill_id)
                    existing_fill_orders.add(order_record.order_id)
                    fills_created += 1

                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.exception("Portfolio sync failed: %s", exc)
                raise

        return {
            "portfolio_id": portfolio_id,
            "orders_created": orders_created,
            "orders_updated": orders_updated,
            "fills_created": fills_created,
            "holdings_refreshed": holdings_refreshed,
            "portfolio_state_updated": portfolio_state_updated,
            "synced_at": datetime.utcnow().isoformat(),
        }

    def _apply_alpaca_order(self, order: Order, alpaca_order: Any, portfolio_id: str) -> None:
        order.portfolio_id = portfolio_id
        if getattr(alpaca_order, "symbol", None):
            order.symbol = str(alpaca_order.symbol)
        side = _normalize_side(alpaca_order.side)
        if side:
            order.side = side
        qty = _to_float(getattr(alpaca_order, "qty", None)) or _to_float(
            getattr(alpaca_order, "filled_qty", None)
        )
        if qty:
            order.qty = qty
        order.type = _normalize_order_type(alpaca_order)
        order.status = _map_order_status(alpaca_order.status)
        order.broker_order_id = str(alpaca_order.id)
        order.date = _coerce_date(
            getattr(alpaca_order, "submitted_at", None)
            or getattr(alpaca_order, "created_at", None)
            or getattr(alpaca_order, "filled_at", None)
        )

    def _build_order_from_alpaca(self, alpaca_order: Any, portfolio_id: str) -> Order:
        qty = _to_float(getattr(alpaca_order, "qty", None)) or _to_float(
            getattr(alpaca_order, "filled_qty", None)
        )
        return Order(
            order_id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            date=_coerce_date(
                getattr(alpaca_order, "submitted_at", None)
                or getattr(alpaca_order, "created_at", None)
                or getattr(alpaca_order, "filled_at", None)
            ),
            symbol=str(getattr(alpaca_order, "symbol", "")),
            side=_normalize_side(getattr(alpaca_order, "side", None)),
            qty=qty,
            type=_normalize_order_type(alpaca_order),
            status=_map_order_status(getattr(alpaca_order, "status", "")),
            broker_order_id=str(alpaca_order.id),
        )

    def _build_order_from_activity(self, activity: dict[str, Any], portfolio_id: str) -> Order:
        status = "FILLED" if activity.get("activity_type") == "FILL" else "PENDING_EXECUTION"
        return Order(
            order_id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            date=_coerce_date(self._activity_timestamp(activity)),
            symbol=str(activity.get("symbol") or ""),
            side=str(activity.get("side") or "").upper(),
            qty=_to_float(activity.get("cum_qty") or activity.get("qty")),
            type="MARKET",
            status=status,
            broker_order_id=str(activity.get("order_id")),
        )

    def _activity_timestamp(self, activity: dict[str, Any]) -> datetime:
        for key in ("transaction_time", "timestamp", "date", "created_at"):
            value = activity.get(key)
            parsed = _parse_datetime(value)
            if parsed:
                return parsed
        return datetime.utcnow()

    def _activity_fill_id(self, activity: dict[str, Any]) -> str:
        activity_id = activity.get("id")
        if not activity_id:
            return ""
        return f"alpaca:{activity_id}"


def _normalize_side(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value).upper()
    return str(value).upper()


def _normalize_order_type(order: Any) -> str:
    order_type = getattr(order, "order_type", None) or getattr(order, "type", None)
    if order_type is None:
        return "MARKET"
    if hasattr(order_type, "value"):
        return str(order_type.value).upper()
    return str(order_type).upper()


def _map_order_status(value: Any) -> str:
    status = str(value).upper() if value is not None else ""
    pending = {
        "NEW",
        "ACCEPTED",
        "PENDING_NEW",
        "PENDING_CANCEL",
        "PENDING_REPLACE",
        "ACCEPTED_FOR_BIDDING",
        "HELD",
        "STOPPED",
        "PARTIALLY_FILLED",
    }
    if status in pending:
        return "PENDING_EXECUTION"
    if status in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}:
        return "FAILED"
    if status == "FILLED":
        return "FILLED"
    return status or "NEW"


def _coerce_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else date.today()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _signed_qty(position: Any) -> float:
    qty = _to_float(getattr(position, "qty", None))
    side = str(getattr(position, "side", "")).lower()
    return -qty if side == "short" else qty
