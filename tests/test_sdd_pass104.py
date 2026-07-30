"""
SDD Pass 104 — 鼓過門密集擊點排除區與 Click Snap 防追逐測試
"""

import os

import numpy as np
import soundfile as sf

from pgm_craft.workflow.beat_tracking_bt import (
    DrumFillDetectionNode,
    MicroTimingTransientSnapNode,
    OnsetPhaseRealignmentNode,
    build_beat_tracking_tree,
)
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_drum_fill_detection_marks_dense_subdivision_region():
    bb = Blackboard()
    beats = np.array([
        [0.0, 1],
        [0.5, 2],
        [1.0, 3],
        [1.5, 4],
        [2.0, 1],
    ])
    bb.set_val("beats", beats)
    bb.set_val("kick_anchors", np.array([1.0, 1.125, 1.25, 1.375]))
    bb.set_val("snare_anchors", np.array([]))

    node = DrumFillDetectionNode(min_events_per_beat=4, padding_sec=0.02)
    status = node.execute(bb)

    assert status == NodeStatus.SUCCESS
    regions = bb.get_val("drum_fill_regions")
    assert regions
    assert regions[0]["start_time"] <= 1.0
    assert regions[0]["end_time"] >= 1.5
    assert any(zone["reason"] == "drum_fill_dense_subdivision" for zone in bb.get_val("snap_exclusion_zones"))
    assert bb.get_val("drum_fill_report")["status"] == "DETECTED"


def test_onset_phase_realignment_ignores_fill_exclusion_window():
    bb = Blackboard()
    sr = 22050
    audio = np.zeros(int(2.0 * sr), dtype=np.float32)
    audio[int(1.025 * sr): int(1.025 * sr) + 128] = 1.0

    bb.set_val("y", audio)
    bb.set_val("sr", sr)
    bb.set_val("beats", np.array([[1.0, 1]]))
    bb.set_val("snap_exclusion_zones", [{"start_time": 0.98, "end_time": 1.06, "reason": "drum_fill_dense_subdivision"}])

    node = OnsetPhaseRealignmentNode(search_window_ms=35.0)
    status = node.execute(bb)

    assert status == NodeStatus.SUCCESS
    assert abs(bb.get_val("beats")[0, 0] - 1.0) < 0.0001
    assert bb.get_val("phase_realignment_report")["skipped_exclusion_count"] == 1


def test_micro_timing_snap_ignores_fill_exclusion_window(tmp_path):
    bb = Blackboard()
    sr = 22050
    audio = np.zeros(int(2.0 * sr), dtype=np.float32)
    audio[int(1.025 * sr)] = 1.0

    drums_path = os.path.join(tmp_path, "drums.wav")
    sf.write(drums_path, audio, sr)

    bb.set_val("beats", np.array([[1.0, 1]]))
    bb.set_val("stems", {"drums": drums_path})
    bb.set_val("sr", sr)
    bb.set_val("snap_exclusion_zones", [{"start_time": 0.98, "end_time": 1.06, "reason": "drum_fill_dense_subdivision"}])

    node = MicroTimingTransientSnapNode(search_window_ms=35.0)
    status = node.execute(bb)

    assert status == NodeStatus.SUCCESS
    assert abs(bb.get_val("refined_beats")[0, 0] - 1.0) < 0.0001
    assert bb.get_val("snap_skip_report")["skipped_exclusion_count"] == 1
    assert bb.get_val("snap_offsets_ms") == []


def test_build_beat_tracking_tree_contains_pass104_fill_guard_before_snap_nodes():
    tree = build_beat_tracking_tree()
    node_names = [child.name for child in tree.children]

    assert "DrumFillDetectionNode" in node_names
    assert node_names.index("DrumFillDetectionNode") < node_names.index("OnsetPhaseRealignmentNode")
    assert node_names.index("DrumFillDetectionNode") < node_names.index("MicroTimingTransientSnapNode")
