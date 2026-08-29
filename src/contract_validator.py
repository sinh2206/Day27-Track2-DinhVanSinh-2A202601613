"""Contract validator for Data Contracts.

Covers deterministic checks:
- Required column presence
- Nullability (not_null)
- Uniqueness (unique)
- Type drift & strict type checking (integer, number/float, string, datetime, boolean)
- Range constraints (min, max)
- String length constraints (min_length, max_length)
- Accepted values set
- Contract-level freshness check
- Severity classification (critical, warning, info)
- Severity-aware actions (block, quarantine, warn)
- Quarantine helper for separating invalid rows
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
    action: str | None = None,
) -> dict[str, Any]:
    if action is None:
        severity_lower = severity.lower()
        if severity_lower == "critical":
            action = "block"
        elif severity_lower == "warning":
            action = "warn"
        else:
            action = "info"

    return {
        "check": check,
        "column": column,
        "severity": severity,
        "passed": bool(passed),
        "details": details,
        "action": action,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _check_type(series: pd.Series, declared_type: str) -> tuple[bool, int, str]:
    """Validate series values against declared type without hiding errors."""
    non_null = series.dropna()
    if non_null.empty:
        return True, 0, f"type={declared_type}; null_series=True"

    dtype_str = declared_type.lower()
    invalid_mask = pd.Series(False, index=non_null.index)

    if dtype_str in {"integer", "int", "int64", "int32"}:
        if pd.api.types.is_integer_dtype(non_null.dtype):
            invalid_count = 0
        else:
            def _is_int(val: Any) -> bool:
                if isinstance(val, (int, np.integer)):
                    return True
                if isinstance(val, (float, np.floating)):
                    return float(val).is_integer()
                if isinstance(val, str):
                    s = val.strip()
                    try:
                        int(s)
                        return True
                    except ValueError:
                        return False
                return False

            invalid_mask = ~non_null.apply(_is_int)
            invalid_count = int(invalid_mask.sum())

    elif dtype_str in {"number", "float", "numeric", "double", "float64", "float32"}:
        if pd.api.types.is_numeric_dtype(non_null.dtype):
            invalid_count = 0
        else:
            def _is_float(val: Any) -> bool:
                if isinstance(val, (int, float, np.number)):
                    return True
                if isinstance(val, str):
                    try:
                        float(val.strip())
                        return True
                    except ValueError:
                        return False
                return False

            invalid_mask = ~non_null.apply(_is_float)
            invalid_count = int(invalid_mask.sum())

    elif dtype_str in {"string", "str", "text"}:
        def _is_str(val: Any) -> bool:
            return isinstance(val, str)

        invalid_mask = ~non_null.apply(_is_str)
        invalid_count = int(invalid_mask.sum())

    elif dtype_str in {"datetime", "date", "timestamp"}:
        if pd.api.types.is_datetime64_any_dtype(non_null.dtype):
            invalid_count = 0
        else:
            parsed = pd.to_datetime(non_null, errors="coerce", utc=True)
            invalid_mask = parsed.isna()
            invalid_count = int(invalid_mask.sum())

    elif dtype_str in {"boolean", "bool"}:
        if pd.api.types.is_bool_dtype(non_null.dtype):
            invalid_count = 0
        else:
            valid_bools = {True, False, 1, 0, "true", "false", "True", "False", "1", "0"}
            invalid_mask = ~non_null.isin(valid_bools)
            invalid_count = int(invalid_mask.sum())

    else:
        # Fallback unknown type: treat as passed with note
        return True, 0, f"unsupported_type_check={declared_type}"

    passed = (invalid_count == 0)
    details = f"expected_type={declared_type}; invalid_count={invalid_count}"
    return passed, invalid_count, details


def validate_dataframe(
    df: pd.DataFrame,
    contract: dict[str, Any],
    *,
    now: Any = None,
) -> list[dict[str, Any]]:
    """Validate DataFrame against a Data Contract dictionary."""
    issues: list[dict[str, Any]] = []

    # Support both 'columns' and 'fields' contract schemas
    columns: dict[str, Any] = contract.get("columns") or contract.get("fields") or {}

    for column, rules in columns.items():
        severity = rules.get("severity", "warning")
        action = rules.get("action")
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                        action=action,
                    )
                )
            continue

        series = df[column]

        # 1. Nullability check
        if required or rules.get("not_null") or rules.get("nullable") is False:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                    action=action,
                )
            )

        # 2. Uniqueness check
        if rules.get("unique"):
            non_null = series.dropna()
            duplicate_count = int(non_null.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                    action=action,
                )
            )

        # 3. Type check
        if "type" in rules:
            passed_type, _, type_details = _check_type(series, rules["type"])
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=passed_type,
                    details=type_details,
                    action=action,
                )
            )

        # 4. Accepted values check
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                    action=action,
                )
            )

        # 5. Numeric range check
        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                    action=action,
                )
            )

        # 6. String length check
        if "min_length" in rules or "max_length" in rules:
            str_series = series.dropna().astype(str)
            lengths = str_series.str.len()
            invalid = pd.Series(False, index=str_series.index)
            if "min_length" in rules:
                invalid |= lengths < rules["min_length"]
            if "max_length" in rules:
                invalid |= lengths > rules["max_length"]
            invalid_count = int(invalid.sum())
            issues.append(
                _issue(
                    "length",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_length_count={invalid_count}",
                    action=action,
                )
            )

    # 7. Freshness check
    if "freshness" in contract:
        freshness = contract["freshness"]
        fresh_col = freshness.get("column")
        max_delay = freshness.get("max_delay_minutes", freshness.get("max_delay_hours", 0) * 60)
        fresh_severity = freshness.get("severity", "warning")
        fresh_action = freshness.get("action")

        if not fresh_col or fresh_col not in df.columns:
            issues.append(
                _issue(
                    "freshness",
                    column=fresh_col,
                    severity=fresh_severity,
                    passed=False,
                    details=f"Freshness column '{fresh_col}' missing from dataframe",
                    action=fresh_action,
                )
            )
        else:
            ts = pd.to_datetime(df[fresh_col], utc=True, errors="coerce").dropna()
            if ts.empty:
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_severity,
                        passed=False,
                        details=f"No valid datetime values in freshness column '{fresh_col}'",
                        action=fresh_action,
                    )
                )
            else:
                max_ts = ts.max()
                ref_time = now if now is not None else pd.Timestamp.now(tz="UTC")
                ref_time = pd.to_datetime(ref_time, utc=True)
                delay_minutes = (ref_time - max_ts).total_seconds() / 60.0

                passed_fresh = bool(delay_minutes <= max_delay)
                issues.append(
                    _issue(
                        "freshness",
                        column=fresh_col,
                        severity=fresh_severity,
                        passed=passed_fresh,
                        details=f"delay_minutes={delay_minutes:.2f}; max_delay_minutes={max_delay}; latest_timestamp={max_ts.isoformat()}",
                        action=fresh_action,
                    )
                )

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    """Filter issues to only failed ones, optionally filtered by minimum severity."""
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    order = {"info": 0, "warning": 1, "critical": 2}
    threshold = order.get(min_severity.lower(), 1)
    return [i for i in failed if order.get(i.get("severity", "warning").lower(), 1) >= threshold]


def determine_action(issues: list[dict[str, Any]]) -> str:
    """Determine downstream pipeline action based on validation results."""
    failed = [i for i in issues if not i.get("passed", False)]
    if not failed:
        return "pass"

    # Check for blocking / critical failures
    for issue in failed:
        if issue.get("action") == "block" or issue.get("severity") == "critical":
            return "block"

    # Check for quarantine requests
    for issue in failed:
        if issue.get("action") == "quarantine":
            return "quarantine"

    # Check for warnings
    for issue in failed:
        if issue.get("action") == "warn" or issue.get("severity") == "warning":
            return "warn"

    return "info"


def quarantine_invalid_rows(
    df: pd.DataFrame,
    contract: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split dataframe into clean rows and quarantined invalid rows."""
    columns = contract.get("columns") or contract.get("fields") or {}
    invalid_mask = pd.Series(False, index=df.index)

    for col, rules in columns.items():
        if col not in df.columns:
            if rules.get("required"):
                return df.iloc[0:0], df.copy()
            continue

        s = df[col]
        # Not null
        if rules.get("required") or rules.get("not_null") or rules.get("nullable") is False:
            invalid_mask |= s.isna()

        # Unique
        if rules.get("unique"):
            invalid_mask |= s.duplicated(keep=False)

        # Accepted values
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask |= (s.notna() & ~s.isin(accepted))

        # Range
        if "min" in rules or "max" in rules:
            num = pd.to_numeric(s, errors="coerce")
            if "min" in rules:
                invalid_mask |= (num < rules["min"]) | num.isna()
            if "max" in rules:
                invalid_mask |= (num > rules["max"]) | num.isna()

    clean_df = df[~invalid_mask].copy()
    quarantine_df = df[invalid_mask].copy()
    return clean_df, quarantine_df

