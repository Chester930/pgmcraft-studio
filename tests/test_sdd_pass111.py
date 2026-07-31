"""
SDD Pass 111 — Module 3 BarStart v2 melody track PK and phrase/count evidence tests.
"""

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    MelodyTrackPKNode,
    Module3BarStartV2SummaryNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_melody_track_pk_selects_primary_phrase_anchor_from_vocal_piano_guitar():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("vocal_melody_anchors", [{"time": 4.0, "confidence": 0.76, "phrase": "entry"}])
    bb.set_val("piano_melody_anchors", [{"time": 4.02, "confidence": 0.68, "phrase": "pickup"}])
    bb.set_val("guitar_melody_anchors", [{"time": 5.5, "confidence": 0.6, "phrase": "riff"}])

    assert MelodyTrackPKNode().execute(bb) == NodeStatus.SUCCESS

    pk = bb.get_val("melody_track_pk")
    assert pk["primary_source"] == "vocal_melody"
    assert pk["primary_anchor_time"] == 4.0
    assert pk["anchor_count"] == 3
    assert pk["consensus_count"] == 2
    assert bb.get_val("phrase_anchor_evidence_report")["status"] == "ANCHORS_BUILT"


def test_melody_track_pk_boosts_existing_candidate_as_phrase_support_only():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {
            "time": 4.0,
            "confidence": 0.64,
            "evidence_sources": ["drums", "harmonic_anchor_support"],
            "source_node": "DrumEvidenceBarSearchNode",
        }
    ])
    bb.set_val("vocal_melody_anchors", [{"time": 4.03, "confidence": 0.8, "phrase": "vocal_entry"}])

    assert MelodyTrackPKNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["confidence"] == 0.72
    assert candidate["phrase_support_time"] == 4.03
    assert "phrase_anchor_support" in candidate["evidence_sources"]


def test_melody_track_pk_adds_low_confidence_phrase_only_candidate():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("vocal_melody_anchors", [{"time": 4.0, "confidence": 0.85, "phrase": "entry"}])

    assert MelodyTrackPKNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["time"] == 4.0
    assert candidate["confidence"] < 0.7
    assert candidate["source_node"] == "MelodyTrackPKNode"
    assert candidate["uncertainty_reason"] == "phrase_only_requires_rhythm_or_harmonic_support"


def test_phrase_only_candidate_stays_unresolved_at_default_commit_threshold():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("vocal_melody_anchors", [{"time": 4.0, "confidence": 0.9, "phrase": "entry"}])

    assert MelodyTrackPKNode().execute(bb) == NodeStatus.SUCCESS
    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("committed_bar_starts") == [0.0, 2.0]
    assert bb.get_val("bar_start_decision_report")["status"] == "UNRESOLVED"
    assert bb.get_val("bar_start_decision_report")["reason"] == "confidence_below_threshold"


def test_module3_barstart_v2_tree_places_melody_pk_before_commit():
    tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    names = _node_names(tree)

    assert "MelodyTrackPKNode" in names
    assert names.index("ChordTrackPKNode") < names.index("MelodyTrackPKNode")
    assert names.index("MelodyTrackPKNode") < names.index("BarStartCandidateCommitNode")


def test_module3_barstart_v2_summary_includes_melody_track_pk_report():
    bb = Blackboard()
    bb.set_val("melody_track_pk", {"primary_source": "vocal_melody"})
    bb.set_val("phrase_anchor_evidence_report", {"status": "ANCHORS_BUILT"})

    assert Module3BarStartV2SummaryNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("barstart_v2_report")
    assert report["status"] == "EXPERIMENTAL_PASS_129"
    assert report["melody_track_pk"]["primary_source"] == "vocal_melody"
    assert report["phrase_anchor_evidence_report"]["status"] == "ANCHORS_BUILT"
