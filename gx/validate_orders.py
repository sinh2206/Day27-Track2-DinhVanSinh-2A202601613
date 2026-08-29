#!/usr/bin/env python3
"""Great Expectations Core 1.21 validation workflow for orders dataset.

Implements:
- Data Source & Dataframe Asset
- Expectation Suite covering schema, nullability, uniqueness, sets, ranges, row counts
- Validation Definition
- Checkpoint execution
- Severity classification & Action determination (block / warn)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_expectation_suite(context: gx.DataContext) -> gx.ExpectationSuite:
    """Construct an ExpectationSuite matching the orders data contract."""
    suite = gx.ExpectationSuite(name="orders_contract_suite")

    # Table-level expectations
    suite.add_expectation(gx.expectations.ExpectTableRowCountToBeBetween(min_value=1))

    # Column-level expectations
    # order_id: critical (not null, unique)
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeUnique(column="order_id"))

    # customer_id: critical (not null)
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"))

    # amount: critical (not null, min 0)
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="amount"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0))

    # currency: critical (not null, in [USD, VND])
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="currency"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeInSet(column="currency", value_set=["USD", "VND"]))

    # status: warning (not null, in [pending, completed, refunded, cancelled])
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="status"))
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status",
            value_set=["pending", "completed", "refunded", "cancelled"],
        )
    )

    # created_at & updated_at: critical (not null)
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="created_at"))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column="updated_at"))

    return context.suites.add(suite)


def run_validation(df: pd.DataFrame) -> tuple[bool, str, list[dict]]:
    """Run GX validation checkpoint on orders DataFrame."""
    context = gx.get_context()

    data_source = context.data_sources.add_pandas("orders_pandas")
    asset = data_source.add_dataframe_asset(name="orders_dataframe")
    batch_definition = asset.add_batch_definition_whole_dataframe("whole_orders")

    suite = build_expectation_suite(context)
    validation_definition = gx.ValidationDefinition(
        data=batch_definition,
        suite=suite,
        name="orders_validation_def",
    )
    context.validation_definitions.add(validation_definition)

    checkpoint = gx.Checkpoint(
        name="orders_checkpoint",
        validation_definitions=[validation_definition],
    )
    context.checkpoints.add(checkpoint)

    result = checkpoint.run(batch_parameters={"dataframe": df})

    # Severity mapping for action determination
    warning_expectations = {"ExpectColumnValuesToBeInSet:status"}
    
    details = []
    has_critical_failure = False
    has_warning_failure = False

    for run_result in result.run_results.values():
        for res in run_result.results:
            exp_type = res.expectation_config.type
            kwargs = res.expectation_config.kwargs
            col = kwargs.get("column", "table")
            success = bool(res.success)
            exp_key = f"{exp_type}:{col}"

            is_warning = exp_key in warning_expectations or col == "status"
            severity = "warning" if is_warning else "critical"

            if not success:
                if severity == "critical":
                    has_critical_failure = True
                else:
                    has_warning_failure = True

            details.append({
                "expectation": exp_type,
                "column": col,
                "severity": severity,
                "success": success,
                "result": res.result,
            })

    if has_critical_failure:
        action = "block"
    elif has_warning_failure:
        action = "warn"
    else:
        action = "pass"

    return bool(result.success), action, details


def main() -> None:
    orders_path = ROOT / "data" / "incoming" / "orders.csv"
    if not orders_path.exists():
        raise SystemExit(f"Orders file not found: {orders_path}")

    df = pd.read_csv(orders_path)
    print(f"Loaded {len(df)} rows from {orders_path.name}")
    print("Running Great Expectations Checkpoint...")

    success, action, details = run_validation(df)

    print("\n" + "=" * 65)
    print(f"{'EXPECTATION':<42} {'SEVERITY':<10} {'STATUS'}")
    print("=" * 65)
    for item in details:
        col_str = f" ({item['column']})" if item['column'] != 'table' else ""
        label = f"{item['expectation']}{col_str}"
        status = "PASS" if item["success"] else "FAIL"
        print(f"{label:<42} {item['severity']:<10} {status}")
    print("=" * 65)

    print(f"\nOverall Checkpoint Result : {'PASS' if success else 'FAIL'}")
    print(f"Determined Pipeline Action: {action.upper()}")

    if action == "block":
        print("[ACTION] Critical data contract violation! Blocking ingestion pipeline.")
    elif action == "warn":
        print("[ACTION] Warning contract violation detected. Alert emitted; pipeline continuing.")
    else:
        print("[ACTION] All contract checks passed. Ingestion pipeline proceed.")


if __name__ == "__main__":
    main()

