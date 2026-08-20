"""PASS-208: downstream grid repairs must participate in the promotion gate."""

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartTempoSmoothingNode,
    evaluate_barstart_v2_completeness,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_inserted_grid_bars_block_adoption_even_without_fallback_carry():
    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[],
        carried_bar_ratio=0.01,
        bar_grid_repair_report={
            "inserted_bar_count": 6,
            "bar_count_after": 10,
        },
    )

    assert gate["adoptable"] is False
    assert gate["carried_bar_ratio"] == 0.01
    assert gate["bar_grid_inserted_count"] == 6
    assert gate["repaired_bar_ratio"] == 0.6
    assert "EXCESSIVE_BAR_GRID_REPAIR_RATIO" in gate["blockers"]
    assert "EXCESSIVE_NON_EVIDENCE_BAR_RATIO" in gate["blockers"]


def test_small_grid_repair_ratio_does_not_block_adoption():
    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[],
        carried_bar_ratio=0.01,
        bar_grid_repair_report={
            "inserted_bar_count": 1,
            "bar_count_after": 10,
        },
    )

    assert gate["adoptable"] is True
    assert gate["repaired_bar_ratio"] == 0.1
    assert gate["non_evidence_bar_ratio"] == 0.11


def test_tempo_smoothing_does_not_create_short_gap_before_protected_anchor():
    blackboard = Blackboard()
    original = [0.0, 1.0, 2.0, 3.0, 4.0, 5.5, 7.0, 8.5]
    blackboard.set_val("committed_bar_starts", original)
    blackboard.set_val("kick_anchors", [4.0])
    blackboard.set_val("snare_anchors", [])

    status = BarStartTempoSmoothingNode().execute(blackboard)

    assert status == NodeStatus.SUCCESS
    repaired = blackboard.get_val("committed_bar_starts")
    intervals = [repaired[i] - repaired[i - 1] for i in range(1, len(repaired))]
    assert min(intervals) >= 0.75
    assert max(intervals) <= 2.25


def test_tempo_smoothing_rejects_anchor_snap_residual_gap():
    blackboard = Blackboard()
    original = [
        0.0,
        1.784919,
        2.901928,
        3.761071,
        4.74556,
        5.817917,
        7.035555,
        8.559126,
        9.57675,
        10.621986,
        12.091713,
        12.948525,
        14.231304,
    ]
    blackboard.set_val("committed_bar_starts", original)
    blackboard.set_val("kick_anchors", [9.57675])
    blackboard.set_val("snare_anchors", [])

    BarStartTempoSmoothingNode().execute(blackboard)

    repaired = blackboard.get_val("committed_bar_starts")
    intervals = [repaired[i] - repaired[i - 1] for i in range(1, len(repaired))]
    assert min(intervals) >= 0.5
    assert max(intervals) <= 2.5
