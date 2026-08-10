"""PASS-201: fallback carry must participate in the promotion gate."""

from pgm_craft.workflow.module3_barstart_v2_bt import (
    FullSongBarStartLoopNode,
    evaluate_barstart_v2_completeness,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_excessive_fallback_carry_blocks_adoption():
    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[],
        carried_bar_ratio=0.85,
    )
    assert gate["adoptable"] is False
    assert "EXCESSIVE_FALLBACK_CARRY_RATIO" in gate["blockers"]
    assert gate["carried_bar_ratio"] == 0.85


def test_low_fallback_carry_does_not_block_adoption():
    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[],
        carried_bar_ratio=0.01,
    )
    assert gate["adoptable"] is True
    assert gate["blockers"] == []


def test_unresolved_span_blocker_remains_unchanged():
    gate = evaluate_barstart_v2_completeness(
        unresolved_bar_spans=[{"reason": "no_evidence"}],
        carried_bar_ratio=0.01,
    )
    assert gate["adoptable"] is False
    assert gate["blockers"] == ["UNRESOLVED_BAR_SPANS_PRESENT"]


def test_full_song_loop_reports_carried_bar_count_and_ratio():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0])
    bb.set_val("audio_duration_sec", 8.0)
    status = FullSongBarStartLoopNode(max_iterations=30, stall_limit=2).execute(bb)
    assert status == NodeStatus.SUCCESS
    report = bb.get_val("full_song_loop_report")
    assert report["carried_bar_count"] >= 1
    assert report["carried_bar_ratio"] == round(
        report["carried_bar_count"] / report["committed_bar_count"], 6
    )
