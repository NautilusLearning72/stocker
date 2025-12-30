# Stocker Data Model Design

This document defines the data architecture for the Stocker trading platform, supporting the **Volatility-Targeted Trend-Following Strategy**.

## 1. Design Principles

1.  **Immutable Event Log**: The source of truth for decision-making is the sequence of events (market data -> signals -> targets -> orders).
2.  **Double-Entry Ledger**: Portfolio state is derived from a strict ledger of fills and transfers, not just current snapshots.
3.  **Auditability**: Every decision (signal, target, order) links back to the data that generated it.
4.  **Precision**: Financial values use `DECIMAL` (Numeric) types, not Floating Point, to prevent rounding errors.

---

## 2. PostgreSQL Schema

### 2.1 Market Data

#### `prices_daily`
Source of truth for historical and daily intake data.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | Internal ID |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | Ticker symbol (e.g., 'SPY') |
| `date` | DATE | NOT NULL, IDX | Trading date |
| `open` | NUMERIC(14, 4) | NOT NULL | Open price |
| `high` | NUMERIC(14, 4) | NOT NULL | High price |
| `low` | NUMERIC(14, 4) | NOT NULL | Low price |
| `close` | NUMERIC(14, 4) | NOT NULL | Close price (raw) |
| `adj_close` | NUMERIC(14, 4) | NOT NULL | Adjusted close (splits/divs) |
| `volume` | BIGINT | NOT NULL | Trading volume |
| `source` | VARCHAR(50) | NOT NULL | e.g., 'yfinance', 'alpaca', 'polygon' |
| `source_hash` | VARCHAR(64) | | SHA256 of raw payload for audit |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Ingestion time |

*   **Unique Constraint**: `(symbol, date)`

#### `prices_intraday`
Historical and live intraday data (e.g., 1-minute, 5-minute bars).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | Internal ID |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | Ticker symbol |
| `timestamp` | TIMESTAMPTZ | NOT NULL, IDX | Bar start time (UTC) |
| `interval` | VARCHAR(10) | NOT NULL | e.g., '1m', '5m', '1h' |
| `open` | NUMERIC(14, 4) | NOT NULL | |
| `high` | NUMERIC(14, 4) | NOT NULL | |
| `low` | NUMERIC(14, 4) | NOT NULL | |
| `close` | NUMERIC(14, 4) | NOT NULL | |
| `volume` | BIGINT | NOT NULL | |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

*   **Unique Constraint**: `(symbol, timestamp, interval)`

#### `corporate_actions`
Splits and dividends (sourced from yfinance/Alpaca).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | |
| `date` | DATE | NOT NULL, IDX | Ex-date |
| `action_type` | VARCHAR(20) | CHECK (SPLIT, DIVIDEND) | |
| `value` | NUMERIC(14, 4) | NOT NULL | Dividend amount or Split ratio |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

---

### 2.2 Metadata & Fundamentals

#### `instrument_info`
Master table for tradable assets (Sector, Industry, etc.).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `symbol` | VARCHAR(20) | PK | |
| `name` | VARCHAR(255) | | Company Name |
| `asset_class` | VARCHAR(20) | DEFAULT 'US_EQUITY' | Equity, ETF, Crypto |
| `sector` | VARCHAR(100) | | e.g., 'Technology' |
| `industry` | VARCHAR(100) | | e.g., 'Semiconductors' |
| `exchange` | VARCHAR(50) | | NYSE, NASDAQ |
| `currency` | VARCHAR(10) | DEFAULT 'USD' | |
| `active` | BOOLEAN | DEFAULT TRUE | Is currently tradable |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | |

#### `instrument_metrics`
Investor-facing fundamentals and valuation metrics (one row per symbol per as-of date).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | |
| `as_of_date` | DATE | NOT NULL, IDX | Date metrics apply (market date or report date) |
| `period_type` | VARCHAR(10) | NOT NULL | DAILY, TTM, FQ, FY |
| `period_end` | DATE | | Fiscal period end date (if applicable) |
| `fiscal_year` | INTEGER | | |
| `fiscal_quarter` | INTEGER | | |
| `source` | VARCHAR(50) | NOT NULL | e.g., 'yfinance', 'tiingo' |
| `currency` | VARCHAR(10) | DEFAULT 'USD' | |
| `market_cap` | NUMERIC(20, 2) | | |
| `enterprise_value` | NUMERIC(20, 2) | | |
| `shares_outstanding` | BIGINT | | |
| `float_shares` | BIGINT | | |
| `beta` | NUMERIC(6, 4) | | |
| `pe_ttm` | NUMERIC(12, 4) | | Trailing P/E |
| `pe_forward` | NUMERIC(12, 4) | | Forward P/E |
| `price_to_book` | NUMERIC(12, 4) | | |
| `price_to_sales` | NUMERIC(12, 4) | | |
| `peg_ratio` | NUMERIC(12, 4) | | |
| `ev_to_ebitda` | NUMERIC(12, 4) | | |
| `ev_to_ebit` | NUMERIC(12, 4) | | |
| `fcf_yield` | NUMERIC(12, 6) | | |
| `dividend_yield` | NUMERIC(12, 6) | | |
| `dividend_rate` | NUMERIC(14, 6) | | Annual dividend per share |
| `payout_ratio` | NUMERIC(12, 6) | | |
| `revenue` | NUMERIC(20, 2) | | |
| `ebitda` | NUMERIC(20, 2) | | |
| `net_income` | NUMERIC(20, 2) | | |
| `free_cash_flow` | NUMERIC(20, 2) | | |
| `gross_margin` | NUMERIC(12, 6) | | |
| `operating_margin` | NUMERIC(12, 6) | | |
| `net_margin` | NUMERIC(12, 6) | | |
| `ebitda_margin` | NUMERIC(12, 6) | | |
| `roe` | NUMERIC(12, 6) | | Return on equity |
| `roa` | NUMERIC(12, 6) | | Return on assets |
| `roic` | NUMERIC(12, 6) | | Return on invested capital |
| `revenue_growth_yoy` | NUMERIC(12, 6) | | |
| `earnings_growth_yoy` | NUMERIC(12, 6) | | |
| `eps_growth_yoy` | NUMERIC(12, 6) | | |
| `fcf_growth_yoy` | NUMERIC(12, 6) | | |
| `debt_to_equity` | NUMERIC(12, 6) | | |
| `net_debt_to_ebitda` | NUMERIC(12, 6) | | |
| `interest_coverage` | NUMERIC(12, 6) | | |
| `current_ratio` | NUMERIC(12, 6) | | |
| `quick_ratio` | NUMERIC(12, 6) | | |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

*   **Unique Constraint**: `(symbol, as_of_date, period_type, source)`

---

### 2.3 Trading Universe

#### `instrument_universe`
User-managed universes (global and per-strategy).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | Universe name |
| `description` | TEXT | | |
| `is_global` | BOOLEAN | DEFAULT FALSE | Global master universe flag |
| `is_deleted` | BOOLEAN | DEFAULT FALSE | Soft delete |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

#### `instrument_universe_member`
Membership of instruments in a user-managed universe.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `universe_id` | INT | FK `instrument_universe.id` | |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | |
| `is_deleted` | BOOLEAN | DEFAULT FALSE | Soft delete |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

*   **Unique Constraint**: `(universe_id, symbol)`

#### `strategy_universe`
Mapping between strategies and their assigned universe.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `strategy_id` | VARCHAR(100) | UNIQUE, NOT NULL | Strategy identifier |
| `universe_id` | INT | FK `instrument_universe.id` | |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

*   **Unique Constraint**: `(strategy_id)`

#### `trading_universe`
Legacy dynamic universe (kept for historical reference).
Daily snapshot of the dynamic trading universe (top-N by liquidity).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `as_of_date` | DATE | NOT NULL, IDX | Date of ranking |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | |
| `rank` | INTEGER | NOT NULL | 1 = most active |
| `avg_dollar_volume` | NUMERIC(20, 2) | | Avg(Price * Volume) |
| `source` | VARCHAR(50) | NOT NULL | e.g., 'prices_daily' |
| `lookback_days` | INTEGER | | |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

*   **Unique Constraint**: `(as_of_date, symbol, source)`

---

### 2.4 Market Intelligence (Sentiment & Broad Market)

#### `market_sentiment`
Aggregated sentiment data derived from news/social.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `symbol` | VARCHAR(20) | IDX | Nullable if market-wide |
| `date` | DATE | NOT NULL, IDX | |
| `source` | VARCHAR(50) | NOT NULL | e.g., 'finbert_news', 'twitter_agg' |
| `sentiment_score` | NUMERIC(5, 4) | NOT NULL | -1.0 (neg) to 1.0 (pos) |
| `sentiment_magnitude`| NUMERIC(10, 4)| | Confidence or Volume of mentions |
| `article_count` | INTEGER | | Number of sources aggregated |

#### `market_breadth`
Broad market health indicators.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `date` | DATE | NOT NULL, IDX | |
| `metric` | VARCHAR(50) | NOT NULL | e.g., 'advance_decline_ratio', 'new_highs_lows', 'sector_rotation' |
| `scope` | VARCHAR(50) | DEFAULT 'US_ALL' | S&P500, NASDAQ, RUSSELL2000 |
| `value` | NUMERIC(14, 4) | NOT NULL | |

---

### 2.5 Strategy & Portfolio

#### `signals`
Output of the **Signal Engine**. One row per symbol per day.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | Internal ID |
| `strategy_version` | VARCHAR(50) | NOT NULL | e.g., 'vol_target_trend_v1' |
| `symbol` | VARCHAR(20) | NOT NULL, IDX | Ticker symbol |
| `date` | DATE | NOT NULL, IDX | Date of signal generation |
| `lookback_return` | NUMERIC(10, 6) | | 126-day return |
| `ewma_vol` | NUMERIC(10, 6) | | Annualized EWMA volatility |
| `direction` | SMALLINT | CHECK (-1, 0, 1) | Trend direction |
| `target_weight` | NUMERIC(10, 6) | | Raw inverse-vol weight (pre-caps) |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

*   **Unique Constraint**: `(strategy_version, symbol, date)`

#### `target_exposures`
Output of the **Portfolio Engine**. Defines what we *want* to own.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | Internal ID |
| `portfolio_id` | VARCHAR(50) | NOT NULL | e.g., 'main_strategy' |
| `date` | DATE | NOT NULL | Target date |
| `symbol` | VARCHAR(20) | NOT NULL | Ticker symbol |
| `target_exposure` | NUMERIC(10, 6) | NOT NULL | Desired exposure (e.g., 0.15 for 15%) |
| `scaling_factor` | NUMERIC(5, 4) | DEFAULT 1.0 | Portfolio-level leverage scaler (k) |
| `is_capped` | BOOLEAN | DEFAULT FALSE | True if single-asset cap applied |
| `reason` | TEXT | | Explanation for caps/cuts |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |

*   **Unique Constraint**: `(portfolio_id, symbol, date)`

---

### 2.6 Execution

#### `orders`
Instructions sent to the broker.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | Internal ID |
| `order_id` | UUID | UNIQUE, NOT NULL | Public ID for idempotency |
| `portfolio_id` | VARCHAR(50) | NOT NULL | |
| `date` | DATE | NOT NULL | Intended trade date |
| `symbol` | VARCHAR(20) | NOT NULL | |
| `side` | VARCHAR(10) | CHECK (BUY, SELL) | |
| `qty` | NUMERIC(12, 4) | NOT NULL | Quantity to trade |
| `type` | VARCHAR(20) | DEFAULT 'MOO' | Market-On-Open, MARKET, LIMIT |
| `status` | VARCHAR(20) | | PENDING, SHIPPED, FILLED, CANCELED |
| `broker_order_id` | VARCHAR(100) | | ID returned by Alpaca/Broker |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ | | |

#### `fills`
Confirmed trades from the broker.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | Internal ID |
| `fill_id` | VARCHAR(100) | UNIQUE, NOT NULL | Broker's execution ID |
| `order_id` | UUID | FK `orders.order_id` | Link to parent order |
| `date` | TIMESTAMPTZ | NOT NULL | Precise execution time |
| `symbol` | VARCHAR(20) | NOT NULL | |
| `side` | VARCHAR(10) | NOT NULL | |
| `qty` | NUMERIC(12, 4) | NOT NULL | Executed quantity |
| `price` | NUMERIC(14, 4) | NOT NULL | Execution price |
| `commission` | NUMERIC(10, 4) | DEFAULT 0 | Fees |
| `exchange` | VARCHAR(50) | | e.g., 'NYSE', 'ARCA' |

---

### 2.7 Accounting

#### `portfolio_state`
Daily snapshots of portfolio health.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `portfolio_id` | VARCHAR(50) | NOT NULL | |
| `date` | DATE | NOT NULL | Snapshot date |
| `nav` | NUMERIC(18, 4) | NOT NULL | Net Asset Value |
| `cash` | NUMERIC(18, 4) | NOT NULL | Cash balance |
| `gross_exposure` | NUMERIC(10, 4) | NOT NULL | Sum of abs(positions) / NAV |
| `net_exposure` | NUMERIC(10, 4) | NOT NULL | Net positions / NAV |
| `realized_pnl` | NUMERIC(18, 4) | NOT NULL | Daily Realized P&L |
| `unrealized_pnl` | NUMERIC(18, 4) | NOT NULL | Daily MTM P&L |
| `drawdown` | NUMERIC(10, 4) | NOT NULL | Current drawdown from peak |
| `high_water_mark`| NUMERIC(18, 4) | NOT NULL | Peak NAV seen so far |

#### `holdings`
Current positions (Snapshot).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | BIGSERIAL | PK | |
| `portfolio_id` | VARCHAR(50) | NOT NULL | |
| `date` | DATE | NOT NULL | Date of holding record |
| `symbol` | VARCHAR(20) | NOT NULL | |
| `qty` | NUMERIC(12, 4) | NOT NULL | Current quantity |
| `cost_basis` | NUMERIC(14, 4) | NOT NULL | Avg entry price |
| `market_value` | NUMERIC(18, 4) | NOT NULL | Qty * Current Price |

---

## 3. Redis Stream Schemas

All messages are JSON objects.

### 3.1 `market-bars`
Trigger: Daily Market Data Ingest

```json
{
  "event_type": "market_bar",
  "symbol": "SPY",
  "date": "2023-10-27",
  "open": "415.20",
  "high": "418.90",
  "low": "414.05",
  "close": "417.55",
  "adj_close": "417.55",
  "volume": 75000000,
  "provider": "alpaca"
}
```

### 3.2 `signals`
Trigger: Signal Engine

```json
{
  "event_type": "signal_generated",
  "strategy": "trend_v1",
  "symbol": "SPY",
  "date": "2023-10-27",
  "metrics": {
    "lookback_return": 0.054,
    "ewma_vol": 0.145,
    "direction": 1
  },
  "raw_weight": 0.25
}
```

### 3.3 `targets`
Trigger: Portfolio Engine

```json
{
  "event_type": "portfolio_targets",
  "portfolio_id": "main",
  "date": "2023-10-27",
  "targets": [
    {
      "symbol": "SPY",
      "target_exposure": 0.35,
      "reason": "Capped at 35%"
    },
    {
      "symbol": "GLD",
      "target_exposure": 0.15,
      "reason": null
    }
  ],
  "meta": {
    "scaling_factor": 1.0,
    "drawdown": 0.02
  }
}
```

### 3.4 `orders`
Trigger: Order Manager

```json
{
  "event_type": "order_created",
  "order_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "portfolio_id": "main",
  "symbol": "SPY",
  "side": "BUY",
  "qty": 15,
  "order_type": "MOO",
  "target_date": "2023-10-28"
}
```

### 3.5 `fills`
Trigger: Broker Adapter (Webhook/Polling)

```json
{
  "event_type": "order_filled",
  "order_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "broker_id": "alpaca_12345",
  "symbol": "SPY",
  "qty": 15,
  "price": 418.05,
  "commission": 0.00,
  "timestamp": "2023-10-28T09:30:01Z"
}
```

### 3.6 `portfolio-state`
Trigger: Ledger Service

```json
{
  "event_type": "state_update",
  "portfolio_id": "main",
  "date": "2023-10-28",
  "nav": 10500.50,
  "cash": 450.20,
  "pnl": {
    "realized": 120.50,
    "unrealized": 30.00,
    "day_total": 150.50
  }
}
```
