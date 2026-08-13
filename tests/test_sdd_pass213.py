"""PASS-213: bar-grid repairs are reported (count + exact positions) but no
longer deducted from barstart_v2_quality_score.

The previous min(8.0, repaired_count*2.0) formula had no documented
rationale for either constant (git blame traces both to the original Pass
118-125 bundle commit with no explanation), and its hard cap made the score
identically insensitive to 4 repaired bars vs 40 -- exactly the range that
matters for a real song (World is Mine has 19). Whether a repair-heavy grid
is acceptable is already a promotion-gate decision
(evaluate_barstart_v2_completeness, which reads bar_grid_repair_report/
non_evidence_bar_ratio directly and is unaffected by this change), so it
should not also be folded into this single number.
"""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarGridContinuityRepairNode,
    BarStartV2QualityScoreNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _clean_beats(n_bars=8):
    rows = []
    for bar in range(n_bars):
        for beat in range(4):
            t = bar * 2.0 + beat * 0.5
            rows.append([t, beat + 1])
    return np.asarray(rows, dtype=float)


def test_bar_grid_repair_report_now_lists_exact_positions():
    bb = Blackboard()
    # bars at 0,2,4,6 regular; 6->10 skips a detection (should insert ~8);
    # 10,10.05 is a near-duplicate (10.05 dropped).
    bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0, 6.0, 10.0, 10.05, 12.0])
    status = BarGridContinuityRepairNode().execute(bb)
    assert status == NodeStatus.SUCCESS

    report = bb.get_val("bar_grid_repair_report")
    assert report["status"] == "REPAIRED"
    assert report["inserted_bar_count"] == 1
    assert report["inserted_bar_times"] == [8.0]
    assert report["removed_bar_count"] == 1
    assert report["removed_bar_times"] == [10.05]
    assert report["oscillation_damped_bars"] == []


def test_repaired_grid_no_longer_reduces_score_but_is_surfaced():
    bb = Blackboard()
    bb.set_val("beats", _clean_beats())
    bb.set_val("bar_grid_repair_report", {
        "status": "REPAIRED",
        "inserted_bar_count": 19,
        "removed_bar_count": 0,
        "oscillation_damped_count": 0,
        "inserted_bar_times": [1.1, 2.2, 3.3],
        "removed_bar_times": [],
        "oscillation_damped_bars": [],
    })

    clean_bb = Blackboard()
    clean_bb.set_val("beats", _clean_beats())
    BarStartV2QualityScoreNode().execute(clean_bb)
    clean_result = clean_bb.get_val("barstart_v2_quality_score")

    status = BarStartV2QualityScoreNode().execute(bb)
    assert status == NodeStatus.SUCCESS
    result = bb.get_val("barstart_v2_quality_score")

    # A heavily repaired grid (19 repairs, far past the old cap-4 threshold)
    # must score identically to a clean grid -- the repair itself is no
    # longer a scoring input.
    assert result["score"] == clean_result["score"]
    assert "bar_grid_repairs=19" in result["warnings"]
    assert result["repaired_bar_count"] == 3
    assert result["repaired_bar_times"] == [1.1, 2.2, 3.3]


def test_unresolved_spans_and_rotation_still_reduce_score():
    bb = Blackboard()
    bb.set_val("beats", _clean_beats())
    bb.set_val("unresolved_bar_spans", [{"start_time": 4.0, "end_time": 6.0}])
    bb.set_val("downbeat_fix_report", {"status": "ROTATED", "rotated_beat_count": 2})

    clean_bb = Blackboard()
    clean_bb.set_val("beats", _clean_beats())
    BarStartV2QualityScoreNode().execute(clean_bb)
    clean_result = clean_bb.get_val("barstart_v2_quality_score")

    status = BarStartV2QualityScoreNode().execute(bb)
    assert status == NodeStatus.SUCCESS
    result = bb.get_val("barstart_v2_quality_score")

    assert result["score"] == round(clean_result["score"] - 5.0 - 3.0, 2)
