"""PASS-211: extrapolate an evidence-poor song tail from one trusted side."""

import numpy as np
import soundfile as sf

from pgm_craft.workflow.module3_barstart_v2_bt import (
    TailBarExtrapolationNode,
    evaluate_barstart_v2_completeness,
)
from pgm_craft.workflow.module3_bt import (
    Module3BarStartV2MergeNode,
    _barstart_v2_promotion_decision,
    _synchronize_barstart_v2_loop_report,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _tail_blackboard():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0, 3.0])
    bb.set_val("audio_duration_sec", 6.0)
    bb.set_val(
        "unresolved_bar_spans",
        [{"start_time": 3.1, "end_time": 6.0, "reason": "no_candidates"}],
    )
    return bb


def test_tail_extrapolation_evenly_fills_the_whole_remaining_interval():
    bb = _tail_blackboard()

    assert TailBarExtrapolationNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("tail_extrapolation_report")
    assert report["triggered"] is True
    assert report["extrapolated_bar_count"] == 3
    assert report["step_sec"] == 1.0
    assert bb.get_val("committed_bar_starts") == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert [
        round(b - a, 6)
        for a, b in zip(bb.get_val("committed_bar_starts"), bb.get_val("committed_bar_starts")[1:])
    ][-3:] == [1.0, 1.0, 1.0]


def test_tail_extrapolated_bars_are_marked_and_counted_as_non_evidence():
    bb = _tail_blackboard()
    TailBarExtrapolationNode().execute(bb)

    entries = bb.get_val("tail_extrapolated_bars")
    assert len(entries) == 3
    assert all(entry["evidence_sources"] == ["tail_extrapolation"] for entry in entries)

    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[],
        carried_bar_ratio=0.0,
        bar_grid_repair_report={},
        final_bar_count=7,
        tail_extrapolated_bar_count=len(entries),
    )
    assert gate["tail_extrapolated_bar_count"] == 3
    assert gate["non_evidence_bar_ratio"] == 0.428571
    assert gate["adoptable"] is True


def test_tail_extrapolation_skips_a_sub_half_bar_remainder():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0, 3.0])
    bb.set_val("audio_duration_sec", 3.4)
    bb.set_val(
        "unresolved_bar_spans",
        [{"start_time": 3.0, "end_time": 3.4, "reason": "no_candidates"}],
    )

    assert TailBarExtrapolationNode().execute(bb) == NodeStatus.SUCCESS
    assert bb.get_val("committed_bar_starts") == [0.0, 1.0, 2.0, 3.0]
    assert bb.get_val("tail_extrapolation_report")["triggered"] is False

def test_tail_extrapolation_requires_a_real_unresolved_tail():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 1.0, 2.0, 3.0])
    bb.set_val("audio_duration_sec", 6.0)

    assert TailBarExtrapolationNode().execute(bb) == NodeStatus.SUCCESS
    assert bb.get_val("committed_bar_starts") == [0.0, 1.0, 2.0, 3.0]
    assert bb.get_val("tail_extrapolation_report")["triggered"] is False


def test_adoptable_gate_does_not_auto_promote_without_manual_approval():
    gate = {"adoptable": True, "status": "V2_READY", "blockers": []}

    decision = _barstart_v2_promotion_decision(gate, manual_approval=False)

    assert decision["gate_adoptable"] is True
    assert decision["manual_approval"] is False
    assert decision["promoted"] is False
    assert decision["reason"] == "MANUAL_APPROVAL_REQUIRED"


def test_loop_report_separates_loop_output_from_downstream_repairs():
    report = _synchronize_barstart_v2_loop_report(
        {
            "final_committed_bar_starts": [0.0, 1.0, 2.0],
            "committed_bar_count": 3,
            "last_committed_time": 2.0,
        },
        [0.0, 1.0, 2.0, 3.0],
    )

    assert report["loop_final_committed_bar_starts"] == [0.0, 1.0, 2.0]
    assert report["final_committed_bar_starts"] == [0.0, 1.0, 2.0, 3.0]
    assert report["committed_bar_count"] == 4
    assert report["last_committed_time"] == 3.0


def test_merge_reports_adoptable_but_keeps_legacy_default_without_approval(
    tmp_path, monkeypatch
):
    audio_path = tmp_path / "source.wav"
    sf.write(audio_path, np.zeros(22050 * 2, dtype=np.float32), 22050)
    original = np.array([[0.0, 1], [0.5, 2], [1.0, 3], [1.5, 4]], dtype=float)
    v2 = np.array([[0.0, 1], [0.25, 2], [0.5, 3], [0.75, 4]], dtype=float)

    monkeypatch.setattr(
        "pgm_craft.workflow.module3_bt._run_barstart_v2_comparison",
        lambda blackboard: {
            "success": True,
            "original_beat_grid": original,
            "v2_beat_grid": v2,
            "original_quality": {"score": 80.0},
            "v2_quality": {"score": 79.0},
            "unresolved_spans": [],
            "bar_grid_repair_report": {},
            "committed_bar_starts": [0.0, 1.0],
            "full_song_loop_report": {
                "final_committed_bar_starts": [0.0, 1.0],
                "carried_bar_ratio": 0.0,
                "tail_extrapolated_bar_count": 0,
            },
            "state_consistency": {
                "committed_bar_starts_match_loop_report": True,
            },
        },
    )

    bb = Blackboard()
    bb.set_val("beats", original.copy())
    bb.set_val("refined_beats", original.copy())
    bb.set_val("audio_path", str(audio_path))
    bb.set_val("project_dir", str(tmp_path))

    assert Module3BarStartV2MergeNode().execute(bb) == NodeStatus.SUCCESS
    report = bb.get_val("barstart_v2_report")

    assert report["promotion_gate"]["adoptable"] is True
    assert report["promotion_decision"]["reason"] == "MANUAL_APPROVAL_REQUIRED"
    assert report["status"] == "COMPARED_NOT_PROMOTED"
    assert report["replaces_module3_click"] is False
    np.testing.assert_array_equal(bb.get_val("beats"), original)


def test_workflow_engine_threads_promotion_approval_into_blackboard(monkeypatch):
    """barstart_v2_promotion_approved must reach the blackboard unchanged so a
    caller can explicitly opt a specific run into promotion, without flipping
    the default for every other invocation (which stays unset/False)."""
    from pgm_craft.workflow.builder import BTWorkflowEngine

    engine = BTWorkflowEngine(target_stage="module3")
    captured = {}

    def fake_run(blackboard):
        captured["value"] = blackboard.get_val("barstart_v2_promotion_approved")
        return NodeStatus.SUCCESS

    monkeypatch.setattr(engine.tree, "run", fake_run)

    blackboard = engine.run(
        audio_path="unused.wav",
        target_stage="module3",
        barstart_v2_promotion_approved=True,
    )

    assert captured["value"] is True
    assert blackboard.get_val("barstart_v2_promotion_approved") is True


def test_workflow_engine_leaves_promotion_approval_unset_by_default(monkeypatch):
    from pgm_craft.workflow.builder import BTWorkflowEngine

    engine = BTWorkflowEngine(target_stage="module3")
    captured = {}

    def fake_run(blackboard):
        captured["value"] = blackboard.get_val("barstart_v2_promotion_approved", "UNSET")
        return NodeStatus.SUCCESS

    monkeypatch.setattr(engine.tree, "run", fake_run)

    engine.run(audio_path="unused.wav", target_stage="module3")

    assert captured["value"] == "UNSET"
