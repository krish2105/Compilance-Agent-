"""
Eval-gate test — runs the deterministic evaluation pipeline and asserts the CI
gates hold. This makes eval-driven development part of the test suite itself.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval import metrics as M  # noqa: E402
from eval.run_eval import run  # noqa: E402


def test_eval_gates_pass():
    summary = run()
    failed = [g for g in summary["gates"] if not g["passed"]]
    assert not failed, f"eval gates failed: {failed}"


def test_key_metrics_meet_expectations():
    summary = run()
    o = summary["overall"]
    assert o["typology_top3"] == 1.0, "correct typology must always be in top-3"
    assert o["faithfulness"] >= 0.95
    assert o["citation_validity"] == 1.0
    assert o["hallucination_rate"] == 0.0
    assert o["verifier_catch_rate"] == 1.0


def test_gate_definitions_are_sane():
    # Guard against accidentally weakening the gates.
    assert M.GATES["faithfulness"] == (">=", 0.95)
    assert M.GATES["hallucination_rate"] == ("<=", 0.0)
