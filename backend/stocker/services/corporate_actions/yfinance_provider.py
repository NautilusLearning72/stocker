import hashlib
import logging
import time
from datetime import date
from typing import Any, Optional

import yfinance as yf

from stocker.core.config import settings
from stocker.services.corporate_actions.base import CorporateActionsProvider

logger = logging.getLogger(__name__)


class YFinanceCorporateActionsProvider(CorporateActionsProvider):
    """yfinance provider for splits and dividends."""

    def fetch_corporate_actions(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        if not symbols:
            return []

        records: list[dict[str, Any]] = []
        for symbol in symbols:
            actions = self._fetch_actions_with_retry(symbol)
            if actions is None or actions.empty:
                continue

            for action_date, row in actions.iterrows():
                action_day = _to_date(action_date)
                if action_day is None:
                    continue
                if action_day < start_date or action_day > end_date:
                    continue

                dividend = _num(row.get("Dividends"))
                split = _num(row.get("Stock Splits"))

                if dividend and dividend > 0:
                    records.append(
                        _build_record(
                            symbol,
                            action_day,
                            "DIVIDEND",
                            dividend,
                        )
                    )
                if split and split > 0:
                    records.append(
                        _build_record(
                            symbol,
                            action_day,
                            "SPLIT",
                            split,
                        )
                    )

        return records

    def _fetch_actions_with_retry(self, symbol: str) -> Optional[Any]:
        max_retries = max(1, settings.CORP_ACTIONS_MAX_RETRIES)
        backoff = max(0.0, settings.CORP_ACTIONS_RETRY_BACKOFF_SEC)
        ticker = yf.Ticker(symbol)

        for attempt in range(1, max_retries + 1):
            try:
                actions = ticker.actions
                if actions is None or actions.empty:
                    logger.info("yfinance returned empty actions for %s", symbol)
                    return None
                return actions
            except Exception as exc:
                logger.warning(
                    "yfinance actions fetch failed for %s (attempt %s/%s): %s",
                    symbol,
                    attempt,
                    max_retries,
                    exc,
                )

            if attempt < max_retries and backoff:
                sleep_for = backoff * (2 ** (attempt - 1))
                time.sleep(sleep_for)

        return None


def _build_record(symbol: str, action_day: date, action_type: str, value: float) -> dict[str, Any]:
    payload = f"{symbol}|{action_type}|{action_day.isoformat()}|{value}"
    return {
        "symbol": symbol,
        "date": action_day,
        "action_type": action_type,
        "value": value,
        "source": "yfinance",
        "source_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    from datetime import datetime as _dt

    if isinstance(value, _dt):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return value.to_pydatetime().date()
    except Exception:
        return None
