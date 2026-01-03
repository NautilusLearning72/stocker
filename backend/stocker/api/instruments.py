from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.core.database import get_db
from stocker.models.daily_bar import DailyBar
from stocker.models.instrument_info import InstrumentInfo
from stocker.models.instrument_metrics import InstrumentMetrics
from stocker.models.market_sentiment import MarketSentiment

router = APIRouter()


# --- Response Schemas ---


class InstrumentInfoResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None

    class Config:
        from_attributes = True


class InstrumentMetricsResponse(BaseModel):
    as_of_date: date
    period_type: str
    # Market & valuation
    market_cap: Optional[Decimal] = None
    enterprise_value: Optional[Decimal] = None
    shares_outstanding: Optional[int] = None
    beta: Optional[Decimal] = None
    # Valuation ratios
    pe_ttm: Optional[Decimal] = None
    pe_forward: Optional[Decimal] = None
    price_to_book: Optional[Decimal] = None
    price_to_sales: Optional[Decimal] = None
    peg_ratio: Optional[Decimal] = None
    ev_to_ebitda: Optional[Decimal] = None
    fcf_yield: Optional[Decimal] = None
    dividend_yield: Optional[Decimal] = None
    # Profitability
    gross_margin: Optional[Decimal] = None
    operating_margin: Optional[Decimal] = None
    net_margin: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    roa: Optional[Decimal] = None
    roic: Optional[Decimal] = None
    # Growth
    revenue_growth_yoy: Optional[Decimal] = None
    earnings_growth_yoy: Optional[Decimal] = None
    eps_growth_yoy: Optional[Decimal] = None
    # Leverage
    debt_to_equity: Optional[Decimal] = None
    net_debt_to_ebitda: Optional[Decimal] = None
    current_ratio: Optional[Decimal] = None
    quick_ratio: Optional[Decimal] = None

    class Config:
        from_attributes = True


class SymbolDetailResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_class: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    active: bool = True
    metrics: Optional[InstrumentMetricsResponse] = None


class DailyPriceResponse(BaseModel):
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adj_close: Decimal
    volume: int

    class Config:
        from_attributes = True


class SentimentResponse(BaseModel):
    date: date
    sentiment_score: Decimal
    sentiment_magnitude: Optional[Decimal] = None
    article_count: Optional[int] = None
    positive_count: Optional[int] = None
    neutral_count: Optional[int] = None
    negative_count: Optional[int] = None

    class Config:
        from_attributes = True


class SearchResultResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[InstrumentInfoResponse])
async def get_instruments(
    symbols: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    if not symbols:
        return []

    stmt = (
        select(InstrumentInfo)
        .where(InstrumentInfo.symbol.in_(symbols))
        .order_by(InstrumentInfo.symbol.asc())
    )
    result = await db.execute(stmt)
    instruments = result.scalars().all()

    # Ensure symbols with no info still return at least symbol
    found = {inst.symbol for inst in instruments}
    missing = [s for s in symbols if s not in found]
    for sym in missing:
        instruments.append(
            InstrumentInfo(
                symbol=sym,
                name=None,
                sector=None,
                industry=None,
                exchange=None,
                currency=None,
            )
        )
    return instruments


@router.get("/search", response_model=list[SearchResultResponse])
async def search_instruments(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search instruments by symbol or name (case-insensitive)."""
    search_pattern = f"%{q.upper()}%"

    stmt = (
        select(InstrumentInfo)
        .where(
            or_(
                func.upper(InstrumentInfo.symbol).like(search_pattern),
                func.upper(InstrumentInfo.name).like(search_pattern),
            )
        )
        .order_by(
            # Prioritize exact symbol matches, then prefix matches
            func.upper(InstrumentInfo.symbol) == q.upper(),
            func.upper(InstrumentInfo.symbol).like(f"{q.upper()}%"),
            InstrumentInfo.symbol,
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{symbol}", response_model=SymbolDetailResponse)
async def get_symbol_detail(
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information for a specific symbol including latest metrics."""
    symbol = symbol.upper()

    # Get instrument info
    stmt = select(InstrumentInfo).where(InstrumentInfo.symbol == symbol)
    result = await db.execute(stmt)
    info = result.scalar_one_or_none()

    # Get latest metrics
    metrics_stmt = (
        select(InstrumentMetrics)
        .where(InstrumentMetrics.symbol == symbol)
        .order_by(InstrumentMetrics.as_of_date.desc())
        .limit(1)
    )
    metrics_result = await db.execute(metrics_stmt)
    metrics = metrics_result.scalar_one_or_none()

    if not info and not metrics:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")

    return SymbolDetailResponse(
        symbol=symbol,
        name=info.name if info else None,
        asset_class=info.asset_class if info else None,
        sector=info.sector if info else None,
        industry=info.industry if info else None,
        exchange=info.exchange if info else None,
        currency=info.currency if info else None,
        active=info.active if info else True,
        metrics=InstrumentMetricsResponse.model_validate(metrics) if metrics else None,
    )


@router.get("/{symbol}/prices", response_model=list[DailyPriceResponse])
async def get_symbol_prices(
    symbol: str,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get daily price history for a symbol."""
    symbol = symbol.upper()
    cutoff_date = date.today() - timedelta(days=days)

    stmt = (
        select(DailyBar)
        .where(DailyBar.symbol == symbol, DailyBar.date >= cutoff_date)
        .order_by(DailyBar.date.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{symbol}/sentiment", response_model=list[SentimentResponse])
async def get_symbol_sentiment(
    symbol: str,
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get sentiment history for a symbol."""
    symbol = symbol.upper()
    cutoff_date = date.today() - timedelta(days=days)

    stmt = (
        select(MarketSentiment)
        .where(MarketSentiment.symbol == symbol, MarketSentiment.date >= cutoff_date)
        .order_by(MarketSentiment.date.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# --- Validation Schemas ---


class SymbolValidationRequest(BaseModel):
    symbols: list[str]


class SymbolValidationResponse(BaseModel):
    valid: list[str]
    invalid: list[str]


@router.post("/validate", response_model=SymbolValidationResponse)
async def validate_symbols(payload: SymbolValidationRequest):
    """
    Validate that symbols exist via yfinance ticker info.
    
    This uses yf.Ticker().info which is more reliable than price downloads
    for validating symbol existence, especially for international tickers
    that may not have recent price data in the default period.
    
    Returns lists of valid and invalid symbols.
    """
    import yfinance as yf
    import logging
    
    logger = logging.getLogger(__name__)

    symbols = [s.upper().strip() for s in payload.symbols if s.strip()]
    if not symbols:
        return SymbolValidationResponse(valid=[], invalid=[])

    valid_symbols: list[str] = []
    invalid_symbols: list[str] = []

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            # Use .info which returns company metadata
            # Valid tickers have meaningful info like 'shortName' or 'symbol'
            info = ticker.info
            
            # Check for indicators that the ticker is valid
            # Invalid/delisted tickers return empty dict or dict with only 'trailingPegRatio'
            if info and (
                info.get('shortName') or 
                info.get('longName') or 
                (info.get('symbol') and info.get('symbol') == sym) or
                info.get('regularMarketPrice') is not None or
                info.get('previousClose') is not None
            ):
                valid_symbols.append(sym)
                logger.debug(f"Symbol {sym} validated successfully")
            else:
                invalid_symbols.append(sym)
                logger.debug(f"Symbol {sym} appears invalid - no meaningful info returned")
        except Exception as e:
            # Any exception means we couldn't validate the symbol
            logger.debug(f"Symbol {sym} validation failed: {e}")
            invalid_symbols.append(sym)

    return SymbolValidationResponse(valid=valid_symbols, invalid=invalid_symbols)

