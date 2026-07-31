"""
SDD Pass 112 — Module 3 BarStart v2 Beat This! optional candidate adapter tests.
"""

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    BeatThisCandidateAdapterNode,
    Module3BarStartV2SummaryNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_beat_this_adapter_adds_downbeat_candidate_inside_active_window():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("beat_this_beats", [[3.0, 2], [4.0, 1], [5.0, 2]])

    assert BeatThisCandidateAdapterNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["time"] == 4.0
    assert candidate["confidence"] >= 0.7
    assert candidate["source_node"] == "BeatThisCandidateAdapterNode"
    assert "beat_this_downbeat" in candidate["evidence_sources"]
    assert "expected_bar_interval" in candidate["evidence_sources"]
    report = bb.get_val("beat_this_candidate_report")
    assert report["status"] == "CANDIDATES_BUILT"
    assert report["candidate_count"] == 1


def test_beat_this_adapter_boosts_existing_candidate_near_downbeat():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {
            "time": 4.02,
            "confidence": 0.66,
            "evidence_sources": ["drums", "harmonic_anchor_support"],
            "source_node": "DrumEvidenceBarSearchNode",
        }
    ])
    bb.set_val("beat_this_downbeats", [4.0])

    assert BeatThisCandidateAdapterNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["confidence"] == 0.82
    assert candidate["beat_this_support_time"] == 4.0
    assert "beat_this_downbeat_support" in candidate["evidence_sources"]


def test_beat_this_adapter_commits_high_confidence_downbeat_candidate():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("beat_this_downbeats", [{"time": 4.0, "confidence": 0.9}])

    assert BeatThisCandidateAdapterNode().execute(bb) == NodeStatus.SUCCESS
    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("committed_bar_starts") == [0.0, 2.0, 4.0]
    assert bb.get_val("bar_start_decision_report")["status"] == "COMMITTED"


def test_beat_this_adapter_skips_gracefully_without_candidates_or_model():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})

    assert BeatThisCandidateAdapterNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("bar_start_candidates", []) == []
    report = bb.get_val("beat_this_candidate_report")
    assert report["status"] == "SKIPPED_NO_BEAT_THIS_CANDIDATES"
    assert report["fallback"] == "BeatNet/Librosa candidates remain authoritative"


def test_module3_barstart_v2_tree_places_beat_this_adapter_before_commit():
    tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    names = _node_names(tree)

    assert "BeatThisCandidateAdapterNode" in names
    assert names.index("MelodyTrackPKNode") < names.index("BeatThisCandidateAdapterNode")
    assert names.index("BeatThisCandidateAdapterNode") < names.index("BarStartCandidateCommitNode")


def test_module3_barstart_v2_summary_includes_beat_this_report():
    bb = Blackboard()
    bb.set_val("beat_this_candidate_report", {"status": "CANDIDATES_BUILT", "candidate_count": 1})

    assert Module3BarStartV2SummaryNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("barstart_v2_report")
    assert report["status"] == "EXPERIMENTAL_PASS_126"
    assert report["beat_this_candidate_report"]["candidate_count"] == 1
