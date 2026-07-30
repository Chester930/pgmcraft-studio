"""
SDD Pass 107 — Module 3 BarStart v2 candidate commit contract tests.
"""

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import BarStartCandidateCommitNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_bar_start_candidate_commit_adds_best_high_confidence_candidate():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("active_bar_probe_window", {"start_time": 2.0, "end_time": 7.0})
    bb.set_val("bar_start_candidates", [
        {"time": 4.0, "confidence": 0.65, "evidence_sources": ["drums"]},
        {"time": 4.08, "confidence": 0.86, "evidence_sources": ["drums", "bass"]},
    ])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("committed_bar_starts") == [0.0, 2.0, 4.08]
    report = bb.get_val("bar_start_decision_report")
    assert report["status"] == "COMMITTED"
    assert report["committed_time"] == 4.08
    assert report["evidence_sources"] == ["drums", "bass"]
    result = bb.get_val("last_bar_probe_result")
    assert result["status"] == "found"
    assert result["candidate_offset_sec"] == 2.08


def test_bar_start_candidate_commit_records_unresolved_when_confidence_is_low():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [10.0])
    bb.set_val("active_bar_probe_window", {"start_time": 10.0, "end_time": 15.0})
    bb.set_val("bar_start_candidates", [
        {"time": 12.0, "confidence": 0.45, "evidence_sources": ["vocal"]},
    ])

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("committed_bar_starts") == [10.0]
    assert bb.get_val("bar_start_decision_report")["status"] == "UNRESOLVED"
    assert bb.get_val("bar_start_decision_report")["reason"] == "confidence_below_threshold"
    assert bb.get_val("unresolved_bar_spans")[0]["best_confidence"] == 0.45
    assert bb.get_val("last_bar_probe_result")["status"] == "uncertain"


def test_bar_start_candidate_commit_records_not_found_without_candidates():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [20.0])
    bb.set_val("active_bar_probe_window", {"start_time": 20.0, "end_time": 25.0})

    assert BarStartCandidateCommitNode().execute(bb) == NodeStatus.SUCCESS

    assert bb.get_val("bar_start_decision_report")["reason"] == "no_candidates"
    assert bb.get_val("unresolved_bar_spans")[0]["start_time"] == 20.0
    assert bb.get_val("unresolved_bar_spans")[0]["end_time"] == 25.0
    assert bb.get_val("last_bar_probe_result")["status"] == "not_found"


def test_module3_barstart_v2_tree_commits_candidates_after_probe_window():
    tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    names = _node_names(tree)

    assert "BarStartCandidateCommitNode" in names
    assert names.index("RollingProbeWindowNode") < names.index("BarStartCandidateCommitNode")
    assert names.index("BarStartCandidateCommitNode") < names.index("MeterAwareBeatGridNode")
