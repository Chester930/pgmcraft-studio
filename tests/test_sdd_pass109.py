"""
SDD Pass 109 — Module 3 BarStart v2 drums + bass evidence tests.
"""

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import (
    BarStartCandidateCommitNode,
    DrumBassEvidenceBarSearchNode,
    Module3BarStartV2SummaryNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_drum_bass_evidence_boosts_drum_candidate_with_nearby_bass_anchor():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {
            "time": 4.0,
            "confidence": 0.78,
            "evidence_sources": ["drums", "kick", "expected_bar_interval"],
            "source_node": "DrumEvidenceBarSearchNode",
        }
    ])
    bb.set_val("bass_anchors", [4.04])

    assert DrumBassEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["confidence"] == 0.9
    assert candidate["bass_support_time"] == 4.04
    assert "bass_coincidence_support" in candidate["evidence_sources"]
    report = bb.get_val("drum_bass_evidence_report")
    assert report["status"] == "UPDATED"
    assert report["boosted_candidate_count"] == 1
    assert report["bass_only_candidate_count"] == 0


def test_drum_bass_evidence_does_not_boost_when_bass_is_outside_tolerance():
    bb = Blackboard()
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {
            "time": 4.0,
            "confidence": 0.78,
            "evidence_sources": ["drums", "kick"],
            "source_node": "DrumEvidenceBarSearchNode",
        }
    ])
    bb.set_val("bass_anchors", [4.2])

    assert DrumBassEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS

    candidate = bb.get_val("bar_start_candidates")[0]
    assert candidate["confidence"] == 0.78
    assert "bass_support_time" not in candidate
    assert bb.get_val("drum_bass_evidence_report")["status"] == "NO_BASS_SUPPORT"


def test_drum_bass_evidence_adds_low_confidence_bass_only_when_no_drum_candidate_exists():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {
            "time": 4.5,
            "confidence": 0.5,
            "evidence_sources": ["vocal_phrase"],
            "source_node": "VocalPhraseEvidenceNode",
        }
    ])
    bb.set_val("bass_onset_candidates", [4.0, 8.0])

    assert DrumBassEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS

    candidates = bb.get_val("bar_start_candidates")
    bass_only = [item for item in candidates if item["source_node"] == "DrumBassEvidenceBarSearchNode"]
    assert len(bass_only) == 1
    assert bass_only[0]["time"] == 4.0
    assert bass_only[0]["confidence"] < 0.7
    assert bass_only[0]["uncertainty_reason"] == "bass_only_requires_other_support"
    assert "expected_bar_interval" in bass_only[0]["evidence_sources"]
    assert bb.get_val("drum_bass_evidence_report")["bass_only_candidate_count"] == 1


def test_bass_only_candidate_stays_unresolved_at_default_commit_threshold():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bass_anchors", [4.0])

    assert DrumBassEvidenceBarSearchNode().execute(bb) == NodeStatus.SUCCESS
    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("committed_bar_starts") == [0.0, 2.0]
    assert bb.get_val("bar_start_decision_report")["status"] == "UNRESOLVED"
    assert bb.get_val("bar_start_decision_report")["reason"] == "confidence_below_threshold"


def test_module3_barstart_v2_tree_places_drum_bass_evidence_before_commit():
    tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    names = _node_names(tree)

    assert "DrumBassEvidenceBarSearchNode" in names
    assert names.index("DrumEvidenceBarSearchNode") < names.index("DrumBassEvidenceBarSearchNode")
    assert names.index("DrumBassEvidenceBarSearchNode") < names.index("BarStartCandidateCommitNode")


def test_module3_barstart_v2_summary_includes_drum_bass_report():
    bb = Blackboard()
    bb.set_val("drum_bass_evidence_report", {"status": "UPDATED", "boosted_candidate_count": 1})

    assert Module3BarStartV2SummaryNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("barstart_v2_report")
    assert report["status"] == "EXPERIMENTAL_PASS_126"
    assert report["drum_bass_evidence_report"]["boosted_candidate_count"] == 1
    assert bb.get_val("module3_outputs")["barstart_v2_report"]["drum_bass_evidence_report"]["status"] == "UPDATED"
