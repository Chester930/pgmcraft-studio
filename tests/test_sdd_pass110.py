"""
SDD Pass 110 — Module 3 BarStart v2 chord track PK and harmonic anchor tests.
"""

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    ChordTrackPKNode,
    Module3BarStartV2SummaryNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_chord_track_pk_selects_primary_harmonic_anchor_from_guitar_and_piano():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("guitar_chord_anchors", [{"time": 4.0, "confidence": 0.72, "chord": "Cmaj7"}])
    bb.set_val("piano_chord_anchors", [{"time": 4.03, "confidence": 0.8, "chord": "Cmaj7"}])

    assert ChordTrackPKNode().execute(bb) == NodeStatus.SUCCESS

    pk = bb.get_val("chord_track_pk")
    assert pk["primary_source"] == "piano_chord"
    assert pk["primary_anchor_time"] == 4.03
    assert pk["anchor_count"] == 2
    assert pk["consensus_count"] == 2
    report = bb.get_val("harmonic_anchor_evidence_report")
    assert report["status"] == "ANCHORS_BUILT"
    assert report["primary_source"] == "piano_chord"


def test_chord_track_pk_boosts_existing_drum_bass_candidate_with_harmonic_support():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {
            "time": 4.0,
            "confidence": 0.62,
            "evidence_sources": ["drums", "bass_coincidence_support"],
            "source_node": "DrumEvidenceBarSearchNode",
        }
    ])
    bb.set_val("guitar_chord_anchors", [{"time": 4.02, "confidence": 0.78, "chord": "G"}])

    assert ChordTrackPKNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["confidence"] == 0.76
    assert candidate["harmonic_support_time"] == 4.02
    assert "harmonic_anchor_support" in candidate["evidence_sources"]


def test_chord_track_pk_adds_low_confidence_harmonic_only_candidate_without_rhythm_support():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("piano_chord_anchors", [{"time": 4.0, "confidence": 0.82, "chord": "F"}])

    assert ChordTrackPKNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["time"] == 4.0
    assert candidate["confidence"] < 0.7
    assert candidate["source_node"] == "ChordTrackPKNode"
    assert candidate["uncertainty_reason"] == "harmonic_only_requires_rhythm_support"


def test_harmonic_only_candidate_stays_unresolved_at_default_commit_threshold():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("piano_chord_anchors", [{"time": 4.0, "confidence": 0.82, "chord": "F"}])

    assert ChordTrackPKNode().execute(bb) == NodeStatus.SUCCESS
    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("committed_bar_starts") == [0.0, 2.0]
    assert bb.get_val("bar_start_decision_report")["status"] == "UNRESOLVED"
    assert bb.get_val("bar_start_decision_report")["reason"] == "confidence_below_threshold"


def test_module3_barstart_v2_tree_places_chord_pk_before_commit():
    tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    names = _node_names(tree)

    assert "ChordTrackPKNode" in names
    assert names.index("DrumBassEvidenceBarSearchNode") < names.index("ChordTrackPKNode")
    assert names.index("ChordTrackPKNode") < names.index("BarStartCandidateCommitNode")


def test_module3_barstart_v2_summary_includes_chord_track_pk_report():
    bb = Blackboard()
    bb.set_val("chord_track_pk", {"primary_source": "guitar_chord"})
    bb.set_val("harmonic_anchor_evidence_report", {"status": "ANCHORS_BUILT"})

    assert Module3BarStartV2SummaryNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("barstart_v2_report")
    assert report["status"] == "EXPERIMENTAL_PASS_126"
    assert report["chord_track_pk"]["primary_source"] == "guitar_chord"
    assert report["harmonic_anchor_evidence_report"]["status"] == "ANCHORS_BUILT"
