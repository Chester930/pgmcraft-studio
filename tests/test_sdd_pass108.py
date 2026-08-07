"""
SDD Pass 108 — Module 3 BarStart v2 drum evidence candidate tests.
"""

from pgm_craft.workflow.module3_barstart_v2_bt import DrumEvidenceBarSearchNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_drum_evidence_builds_high_confidence_candidate_from_kick_snare_support():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("kick_anchors", [4.01])
    bb.set_val("snare_anchors", [5.0])

    assert DrumEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS

    candidates = bb.get_val("bar_start_candidates")
    assert len(candidates) == 1
    assert candidates[0]["time"] == 4.01
    assert candidates[0]["confidence"] >= 0.9
    assert "expected_bar_interval" in candidates[0]["evidence_sources"]
    assert "snare_backbeat_support" in candidates[0]["evidence_sources"]
    assert bb.get_val("drum_bar_evidence_report")["status"] == "CANDIDATES_BUILT"


def test_drum_evidence_penalizes_candidates_inside_fill_exclusion():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("kick_anchors", [4.0])
    bb.set_val("snare_anchors", [5.0])
    bb.set_val("drum_fill_regions", [{"start_time": 3.9, "end_time": 4.1, "reason": "dense_fill"}])

    assert DrumEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["confidence"] < 0.7
    assert candidate["uncertainty_reason"] == "inside_drum_fill_or_snap_exclusion"
    assert "exclusion_penalty" in candidate["evidence_sources"]


def test_drum_evidence_falls_back_to_low_confidence_drum_onset_without_kick():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [10.0])
    bb.set_val("active_bar_probe_window", {"start_time": 10.0, "end_time": 15.0})
    bb.set_val("drum_onset_candidates", [12.5])

    assert DrumEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["time"] == 12.5
    assert 0.0 < candidate["confidence"] < 0.7
    assert candidate["source_node"] == "DrumEvidenceBarSearchNode"
