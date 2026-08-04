"""
SDD Pass 106 — Module 3 BarStart v2 rolling probe window tests.
"""

from pgm_craft.workflow.module3_barstart_v2_bt import RollingProbeWindowNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_rolling_probe_window_starts_from_latest_committed_bar_start():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0])

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    window = bb.get_val("active_bar_probe_window")
    assert window["start_time"] == 4.0
    assert window["end_time"] == 9.0
    assert window["duration_sec"] == 5.0
    assert window["expected_bar_starts"] == 1
    assert bb.get_val("bar_probe_windows") == [window]
    assert bb.get_val("bar_probe_policy")["adjustment"] == "keep"


def test_rolling_probe_window_increases_and_shifts_after_not_found():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [10.0])
    bb.set_val("bar_probe_window_sec", 5.0)
    bb.set_val("last_bar_probe_result", {
        "status": "not_found",
        "window_start": 10.0,
        "window_end": 15.0,
    })

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    window = bb.get_val("active_bar_probe_window")
    assert window["start_time"] == 15.0
    assert window["end_time"] == 21.0
    assert bb.get_val("bar_probe_window_sec") == 6.0
    assert bb.get_val("bar_probe_policy")["adjustment"] == "increase_by_1s"
    assert len(bb.get_val("bar_probe_history")) == 1


def test_rolling_probe_window_decreases_after_fast_found():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [20.0])
    bb.set_val("bar_probe_window_sec", 5.0)
    bb.set_val("last_bar_probe_result", {
        "status": "found",
        "window_start": 20.0,
        "window_end": 25.0,
        "candidate_time": 21.0,
    })

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    window = bb.get_val("active_bar_probe_window")
    assert window["start_time"] == 21.0
    assert window["end_time"] == 25.0
    assert bb.get_val("bar_probe_window_sec") == 4.0
    assert bb.get_val("bar_probe_policy")["adjustment"] == "decrease_by_1s"
