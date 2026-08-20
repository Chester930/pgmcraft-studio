"""PASS-206: make no-candidate causes and loop/report state observable."""

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    FullSongBarStartLoopNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_no_candidate_diagnostic_identifies_candidates_outside_probe_window():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 10.0, "end_time": 11.0})
    bb.set_val("bar_start_candidates", [{"time": 5.0, "confidence": 0.9}])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("bar_start_decision_report")
    filters = report["candidate_filter_diagnostics"]
    assert report["reason"] == "no_candidates"
    assert report["diagnostic_classification"] == "all_candidates_outside_probe_window"
    assert filters["input_candidate_count"] == 1
    assert filters["after_probe_window_count"] == 0


def test_no_candidate_diagnostic_identifies_already_committed_candidates():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [5.0])
    bb.set_val("active_bar_probe_window", {"start_time": 5.0, "end_time": 6.0})
    bb.set_val("bar_start_candidates", [{"time": 5.0, "confidence": 0.9}])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("bar_start_decision_report")
    assert report["diagnostic_classification"] == "all_candidates_already_committed"
    assert report["candidate_filter_diagnostics"]["after_duplicate_filter_count"] == 0


def test_full_song_report_owns_final_committed_state_and_run_id():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("audio_duration_sec", 2.0)

    assert FullSongBarStartLoopNode(max_iterations=2).execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("full_song_loop_report")
    assert report["run_id"] == bb.get_val("barstart_v2_run_id")
    assert report["final_committed_bar_starts"] == bb.get_val("committed_bar_starts")
    assert report["last_committed_time"] == 2.0
    assert report["diagnostic_trace"] == []

