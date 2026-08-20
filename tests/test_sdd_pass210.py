"""PASS-210: reconcile stale unresolved bar spans after the final grid exists."""

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    FullSongBarStartLoopNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _bb_with_expected_bar_duration():
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", [[0.0, 1], [1.543, 1], [3.086, 1]])
    return bb


def test_duplicate_candidate_is_not_counted_as_unresolved_but_is_kept_in_history():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [5.0])
    bb.set_val("active_bar_probe_window", {"start_time": 5.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [{"time": 5.0, "confidence": 0.95}])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("bar_start_decision_report")
    assert report["diagnostic_classification"] == "all_candidates_already_committed"
    assert bb.get_val("unresolved_bar_spans") == []
    assert bb.get_val("all_probe_failures_ever")[0]["diagnostic_classification"] == (
        "all_candidates_already_committed"
    )


def test_reconcile_removes_confidence_span_covered_by_normal_final_grid_interval():
    bb = _bb_with_expected_bar_duration()
    bb.set_val(
        "unresolved_bar_spans",
        [{"start_time": 100.333424, "end_time": 102.333424, "reason": "confidence_below_threshold"}],
    )
    loop = FullSongBarStartLoopNode()

    retained = loop._reconcile_unresolved_spans(
        bb,
        [98.7627, 100.3057, 101.8487, 103.3917],
    )

    assert retained == []


def test_reconcile_keeps_true_tail_gap_without_following_final_grid_bar():
    bb = _bb_with_expected_bar_duration()
    tail_span = {
        "start_time": 173.736837,
        "end_time": 176.736837,
        "reason": "no_candidates",
    }
    bb.set_val("unresolved_bar_spans", [tail_span])
    loop = FullSongBarStartLoopNode()

    retained = loop._reconcile_unresolved_spans(bb, [172.6909])

    assert retained == [tail_span]


def test_loop_report_preserves_historical_failures_after_reconciliation():
    bb = _bb_with_expected_bar_duration()
    span = {"start_time": 1.0, "end_time": 2.0, "reason": "confidence_below_threshold"}
    bb.set_val("unresolved_bar_spans", [span])
    bb.set_val("all_probe_failures_ever", [span])
    bb.set_val("committed_bar_starts", [0.0, 1.543, 3.086])
    bb.set_val("audio_duration_sec", 3.086)

    assert FullSongBarStartLoopNode(max_iterations=1).execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("full_song_loop_report")
    assert report["unresolved_span_count"] == 0
    assert report["all_probe_failures_ever"] == [span]
