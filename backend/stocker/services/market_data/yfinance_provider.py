import yfinance as yf
from stocker.services.market_data.base import MarketDataProvider
from datetime import date
from typing import List, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class YFinanceProvider(MarketDataProvider):
    """yfinance provider for backtesting and historical data."""

    def fetch_daily_bars(self, symbols: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()

        try:
            # yfinance expects YYYY-MM-DD strings
            # auto_adjust=False gives us valid Open/High/Low/Close and an 'Adj Close' column
            data = yf.download(
                tickers=symbols,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False
            )
        except Exception as e:
            logger.error(f"yfinance download failed: {e}")
            return pd.DataFrame()

        if data is None or data.empty:
            logger.warning("yfinance returned no data")
            return pd.DataFrame()

        # Transformation logic
        frames = []
        has_multi_index = isinstance(data.columns, pd.MultiIndex)
        if len(symbols) == 1:
            symbol = symbols[0]
            if has_multi_index:
                try:
                    df = data[symbol].copy()
                except KeyError:
                    try:
                        df = data.xs(symbol, axis=1, level=1).copy()
                    except KeyError:
                        logger.warning(f"No data for {symbol} in yfinance response")
                        return pd.DataFrame()
            else:
                df = data.copy()
            df['symbol'] = symbol
            frames.append(df)
        else:
            # Multi-index columns (Symbol, Metric) -> iterate tickers
            for symbol in symbols:
                try:
                    if has_multi_index:
                        if symbol in data.columns.get_level_values(0):
                            df = data[symbol].copy()
                        else:
                            df = data.xs(symbol, axis=1, level=1).copy()
                    else:
                        logger.warning("Unexpected yfinance response shape for multiple symbols")
                        return pd.DataFrame()
                    df['symbol'] = symbol
                    frames.append(df)
                except KeyError:
                    logger.warning(f"No data for {symbol} in yfinance response")

        if not frames:
            return pd.DataFrame()

        result = pd.concat(frames)
        result.index.name = 'date'
        result = result.reset_index()

        # Normalize columns to lowercase snake_case
        normalized_columns = {}
        for col in result.columns:
            col_str = str(col).strip()
            if col_str.lower() in {"adj close", "adj_close"}:
                normalized_columns[col] = "adj_close"
            else:
                normalized_columns[col] = col_str.lower().replace(" ", "_")
        result.rename(columns=normalized_columns, inplace=True)

        if "adj_close" not in result.columns and "close" in result.columns:
            result["adj_close"] = result["close"]

        required_columns = ['symbol', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
        missing = [col for col in required_columns if col not in result.columns]
        if missing:
            logger.error(
                "yfinance response missing columns: %s (available: %s)",
                missing,
                list(result.columns),
            )
            return pd.DataFrame()

        # Ensure correct types
        # Note: yfinance can return 0 or NaN for some cols
        return result[required_columns].dropna()

    def fetch_latest_bar(self, symbol: str) -> Optional[dict]:
        # yf doesn't have a reliable low-latency "realtime" API, 
        # so for this provider we just fetch the last 2 days and take the last one
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2d")
        if hist.empty:
            return None
        
        last_row = hist.iloc[-1]
        # history() returns columns: [Open, High, Low, Close, Volume, Dividends, Stock Splits]
        # It's already adjusted by default unless auto_adjust=False is passed to history (defaults to True)
        # We'll treat Close as Adj Close here for simplicity or assume adjustments
        
        return {
            "symbol": symbol,
            "date": last_row.name.date(),
            "open": float(last_row['Open']),
            "high": float(last_row['High']),
            "low": float(last_row['Low']),
            "close": float(last_row['Close']),
            "adj_close": float(last_row['Close']), # yf.history auto-adjusts by default
            "volume": int(last_row['Volume'])
        }
