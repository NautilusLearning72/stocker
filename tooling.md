# Tooling Investigation & Recommendations

## Executive Summary

For the **Stocker** systematic trading platform, the optimal zero-cost starting point is to utilize **Alpaca** for both trade execution and live market data, supplemented by **yfinance** for extensive historical backtesting data. 

**Recommended Stack:**
- **Historical Data (Backtesting)**: `yfinance` (Unofficial Yahoo Finance API) - *Unlimited/Free*
- **Live/Daily Data**: `Alpaca Data API` (Free Tier) - *Authorized/Stable*
- **Trade Execution**: `Alpaca Trading API` - *Commission-Free/API-First*

---

## 1. Market Data Sources (Free Tiers)

Accessing high-quality market data for free is the biggest challenge in algorithmic trading. Most "free" tiers have severe rate limits that make scanning thousands of stocks daily impossible.

| Provider | Free Tier Limits | Data Quality | Best Use Case |
| :--- | :--- | :--- | :--- |
| **Yahoo Finance** (`yfinance`) | Unlimited (Soft limits based on IP) | Good (Retail standard) | **Backtesting**. Downloading 20 years of history for 500 stocks is easy and free. |
| **Alpaca Data** | Unlimited requests (IEX Exchange only) | Fair (IEX is ~2.5% of volume). No SIP (100% market) data on free tier. | **Live Trading**. Good enough for daily bars if you aren't HFT. Seamless integration if using Alpaca for execution. |
| **Tiingo** | 500 symbols/month, 1000 req/day | Excellent (Composite feed) | **Production Backup**. Best "official" free API limits. Great for a small universe (e.g., S&P 100). |
| **Alpha Vantage** | 25 requests/day | Good | **Not Recommended**. The limit is too strict for any serious portfolio scanning. |
| **Polygon.io** | 5 requests/min, 2-year history | Excellent | **Testing**. Great API design, but free tier is too restrictive for full backtesting. |

### Recommendation: Hybrid Approach
1.  **Backtesting**: Use `yfinance`. It is the only free source that allows you to pull full history for the entire S&P 500 without hitting rate limits.
2.  **Daily Ingest**: Use **Alpaca Data (Free)** or **Tiingo**.
    *   *Why Alpaca?* If you trade there, you get their data for free. It's "good enough" for daily trend following.
    *   *Why Tiingo?* If you need higher quality composite data for a smaller set of stocks (up to 500), Tiingo is superior to IEX-only data.

---

## 2. Trade Execution Platforms

For a systematic Python/FastAPI application, the "Developer Experience" (DX) of the broker's API is as important as the commissions.

### Option A: Alpaca (Winner) 🏆
Alpaca is built specifically for algorithmic trading. It is the industry standard for modern retail algos.

*   **Cost**: Commission-free for US Stocks/ETFs.
*   **API**: Modern REST/Streaming API. Excellent Python SDK (`alpaca-py`).
*   **Paper Trading**: Best-in-class paper environment that mimics live trading perfectly.
*   **Data**: Built-in market data API (removes need for separate data integration).
*   **Ease of Use**: You can get an API key and place a trade in 5 minutes.

### Option B: Interactive Brokers (IBKR)
The professional choice. unparalleled market access but higher complexity.

*   **Cost**: "IBKR Lite" is commission-free (US), but "Pro" (better execution) costs money.
*   **API**: The "Client Portal API" is difficult to work with (cookie-based auth). The "TWS API" requires running a Java desktop gateway software alongside your Python backend.
*   **Complexity**: High. Overkill for a startup strategy.

### Option C: Tradier
A middle ground between Alpaca and IBKR.

*   **Cost**: Commission-free (mostly).
*   **API**: REST API is decent, but less popular in the Python community than Alpaca.
*   **Community**: Smaller ecosystem of open-source tools compared to Alpaca.

---

## 3. Implementation Strategy for Stocker

Based on your architecture, here is how you should integrate these tools:

### Phase 1: Development & Backtesting
*   **Library**: `yfinance`
*   **Action**: Update your "Market Data Ingestor" service to have a `YFinanceProvider` class.
*   **Logic**: 
    ```python
    import yfinance as yf
    # Fetch 10 years of history for S&P 500
    data = yf.download(tickers, period="10y", interval="1d")
    ```

### Phase 2: Paper Trading (Live Simulation)
*   **Broker**: Alpaca (Paper Account)
*   **Data**: Alpaca Data API
*   **Action**: Implement `AlpacaBrokerAdapter` in your architecture.
*   **Logic**:
    *   Use Alpaca to fetch "yesterday's close" to update your daily signals.
    *   Submit orders to Alpaca Paper API.

### Phase 3: Live Trading
*   **Broker**: Alpaca (Live Account)
*   **Data**: Upgrade to **Alpaca Unlimited** ($99/mo) OR stick to **Tiingo** (Free) if universe < 500 stocks.
*   *Note*: For a trend-following strategy, the IEX-only data (free) from Alpaca might theoretically result in slightly different "Close" prices than the official SIP, but for daily candles, the discrepancy is usually negligible.

## Summary Checklist
- [ ] Sign up for **Alpaca** (Paper trading is free and instant).
- [ ] Get a **Tiingo** API key (as a backup high-quality data source).
- [ ] Install `yfinance` for your backtesting engine.
- [ ] Install `alpaca-py` for your broker adapter.
