-- Protected mart model: deduplicates active customer records to prevent
-- unintended join fanout and revenue inflation when customer dimension contains
-- multiple active versions.

with completed_orders as (
    select *
    from {{ ref('stg_orders') }}
    where status = 'completed'
),
active_customers as (
    select
        customer_id,
        country,
        tier,
        valid_from,
        row_number() over (
            partition by customer_id
            order by valid_from desc nulls last
        ) as rn
    from {{ ref('stg_customers') }}
    where is_active = true
),
deduped_customers as (
    select *
    from active_customers
    where rn = 1
)
select
    o.order_date,
    count(*) as completed_order_rows,
    sum(o.amount_usd) as daily_revenue
from completed_orders o
left join deduped_customers c
    on o.customer_id = c.customer_id
group by 1
order by 1

