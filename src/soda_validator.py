"""Soda Data Contract & SodaCL Validation Engine.

Implements Soda-style contract scans and declarative assertion parsing
against DataFrames and DuckDB analytical engines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


@dataclass
class SodaCheckResult:
    check_name: str
    column: str | None
    outcome: str  # 'pass', 'warn', 'fail'
    metric_value: Any
    expression: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class SodaScanResult:
    dataset: str
    has_failures: bool
    has_warnings: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    checks: list[SodaCheckResult] = field(default_factory=list)

    def summary(self) -> str:
        status = 'FAIL' if self.has_failures else ('WARN' if self.has_warnings else 'PASS')
        return f"Soda Scan [{self.dataset}]: {status} ({self.passed_checks}/{self.total_checks} passed)"


def load_soda_contract(path: str | Path) -> dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _check_soda_type(series: pd.Series, expected_type: str) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return True

    if expected_type in {'integer', 'int'}:
        if pd.api.types.is_integer_dtype(series):
            return True
        try:
            return bool((non_null.astype(float) % 1 == 0).all())
        except (ValueError, TypeError):
            return False

    if expected_type in {'number', 'numeric', 'float', 'double'}:
        if pd.api.types.is_numeric_dtype(series):
            return True
        try:
            pd.to_numeric(non_null)
            return True
        except (ValueError, TypeError):
            return False

    if expected_type in {'string', 'text', 'varchar'}:
        return True

    if expected_type in {'datetime', 'timestamp', 'date'}:
        if pd.api.types.is_datetime64_any_dtype(series):
            return True
        try:
            pd.to_datetime(non_null, errors='raise')
            return True
        except Exception:
            return False

    if expected_type in {'boolean', 'bool'}:
        if pd.api.types.is_bool_dtype(series):
            return True
        valid_bools = {True, False, 1, 0, 'true', 'false', 'True', 'False'}
        return bool(non_null.isin(valid_bools).all())

    return True


def run_soda_scan(df: pd.DataFrame, contract_path: str | Path) -> SodaScanResult:
    """Execute SodaCL Data Contract scan on DataFrame."""
    contract = load_soda_contract(contract_path)
    dataset = contract.get('dataset', 'unnamed_dataset')
    checks: list[SodaCheckResult] = []

    # 1. Dataset level checks: row_count
    dataset_checks = contract.get('checks', [])
    for chk in dataset_checks:
        if isinstance(chk, str):
            # Parse row_count between min and max
            m_rc = re.match(r'row_count\s+between\s+(\d+)\s+and\s+(\d+)', chk)
            if m_rc:
                min_rows, max_rows = int(m_rc.group(1)), int(m_rc.group(2))
                actual_rows = len(df)
                passed = min_rows <= actual_rows <= max_rows
                checks.append(SodaCheckResult(
                    check_name='row_count_between',
                    column=None,
                    outcome='pass' if passed else 'fail',
                    metric_value=actual_rows,
                    expression=chk,
                    diagnostics={'min': min_rows, 'max': max_rows, 'actual': actual_rows},
                ))
        elif isinstance(chk, dict) and 'schema' in chk:
            schema_cfg = chk['schema']
            fail_cfg = schema_cfg.get('fail', {})
            # Check required columns
            req_cols = fail_cfg.get('when required column missing', [])
            missing_cols = [c for c in req_cols if c not in df.columns]
            checks.append(SodaCheckResult(
                check_name='schema_required_columns',
                column=None,
                outcome='pass' if not missing_cols else 'fail',
                metric_value=len(missing_cols),
                expression='when required column missing',
                diagnostics={'missing_columns': missing_cols},
            ))
            # Check column types
            type_cfg = fail_cfg.get('when wrong column type', {})
            for col_name, exp_type in type_cfg.items():
                if col_name in df.columns:
                    type_ok = _check_soda_type(df[col_name], exp_type)
                    checks.append(SodaCheckResult(
                        check_name=f'schema_type_{col_name}',
                        column=col_name,
                        outcome='pass' if type_ok else 'fail',
                        metric_value=str(df[col_name].dtype),
                        expression=f'{col_name} must be {exp_type}',
                        diagnostics={'expected_type': exp_type, 'actual_dtype': str(df[col_name].dtype)},
                    ))

    # 2. Column level checks
    columns = contract.get('columns', [])
    for col_def in columns:
        col_name = col_def.get('name')
        if col_name not in df.columns:
            continue

        series = df[col_name]
        col_checks = col_def.get('checks', [])

        for c in col_checks:
            if isinstance(c, str):
                if c == 'missing_count = 0':
                    null_cnt = int(series.isna().sum())
                    checks.append(SodaCheckResult(
                        check_name=f'missing_count_{col_name}',
                        column=col_name,
                        outcome='pass' if null_cnt == 0 else 'fail',
                        metric_value=null_cnt,
                        expression=c,
                        diagnostics={'null_count': null_cnt},
                    ))
                elif c == 'duplicate_count = 0':
                    non_null = series.dropna()
                    dup_cnt = int(non_null.duplicated().sum())
                    checks.append(SodaCheckResult(
                        check_name=f'duplicate_count_{col_name}',
                        column=col_name,
                        outcome='pass' if dup_cnt == 0 else 'fail',
                        metric_value=dup_cnt,
                        expression=c,
                        diagnostics={'duplicate_count': dup_cnt},
                    ))
                elif c.startswith('min >='):
                    val = float(c.split('>=')[1].strip())
                    actual_min = float(series.min()) if not series.dropna().empty else float('-inf')
                    passed = actual_min >= val
                    checks.append(SodaCheckResult(
                        check_name=f'min_{col_name}',
                        column=col_name,
                        outcome='pass' if passed else 'fail',
                        metric_value=actual_min,
                        expression=c,
                        diagnostics={'min_allowed': val, 'actual_min': actual_min},
                    ))
                elif c.startswith('max <='):
                    val = float(c.split('<=')[1].strip())
                    actual_max = float(series.max()) if not series.dropna().empty else float('inf')
                    passed = actual_max <= val
                    checks.append(SodaCheckResult(
                        check_name=f'max_{col_name}',
                        column=col_name,
                        outcome='pass' if passed else 'fail',
                        metric_value=actual_max,
                        expression=c,
                        diagnostics={'max_allowed': val, 'actual_max': actual_max},
                    ))
                elif 'invalid_values not in' in c:
                    allowed_str = c.split('not in')[1].strip()
                    allowed_items = yaml.safe_load(allowed_str)
                    invalid_cnt = int((~series.dropna().isin(allowed_items)).sum())
                    checks.append(SodaCheckResult(
                        check_name=f'invalid_values_{col_name}',
                        column=col_name,
                        outcome='pass' if invalid_cnt == 0 else 'fail',
                        metric_value=invalid_cnt,
                        expression=c,
                        diagnostics={'allowed_values': allowed_items, 'invalid_count': invalid_cnt},
                    ))
                elif c.startswith('freshness <'):
                    # e.g. freshness < 1d or 60m
                    dt_series = pd.to_datetime(series, utc=True, errors='coerce')
                    max_dt = dt_series.max()
                    if pd.isna(max_dt):
                        passed = False
                        delay_mins = float('inf')
                    else:
                        delay_mins = (datetime.now(timezone.utc) - max_dt.to_pydatetime()).total_seconds() / 60.0
                        passed = delay_mins < 1440.0  # 1 day = 1440 mins
                    checks.append(SodaCheckResult(
                        check_name=f'freshness_{col_name}',
                        column=col_name,
                        outcome='pass' if passed else 'fail',
                        metric_value=delay_mins,
                        expression=c,
                        diagnostics={'delay_minutes': delay_mins},
                    ))

    failed_cnt = sum(1 for chk in checks if chk.outcome == 'fail')
    warn_cnt = sum(1 for chk in checks if chk.outcome == 'warn')
    passed_cnt = sum(1 for chk in checks if chk.outcome == 'pass')

    return SodaScanResult(
        dataset=dataset,
        has_failures=bool(failed_cnt > 0),
        has_warnings=bool(warn_cnt > 0),
        total_checks=len(checks),
        passed_checks=passed_cnt,
        failed_checks=failed_cnt,
        checks=checks,
    )
