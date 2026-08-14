"""PASS-215: LookaheadDrumEventScanNode's lookahead horizon scales with the
song's own expected bar duration instead of a fixed 30.0s.

Same class of problem as Pass 214's RollingProbeWindowNode: a fixed
wall-clock horizon covers a different number of bars depending on tempo. A
slower song gets fewer bars of lookahead reach for the same 30s window; a
faster song gets proportionally more candidate noise for
LookaheadDrumAnchorSearchNode to sift through. The multiple is calibrated
to reproduce the previous fixed 30.0s exactly at World is Mine's verified
tempo, matching Pass 214's approach and constant.

Also verifies the same report-wiring discipline Pass 213 established: a new
diagnostic field is worthless if it never reaches the file a user actually
opens. bar_probe_policy (Pass 214) and lookahead_scan_report (this pass)
are both snapshotted into full_song_loop_report as final_probe_policy /
final_lookahead_scan_report, which was already confirmed (Pass 213) to
survive all the way to the real production report.
"""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import (
    LookaheadDrumEventScanNode,
    RollingProbeWindowNode,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _v1_grid(bar_duration_sec, n_bars=6):
    rows = []
    for i in range(n_bars):
        rows.append([round(i * bar_duration_sec, 6), 1])
    return np.asarray(rows, dtype=float)


def test_falls_back_to_fixed_seconds_when_no_tempo_reference_available():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0])
    bb.set_val("kick_anchors", np.array([5.0, 40.0]))

    assert LookaheadDrumEventScanNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("lookahead_scan_report")
    assert report["source"] == "fixed_fallback"
    assert report["horizon_sec"] == 30.0
    events = bb.get_val("lookahead_drum_events")
    assert [e["time"] for e in events] == [5.0]  # 40.0 is past the fixed 30s horizon


def test_reproduces_fixed_horizon_at_world_is_mine_calibration_tempo():
    bar_duration = RollingProbeWindowNode._CALIBRATION_BAR_DURATION_SEC
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0])

    assert LookaheadDrumEventScanNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("lookahead_scan_report")
    assert report["source"] == "tempo_scaled"
    assert abs(report["horizon_sec"] - 30.0) < 1e-6


def test_slow_song_gets_a_proportionally_larger_horizon():
    # 70 BPM, 4/4 -> ~3.4286s/bar.
    bar_duration = 60.0 / 70.0 * 4.0
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0])

    assert LookaheadDrumEventScanNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("lookahead_scan_report")
    assert report["source"] == "tempo_scaled"
    assert report["horizon_sec"] > 30.0


def test_fast_song_gets_a_proportionally_smaller_horizon():
    # 200 BPM, 4/4 -> 1.2s/bar.
    bar_duration = 60.0 / 200.0 * 4.0
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0])

    assert LookaheadDrumEventScanNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("lookahead_scan_report")
    assert report["source"] == "tempo_scaled"
    assert report["horizon_sec"] < 30.0


def test_explicit_override_still_wins_over_tempo_scaling():
    bar_duration = 60.0 / 70.0 * 4.0
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0])
    bb.set_val("lookahead_horizon_sec", 12.0)
    bb.set_val("kick_anchors", np.array([15.0]))

    assert LookaheadDrumEventScanNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("lookahead_scan_report")
    assert report["source"] == "explicit_override"
    assert report["horizon_sec"] == 12.0
    assert bb.get_val("lookahead_drum_events") == []  # 15.0 is past the 12s override
