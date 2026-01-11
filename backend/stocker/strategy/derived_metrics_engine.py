from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class DerivedMetricResult:
    symbol: str
    metrics: dict[str, float | None]


class DerivedMetricsEngine:
    """Pure computation engine for derived metrics."""

    def compute_for_symbol(
        self,
        symbol: str,
        bars: pd.DataFrame,
        instrument: dict[str, Any] | None = None,
        sentiment: pd.Series | None = None,
    ) -> DerivedMetricResult:
        if bars.empty:
            return DerivedMetricResult(symbol=symbol, metrics={})

        bars = bars.sort_index()
        metrics: dict[str, float | None] = {}

        price = self._last_value(bars.get("adj_close"))
        if price is None:
            return DerivedMetricResult(symbol=symbol, metrics={})

        returns = bars["adj_close"].pct_change()
        metrics["mom_1m"] = self._momentum(bars["adj_close"], 21)
        metrics["mom_3m"] = self._momentum(bars["adj_close"], 63)
        metrics["mom_6m"] = self._momentum(bars["adj_close"], 126)
        metrics["mom_12m"] = self._momentum(bars["adj_close"], 252)

        metrics["vol_20d"] = self._rolling_volatility(returns, 20)
        metrics["atr_14"] = self._atr(bars, 14)

        sma_50 = self._rolling_mean(bars["adj_close"], 50)
        sma_200 = self._rolling_mean(bars["adj_close"], 200)
        ema_20 = self._ema(bars["adj_close"], 20)
        metrics["sma_50"] = self._ratio_from_price(price, sma_50)
        metrics["sma_200"] = self._ratio_from_price(price, sma_200)
        metrics["ema_20"] = self._ratio_from_price(price, ema_20)

        macd = self._macd(bars["adj_close"])
        metrics["macd"] = self._ratio_from_price(price, macd)
        metrics["adx"] = self._adx(bars, 14)
        metrics["rsi_14"] = self._rsi(bars["adj_close"], 14)
        stoch_k, stoch_d = self._stochastic(bars, 14, 3)
        metrics["stoch_k"] = stoch_k
        metrics["stoch_d"] = stoch_d

        vwap_20 = self._vwap(bars, 20)
        metrics["vwap_20"] = self._ratio_from_price(price, vwap_20)
        metrics["obv"] = self._obv_change(bars, 20)

        if instrument:
            metrics.update(self._fundamental_metrics(instrument))
        if sentiment is not None:
            metrics.update(self._sentiment_metrics(sentiment))

        metrics.update(self._cross_domain_metrics(metrics))

        return DerivedMetricResult(symbol=symbol, metrics=metrics)

    def _last_value(self, series: pd.Series | None) -> float | None:
        if series is None or series.empty:
            return None
        value = series.iloc[-1]
        if pd.isna(value):
            return None
        return float(value)

    def _momentum(self, series: pd.Series, periods: int) -> float | None:
        if len(series) <= periods:
            return None
        base = series.iloc[-periods - 1]
        current = series.iloc[-1]
        if pd.isna(base) or base == 0:
            return None
        return float(current / base - 1)

    def _rolling_mean(self, series: pd.Series, window: int) -> float | None:
        if len(series) < window:
            return None
        value = series.rolling(window).mean().iloc[-1]
        return None if pd.isna(value) else float(value)

    def _ema(self, series: pd.Series, span: int) -> float | None:
        if len(series) < span:
            return None
        value = series.ewm(span=span, adjust=False).mean().iloc[-1]
        return None if pd.isna(value) else float(value)

    def _rolling_volatility(self, returns: pd.Series, window: int) -> float | None:
        if len(returns) < window:
            return None
        vol = returns.rolling(window).std(ddof=0).iloc[-1]
        if pd.isna(vol):
            return None
        return float(vol * np.sqrt(252))

    def _atr(self, bars: pd.DataFrame, window: int) -> float | None:
        if len(bars) < window + 1:
            return None
        high = bars["high"].astype(float)
        low = bars["low"].astype(float)
        close = bars["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]
        return None if pd.isna(atr) else float(atr)

    def _macd(self, series: pd.Series) -> float | None:
        if len(series) < 26:
            return None
        ema_fast = series.ewm(span=12, adjust=False).mean()
        ema_slow = series.ewm(span=26, adjust=False).mean()
        value = (ema_fast - ema_slow).iloc[-1]
        return None if pd.isna(value) else float(value)

    def _adx(self, bars: pd.DataFrame, window: int) -> float | None:
        if len(bars) < window + 1:
            return None
        high = bars["high"].astype(float)
        low = bars["low"].astype(float)
        close = bars["close"].astype(float)

        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        tr_smooth = pd.Series(tr).rolling(window).mean()
        plus_di = 100 * pd.Series(plus_dm).rolling(window).mean() / tr_smooth
        minus_di = 100 * pd.Series(minus_dm).rolling(window).mean() / tr_smooth
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan) * 100
        adx = dx.rolling(window).mean().iloc[-1]
        return None if pd.isna(adx) else float(adx)

    def _rsi(self, series: pd.Series, window: int) -> float | None:
        if len(series) < window + 1:
            return None
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window).mean()
        avg_loss = loss.rolling(window).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        value = rsi.iloc[-1]
        return None if pd.isna(value) else float(value)

    def _stochastic(
        self, bars: pd.DataFrame, window: int, smooth: int
    ) -> tuple[float | None, float | None]:
        if len(bars) < window:
            return None, None
        low_min = bars["low"].rolling(window).min()
        high_max = bars["high"].rolling(window).max()
        denom = high_max - low_min
        stoch_k = 100 * (bars["close"] - low_min) / denom.replace(0, np.nan)
        stoch_d = stoch_k.rolling(smooth).mean()
        k_val = stoch_k.iloc[-1]
        d_val = stoch_d.iloc[-1]
        return (
            None if pd.isna(k_val) else float(k_val),
            None if pd.isna(d_val) else float(d_val),
        )

    def _vwap(self, bars: pd.DataFrame, window: int) -> float | None:
        if len(bars) < window:
            return None
        typical = (bars["high"] + bars["low"] + bars["close"]) / 3
        vol = bars["volume"]
        vwap = (typical * vol).rolling(window).sum() / vol.rolling(window).sum()
        value = vwap.iloc[-1]
        return None if pd.isna(value) else float(value)

    def _obv_change(self, bars: pd.DataFrame, window: int) -> float | None:
        if len(bars) < window + 1:
            return None
        close = bars["close"]
        direction = np.sign(close.diff()).fillna(0)
        obv = (direction * bars["volume"]).cumsum()
        prev = obv.iloc[-window - 1]
        current = obv.iloc[-1]
        if prev == 0:
            return None
        return float((current - prev) / abs(prev))

    def _ratio_from_price(self, price: float | None, value: float | None) -> float | None:
        if price is None or value is None or value == 0:
            return None
        return float(price / value - 1)

    def _fundamental_metrics(self, instrument: dict[str, Any]) -> dict[str, float | None]:
        metrics: dict[str, float | None] = {}
        metrics["pe_ttm"] = instrument.get("pe_ttm")
        metrics["pe_forward"] = instrument.get("pe_forward")
        metrics["peg_ratio"] = instrument.get("peg_ratio")
        metrics["ev_to_ebitda"] = instrument.get("ev_to_ebitda")
        metrics["fcf_yield"] = instrument.get("fcf_yield")
        metrics["roe"] = instrument.get("roe")
        metrics["roic"] = instrument.get("roic")
        metrics["debt_to_equity"] = instrument.get("debt_to_equity")
        metrics["beta"] = instrument.get("beta")

        price_to_book = instrument.get("price_to_book")
        if price_to_book:
            metrics["book_to_market"] = 1 / price_to_book
        pe_ttm = instrument.get("pe_ttm")
        if pe_ttm:
            metrics["earnings_yield"] = 1 / pe_ttm
        fcf_yield = instrument.get("fcf_yield")
        if fcf_yield is not None:
            metrics["cash_flow_yield"] = fcf_yield
        gross_margin = instrument.get("gross_margin")
        if gross_margin is not None:
            metrics["gross_profitability"] = gross_margin
        debt_to_equity = instrument.get("debt_to_equity")
        if debt_to_equity is not None:
            metrics["leverage"] = debt_to_equity

        return metrics

    def _sentiment_metrics(self, sentiment: pd.Series) -> dict[str, float | None]:
        metrics: dict[str, float | None] = {}
        if sentiment.empty:
            return metrics
        latest = sentiment.iloc[-1]
        metrics["sentiment_score"] = None if pd.isna(latest) else float(latest)
        if len(sentiment) >= 2:
            prev = sentiment.iloc[-2]
            if not pd.isna(prev):
                metrics["sentiment_mom"] = float(latest - prev)
        if len(sentiment) >= 3:
            vol = sentiment.std(ddof=0)
            metrics["sentiment_vol"] = None if pd.isna(vol) else float(vol)
        return metrics

    def _cross_domain_metrics(self, metrics: dict[str, float | None]) -> dict[str, float | None]:
        cross: dict[str, float | None] = {}
        quality = metrics.get("roic") or metrics.get("roe") or metrics.get("gross_profitability")
        momentum = metrics.get("mom_6m")
        if quality is not None and momentum is not None:
            cross["quality_x_momentum"] = float(quality) * float(momentum)

        beta = metrics.get("beta")
        sentiment_score = metrics.get("sentiment_score")
        if beta is not None:
            if sentiment_score is None:
                cross["sentiment_adjusted_beta"] = float(beta)
            else:
                cross["sentiment_adjusted_beta"] = float(beta) * (1 - float(sentiment_score))

        earnings_yield = metrics.get("earnings_yield")
        vol = metrics.get("vol_20d")
        if earnings_yield is not None and vol:
            cross["risk_adjusted_value"] = float(earnings_yield) / float(vol)

        return cross
