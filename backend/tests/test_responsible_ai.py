"""
Responsible-AI tests: red-team suite, golden-set groundedness, fairness audit, judge.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import orchestrator  # noqa: E402
from app.config import settings  # noqa: E402
from app.data_pipeline import build_database  # noqa: E402
from app.tools import audit  # noqa: E402
from eval import fairness, judge, redteam  # noqa: E402


def _setup():
    if not os.path.exists(settings.duckdb_path):
        build_database()
    audit.init_db()


def test_redteam_all_blocked_or_safe():
    _setup()
    r = orchestrator.run_case("CASE-0001")
    out = redteam.run_redteam(r, "CASE-0001")
    assert out["pass_rate"] == 1.0, out["outcomes"]


def test_deterministic_judge():
    v = judge.deterministic_judge("This is a structuring case.", ["structuring"])
    assert v["verdict"] == "pass"
    v2 = judge.deterministic_judge("Unrelated text.", ["structuring"])
    assert v2["verdict"] == "fail"


def test_fairness_audit_computes():
    records = [{"group": "UAE", "risk": 0.9}, {"group": "UAE", "risk": 0.8},
               {"group": "India", "risk": 0.3}, {"group": "India", "risk": 0.2}]
    a = fairness.audit(records)
    assert "disparate_impact_ratio" in a
    assert a["groups"]["UAE"]["flag_rate"] == 1.0
    assert a["groups"]["India"]["flag_rate"] == 0.0
    assert a["concern_flag"] is True  # 0.0/1.0 -> DI ratio 0 < 0.8


def test_sampling_policy_prioritises_failures():
    assert judge.should_sample({"case_id": "X", "verification": {"passed": False}})
    assert judge.should_sample({"case_id": "X", "metrics": {"total_cost_usd": 0.01}})
