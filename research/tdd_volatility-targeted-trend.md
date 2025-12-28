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


Great — Java + streaming is a strong fit for this kind of system. Below is a **Java/streaming-focused PDD addendum** that turns the strategy into a **buildable production design** (components, topics, schemas, services, and a repo skeleton). It assumes **daily-bar** trading to start (low latency not required), but the architecture cleanly extends to intraday later.

---

## PDD Addendum: Java + Streaming Implementation

### 1) Target Architecture (high level)

**Goal:** An event-driven pipeline where each step is reproducible, auditable, and idempotent.

**Flow**

1. **Market Data Ingestor** pulls daily bars → publishes `market-bars.v1`
2. **Feature/Signal Job** computes returns + EWMA vol + direction → publishes `signals.v1`
3. **Portfolio/Risk Job** computes target exposures + caps + scaling → publishes `targets.v1`
4. **Order Manager** diffs holdings vs targets → publishes `orders.v1`
5. **Broker Adapter** submits orders, emits `fills.v1` + `order-status.v1`
6. **Ledger** builds positions/NAV/PnL and emits `portfolio-state.v1`
7. **Monitoring** watches every topic + invariants; triggers kill switch if needed

**Streaming choice**

* **Kafka** for event bus + compacted state topics
* **Flink (Java)** for streaming computations OR **Kafka Streams** for simpler stateful jobs

  * Start with **Kafka Streams** (simpler ops), move to Flink if you add intraday / heavier analytics.

---

### 2) Core Kafka Topics (v1)

Use **Avro or Protobuf** with Schema Registry. Keep schemas versioned and immutable.

1. `market-bars.v1` (partition by `symbol`)

* key: `symbol|date`
* value: OHLCV + adjusted close

2. `signals.v1` (partition by `symbol`)

* key: `symbol|date`
* value: lookback return (L=126), EWMA vol, direction, inv-vol weight

3. `targets.v1` (partition by `portfolioId`)

* key: `portfolioId|date`
* value: target exposure per symbol (float), caps applied, scaling factor k, reasons/flags

4. `holdings.v1` (compacted, partition by `portfolioId|symbol`)

* key: `portfolioId|symbol`
* value: current qty, avg price, last update

5. `orders.v1` (partition by `portfolioId`)

* key: `portfolioId|date|symbol|side`
* value: qty, order type (MOO/TWAP), time-in-force, idempotency key

6. `order-status.v1`, `fills.v1`

* status changes + execution fills

7. `portfolio-state.v1` (partition by `portfolioId`)

* NAV, gross/net exposure, drawdown, daily PnL

8. `alerts.v1`

* data gaps, sanity check violations, drawdown triggers, broker failures

---

### 3) Data Stores (minimal + robust)

Even with Kafka, keep a store for queries, reports, and reconciliation.

* **PostgreSQL** (or Aurora) for:

  * `prices_daily`, `signals`, `targets`, `orders`, `fills`, `portfolio_state`
* Kafka retains the event log; Postgres is your **serving layer** and audit-friendly snapshot.

---

### 4) Services / Jobs (concrete specs)

#### A) `market-data-ingestor`

**Schedule:** once daily after official close + once retry early morning
**Responsibility:**

* Fetch daily bars (provider of your choice)
* Validate (no negative prices, no missing bars, sensible gaps)
* Publish to `market-bars.v1`
* Persist raw payload hash for audit

**Key invariants**

* Exactly 1 bar per symbol per trading day
* If missing → emit `alerts.v1` and do not progress downstream for that symbol/date

---

#### B) `signal-engine` (Kafka Streams or Flink)

Consumes `market-bars.v1` → produces `signals.v1`

**Compute**

* log returns series
* EWMA vol (λ=0.94) annualised
* 126-day lookback return (using adjusted close)
* direction = sign(lookback return)
* inv-vol weight (temporary; final weights in portfolio job)

**State**

* Rolling window storage per symbol (need last ~252 closes + returns)
* Use Kafka Streams state store (RocksDB) or Flink keyed state

---

#### C) `portfolio-risk-engine`

Consumes `signals.v1` → produces `targets.v1`

**Inputs**

* signals (per symbol)
* config (target vol, caps)
* portfolio context (enabled symbols, capital, leverage rules)
* most recent `portfolio-state.v1` for drawdown scaling

**Logic**

* compute inverse-vol weights across active symbols
* apply direction
* apply caps: single instrument cap, gross exposure cap
* apply drawdown circuit breaker:

  * if drawdown > 10% ⇒ k = 0.5 (or reduce by steps)
* output target exposures per symbol and portfolio-level metadata

**Output format**

* one “portfolio target” event per day containing a list of per-symbol targets

---

#### D) `order-manager`

Consumes `targets.v1` + `holdings.v1` (compacted) → produces `orders.v1`

**Logic**

* desired_qty(symbol) = f(target_exposure, NAV, price, instrument rules)
* delta = desired_qty - current_qty
* threshold to avoid churn: ignore tiny deltas (e.g. < 1 share or < £50 notional)
* create order plan:

  * default: **Market-On-Open** next session
  * optional: TWAP over 60 mins after open

**Idempotency**

* order key: `portfolioId|tradeDate|symbol|strategyVersion|targetHash`
* order-manager must be **pure**: same inputs ⇒ same orders

---

#### E) `broker-adapter` (paper + live)

Consumes `orders.v1` → emits `order-status.v1` + `fills.v1`

**Paper mode**

* Simulate fill at next open with slippage model

**Live mode**

* Integrate with broker API
* Map broker IDs to internal IDs
* Retry rules, rate limits, backoff
* If broker down: emit alert, do not spam resubmits

---

#### F) `ledger`

Consumes `fills.v1` (+ prices) → updates `holdings.v1` (compacted) and emits `portfolio-state.v1`

**Compute**

* positions, avg cost
* NAV (cash + MTM)
* realised/unrealised PnL
* drawdown from peak

---

### 5) Scheduling & “Daily Close” Boundary

Even with streaming, daily trading needs a deterministic boundary.

Use a `trading-calendar` service or a daily “close event”:

* Topic: `trading-session.v1`
* Event: `{date, market="NYSE", session="CLOSE_CONFIRMED", timestamp}`

Downstream jobs only compute for `date` when they see `CLOSE_CONFIRMED`.

This avoids partial data and makes backtests reproducible.

---

### 6) Repo Skeleton (multi-module Gradle)

```
algo-trader/
  build.gradle
  settings.gradle

  common/
    src/main/java/.../schema/   (Avro/Proto generated models)
    src/main/java/.../time/     (trading calendar utils)
    src/main/java/.../risk/     (caps, scaling)
    src/main/java/.../math/     (EWMA, returns)
    src/main/java/.../util/     (idempotency, hashing)

  market-data-ingestor/
    src/main/java/.../IngestorApp.java
    src/main/java/.../providers/...
    src/main/java/.../validators/...

  signal-engine-streams/  (or signal-engine-flink/)
    src/main/java/.../SignalTopology.java
    src/main/java/.../state/...

  portfolio-risk-engine/
    src/main/java/.../PortfolioJob.java
    src/main/java/.../allocator/InverseVolAllocator.java
    src/main/java/.../circuitbreaker/...

  order-manager/
    src/main/java/.../OrderPlanner.java
    src/main/java/.../DiffHoldings.java

  broker-adapter/
    src/main/java/.../PaperBroker.java
    src/main/java/.../LiveBroker.java
    src/main/java/.../mapping/...

  ledger/
    src/main/java/.../LedgerJob.java

  reporting-api/ (optional)
    src/main/java/.../SpringBootApp.java

  infra/
    docker-compose.yml (kafka, schema-registry, postgres)
    k8s/ (optional)
```

---

### 7) Config (example keys)

* `strategy.lookbackDays=126`
* `strategy.ewmaLambda=0.94`
* `risk.targetVol=0.10`
* `risk.grossCap=1.50`
* `risk.singleCap=0.35`
* `risk.ddReduceThreshold=0.10`
* `risk.ddScale=0.50`
* `execution.mode=paper|live`
* `execution.orderType=MOO|TWAP`
* `execution.minNotional=50`
* `universe.symbols=SPY,TLT,GLD,DBC,UUP`

Store configs in:

* a versioned config file in Git (simple) + emit `strategy-config.v1` events for audit, OR
* a config service (later).

---

### 8) “Definition of Done” for Java/Streaming MVP

1. Local `docker-compose` spins up Kafka + Schema Registry + Postgres
2. Ingestor publishes daily bars for 5 symbols for a historical range
3. Signal engine produces deterministic `signals.v1`
4. Portfolio engine produces `targets.v1` with caps applied
5. Order manager produces `orders.v1` with idempotency keys
6. Paper broker simulates fills and ledger produces NAV/PnL
7. A daily report is written to Postgres + a simple console/HTML output

---

### 9) Next step I can produce immediately (pick one)

* **A.** Concrete schemas (Avro/Proto) for `market-bars`, `signals`, `targets`, `orders`, `fills`
* **B.** Kafka Streams topology pseudocode + state-store approach for EWMA + lookback
* **C.** Gradle project scaffold + module interfaces (Java classes + DTOs)
* **D.** Paper execution + ledger logic spec (exact accounting rules)

If you don’t want to choose: I’d do **A + B** first because it locks the contract between all services and unblocks parallel development.
