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

        # Transformation logic
        frames = []
        if len(symbols) == 1:
            # Single ticker returns a DataFrame with direct columns
            df = data.copy()
            df['symbol'] = symbols[0]
            frames.append(df)
        else:
            # Multi-index columns (Symbol, Metric) -> we need to stack or iterate
            # yfinance structure for multiple tickers:
            # columns: (Price, Ticker) -> we want to iterate tickers
            for symbol in symbols:
                try:
                    df = data[symbol].copy()
                    df['symbol'] = symbol
                    frames.append(df)
                except KeyError:
                    logger.warning(f"No data for {symbol} in yfinance response")

        if not frames:
            return pd.DataFrame()

        result = pd.concat(frames)
        result.index.name = 'date'
        result = result.reset_index()

        # Rename columns to match our schema standard (lowercase, snake_case)
        # yfinance cols: [Date, Open, High, Low, Close, Adj Close, Volume, symbol]
        # We need: symbol, date, open, high, low, close, adj_close, volume
        cols_map = {
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Adj Close': 'adj_close',
            'Volume': 'volume'
        }
        result.rename(columns=cols_map, inplace=True)
        
        # Ensure correct types
        # Note: yfinance can return 0 or NaN for some cols
        return result[['symbol', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']].dropna()

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
