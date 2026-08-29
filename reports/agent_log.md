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

## Decision 2
- Hypothesis:
- Prompt / request to agent:
- Agent proposal:
- Evidence/test:
- Accept / reject / revise:
- Why:

