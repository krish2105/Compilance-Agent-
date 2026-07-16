"""Operating-point / threshold analysis (production model-risk control)."""
from __future__ import annotations

import numpy as np

from eval.operating_point import _pr_operating_points


def test_operating_points_are_valid_and_hit_targets():
    rng = np.random.default_rng(0)
    # 3% base rate, a decent (not perfect) separator.
    y = (rng.random(2000) < 0.03).astype(float)
    s = np.clip(0.15 * y + rng.random(2000) * 0.5, 0, 1)
    r = _pr_operating_points(y, s)
    assert 0 < r["base_rate"] < 0.1
    for pt in r["targets"]:
        assert pt["recall"] + 1e-9 >= pt["target_recall"]   # meets its recall target
        assert 0.0 <= pt["precision"] <= 1.0
        assert 0.0 < pt["flag_rate"] <= 1.0
    # Higher target recall must require a lower threshold (monotonic).
    thrs = [pt["threshold"] for pt in r["targets"]]
    assert thrs == sorted(thrs, reverse=True)
    assert 0.0 <= r["f1_optimal"]["f1"] <= 1.0
