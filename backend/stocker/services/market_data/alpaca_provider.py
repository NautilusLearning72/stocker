from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from stocker.services.market_data.base import MarketDataProvider
from stocker.core.config import settings
from datetime import date, datetime
from typing import List, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class AlpacaProvider(MarketDataProvider):
    """
    Alpaca provider for live and paper trading.
    Uses stocker.core.config settings for credentials.
    """

    def __init__(self):
        # Initialize the Alpaca Data Client
        # Note: Depending on the subscription (Free vs Paid), the feed might be IEX or SIP.
        # This is controlled by the account type associated with the keys.
        self.client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY
        )

    def fetch_daily_bars(self, symbols: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        if not symbols:
            return pd.DataFrame()

        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbols,
                start=datetime.combine(start_date, datetime.min.time()),
                end=datetime.combine(end_date, datetime.max.time()),
                timeframe=TimeFrame.Day
            )
            bars = self.client.get_stock_bars(request)
            
            # Alpaca SDK returns a MultiIndex DataFrame usually (symbol, timestamp)
            df = bars.df.reset_index()
            
            # Rename columns to standard format
            # Alpaca cols: [symbol, timestamp, open, high, low, close, volume, trade_count, vwap]
            # We map timestamp -> date
            cols_map = {
                'timestamp': 'date',
                # other cols are typically lowercase already in recent SDK versions, 
                # but verify if strict handling needed
            }
            df.rename(columns=cols_map, inplace=True)
            
            # Normalize date to just date object (comes as timestamp)
            df['date'] = df['date'].dt.date
            
            # Add adj_close if missing (Alpaca V2 data is usually raw/unadjusted or needs check)
            # For simplicity in this implementation, we map Close -> Adj Close
            # In a real production environment, we should check adjustment handling.
            if 'adj_close' not in df.columns:
                df['adj_close'] = df['close']
                
            return df[['symbol', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']]
            
        except Exception as e:
            logger.error(f"Alpaca bar fetch failed: {e}")
            return pd.DataFrame()

    def fetch_latest_bar(self, symbol: str) -> Optional[dict]:
        try:
            # We can use get_stock_latest_bar or just fetch last day
            # get_stock_latest_bar returns a Bar object, not a DF
            # For consistency, let's request 1 day of bars
            # However, during market hours 'latest bar' usually means 'latest completed minute' or 'latest trade'
            # Here we likely want the 'latest daily bar' (e.g. yesterday's close if before market, or today's partial?)
            # The interface implies latest *completed* bar for decision making usually.
            
            # For "Daily" resolution strategies, we want the last closed day.
            # But the method name is generic. Let's stick to the implementation plan usage request.
            request = StockBarsRequest(
                symbol_or_symbols=[symbol], 
                timeframe=TimeFrame.Day,
                limit=1
            )
            bars = self.client.get_stock_bars(request)
            
            if bars.df.empty:
                return None
                
            last_row = bars.df.iloc[-1]
            # row name might be (symbol, timestamp) or just index depending on reset
            
            # Extract data
            return {
                "symbol": symbol,
                "date": last_row.name[1].date(), # Multiindex (symbol, timestamp)
                "open": float(last_row['open']),
                "high": float(last_row['high']),
                "low": float(last_row['low']),
                "close": float(last_row['close']),
                "adj_close": float(last_row['close']),
                "volume": int(last_row['volume'])
            }
        except Exception as e:
            logger.error(f"Alpaca latest bar failed: {e}")
            return None
