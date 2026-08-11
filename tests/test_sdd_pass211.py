"""PASS-211: extrapolate an evidence-poor song tail from one trusted side."""

from pgm_craft.workflow.module3_barstart_v2_bt import (
    TailBarExtrapolationNode,
    evaluate_barstart_v2_completeness,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _tail_blackboard():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0, 3.0])
    bb.set_val("audio_duration_sec", 6.0)
    bb.set_val(
        "unresolved_bar_spans",
        [{"start_time": 3.1, "end_time": 6.0, "reason": "no_candidates"}],
    )
    return bb


def test_tail_extrapolation_evenly_fills_the_whole_remaining_interval():
    bb = _tail_blackboard()

    assert TailBarExtrapolationNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("tail_extrapolation_report")
    assert report["triggered"] is True
    assert report["extrapolated_bar_count"] == 3
    assert report["step_sec"] == 1.0
    assert bb.get_val("committed_bar_starts") == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert [
        round(b - a, 6)
        for a, b in zip(bb.get_val("committed_bar_starts"), bb.get_val("committed_bar_starts")[1:])
    ][-3:] == [1.0, 1.0, 1.0]


def test_tail_extrapolated_bars_are_marked_and_counted_as_non_evidence():
    bb = _tail_blackboard()
    TailBarExtrapolationNode().execute(bb)

    entries = bb.get_val("tail_extrapolated_bars")
    assert len(entries) == 3
    assert all(entry["evidence_sources"] == ["tail_extrapolation"] for entry in entries)

    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[],
        carried_bar_ratio=0.0,
        bar_grid_repair_report={},
        final_bar_count=7,
        tail_extrapolated_bar_count=len(entries),
    )
    assert gate["tail_extrapolated_bar_count"] == 3
    assert gate["non_evidence_bar_ratio"] == 0.428571
    assert gate["adoptable"] is True


def test_tail_extrapolation_skips_a_sub_half_bar_remainder():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0, 3.0])
    bb.set_val("audio_duration_sec", 3.4)
    bb.set_val(
        "unresolved_bar_spans",
        [{"start_time": 3.0, "end_time": 3.4, "reason": "no_candidates"}],
    )

    assert TailBarExtrapolationNode().execute(bb) == NodeStatus.SUCCESS
    assert bb.get_val("committed_bar_starts") == [0.0, 1.0, 2.0, 3.0]
    assert bb.get_val("tail_extrapolation_report")["triggered"] is False

def test_tail_extrapolation_requires_a_real_unresolved_tail():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0, 3.0])
    bb.set_val("audio_duration_sec", 6.0)

    assert TailBarExtrapolationNode().execute(bb) == NodeStatus.SUCCESS
    assert bb.get_val("committed_bar_starts") == [0.0, 1.0, 2.0, 3.0]
    assert bb.get_val("tail_extrapolation_report")["triggered"] is False
