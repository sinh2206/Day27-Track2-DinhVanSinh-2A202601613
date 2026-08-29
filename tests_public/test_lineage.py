from student_api import column_downstream, downstream_assets


def test_transitive_downstream_assets():
    graph = {
        "raw_orders": ["stg_orders"],
        "stg_orders": ["revenue"],
        "revenue": ["dashboard"],
    }
    assert downstream_assets(graph, "raw_orders") == ["stg_orders", "revenue", "dashboard"]


def test_transitive_column_downstream():
    column_graph = {
        "raw_orders.amount": ["stg_orders.amount_usd"],
        "stg_orders.amount_usd": ["fct_daily_revenue.daily_revenue"],
        "fct_daily_revenue.daily_revenue": ["ceo_revenue_dashboard.revenue"],
    }
    result = column_downstream(column_graph, "raw_orders.amount")
    assert result == [
        "stg_orders.amount_usd",
        "fct_daily_revenue.daily_revenue",
        "ceo_revenue_dashboard.revenue",
    ]


def test_openlineage_event_generation():
    from observability.lineage import create_openlineage_event
    event = create_openlineage_event(
        job_name="stg_orders_to_fct_daily_revenue",
        inputs=["stg_orders", "stg_customers"],
        outputs=["fct_daily_revenue"],
    )
    assert event["eventType"] == "COMPLETE"
    assert event["job"]["name"] == "stg_orders_to_fct_daily_revenue"
    assert len(event["inputs"]) == 2
    assert len(event["outputs"]) == 1
    assert "schemaURL" in event
