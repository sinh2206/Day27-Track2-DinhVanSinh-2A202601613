# AI Agent Decision Log

## Decision 1: Data Contract & Deterministic Validation (Phase 1)
- Hypothesis: Starter contract validator only covers basic null/unique checks and lacks type drift validation, freshness evaluation, severity-based action policies, and GX suite packaging.
- Prompt / request to agent: Implement Phase 1 Contract + Validation according to LAB_GUIDE.md by modifying `src/contract_validator.py`, `contracts/orders_contract.yaml`, and `gx/validate_orders.py`.
- Agent proposal:
  1. Add strict data type validation (`integer`, `number`, `string`, `datetime`, `boolean`) in `src/contract_validator.py` without silently coercing errors.
  2. Implement contract-level freshness validation checking `updated_at` against `max_delay_minutes`.
  3. Support severity levels (`critical`, `warning`, `info`) and automated actions (`block`, `quarantine`, `warn`).
  4. Package expectations in `gx/validate_orders.py` into a modern GX 1.21 `ExpectationSuite` + `ValidationDefinition` + `Checkpoint`.
  5. Add quarantine splitting helper `quarantine_invalid_rows`.
- Evidence/test:
  - Public test suite passed (15/15 tests passing, including new tests for type drift, freshness breach, missing columns, action determination, quarantine).
  - Injected `duplicate_pk` fault: deterministic validator and GX checkpoint correctly caught uniqueness violation on `order_id`, classified severity as `critical`, and determined action as `BLOCK`.
- Accept / reject / revise: Accept.
- Why: Ensures contract violations (both structural schema, type drift, freshness staleness, and uniqueness) are caught before data enters downstream dbt models, protecting analytical marts.

## Decision 2: dbt Transformation Protection & Unit Testing (Phase 2)
- Hypothesis: `fct_daily_revenue.sql` directly joins `stg_customers` without deduplicating active records. If the customer dimension contains multiple active rows per customer (e.g. unhandled SCD Type 2 or duplicate records), `left join` causes unintended row fanout, inflating completed order count and daily revenue without throwing a SQL error.
- Prompt / request to agent: Implement Phase 2 dbt transformation protection: add generic tests, singular tests, and dbt native unit tests exposing and preventing revenue inflation.
- Agent proposal:
  1. Add generic data tests (`unique`, `not_null`) on `fct_daily_revenue.order_date`, `completed_order_rows`, `stg_orders.amount_usd`, `stg_orders.order_date`, and `stg_customers.is_active`.
  2. Add singular test `assert_daily_revenue_consistency.sql` ensuring total revenue in the mart equals total completed order revenue in staging.
  3. Write native dbt unit tests in `dbt_project/models/marts/unit_tests.yml` simulating multiple active records for a single customer.
  4. Fix `fct_daily_revenue.sql` by adding active customer deduplication using `row_number() over (partition by customer_id order by valid_from desc)`.
- Evidence/test:
  - Unit test `test_customer_dimension_scd_does_not_inflate_revenue` failed on the original model (`completed_order_rows: 1 -> 2`, `daily_revenue: 100.0 -> 200.0`), successfully exposing the inflation bug.
  - After deduplication logic was added, both unit tests passed (`PASS=2`).
  - Full `dbt build` executed successfully: 2 seeds, 3 models, 15 data tests, 2 unit tests (`PASS=22, ERROR=0`).
- Accept / reject / revise: Accept.
- Why: Combines data-at-rest assertions (generic/singular data tests) with transformation logic verification (dbt native unit tests), preventing silent financial reporting inflation.

## Decision 3: Statistical Anomaly Detection & Distribution Drift (Phase 3)
- Hypothesis: Global naive Z-score produces false alarms on seasonal fluctuations (e.g. weekend vs weekday traffic) and is susceptible to outlier masking. A robust Median Absolute Deviation (MAD) detector combined with same-weekday context and KS-test distribution drift will accurately detect genuine data volume anomalies (e.g. partial ingestion drops).
- Prompt / request to agent: Implement Phase 3 Anomaly Detection: enhance `observability/anomaly.py` with robust MAD, zero-MAD edge handling, and context-aware `auto` mode; upgrade `observability/distribution.py` with Kolmogorov-Smirnov test.
- Agent proposal:
  1. Implement Boris Iglewicz and David Hoaglin's Modified Z-score in `mad_detector` with proper handling for uniform histories ($\text{MAD}=0$).
  2. Implement context-aware routing in `detect_anomaly(..., method='auto')` to leverage `same_segment_history` (day-of-week) and adjust thresholds for `known_event`.
  3. Upgrade `detect_distribution_shift` in `observability/distribution.py` to use two-sample Kolmogorov-Smirnov (`scipy.stats.ks_2samp`) for distribution shape drift.
- Evidence/test:
  - 19/19 public tests passed in pytest.
  - Injected `volume_drop` fault (75% drop to 150 rows): detected as anomaly (`is_anomaly=True`, `method=auto:mad`, `score=5.53`) while deterministic contract checks reported 0 failures.
  - Zero-MAD test passed: identical history with normal input returns `is_anomaly=False`, with perturbed input returns `is_anomaly=True`.
- Accept / reject / revise: Accept.
- Why: Provides resilient anomaly detection across metric streams without false positives from predictable seasonality.

## Decision 4: Lineage Blast Radius, Multi-Window SLO, & RAG Observability (Phases 4–6)
- Hypothesis: Single-window SLO alerts create alert fatigue from transient spikes, while direct-child lineage fails to track the full downstream blast radius of corrupted column metrics. In addition, RAG systems require continuous embedding and text drift tracking to catch stale knowledge base documents.
- Prompt / request to agent: Implement transitive column lineage traversal in `observability/lineage.py`, Google SRE multi-window burn rate evaluation in `observability/slo.py`, and embedding drift detection in `observability/rag_metrics.py`.
- Agent proposal:
  1. Implement transitive BFS traversal in `get_column_downstream` to trace end-to-end column dependencies from `raw_orders.amount` to `ceo_revenue_dashboard.revenue`.
  2. Implement `evaluate_multiwindow_burn` with Google SRE 1h (short) and 6h (long) window policies, distinguishing transient spikes (`page=False, severity=warning`) from sustained critical burn rates (`page=True, severity=critical`).
  3. Implement `detect_embedding_norm_shift` in `observability/rag_metrics.py` to monitor vector embedding norms.
- Evidence/test:
  - 23/23 tests passed in pytest suite.
  - Multi-window tests verified: sustained 15.0x burn pages on call (`page=True`), whereas 16.0x short spike with 2.0x long burn suppresses page (`page=False`).
  - Column lineage test verified complete chain: `raw_orders.amount` -> `stg_orders.amount_usd` -> `fct_daily_revenue.daily_revenue` -> `ceo_revenue_dashboard.revenue`.
  - Injected `stale_kb` fault: accurately flagged freshness violation and surfaced blast radius to `kb_active_docs -> rag_index -> support_agent`.
- Accept / reject / revise: Accept.
- Why: Provides complete operational visibility, protects SRE teams from alert fatigue, and guarantees AI Support Agent reliability.




