"""PASS-205: quality regression must tolerate skipped whole bars, not off-grid jumps."""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _blackboard_with_expected_bar_duration():
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", np.array([
        [0.0, 1],
        [1.45, 1],
        [2.90, 1],
    ], dtype=float))
    bb.set_val("candidate_commit_confidence_threshold", 0.7)
    return bb


def test_quality_regression_allows_reasonable_multi_bar_jump():
    """A candidate exactly two expected bars after the last commit is valid."""
    bb = _blackboard_with_expected_bar_duration()
    bb.set_val("committed_bar_starts", [0.0, 1.45, 2.90])
    bb.set_val("active_bar_probe_window", {"start_time": 2.90, "end_time": 6.0})
    bb.set_val("bar_start_candidates", [{
        "candidate_id": "two-bars-forward",
        "time": 5.80,
        "confidence": 1.0,
        "evidence_sources": ["drums"],
    }])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("bar_start_decision_report")
    assert report["status"] == "COMMITTED"
    assert report["phase_alignment"]["is_reasonable_bar_multiple"] is True
    assert report["phase_alignment"]["bar_multiple"] == 2
    assert bb.get_val("committed_bar_starts") == [0.0, 1.45, 2.9, 5.8]


def test_quality_regression_still_rejects_off_grid_jump():
    """A large off-grid jump remains protected by quality_regression."""
    bb = _blackboard_with_expected_bar_duration()
    original = [0.0, 1.45, 2.90]
    bb.set_val("committed_bar_starts", original)
    bb.set_val("active_bar_probe_window", {"start_time": 2.90, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [{
        "candidate_id": "off-grid",
        "time": 6.525,  # 2.5 expected bars after the last commit
        "confidence": 1.0,
        "evidence_sources": ["drums"],
    }])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("bar_start_decision_report")
    assert report["status"] == "UNRESOLVED"
    assert report["reason"] == "quality_regression"
    assert report["phase_alignment"]["is_reasonable_bar_multiple"] is False
    assert bb.get_val("committed_bar_starts") == original
