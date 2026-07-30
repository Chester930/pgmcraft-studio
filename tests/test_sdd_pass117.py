"""SDD Pass 117 - lookahead and bidirectional bar anchoring tests."""

from pgm_craft.workflow.module3_barstart_v2_bt import (
    BidirectionalBarAlignmentNode,
    InterveningBarCountEstimatorNode,
    LookaheadDrumAnchorSearchNode,
    NoDrumPhaseCarryNode,
    ReliableBarAnchorNode,
    TransitionConfidenceNode,
)
from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _run(nodes, blackboard):
    for node in nodes:
        assert node.execute(blackboard) == NodeStatus.SUCCESS


def _base_blackboard():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0])
    bb.set_val("meter_profile", {"meter": "4/4", "beats_per_bar": 4})
    bb.set_val("bar_duration_sec", 2.0)
    bb.set_val("lookahead_drum_events", [{"time": 8.0, "confidence": 0.95}])
    return bb


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_v2_pipeline_places_lookahead_ladder_before_commit():
    names = _node_names(build_master_pipeline_tree(target_stage="module3_barstart_v2"))
    for name in [
        "ReliableBarAnchorNode",
        "LookaheadDrumAnchorSearchNode",
        "NoDrumPhaseCarryNode",
        "InterveningBarCountEstimatorNode",
        "BidirectionalBarAlignmentNode",
        "TransitionConfidenceNode",
    ]:
        assert name in names
        assert names.index(name) < names.index("BarStartCandidateCommitNode")


def test_four_bar_no_drum_span_is_carried_and_aligned():
    bb = _base_blackboard()
    _run([
        ReliableBarAnchorNode(),
        LookaheadDrumAnchorSearchNode(),
        NoDrumPhaseCarryNode(),
        InterveningBarCountEstimatorNode(),
        BidirectionalBarAlignmentNode(),
    ], bb)

    assert bb.get_val("provisional_bar_starts") == [2.0, 4.0, 6.0]
    assert bb.get_val("selected_intervening_bar_count")["bar_count"] == 4
    assert bb.get_val("bidirectional_alignment_report")["status"] == "ALIGNED"
    assert [item["time"] for item in bb.get_val("bar_start_candidates")][-4:] == [2.0, 4.0, 6.0, 8.0]


def test_pickup_is_candidate_only_and_not_committed_alignment():
    bb = _base_blackboard()
    bb.set_val("lookahead_drum_events", [{"time": 8.0, "confidence": 0.95, "is_fill_or_pickup": True}])
    _run([
        ReliableBarAnchorNode(),
        LookaheadDrumAnchorSearchNode(),
        InterveningBarCountEstimatorNode(),
        BidirectionalBarAlignmentNode(),
    ], bb)
    report = bb.get_val("bidirectional_alignment_report")
    assert report["status"] == "PICKUP_CANDIDATE_ONLY"
    assert bb.get_val("bar_start_candidates") == []


def test_weak_beat_entry_does_not_force_phase_reset():
    bb = _base_blackboard()
    bb.set_val("lookahead_drum_events", [{"time": 8.0, "confidence": 0.5}])
    _run([ReliableBarAnchorNode(), LookaheadDrumAnchorSearchNode(), InterveningBarCountEstimatorNode(), BidirectionalBarAlignmentNode()], bb)
    assert bb.get_val("bidirectional_alignment_report")["status"] == "ALIGNED"
    assert bb.get_val("bar_start_candidates") == []


def test_transition_requires_two_stable_observed_bars_for_high_confidence():
    bb = _base_blackboard()
    bb.set_val("bidirectional_alignment_report", {"status": "ALIGNED", "phase_error_sec": 0.02})
    bb.set_val("transition_observed_bars", 1)
    assert TransitionConfidenceNode().execute(bb) == NodeStatus.SUCCESS
    assert bb.get_val("transition_confidence_report")["can_promote"] is False

    bb.set_val("transition_observed_bars", 2)
    assert TransitionConfidenceNode().execute(bb) == NodeStatus.SUCCESS
    assert bb.get_val("transition_confidence_report")["status"] == "HIGH"


def test_lookahead_pending_is_graceful_when_future_drum_is_missing():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0])
    bb.set_val("meter_profile", {"meter": "6/8", "beats_per_bar": 6})
    bb.set_val("bar_duration_sec", 3.0)
    _run([ReliableBarAnchorNode(), LookaheadDrumAnchorSearchNode(), NoDrumPhaseCarryNode(), InterveningBarCountEstimatorNode(), BidirectionalBarAlignmentNode()], bb)
    assert bb.get_val("lookahead_anchor_report")["status"] == "LOOKAHEAD_PENDING"
    assert bb.get_val("bidirectional_alignment_report")["status"] == "LOOKAHEAD_PENDING"
