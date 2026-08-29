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

## Decision 3
- Hypothesis:
- Prompt / request to agent:
- Agent proposal:
- Evidence/test:
- Accept / reject / revise:
- Why:


