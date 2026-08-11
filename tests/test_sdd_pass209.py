"""PASS-209: probe windows must not create unresolved spans past audio end."""

from pgm_craft.workflow.module3_barstart_v2_bt import FullSongBarStartLoopNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _fake_tick_sequence(loop, windows):
    calls = []

    def fake_run(blackboard, parent=None):
        index = len(calls)
        calls.append(index)
        window = windows[index]
        blackboard.set_val("active_bar_probe_window", window)
        blackboard.set_val(
            "bar_start_decision_report",
            {"status": "not_found", "reason": "no_candidates"},
        )
        unresolved = list(blackboard.get_val("unresolved_bar_spans", []) or [])
        unresolved.append({"tick": index + 1, "window_start": window["start_time"]})
        blackboard.set_val("unresolved_bar_spans", unresolved)

    loop._tick.run = fake_run
    return calls


def test_probe_window_past_duration_stops_without_recording_more_unresolved():
    blackboard = Blackboard()
    blackboard.set_val("committed_bar_starts", [0.0, 2.0])
    blackboard.set_val("audio_duration_sec", 10.0)
    loop = FullSongBarStartLoopNode(max_iterations=4, stall_limit=99)
    calls = _fake_tick_sequence(
        loop,
        [
            {"start_time": 1.0, "end_time": 5.0},
            {"start_time": 5.0, "end_time": 10.0},
            {"start_time": 10.0, "end_time": 15.0},
            {"start_time": 15.0, "end_time": 20.0},
        ],
    )

    status = loop.execute(blackboard)

    assert status == NodeStatus.SUCCESS
    assert len(calls) == 3
    assert blackboard.get_val("full_song_loop_report")["stop_reason"] == "reached_audio_duration"
    assert blackboard.get_val("full_song_loop_report")["unresolved_span_count"] == 2
    assert len(blackboard.get_val("full_song_loop_report")["diagnostic_trace"]) == 2


def test_committed_bar_already_at_duration_keeps_existing_stop_behavior():
    blackboard = Blackboard()
    blackboard.set_val("committed_bar_starts", [0.0, 9.95])
    blackboard.set_val("audio_duration_sec", 10.0)
    loop = FullSongBarStartLoopNode(max_iterations=4, stall_limit=99)
    calls = _fake_tick_sequence(
        loop,
        [{"start_time": 9.95, "end_time": 14.95}],
    )

    status = loop.execute(blackboard)

    assert status == NodeStatus.SUCCESS
    assert calls == []
    assert blackboard.get_val("full_song_loop_report")["stop_reason"] == "reached_audio_duration"
    assert blackboard.get_val("full_song_loop_report")["unresolved_span_count"] == 0
