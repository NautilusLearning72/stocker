from datetime import date, datetime
import logging
import math
import time
from typing import Any, Optional

import yfinance as yf

from stocker.core.config import settings
from stocker.services.fundamentals.base import FundamentalsProvider

logger = logging.getLogger(__name__)


class YFinanceFundamentalsProvider(FundamentalsProvider):
    """yfinance provider for investor-facing fundamentals and valuation metrics."""

    def fetch_instrument_metrics(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not symbols:
            return [], []

        metrics_records: list[dict[str, Any]] = []
        info_records: list[dict[str, Any]] = []
        for symbol in symbols:
            info = self._fetch_info_with_retry(symbol)
            if info is None:
                continue

            if not info:
                logger.warning("yfinance returned no info for %s", symbol)
                continue

            record = self._map_info(symbol, as_of_date, info)
            if record:
                metrics_records.append(record)

            info_record = self._map_instrument_info(symbol, info)
            if info_record:
                info_records.append(info_record)

        return metrics_records, info_records

    def _fetch_info_with_retry(self, symbol: str) -> Optional[dict[str, Any]]:
        max_retries = max(1, settings.FUNDAMENTALS_MAX_RETRIES)
        backoff = max(0.0, settings.FUNDAMENTALS_RETRY_BACKOFF_SEC)
        ticker = yf.Ticker(symbol)

        for attempt in range(1, max_retries + 1):
            try:
                info = ticker.get_info()
                if info:
                    return info
                logger.warning(
                    "yfinance returned empty info for %s (attempt %s/%s)",
                    symbol,
                    attempt,
                    max_retries,
                )
            except Exception as exc:
                logger.warning(
                    "yfinance metrics fetch failed for %s (attempt %s/%s): %s",
                    symbol,
                    attempt,
                    max_retries,
                    exc,
                )

            if attempt < max_retries and backoff:
                sleep_for = backoff * (2 ** (attempt - 1))
                time.sleep(sleep_for)

        return None

    def _map_info(
        self,
        symbol: str,
        as_of_date: date,
        info: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        market_cap = _num(info.get("marketCap"))
        enterprise_value = _num(info.get("enterpriseValue"))
        free_cash_flow = _num(info.get("freeCashflow"))

        record: dict[str, Any] = {
            "symbol": symbol,
            "as_of_date": as_of_date,
            "period_type": "TTM",
            "period_end": _to_date(
                info.get("mostRecentQuarter") or info.get("lastFiscalYearEnd")
            ),
            "source": "yfinance",
            "currency": info.get("financialCurrency") or info.get("currency") or "USD",
            "market_cap": market_cap,
            "enterprise_value": enterprise_value,
            "shares_outstanding": _to_int(
                info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            ),
            "float_shares": _to_int(info.get("floatShares")),
            "beta": _num(info.get("beta")),
            "pe_ttm": _num(info.get("trailingPE")),
            "pe_forward": _num(info.get("forwardPE")),
            "price_to_book": _num(info.get("priceToBook")),
            "price_to_sales": _num(info.get("priceToSalesTrailing12Months")),
            "peg_ratio": _num(info.get("pegRatio")),
            "ev_to_ebitda": _num(info.get("enterpriseToEbitda")),
            "ev_to_ebit": _safe_ev_to_ebit(enterprise_value, _num(info.get("ebit"))),
            "fcf_yield": _safe_yield(free_cash_flow, market_cap),
            "dividend_yield": _num(info.get("dividendYield")),
            "dividend_rate": _num(info.get("dividendRate")),
            "payout_ratio": _num(info.get("payoutRatio")),
            "revenue": _num(info.get("totalRevenue")),
            "ebitda": _num(info.get("ebitda")),
            "net_income": _num(info.get("netIncomeToCommon") or info.get("netIncome")),
            "free_cash_flow": free_cash_flow,
            "gross_margin": _num(info.get("grossMargins")),
            "operating_margin": _num(info.get("operatingMargins")),
            "net_margin": _num(info.get("profitMargins")),
            "ebitda_margin": _num(info.get("ebitdaMargins")),
            "roe": _num(info.get("returnOnEquity")),
            "roa": _num(info.get("returnOnAssets")),
            "roic": _num(info.get("returnOnCapital") or info.get("returnOnInvestedCapital")),
            "revenue_growth_yoy": _num(info.get("revenueGrowth")),
            "earnings_growth_yoy": _num(info.get("earningsGrowth")),
            "eps_growth_yoy": _num(info.get("earningsQuarterlyGrowth")),
            "fcf_growth_yoy": None,
            "debt_to_equity": _num(info.get("debtToEquity")),
            "net_debt_to_ebitda": _num(
                info.get("netDebtToEBITDA") or info.get("netDebtToEbitda")
            ),
            "interest_coverage": _num(info.get("interestCoverage")),
            "current_ratio": _num(info.get("currentRatio")),
            "quick_ratio": _num(info.get("quickRatio")),
        }

        metric_values = [
            record["market_cap"],
            record["enterprise_value"],
            record["pe_ttm"],
            record["price_to_book"],
            record["revenue"],
            record["net_income"],
        ]
        if all(value is None for value in metric_values):
            return None

        return record

    def _map_instrument_info(self, symbol: str, info: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            return {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName"),
                "asset_class": "US_EQUITY",
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency") or info.get("financialCurrency") or "USD",
                "active": True,
            }
        except Exception as exc:
            logger.warning("Failed to map instrument info for %s: %s", symbol, exc)
            return None


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.utcfromtimestamp(float(value)).date()
    except (TypeError, ValueError, OSError):
        return None


def _safe_yield(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _safe_ev_to_ebit(
    enterprise_value: Optional[float],
    ebit: Optional[float],
) -> Optional[float]:
    if enterprise_value is None or ebit in (None, 0):
        return None
    return enterprise_value / ebit
