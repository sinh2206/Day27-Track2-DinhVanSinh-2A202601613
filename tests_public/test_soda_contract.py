from datetime import datetime, timezone
import pandas as pd
from src.soda_validator import run_soda_scan


def test_soda_contract_on_healthy_data():
    now_str = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame([
        {
            'order_id': 1,
            'customer_id': 101,
            'amount': 50.0,
            'currency': 'USD',
            'status': 'completed',
            'created_at': now_str,
            'updated_at': now_str,
        },
        {
            'order_id': 2,
            'customer_id': 102,
            'amount': 120.0,
            'currency': 'VND',
            'status': 'pending',
            'created_at': now_str,
            'updated_at': now_str,
        },
    ] * 60)  # 120 rows to satisfy row_count between 100 and 100000

    # Ensure unique order_ids
    df['order_id'] = range(1, len(df) + 1)

    result = run_soda_scan(df, 'contracts/soda/orders_soda_contract.yml')
    assert result.has_failures is False
    assert result.passed_checks == result.total_checks


def test_soda_contract_catches_duplicate_and_invalid_currency():
    now_str = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame([
        {
            'order_id': 1,
            'customer_id': 101,
            'amount': 50.0,
            'currency': 'INVALID_CURRENCY',  # invalid
            'status': 'completed',
            'created_at': now_str,
            'updated_at': now_str,
        },
        {
            'order_id': 1,  # duplicate
            'customer_id': 102,
            'amount': 120.0,
            'currency': 'USD',
            'status': 'pending',
            'created_at': now_str,
            'updated_at': now_str,
        },
    ] * 60)

    result = run_soda_scan(df, 'contracts/soda/orders_soda_contract.yml')
    assert result.has_failures is True
    failed_check_names = [c.check_name for c in result.checks if c.outcome == 'fail']
    assert 'duplicate_count_order_id' in failed_check_names
    assert 'invalid_values_currency' in failed_check_names
