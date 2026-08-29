# Incident Report: E-commerce Data Corruption & Stale KB Outage

## Severity
**P1 — Critical Data Integrity & AI Support Incident**

## Summary
Pipeline batch ingestion reported `SUCCESS`, but downstream analytics presented revenue discrepancies and the AI Customer Support Agent served obsolete refund policies to customers. Observability telemetry (Data Contracts, dbt Unit Tests, Statistical MAD Anomaly Detectors, and Transitive Lineage) identified two simultaneous root causes: (1) Unhandled active customer records fanout inflating and corrupting revenue calculations, and (2) Upstream KB document ingestion delay (> 3 hours stale) propagating outdated refund policy vectors into the RAG index.

## Detection
- **Signal 1:** `kb_contract.yaml` Freshness validation failed (`delay_minutes > 60` max allowed delay).
- **Signal 2:** dbt Unit Test `test_customer_dimension_scd_does_not_inflate_revenue` failed with `daily_revenue: 100.0 -> 200.0` due to customer join fanout.
- **Signal 3:** Statistical Anomaly Detector flagged significant volume drop (`auto:mad` score > 5.0) during partial ingestion batch.
- **First observed time:** 2026-08-29 02:25:00 UTC

## Root Cause
1. **Dimension Fanout in Revenue Mart:** `fct_daily_revenue.sql` performed a direct `LEFT JOIN` on `stg_customers` filtered by `is_active = true`. Due to upstream SCD Type 2 updates, multiple active records existed for single customer entities, multiplying completed order counts and inflating revenue.
2. **Stale Knowledge Base Ingestion:** Upstream support documentation publisher failed to sync updated refund policy documents on schedule, causing the RAG indexing pipeline to serve embeddings generated from stale text (timestamp lag > 180 minutes).

## Evidence
1. **Contract Failure Evidence:** `kb_contract` validation failed on column `published_at` with `delay_minutes=185.2` (threshold: 60 minutes).
2. **dbt Unit Test Failure:** `test_customer_dimension_scd_does_not_inflate_revenue` output:
   ```text
   actual differs from expected:
   @@,order_date,completed_order_rows,daily_revenue
   → ,2026-08-01,1→2                 ,100.0→200.0
   ```
3. **Statistical Anomaly Evidence:** Injected partial ingestion dropped volume from 600 to 150 rows, triggering `row-count anomaly: True (auto:mad, score=5.53)`.
4. **SLO Breach Evidence:** Multi-window burn rate exceeded critical paging threshold ($>14.4\times$) during sustained contract failures.

## Blast Radius

```text
1. Orders Pipeline Blast Radius:
raw_orders -> stg_orders -> fct_daily_revenue -> ceo_revenue_dashboard

2. Column Lineage Blast Radius:
raw_orders.amount -> stg_orders.amount_usd -> fct_daily_revenue.daily_revenue -> ceo_revenue_dashboard.revenue

3. Knowledge Base / AI Blast Radius:
kb_documents -> kb_active_docs -> rag_index -> support_agent.answer
```

## Mitigation
1. **Ingestion Block & Quarantine:** Activated Great Expectations Checkpoint and Data Contract Validator with `action: block` on critical violations and `quarantine_invalid_rows()` to isolate duplicate/corrupted records before entering warehouse staging.
2. **Mart Deduplication Fix:** Refactored `fct_daily_revenue.sql` with window function `row_number() over (partition by customer_id order by valid_from desc nulls last)` to ensure exactly 1 active customer dimension record per join.
3. **KB Freshness Gate:** Enforced contract freshness gate preventing outdated documents from triggering RAG re-indexing.

## Recovery
- Rebuilt dbt models with `dbt build --project-dir dbt_project --profiles-dir dbt_project` (all 22 models, data tests, and unit tests passing).
- Resynced fresh Knowledge Base documents and re-indexed vector embeddings.

## Verification
- [x] Contract healthy (`orders_contract` & `kb_contract` passed 100%)
- [x] dbt tests healthy (15 generic/singular data tests + 2 unit tests passed)
- [x] Anomaly returned to expected range (`auto:mad` and KS-test within normal bounds)
- [x] SLO healthy / Error budget understood (multi-window burn rate < 1.0)
- [x] Downstream output verified (CEO Dashboard and Support Agent metrics match truth)

## Prevention / Action Items
| Action | Owner | Deadline | Why |
|---|---|---|---|
| Enforce pre-ingestion contract validation in CI/CD & Airflow DAGs | Data Reliability Team | 2026-09-05 | Block malformed batches before landing in raw warehouse |
| Add dbt Unit Tests as mandatory PR check for all Mart models | Analytics Engineering | 2026-09-02 | Prevent join fanout and logic errors from entering production |
| Implement Multi-Window Burn Rate alerting policy in PagerDuty | SRE / Observability | 2026-09-08 | Avoid alert fatigue while ensuring fast response to real outages |
| Automate Knowledge Base staleness alerting & quarantine | AI Platform Team | 2026-09-04 | Prevent outdated customer service policies in LLM RAG pipelines |

