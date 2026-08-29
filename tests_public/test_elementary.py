from observability.elementary_oss import ElementaryOSSEngine, ElementaryTestResult


def test_elementary_schema_drift_detection():
    engine = ElementaryOSSEngine()
    baseline_schema = {'order_id': 'integer', 'amount': 'float', 'status': 'string'}
    current_schema = {'order_id': 'string', 'amount': 'float', 'new_field': 'boolean'}

    drift = engine.detect_schema_drift(current_schema, baseline_schema)
    drift_types = {d['change_type'] for d in drift}

    assert 'column_removed' in drift_types  # status removed
    assert 'column_added' in drift_types    # new_field added
    assert 'type_changed' in drift_types    # order_id integer -> string


def test_elementary_alert_generation():
    engine = ElementaryOSSEngine()
    mock_test_results = [
        ElementaryTestResult(
            id='tr_1',
            data_issue_id='issue_1',
            test_execution_id='exec_1',
            test_unique_id='test.unique_orders_order_id',
            model_unique_id='model.orders',
            table_name='orders',
            column_name='order_id',
            test_type='dbt_test',
            test_sub_type='unique',
            test_name='unique',
            status='fail',
            failures=5,
            detected_at='2026-08-29T10:00:00Z',
            test_params={'column_name': 'order_id'},
            test_results_description='Got 5 duplicate keys',
        ),
        ElementaryTestResult(
            id='tr_2',
            data_issue_id='issue_2',
            test_execution_id='exec_1',
            test_unique_id='test.not_null_orders_order_id',
            model_unique_id='model.orders',
            table_name='orders',
            column_name='order_id',
            test_type='dbt_test',
            test_sub_type='not_null',
            test_name='not_null',
            status='pass',
            failures=0,
            detected_at='2026-08-29T10:00:00Z',
        ),
    ]

    alerts = engine.generate_alerts(mock_test_results)
    assert len(alerts) == 1
    assert alerts[0].severity == 'critical'
    assert alerts[0].table_name == 'orders'
    assert alerts[0].column_name == 'order_id'
