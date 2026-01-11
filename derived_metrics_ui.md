# Derived Metrics UI PRD (Analytics)

## 1. Summary

Build a new "Analytics" component inside the Metrics area to help users discover investment opportunities using derived metrics (fundamental, technical, sentiment, quant, cross-domain). The UI provides a configurable table, rule-based scoring, and actions to create orders. It also links to deeper symbol pages and explains metrics via tooltips.

This PRD aligns with the backend implementation that now stores derived metric values, scores, and rule sets, and computes daily rankings.

## 2. Backend Scope Summary (What Exists)

### Data models
- derived_metric_definitions: catalog of all metrics (key, name, category, direction, description).
- derived_metric_values: per symbol/date metric values with zscore, percentile, rank.
- derived_metric_rule_sets: named scoring rule groups (optionally tied to a universe).
- derived_metric_rules: rules inside a set (operator, thresholds, weight, normalize).
- derived_metric_scores: materialized composite score per symbol/date and rule set.

### Services and computation
- Derived metrics engine computes all metric families from prices_daily, instrument_metrics, and market_sentiment (no duplication of raw data).
- Derived metrics service writes normalized values and ranks.
- Rule score service computes composite scores and ranks.
- DerivedMetricsConsumer listens to market-bars batch events and computes metrics daily.
- Celery tasks compute metrics and scores on schedule.
- Stream "derived-metrics" emits completion events.

### Pipeline integration
- Pipeline runs derived metrics after market data ingestion.
- Scheduled compute runs via Celery Beat.

## 3. Product Goals

- Enable users to define and compare scoring logic across multiple metric families.
- Make discovery fast: global universe, ranked lists, and search/filter.
- Provide transparent metric definitions and sources.
- Offer quick action: submit orders from the table.

## 4. Non-Goals

- Intraday metrics in v1.
- Portfolio optimization or signal generation UI (already elsewhere).
- Complex backtesting UI.

## 5. Personas

- Fundamental analyst: values, quality, leverage.
- Quant researcher: factor screening and ranking.
- Technical trader: momentum, trend, and volatility.
- Sentiment-driven trader: news and sentiment momentum.

## 6. UX Principles (GitHub-inspired)

- Dense but legible data table (like GitHub repo lists).
- Compact controls, minimal chrome, strong hierarchy.
- Inline filters, chips, and status indicators.
- Clear tooltips and predictable keyboard navigation.

## 7. Analytics Component Requirements

### 7.1 Core requirements
1) Selection of predefined rule set.
2) Configure / CRUD rules and rule sets.
3) Search and filter (symbol, sector, category, metric thresholds).
4) Table with row per symbol and sorting on score.
5) Quick order popup (buy/sell, qty or notional) using Alpaca.
6) Show any portfolio holding in the table.

### 7.2 Table behavior
- Columns are user-configurable from metric catalog.
- Default columns: Symbol, Score, Rank, Percentile, Sector, Last Price, Holding, Sentiment Score.
- Each metric column shows value and optional rank/percentile on hover.
- Sorting: by composite score (default), or by any column.
- Pagination: server-side (100 rows default).
- Row click navigates to Symbol History page.

### 7.3 Tooltips
- Hover on column header shows metric name, description, source, direction.
- Tooltip text comes from derived_metric_definitions.

### 7.4 Rule configuration
- Rule set CRUD: create, rename, duplicate, delete, enable/disable.
- Rule CRUD: add metric, operator, thresholds, weight, normalize raw/zscore/percentile.
- Required rule flag to hard-filter symbols.
- Save and instantly re-score (async with loading state).

### 7.5 Quick order
- Button per row: "Trade" opens modal.
- Inputs: side, qty or notional, order type (market, limit, opg if supported by backend rules).
- Show estimated price, notional, and warnings if market closed.
- Submit to backend order endpoint (existing flow) and show status.

## 8. Pre-seeded Rule Sets (at least 4)

1) Quality + Momentum
- Required: mom_6m > 0
- Score = zscore(roic) * 0.6 + zscore(mom_6m) * 0.4

2) Value + Low Volatility
- Required: earnings_yield > 0
- Score = percentile(earnings_yield) * 0.6 + percentile(vol_20d, lower_is_better) * 0.4

3) Sentiment Breakout
- Required: sentiment_mom > 0
- Score = percentile(sentiment_mom) * 0.5 + percentile(mom_3m) * 0.5

4) Defensive Quality
- Required: debt_to_equity < 1
- Score = zscore(roic) * 0.4 + percentile(vol_20d, lower_is_better) * 0.3 + percentile(beta, lower_is_better) * 0.3

## 9. Data Sources and Freshness

- Daily metrics update after market close.
- Scores updated after metrics calculation and rule evaluation.
- UI shows timestamp of last metrics update.

## 10. Required API Endpoints (Aligned with `/api/v1/*`)

### Metric catalog and values
- GET `/api/v1/metrics/derived/definitions`
  - Query: `category`, `active=true`, `version=v1`
  - Returns metric definitions for column picker and tooltips.

- GET `/api/v1/metrics/derived/values`
  - Query: `as_of_date`, `symbol`, `metric_keys[]`
  - Returns metric values (value, zscore, percentile, rank).

### Rule sets and rules (CRUD)
- GET `/api/v1/metrics/derived/rule-sets`
- POST `/api/v1/metrics/derived/rule-sets`
- PATCH `/api/v1/metrics/derived/rule-sets/{id}`
- DELETE `/api/v1/metrics/derived/rule-sets/{id}`

- GET `/api/v1/metrics/derived/rule-sets/{id}/rules`
- POST `/api/v1/metrics/derived/rule-sets/{id}/rules`
- PATCH `/api/v1/metrics/derived/rules/{id}`
- DELETE `/api/v1/metrics/derived/rules/{id}`

### Scored table queries (filtering and sorting)
- GET `/api/v1/metrics/derived/scores`
  - Query: `rule_set_id`, `as_of_date`, `search`, `universe_id`,
    `sector`, `industry`, `min_score`, `max_score`,
    `sort=score|rank|symbol|metric:<metric_key>`, `order=asc|desc`,
    `page`, `page_size`, `columns[]` (metric_keys to include)
  - Returns rows: symbol, score, rank, percentile, holdings, selected metrics

- POST `/api/v1/metrics/derived/scores/query`
  - Body (for complex filters):
    ```json
    {
      "rule_set_id": 12,
      "as_of_date": "2026-01-11",
      "search": "A",
      "universe_id": 3,
      "filters": [
        {"field": "sector", "op": "=", "value": "Technology"},
        {"field": "metric", "metric_key": "mom_6m", "op": ">", "value": 0},
        {"field": "metric", "metric_key": "pe_ttm", "op": "<", "value": 20}
      ],
      "sort": {"field": "score", "order": "desc"},
      "columns": ["mom_6m", "pe_ttm", "sentiment_score"],
      "page": 1,
      "page_size": 100
    }
    ```

### Holdings / portfolio integration
- GET `/api/v1/portfolio/holdings`
  - Query: `portfolio_id`, `as_of`

### Quick order
- POST `/api/v1/orders`
  - Body: `symbol`, `side`, `qty` or `notional`, `type`, `time_in_force`
  - Returns order_id and status.

### Symbol detail links
- GET `/api/v1/instruments/{symbol}`
- GET `/api/v1/instruments/{symbol}/prices`
- GET `/api/v1/instruments/{symbol}/sentiment`

## 11. UI Components

- AnalyticsHeader: rule set selector, search bar, date selector.
- RuleSetDrawer: CRUD UI for rule sets and rules.
- MetricColumnPicker: multi-select of metric columns.
- AnalyticsTable: sortable, virtualized table with row actions.
- QuickOrderModal: order entry and submit.
- MetricTooltip: tooltips for definitions.
- StatusBar: last update time, refresh, number of symbols.

## 12. States and Loading

- Loading: when fetching scores and metrics.
- Empty: no rule set selected or no matches.
- Error: API failure with retry.
- Partial data: some symbols missing metrics (display "--").

## 13. Permissions

- Read-only for most users.
- Rule set CRUD restricted to admin roles.
- Order placement requires trader role.

## 14. Analytics and Observability

- Track rule set usage, column configuration changes, and order submissions.
- Log performance for table fetch and filtering.

## 15. Open Questions

- Should rule set scores persist for historical dates for backtesting view?
- Should order types be restricted per broker mode (paper/live)?
- Do we want a global "favorites" list for symbols?

## 16. Acceptance Criteria

- User can select a rule set and see ranked symbols.
- User can add/remove columns from the metric table.
- User can create and edit rule sets and see updated rankings.
- Tooltips show metric definitions for all metric columns.
- User can submit an order from the table with confirmation.
- Holdings are visible inline in the table.
