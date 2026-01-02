## Product Design Document (PDD): Volatility-Targeted Trend-Following Strategy (Daily bars)

### 0) Summary

Build a **simple, robust, production-grade** systematic strategy that trades a small universe of liquid instruments using **time-series momentum** with **volatility targeting**, **risk limits**, and **rules-based execution**. Start with **paper trading**, then graduate to small live size.

---

## 1) Goals & Non-Goals

### Goals

* A strategy you can **implement quickly**, backtest properly, and run reliably.
* Minimise dependence on speed or exotic data.
* Provide a clean framework you can later extend (filters, more assets, execution improvements).

### Non-Goals

* HFT / market making.
* Options/vol selling.
* ML prediction as core signal (can add later).

---

## 2) Strategy Overview

### Instruments (choose one set)

**Option A (simplest): ETFs (cash equities)**

* SPY (US equities)
* TLT / IEF (US treasuries)
* GLD (gold)
* USO (oil) *or* DBC (broad commodities)
* UUP (USD index proxy) (optional)

**Option B (better for purer trend): Liquid futures (if you have access)**

* ES, NQ (equity indices)
* ZN (notes) / ZB (bonds)
* GC (gold)
* CL (oil)
* 6E (EURUSD)

Start with **5–8 instruments max**.

---

## 3) Trading Rules (Concrete Spec)

### 3.1 Signal: Time-Series Momentum (TSMOM)

Compute for each instrument (i):

* **Lookback return:**
  ( R_i = \frac{P_{t-1}}{P_{t-1-L}} - 1 )
  where **L = 126 trading days** (~6 months).

* **Direction:**
  ( \text{dir}_i = \begin{cases}
  +1 & \text{if } R_i > 0 \
  -1 & \text{if } R_i < 0
  \end{cases} )

### 3.2 Volatility estimate (for position sizing)

* Use **EWMA volatility** of daily returns:

  * returns: ( r_t = \ln(P_t / P_{t-1}) )
  * EWMA with **lambda = 0.94** (RiskMetrics-style)
  * annualise: ( \sigma_i = \text{stdev}_\text{EWMA}(r) \times \sqrt{252} )

### 3.3 Target risk & position sizing

* Portfolio target volatility: **10% annualised** (configurable)
* Risk weight per instrument: **equal risk** across active positions.

Define:

* ( w_i = \frac{1/\sigma_i}{\sum_j 1/\sigma_j} ) (inverse-vol weights)
* Raw desired exposure:
  ( \text{exp}_i = \text{dir}_i \times w_i )

Apply portfolio scaling to hit target vol:

* Estimate portfolio vol from covariance (simpler: assume low corr initially and scale conservatively)
* Add scaling factor (k \in (0, 1]) to keep realised risk under target:
  ( \text{final_exp}_i = k \times \text{exp}_i )

**Initial build simplification:** set (k = 1) but cap gross leverage.

### 3.4 Risk limits (hard rules)

* **Gross exposure cap:** max sum of |final_exp| = **1.5x** (ETFs) or **2.0x** (futures)
* **Single instrument cap:** |final_exp_i| ≤ **0.35**
* **Daily stop / circuit breaker:** if portfolio drawdown from peak > **10%**, reduce (k) by 50% until recovery.
* **Kill switch:** if daily P&L < **-3%** or data/execution integrity fails → flatten all positions (paper trade equivalent: stop trading + alert).

### 3.5 Rebalance schedule

* Recompute signals and target positions **daily after close**.
* Place orders **next day at open** (or using a TWAP window 09:35–10:30 local exchange time).

---

## 4) Data Requirements

### Required data (minimum)

* Daily OHLCV for each instrument.
* Adjusted close (for ETFs) including dividends/splits.

### Optional improvements

* Corporate actions feed (for equities).
* For futures: continuous contract series + roll calendar.

### Data quality rules

* No missing bars in last 200 trading days.
* Price sanity checks (no zero/negative, no >30% gap without confirmation).
* Timestamp consistency (same trading calendar).

---

## 5) Backtesting Spec (to avoid self-deception)

### 5.1 Universe and time period

* At least **10 years** if possible (ETFs may be shorter → use futures or substitute proxies).
* Include **crisis periods** (e.g., 2020, 2022).

### 5.2 Execution assumptions

* Trade at **next day open** or **close-to-close with 1-bar delay**.
* Costs:

  * ETFs: 1–3 bps per trade + slippage 1–5 bps (configurable)
  * Futures: 1 tick slippage + commission per contract

### 5.3 Metrics to report (must-have)

* CAGR, annualised vol, Sharpe, max drawdown
* Turnover (monthly/annual)
* % winning months
* Worst 1m / 3m / 12m performance
* Exposure over time (gross/net)

### 5.4 Robustness tests (must run before live)

* Lookback sensitivity: L = 63, 126, 252
* Vol method: EWMA vs rolling 20/60 day
* Costs sensitivity: 2x and 3x costs
* Walk-forward / out-of-sample split

Pass criteria (example):

* Sharpe > 0.6 *after costs* on at least one robust parameter set
* Max drawdown not catastrophic relative to target vol
* Strategy behaviour matches expectation: trends help, choppy markets hurt

---

## 6) System Design (What you need to build)

### 6.1 Components

1. **Market Data Ingest**

* Pull daily bars from provider/API
* Store raw + cleaned series

2. **Feature/Signal Engine**

* Compute returns, EWMA vol, direction
* Produce target exposures

3. **Portfolio & Risk Engine**

* Apply caps, scaling, circuit breaker
* Output target positions in shares/contracts

4. **Execution Engine**

* Compare current vs target holdings → orders
* Order policy: market-on-open or TWAP
* Idempotent order submission (avoid duplicates)

5. **Ledger & Accounting**

* Positions, fills, cash, P&L (realised/unrealised)
* Daily reconciliation vs broker statements (when live)

6. **Monitoring & Alerts**

* Data freshness
* Signal anomalies
* Trade failures
* Drawdown threshold breaches

### 6.2 Data model (minimal tables)

* `prices_daily(symbol, date, open, high, low, close, adj_close, volume, source_hash)`
* `signals(symbol, date, lookback_return, ewma_vol, direction, target_weight, target_exposure)`
* `portfolio_state(date, nav, gross, net, realised_pnl, unrealised_pnl, drawdown)`
* `orders(order_id, date, symbol, side, qty, type, status, submitted_at)`
* `fills(fill_id, order_id, date, symbol, qty, price, commission)`

---

## 7) Operational Plan

### 7.1 Paper trading rollout

* Run end-to-end daily for **30 trading days**:

  * No missed runs
  * No data gaps
  * Orders match targets
  * P&L consistent with backtest expectations

### 7.2 Live rollout (small)

* Start at **10–20%** of intended size.
* Weekly review of slippage/costs vs assumptions.
* Increase size only after **8–12 weeks** stable operations.

### 7.3 Runbook (daily)

* 07:00–08:00: data ingest + validation
* 08:00–08:10: generate signals + targets
* 08:10–08:20: risk checks + order creation
* 09:30+: execute orders
* EOD: reconcile, archive, report, alerts

---

## 8) Risks & Failure Modes

### Market risks

* Extended drawdowns in choppy/range-bound regimes.
* Correlation spikes (diversification fails).
* Gap risk (overnight moves).

### Model risks

* Overfitting (mitigate with robust tests + simple rules).
* Look-ahead bias (ensure 1-bar delay).
* Survivorship bias (use proper histories).

### Operational risks

* Bad data → wrong positions (mitigate with sanity checks).
* Duplicate orders / partial fills (idempotency + reconciliation).
* Broker API outages (retry + fallback + kill switch).

---

## 9) Acceptance Criteria (Definition of Done)

* Backtest report generated with all metrics + sensitivity tests.
* Paper trading runs 30 days with:

  * 0 failed jobs
  * 0 unhandled exceptions
  * daily reconciliation within tolerance
* Monitoring/alerts in place (email/Slack/etc).
* Kill switch tested (simulated failure triggers flat).

---

## 10) Extensions (Phase 2+)

* Trend filter + mean reversion entries (hybrid)
* Regime filter (e.g., trade only when vol below threshold)
* Dynamic leverage (k) based on drawdown / volatility
* Add more futures markets for diversification
* Intraday execution improvements (TWAP/VWAP)

---

If you tell me what you want to trade (**ETFs vs futures vs crypto**) and what environment you prefer (**Python only vs Java + streaming**), I’ll translate this PDD into a **repo structure + concrete module interfaces + initial backtest skeleton** you can start coding immediately.


