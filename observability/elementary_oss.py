"""Elementary OSS Data Observability Engine.

Implements Elementary-compatible dbt telemetry extraction, schema change detection,
anomaly metrics monitoring, and alert generation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ElementaryTestResult:
    id: str
    data_issue_id: str
    test_execution_id: str
    test_unique_id: str
    model_unique_id: str
    table_name: str
    column_name: str | None
    test_type: str  # 'dbt_test', 'schema_change', 'anomaly_detection'
    test_sub_type: str
    test_name: str
    status: str  # 'pass', 'warn', 'fail', 'error'
    failures: int | None
    detected_at: str
    test_params: dict[str, Any] = field(default_factory=dict)
    test_results_description: str = ''


@dataclass
class ElementaryModelRunResult:
    model_execution_id: str
    unique_id: str
    invocation_id: str
    name: str
    status: str
    execution_time: float
    rows_affected: int | None
    materialization: str
    compiled_code: str = ''


@dataclass
class ElementaryAlert:
    alert_id: str
    alert_type: str  # 'test', 'model', 'schema_change'
    status: str
    title: str
    description: str
    table_name: str
    column_name: str | None
    detected_at: str
    severity: str  # 'critical', 'warning', 'info'


class ElementaryOSSEngine:
    """Elementary OSS Observability collector and analyzer."""

    def __init__(self, dbt_project_dir: str | Path = 'dbt_project') -> None:
        self.project_dir = Path(dbt_project_dir)
        self.target_dir = self.project_dir / 'target'

    def extract_test_results(self) -> list[ElementaryTestResult]:
        run_results_path = self.target_dir / 'run_results.json'
        manifest_path = self.target_dir / 'manifest.json'

        if not run_results_path.exists():
            return []

        with open(run_results_path, 'r', encoding='utf-8') as f:
            run_results = json.load(f)

        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

        nodes = manifest.get('nodes', {})
        elementary_results: list[ElementaryTestResult] = []

        for idx, res in enumerate(run_results.get('results', [])):
            uid = res.get('unique_id', '')
            if not uid.startswith('test.'):
                continue

            node_info = nodes.get(uid, {})
            test_metadata = node_info.get('test_metadata', {})
            test_name = test_metadata.get('name', uid.split('.')[-2] if len(uid.split('.')) > 2 else uid)

            # Extract target model and column
            depends_on = node_info.get('depends_on', {}).get('nodes', [])
            model_uid = depends_on[0] if depends_on else 'unknown'
            table_name = model_uid.split('.')[-1] if model_uid != 'unknown' else 'unknown'
            column_name = test_metadata.get('params', {}).get('column_name')

            status = res.get('status', 'unknown')
            failures = res.get('failures', 0 if status == 'pass' else 1)

            elementary_results.append(ElementaryTestResult(
                id=f'elem_{idx}_{uid}',
                data_issue_id=f'issue_{uid}',
                test_execution_id=run_results.get('invocation_id', 'local_run'),
                test_unique_id=uid,
                model_unique_id=model_uid,
                table_name=table_name,
                column_name=column_name,
                test_type='dbt_test',
                test_sub_type=test_name,
                test_name=test_name,
                status=status,
                failures=failures,
                detected_at=datetime.now(timezone.utc).isoformat(),
                test_params=test_metadata.get('params', {}),
                test_results_description=res.get('message', ''),
            ))

        return elementary_results

    def detect_schema_drift(
        self,
        current_schema: dict[str, str],
        baseline_schema: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Elementary schema drift detection comparing current vs baseline columns."""
        changes: list[dict[str, Any]] = []

        # Missing columns
        for col, col_type in baseline_schema.items():
            if col not in current_schema:
                changes.append({
                    'change_type': 'column_removed',
                    'column_name': col,
                    'baseline_type': col_type,
                    'current_type': None,
                })

        # New columns
        for col, col_type in current_schema.items():
            if col not in baseline_schema:
                changes.append({
                    'change_type': 'column_added',
                    'column_name': col,
                    'baseline_type': None,
                    'current_type': col_type,
                })

        # Type changes
        for col in set(current_schema.keys()) & set(baseline_schema.keys()):
            if current_schema[col] != baseline_schema[col]:
                changes.append({
                    'change_type': 'type_changed',
                    'column_name': col,
                    'baseline_type': baseline_schema[col],
                    'current_type': current_schema[col],
                })

        return changes

    def generate_alerts(self, test_results: list[ElementaryTestResult]) -> list[ElementaryAlert]:
        alerts: list[ElementaryAlert] = []
        for tr in test_results:
            if tr.status in {'fail', 'error'}:
                severity = 'critical' if 'unique' in tr.test_name or 'not_null' in tr.test_name else 'warning'
                alerts.append(ElementaryAlert(
                    alert_id=f'alert_{tr.id}',
                    alert_type='test',
                    status=tr.status,
                    title=f'Elementary Alert: {tr.test_name} failed on {tr.table_name}',
                    description=f'Test {tr.test_name} detected {tr.failures} failures on column {tr.column_name}. Msg: {tr.test_results_description}',
                    table_name=tr.table_name,
                    column_name=tr.column_name,
                    detected_at=tr.detected_at,
                    severity=severity,
                ))
        return alerts
