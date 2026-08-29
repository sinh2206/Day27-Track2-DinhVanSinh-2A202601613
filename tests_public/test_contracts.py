from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from src.contract_validator import determine_action, load_contract, quarantine_invalid_rows
from student_api import validate_orders

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "orders_contract.yaml"


def healthy_df():
    now = pd.Timestamp.now(tz="UTC")
    return pd.DataFrame([
        {
            "order_id": 1,
            "customer_id": "C1",
            "amount": 10.0,
            "currency": "USD",
            "status": "completed",
            "created_at": (now - pd.Timedelta(minutes=10)).isoformat(),
            "updated_at": (now - pd.Timedelta(minutes=5)).isoformat(),
        },
        {
            "order_id": 2,
            "customer_id": "C2",
            "amount": 20.0,
            "currency": "USD",
            "status": "pending",
            "created_at": (now - pd.Timedelta(minutes=9)).isoformat(),
            "updated_at": (now - pd.Timedelta(minutes=4)).isoformat(),
        },
    ])


def failed(issues):
    return [i for i in issues if not i["passed"]]


def test_healthy_contract_passes_starter_checks():
    assert not failed(validate_orders(healthy_df(), CONTRACT))


def test_duplicate_order_id_is_detected():
    df = healthy_df()
    df.loc[1, "order_id"] = 1
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "unique" and i["column"] == "order_id" for i in issues)


def test_invalid_currency_is_detected():
    df = healthy_df()
    df.loc[0, "currency"] = "BTC"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "accepted_values" and i["column"] == "currency" for i in issues)


def test_type_drift_is_detected():
    df = healthy_df()
    df.loc[0, "order_id"] = "not_an_integer"
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "type" and i["column"] == "order_id" for i in issues)


def test_freshness_delay_is_detected():
    df = healthy_df()
    old_time = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=2)).isoformat()
    df["updated_at"] = old_time
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "freshness" and i["column"] == "updated_at" for i in issues)


def test_missing_required_column_is_detected():
    df = healthy_df().drop(columns=["customer_id"])
    issues = failed(validate_orders(df, CONTRACT))
    assert any(i["check"] == "required_column" and i["column"] == "customer_id" for i in issues)


def test_severity_and_action_determination():
    df = healthy_df()
    df.loc[1, "order_id"] = 1  # critical failure
    issues = validate_orders(df, CONTRACT)
    action = determine_action(issues)
    assert action == "block"


def test_quarantine_helper():
    contract = load_contract(CONTRACT)
    df = healthy_df()
    df.loc[1, "amount"] = -50.0  # violates min: 0
    clean_df, quarantine_df = quarantine_invalid_rows(df, contract)
    assert len(clean_df) == 1
    assert len(quarantine_df) == 1
    assert clean_df.iloc[0]["order_id"] == 1
    assert quarantine_df.iloc[0]["order_id"] == 2

