-- Singular data test: Ensure fct_daily_revenue matches stg_orders completed revenue exactly.
-- Query returns rows when there is a mismatch (e.g. from unexpected join fanout or drop).
with mart_revenue as (
    select
        order_date,
        sum(daily_revenue) as mart_total,
        sum(completed_order_rows) as mart_count
    from {{ ref('fct_daily_revenue') }}
    group by 1
),
staging_revenue as (
    select
        order_date,
        sum(amount_usd) as stg_total,
        count(*) as stg_count
    from {{ ref('stg_orders') }}
    where status = 'completed'
    group by 1
)
select
    coalesce(m.order_date, s.order_date) as order_date,
    m.mart_total,
    s.stg_total,
    m.mart_count,
    s.stg_count
from mart_revenue m
full outer join staging_revenue s
    on m.order_date = s.order_date
where
    abs(coalesce(m.mart_total, 0) - coalesce(s.stg_total, 0)) > 0.01
    or coalesce(m.mart_count, 0) != coalesce(s.stg_count, 0)
