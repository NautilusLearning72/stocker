# Derived ➜ Analytical Metrics: Implementation Plan

## 1. Goal and scope

Build a derived-metrics subsystem that:
- Computes fundamental, technical, quant, and sentiment-derived metrics daily.
- Stores metrics in normalized tables for fast search and ranking.
- Supports rule-based consolidation (composite scoring) for UI opportunity screens.
- Integrates with existing Redis Streams + Celery + pipeline launcher.

Non-goals for this phase:
- No UI/Angular work yet.
- No live intraday metrics (daily cadence first).
- No backfill beyond the last N trading days unless requested.

Decisions from review:
- Default universe is the global universe (`InstrumentUniverse.is_global = true`).
- Version 1 includes all metric families (fundamental, quant, technical, sentiment, cross-domain).
- Avoid duplicating raw fundamentals or sentiment data already in `instrument_metrics` and `market_sentiment`.

## 2. Architecture alignment (reviewed)

Current data flow (per architecture.md and consumers):
- Market data ingestion task writes `prices_daily` and publishes `market-bars`.
- `SignalConsumer` listens to `market-bars` batch events.
- `PortfolioConsumer` listens to `signals` batch events.
- Celery Beat schedules periodic data ingestion tasks.
- `run_pipeline.sh` starts consumers and triggers ingest tasks.

Derived metrics will follow the same pattern:
- A stream consumer to compute metrics off `market-bars` batch events.
- A Celery task to do daily batch recompute and ranking.
- Optional Redis stream event for "derived-metrics-complete".

## 3. Proposed database schema

### 3.1 Metric definitions (metadata)

Table: `derived_metric_definitions`

Purpose: stable catalog of metric metadata for search, grouping, and rule definition.

Columns:
- `id` BIGSERIAL PK
- `metric_key` VARCHAR(64) UNIQUE NOT NULL (ex: `mom_3m`, `pe_ttm`, `rsi_14`)
- `name` VARCHAR(120) NOT NULL
- `category` VARCHAR(50) NOT NULL (fundamental, technical, sentiment, quant, cross_domain)
- `unit` VARCHAR(20) NULL (pct, ratio, usd, score)
- `direction` VARCHAR(10) NOT NULL (higher_is_better, lower_is_better, neutral)
- `lookback_days` INTEGER NULL
- `description` TEXT NULL
- `tags` VARCHAR(200) NULL (comma-separated for now)
- `source_table` VARCHAR(50) NULL (instrument_metrics, market_sentiment, prices_daily, computed)
- `source_field` VARCHAR(64) NULL
- `version` VARCHAR(20) NOT NULL DEFAULT "v1"
- `is_active` BOOLEAN DEFAULT TRUE
- `created_at`, `updated_at`

Indexes:
- UNIQUE(`metric_key`)
- INDEX(`category`, `metric_key`)

### 3.2 Metric values (per symbol, per date)

Table: `derived_metric_values`

Purpose: store computed metric values with normalization for rank/search.

Columns:
- `id` BIGSERIAL PK
- `symbol` VARCHAR(20) NOT NULL
- `as_of_date` DATE NOT NULL
- `metric_id` BIGINT FK -> `derived_metric_definitions.id`
- `value` NUMERIC(20, 8) NULL
- `zscore` NUMERIC(12, 6) NULL
- `percentile` NUMERIC(6, 4) NULL
- `rank` INTEGER NULL
- `source` VARCHAR(50) NOT NULL (computed, yfinance, alpaca)
- `calc_version` VARCHAR(20) NOT NULL DEFAULT "v1"
- `created_at`, `updated_at`

Constraints / indexes:
- UNIQUE(`symbol`, `as_of_date`, `metric_id`)
- INDEX(`metric_id`, `as_of_date`)
- INDEX(`symbol`, `as_of_date`)

### 3.3 Rule sets for consolidation

Table: `derived_metric_rule_sets`

Purpose: define composite opportunity screens for UI.

Columns:
- `id` BIGSERIAL PK
- `name` VARCHAR(120) UNIQUE NOT NULL
- `description` TEXT NULL
- `universe_id` INT NULL FK -> `instrument_universe.id`
- `is_active` BOOLEAN DEFAULT TRUE
- `created_at`, `updated_at`

Table: `derived_metric_rules`

Purpose: atomic rules used by rule sets.

Columns:
- `id` BIGSERIAL PK
- `rule_set_id` BIGINT FK -> `derived_metric_rule_sets.id`
- `metric_id` BIGINT FK -> `derived_metric_definitions.id`
- `operator` VARCHAR(10) NOT NULL (>, >=, <, <=, between)
- `threshold_low` NUMERIC(20, 8) NULL
- `threshold_high` NUMERIC(20, 8) NULL
- `weight` NUMERIC(10, 6) NOT NULL DEFAULT 1.0
- `is_required` BOOLEAN DEFAULT FALSE
- `normalize` VARCHAR(20) NULL (raw, zscore, percentile)
- `created_at`, `updated_at`

Constraints / indexes:
- INDEX(`rule_set_id`)
- INDEX(`metric_id`)

### 3.4 Consolidated scores

Table: `derived_metric_scores`

Purpose: materialized composite scores for ranking.

Columns:
- `id` BIGSERIAL PK
- `rule_set_id` BIGINT FK -> `derived_metric_rule_sets.id`
- `symbol` VARCHAR(20) NOT NULL
- `as_of_date` DATE NOT NULL
- `score` NUMERIC(20, 8) NULL
- `rank` INTEGER NULL
- `percentile` NUMERIC(6, 4) NULL
- `passes_required` BOOLEAN NOT NULL DEFAULT FALSE
- `created_at`, `updated_at`

Constraints / indexes:
- UNIQUE(`rule_set_id`, `symbol`, `as_of_date`)
- INDEX(`rule_set_id`, `as_of_date`)
- INDEX(`symbol`, `as_of_date`)

## 4. Derived metrics computation design

### 4.1 Metric coverage (initial set)

Notes:
- Fundamental values come from `instrument_metrics` (no new raw storage).
- Sentiment values come from `market_sentiment` (no new raw storage).
- Derived metrics store normalized/composite outputs (zscore/percentile, cross-domain).

Fundamental:
- `pe_ttm`, `pe_forward`, `peg_ratio`, `ev_to_ebitda`, `fcf_yield`
- `roe`, `roic`, `debt_to_equity`
- `altman_z` (if data available), `piotroski_f` (optional v2)

Quant / factor:
- Value: `book_to_market`, `earnings_yield`, `cash_flow_yield`
- Quality: `gross_profitability`, `roic`, `leverage`
- Momentum: `mom_1m`, `mom_3m`, `mom_6m`, `mom_12m`
- Volatility: `beta`, `atr_14`, `vol_20d`

Technical:
- Trend: `sma_50`, `sma_200`, `ema_20`, `macd`, `adx`
- Oscillators: `rsi_14`, `stoch_k`, `stoch_d`
- Volume: `vwap_20`, `obv`

Sentiment:
- `sentiment_score`, `sentiment_mom`, `sentiment_vol`

Cross-domain:
- `quality_x_momentum`, `sentiment_adjusted_beta`, `risk_adjusted_value`

### 4.2 Engine location

- Add `stocker/strategy/derived_metrics_engine.py` for pure calculations (no IO).
- Add `stocker/services/derived_metrics_service.py` for data fetching + DB upsert.
- Consumer orchestrates the service and publishes stream events.

### 4.3 Normalization and ranking

Compute z-score and percentile per metric per date across the active universe.
Store rank and percentile in `derived_metric_values` for fast UI queries.

## 5. Consumer/service design

### 5.1 DerivedMetricsConsumer

File: `backend/stocker/stream_consumers/derived_metrics_consumer.py`

Behavior:
- Listen to `market-bars` stream.
- On `batch_complete`, parse `symbols` + `date`.
- Fetch DailyBars, InstrumentMetrics, MarketSentiment for symbols/date.
- Compute derived metrics via `DerivedMetricsEngine`.
- Upsert `derived_metric_values`.
- Optionally publish `derived-metrics` stream event.

### 5.2 DerivedMetricsService

File: `backend/stocker/services/derived_metrics_service.py`

Behavior:
- Collect source data for symbols/date (use global universe by default).
- Call pure engine to compute metrics.
- Upsert metrics in a single transaction.
- Compute z-score/percentile/rank using SQL window functions or pandas (batch).

## 6. Rule evaluation and composite scores

### 6.1 Rule evaluation

New service: `DerivedMetricRuleEngine`
- Load active rule sets.
- For each rule set/date, filter symbols by required rules.
- Compute weighted score using selected normalization (raw/zscore/percentile).
- Upsert `derived_metric_scores`.

### 6.2 UI usage

Angular dashboard can:
- Search metrics by `metric_key`, `category`, or tags.
- Rank by `metric_id` percentile for a date.
- Rank by composite `rule_set_id` score for a date.

## 7. Celery integration

### 7.1 Tasks

Add tasks:
- `stocker.tasks.derived_metrics.ingest_derived_metrics`
- `stocker.tasks.derived_metrics.compute_metric_scores`

### 7.2 Scheduling (Celery Beat)

Proposed schedule:
- `ingest_derived_metrics`: after market data ingestion, e.g. 17:30 ET.
- `compute_metric_scores`: after instrument metrics refresh, e.g. 19:15 ET.

Both tasks should accept optional `as_of_date` and `universe_id` for backfills.

## 8. Pipeline integration

Update `backend/scripts/run_pipeline.sh`:
- Start `derived_metrics_consumer`.
- Trigger `ingest_derived_metrics` after market data ingestion.
- Trigger `compute_metric_scores` after instrument metrics refresh.

## 9. Migration and models

Add SQLAlchemy models in `backend/stocker/models/` and generate Alembic migration:
- `derived_metric_definition.py`
- `derived_metric_value.py`
- `derived_metric_rule_set.py`
- `derived_metric_rule.py`
- `derived_metric_score.py`

## 10. Testing and validation

Unit tests:
- DerivedMetricsEngine calculations with deterministic inputs.
- Rule engine scoring with mock metric values.

Integration tests:
- Ingest task stores expected metrics for a small universe.
- Consumer processes `batch_complete` messages end-to-end.

## 11. Rollout plan

Phase 1:
- Implement schema, engine, service, and consumer.
- Compute only a small, core subset of metrics (momentum, volatility, sentiment).

Phase 2:
- Expand fundamental metrics and technical indicators.
- Add rule set UI + API endpoints.

Phase 3:
- Add cross-domain metrics and custom user-defined metrics.
