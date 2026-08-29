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

## Decision 4: Lineage Blast Radius & Column-Level Traversal (Phase 4)
- Hypothesis: Direct-child lineage mapping only reveals immediate downstream tables (e.g. `raw_orders -> stg_orders`), failing to expose the true transitive blast radius when a specific metric column (e.g. `amount`) is corrupted. Transitive BFS graph traversal at both dataset and column levels is needed to compute impact on executive dashboards.
- Prompt / request to agent: Upgrade `observability/lineage.py` with transitive column-level lineage traversal and manifest parsing.
- Agent proposal:
  1. Implement transitive BFS queue in `get_column_downstream` to traverse from source columns through staging and mart models down to consumer exposures.
  2. Implement `extract_dbt_dataset_graph` to parse dbt `manifest.json`.
- Evidence/test:
  - Column lineage test verified complete dependency chain: `raw_orders.amount` -> `stg_orders.amount_usd` -> `fct_daily_revenue.daily_revenue` -> `ceo_revenue_dashboard.revenue`.
  - Dataset lineage test verified transitive BFS traversal: `raw_orders` -> `stg_orders`, `fct_daily_revenue`, `ceo_revenue_dashboard`.
- Accept / reject / revise: Accept.
- Why: Guarantees precise impact scoping for on-call engineers when deciding incident blast radius.

## Decision 5: SLO Multi-Window Burn-Rate Alerting Policy (Phase 5)
- Hypothesis: Single-window error budget alerting causes severe alert fatigue due to brief, transient error spikes. A multi-window multi-burn-rate policy following Google SRE principles (1h short window + 6h long window) ensures paging triggers only for sustained, critical budget exhaustion.
- Prompt / request to agent: Implement a multi-window burn-rate policy in `observability/slo.py`. Add tests for sustained fast burn (paging) and transient spikes (no page).
- Agent proposal:
  1. Implement `evaluate_multiwindow_burn` requiring both short window ($\ge 14.4\times$) and long window ($\ge 14.4\times$) burn rates to trigger page alerts.
  2. Demote short-window-only spikes to `severity: warning, page: False`.
- Evidence/test:
  - Test `test_sustained_fast_burn_triggers_page` (short=15.0, long=14.8) passed with `page=True, severity="critical"`.
  - Test `test_transient_spike_does_not_page` (short=16.0, long=2.0) passed with `page=False, severity="warning"`.
- Accept / reject / revise: Accept.
- Why: Meets Google SRE reliability standards, avoiding on-call burnout while preserving high-urgency notifications for real outages.

## Decision 6: Mystery Incident Investigation & Root Cause Ranking (Phase 6)
- Hypothesis: By analyzing telemetry strictly from Contract Validation, dbt test assertions, MAD volume detectors, and Transitive Lineage (without inspecting the fault injection scripts), we can rank potential root causes and eliminate false hypotheses with empirical evidence.
- Prompt / request to agent: Do not inspect the fault-injection script. Based only on contract results, dbt tests, anomaly metrics, lineage and SLO output, rank three root-cause hypotheses and list evidence for/against each.
- Agent proposal:
  - **Hypothesis A (Rank 1 - Proven):** Upstream Knowledge Base sync failure causing stale embeddings.
    - *Evidence For:* `kb_contract` freshness failed (`delay_minutes=185.2 > 60`), blast radius traced to `support_agent`.
    - *Evidence Against:* None.
  - **Hypothesis B (Rank 2 - Proven in Mart):** Customer dimension join fanout causing revenue inflation.
    - *Evidence For:* dbt unit test `test_customer_dimension_scd_does_not_inflate_revenue` failed with doubled revenue.
    - *Evidence Against:* Orders contract itself passed schema validation (clean orders).
  - **Hypothesis C (Rank 3 - Refuted):** Data corruption in order amount currencies.
    - *Evidence Against:* All currency values strictly passed contract accepted set `['USD', 'VND']`.
- Evidence/test:
  - Incident report written in `reports/incident_report.md` with complete evidence references and action items.
- Accept / reject / revise: Accept.
- Why: Enforces evidence-driven Root Cause Analysis (RCA) and disciplined postmortem practices.

## Decision 7: Soda Data Contract Integration (Bonus +5)
- Hypothesis: Adding a declarative SodaCL data contract (`contracts/soda/orders_soda_contract.yml`) and Soda-style assertion engine provides industry-standard contract specification supporting schema matching, bounds, invalid sets, and freshness.
- Prompt / request to agent: Integrate Soda Data Contract into the project.
- Agent proposal:
  1. Define SodaCL contract specification in `contracts/soda/orders_soda_contract.yml`.
  2. Implement `src/soda_validator.py` with `run_soda_scan` evaluating dataset-level row counts, schema matching, and column-level checks.
- Evidence/test:
  - `tests_public/test_soda_contract.py` passed: verified healthy contract scan and caught duplicate/invalid currency violations.
- Accept / reject / revise: Accept.
- Why: Standardizes contract declarations with SodaCL syntax across teams.

## Decision 8: Elementary OSS Data Observability Integration (Bonus +5)
- Hypothesis: Parsing dbt execution artifacts (`manifest.json` and `run_results.json`) into Elementary-compatible models (`elementary_test_results`, `schema_columns_snapshot`) enables automated schema change alerts and centralized observability.
- Prompt / request to agent: Integrate Elementary OSS into the data reliability pipeline.
- Agent proposal:
  1. Implement `observability/elementary_oss.py` with `ElementaryOSSEngine`.
  2. Extract test execution telemetry, detect schema drift (column added/removed, type changed), and generate actionable alerts.
- Evidence/test:
  - `tests_public/test_elementary.py` passed: verified schema drift detection and critical alert generation for test failures.
- Accept / reject / revise: Accept.
- Why: Bridges dbt transformation tests with centralized observability and real-time alert routing.






