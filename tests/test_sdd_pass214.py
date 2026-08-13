"""PASS-214: RollingProbeWindowNode's search-window bounds scale with the
song's own expected bar duration instead of a fixed absolute-second window.

Root cause: the window bounds (default 5.0s, min 2.0s, max 12.0s, step 1.0s)
were hardcoded regardless of tempo. At World is Mine's ~164 BPM
(bar length ~1.4529s) that's fine -- the 2.0s floor still covers more than
one bar. But a slower song (e.g. 70 BPM, ~3.43s/bar) would get a *minimum*
search window smaller than a single bar, and a much faster song would get a
max window spanning 8-10+ bars, multiplying the close-candidate arbitration
ambiguity this subsystem already struggles with (see Pass 212's Verse1
skip-pattern investigation). The bounds are now multiples of
`_expected_bar_duration` (already used throughout this subsystem for phase
scoring), calibrated to reproduce the previous fixed values exactly at World
is Mine's verified tempo so its known-good baseline is unaffected.
"""

import numpy as np

from pgm_craft.workflow.module3_barstart_v2_bt import RollingProbeWindowNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _v1_grid(bar_duration_sec, n_bars=6):
    rows = []
    for i in range(n_bars):
        rows.append([round(i * bar_duration_sec, 6), 1])
    return np.asarray(rows, dtype=float)


def test_falls_back_to_fixed_seconds_when_no_tempo_reference_available():
    bb = Blackboard()
    bb.set_val("committed_bar_starts", [0.0, 2.0, 4.0])

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    window = bb.get_val("active_bar_probe_window")
    assert window["duration_sec"] == 5.0
    policy = bb.get_val("bar_probe_policy")
    assert policy["tempo_scaled"] is False
    assert policy["default_window_sec"] == 5.0
    assert policy["min_window_sec"] == 2.0
    assert policy["max_window_sec"] == 12.0
    assert policy["step_sec"] == 1.0


def test_reproduces_fixed_bounds_at_world_is_mine_calibration_tempo():
    bb = Blackboard()
    bar_duration = RollingProbeWindowNode._CALIBRATION_BAR_DURATION_SEC
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0, bar_duration, 2 * bar_duration])

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    policy = bb.get_val("bar_probe_policy")
    assert policy["tempo_scaled"] is True
    assert abs(policy["default_window_sec"] - 5.0) < 1e-6
    assert abs(policy["min_window_sec"] - 2.0) < 1e-6
    assert abs(policy["max_window_sec"] - 12.0) < 1e-6
    assert abs(policy["step_sec"] - 1.0) < 1e-6


def test_slow_song_gets_a_proportionally_larger_window():
    # 70 BPM, 4/4 -> ~3.4286s/bar. The old fixed 2.0s minimum would have
    # been smaller than a single bar; the scaled minimum must not be.
    bar_duration = 60.0 / 70.0 * 4.0
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0, bar_duration, 2 * bar_duration])

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    policy = bb.get_val("bar_probe_policy")
    assert policy["tempo_scaled"] is True
    assert policy["min_window_sec"] > bar_duration
    assert policy["default_window_sec"] > 5.0
    assert policy["max_window_sec"] > 12.0


def test_fast_song_gets_a_proportionally_smaller_window():
    # 200 BPM, 4/4 -> 1.2s/bar.
    bar_duration = 60.0 / 200.0 * 4.0
    bb = Blackboard()
    bb.set_val("v1_reference_beat_grid", _v1_grid(bar_duration))
    bb.set_val("committed_bar_starts", [0.0, bar_duration, 2 * bar_duration])

    assert RollingProbeWindowNode().execute(bb) == NodeStatus.SUCCESS

    policy = bb.get_val("bar_probe_policy")
    assert policy["tempo_scaled"] is True
    assert policy["min_window_sec"] < 2.0
    assert policy["default_window_sec"] < 5.0
    assert policy["max_window_sec"] < 12.0
