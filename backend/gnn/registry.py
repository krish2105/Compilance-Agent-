"""
Lightweight model registry (MLflow-style).

Versions each trained model with its params, metrics, and a **model card**, in a
JSON registry ($0, no server). If MLflow is installed and `MLFLOW_TRACKING_URI` is
set, runs are ALSO logged there — so the same call works locally and against a real
MLflow server (the documented production path).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REGISTRY = Path(__file__).resolve().parent / "registry.json"


def _load() -> List[Dict[str, Any]]:
    if _REGISTRY.exists():
        try:
            return json.loads(_REGISTRY.read_text())
        except json.JSONDecodeError:
            return []
    return []


def register(name: str, params: Dict[str, Any], metrics: Dict[str, Any],
             card: Dict[str, Any]) -> Dict[str, Any]:
    entries = _load()
    version = len(entries) + 1
    entry = {
        "name": name, "version": version, "stage": "Production",
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "params": params, "metrics": metrics, "model_card": card,
    }
    # Demote previous versions.
    for e in entries:
        e["stage"] = "Archived"
    entries.append(entry)
    _REGISTRY.write_text(json.dumps(entries, indent=2))

    # Optional: mirror to a real MLflow server if configured.
    _log_mlflow(name, version, params, metrics)
    return entry


def _log_mlflow(name, version, params, metrics) -> None:
    import os
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        return
    try:
        import mlflow  # noqa: F401

        with mlflow.start_run(run_name=f"{name}-v{version}"):
            mlflow.log_params({k: str(v) for k, v in params.items()})
            mlflow.log_metrics({k: float(v) for k, v in metrics.items()
                                if isinstance(v, (int, float))})
    except Exception:  # noqa: BLE001 - never fail training on telemetry
        pass


def list_versions() -> List[Dict[str, Any]]:
    return _load()


def latest() -> Dict[str, Any]:
    entries = _load()
    return entries[-1] if entries else {}
