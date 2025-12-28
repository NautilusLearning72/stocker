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
