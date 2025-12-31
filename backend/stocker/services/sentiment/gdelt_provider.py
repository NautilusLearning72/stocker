import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from stocker.core.config import settings
from stocker.services.sentiment.base import SentimentProvider

logger = logging.getLogger(__name__)


class GdeltSentimentProvider(SentimentProvider):
    """Sentiment provider using GDELT Doc API ToneChart."""

    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(
        self,
        max_retries: int | None = None,
        backoff_sec: float | None = None,
        request_delay_sec: float | None = None,
        timeout_sec: float | None = None,
        max_concurrency: int | None = None,
        rate_limit_per_sec: float | None = None,
    ) -> None:
        self.max_retries = (
            settings.SENTIMENT_MAX_RETRIES if max_retries is None else max_retries
        )
        self.backoff_sec = (
            settings.SENTIMENT_RETRY_BACKOFF_SEC if backoff_sec is None else backoff_sec
        )
        self.request_delay_sec = (
            settings.SENTIMENT_REQUEST_DELAY_SEC
            if request_delay_sec is None
            else request_delay_sec
        )
        self.timeout_sec = (
            settings.SENTIMENT_REQUEST_TIMEOUT_SEC if timeout_sec is None else timeout_sec
        )
        self.max_concurrency = (
            settings.SENTIMENT_MAX_CONCURRENCY
            if max_concurrency is None
            else max_concurrency
        )
        self.rate_limit_per_sec = (
            settings.SENTIMENT_RATE_LIMIT_PER_SEC
            if rate_limit_per_sec is None
            else rate_limit_per_sec
        )

    async def fetch_market_sentiment(
        self,
        symbols: list[str],
        as_of_date: date,
        window_days: int,
        period: str,
        symbol_names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if not symbols:
            return []

        end_dt = datetime(
            as_of_date.year,
            as_of_date.month,
            as_of_date.day,
            23,
            59,
            59,
            tzinfo=timezone.utc,
        )
        start_dt = end_dt - timedelta(days=max(window_days - 1, 0))
        start_str = start_dt.strftime("%Y%m%d%H%M%S")
        end_str = end_dt.strftime("%Y%m%d%H%M%S")

        records: list[dict[str, Any]] = []
        limiter = _RateLimiter(self._min_delay_seconds())
        concurrency = max(self.max_concurrency or 1, 1)
        limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

        async with httpx.AsyncClient(timeout=self.timeout_sec, limits=limits) as client:
            gate = _AsyncGate(concurrency)

            async def fetch_symbol(symbol: str) -> dict[str, Any] | None:
                async with gate:
                    await limiter.wait()
                    query = self._build_query(symbol, (symbol_names or {}).get(symbol))
                    params = {
                        "query": query,
                        "mode": "ToneChart",
                        "format": "json",
                        "startdatetime": start_str,
                        "enddatetime": end_str,
                    }
                    response_text = await self._fetch_with_retry(client, params, symbol)
                    if not response_text:
                        return None
                    data = self._safe_json(response_text)
                    if not data:
                        return None
                    tonechart = data.get("tonechart") or []
                    aggregate = self._aggregate_tonechart(tonechart)
                    if not aggregate:
                        return None
                    avg_tone, avg_magnitude, total, pos, neu, neg = aggregate
                    score, magnitude = self._normalize(avg_tone, avg_magnitude)

                    return {
                        "symbol": symbol,
                        "date": as_of_date,
                        "source": "gdelt",
                        "period": period,
                        "window_days": window_days,
                        "sentiment_score": score,
                        "sentiment_magnitude": magnitude,
                        "article_count": total,
                        "positive_count": pos,
                        "neutral_count": neu,
                        "negative_count": neg,
                        "source_hash": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
                    }

            import asyncio

            results = await asyncio.gather(*[fetch_symbol(symbol) for symbol in symbols])

        for row in results:
            if row:
                records.append(row)

        return records

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient, params: dict[str, str], symbol: str
    ) -> str | None:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                return resp.text
            except Exception as exc:
                if attempt >= self.max_retries:
                    logger.warning("GDELT sentiment fetch failed for %s: %s", symbol, exc)
                    return None
                await _sleep_with_backoff(self.backoff_sec, attempt)
        return None

    def _safe_json(self, response_text: str) -> dict[str, Any] | None:
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return None

    def _aggregate_tonechart(
        self, tonechart: list[dict[str, Any]]
    ) -> tuple[float, float, int, int, int, int] | None:
        total = 0
        weighted = 0.0
        weighted_abs = 0.0
        pos = 0
        neg = 0
        neu = 0

        for row in tonechart:
            count = int(row.get("count") or row.get("volume") or 0)
            if count <= 0:
                continue
            tone_raw = row.get("bin")
            if tone_raw is None:
                tone_raw = row.get("tone") or row.get("avg") or row.get("avgTone")
            if tone_raw is None:
                continue
            try:
                tone_val = float(tone_raw)
            except (TypeError, ValueError):
                continue

            total += count
            weighted += tone_val * count
            weighted_abs += abs(tone_val) * count
            if tone_val > 0:
                pos += count
            elif tone_val < 0:
                neg += count
            else:
                neu += count

        if total == 0:
            return None
        return weighted / total, weighted_abs / total, total, pos, neu, neg

    def _normalize(self, avg_tone: float, avg_magnitude: float) -> tuple[float, float]:
        scale = 1.0 if abs(avg_tone) <= 1 and abs(avg_magnitude) <= 1 else 100.0
        score = max(min(avg_tone / scale, 1.0), -1.0)
        magnitude = max(min(avg_magnitude / scale, 1.0), 0.0)
        return score, magnitude

    def _build_query(self, symbol: str, name: str | None) -> str:
        clean_symbol = symbol.strip().upper()
        if not name:
            return clean_symbol
        cleaned_name = name.strip()
        if not cleaned_name:
            return clean_symbol
        if cleaned_name.upper() == clean_symbol:
            return clean_symbol
        return f'({clean_symbol} OR \"{cleaned_name}\")'

    def _min_delay_seconds(self) -> float:
        delay = 0.0
        if self.rate_limit_per_sec and self.rate_limit_per_sec > 0:
            delay = max(delay, 1.0 / self.rate_limit_per_sec)
        if self.request_delay_sec and self.request_delay_sec > 0:
            delay = max(delay, self.request_delay_sec)
        return delay


class _RateLimiter:
    def __init__(self, min_delay: float) -> None:
        self.min_delay = min_delay
        self._lock = None
        self._next_time = 0.0

    async def wait(self) -> None:
        if self.min_delay <= 0:
            return
        if self._lock is None:
            import asyncio

            self._lock = asyncio.Lock()
        import time

        async with self._lock:
            now = time.monotonic()
            if now < self._next_time:
                await _sleep(self._next_time - now)
            self._next_time = time.monotonic() + self.min_delay


class _AsyncGate:
    def __init__(self, max_concurrency: int) -> None:
        import asyncio

        self._sem = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> None:
        await self._sem.acquire()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()


async def _sleep(seconds: float) -> None:
    import asyncio

    if seconds > 0:
        await asyncio.sleep(seconds)


async def _sleep_with_backoff(base: float, attempt: int) -> None:
    await _sleep(base * (2 ** (attempt - 1)))
