import os
import pytest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.beat_tracking_bt import (
    MultiModelBeatEnsembleNode,
    MicroTimingTransientSnapNode,
    build_beat_tracking_tree
)

def test_multi_model_ensemble_voting():
    bb = Blackboard()
    # Model A: beats at 0.0, 0.5, 1.0, 1.5
    beats_a = np.array([[0.0, 1], [0.505, 2], [1.0, 3], [1.502, 4]])
    # Model B: beats at 0.002, 0.495, 1.001, 1.498
    beats_b = np.array([[0.002, 1], [0.495, 2], [1.001, 3], [1.498, 4]])

    bb.set_val("beats_rhythm", beats_a)
    bb.set_val("beats_inst", beats_b)

    node = MultiModelBeatEnsembleNode(tolerance_ms=40.0)
    res = node.execute(bb)

    assert res == NodeStatus.SUCCESS
    ensemble_beats = bb.get_val("ensemble_beats")
    assert ensemble_beats is not None
    assert len(ensemble_beats) == 4
    # Consensus at beat 2: 0.65*0.505 + 0.35*0.495 = 0.5015
    assert abs(ensemble_beats[1, 0] - 0.5015) < 0.001

def test_micro_timing_transient_snap(tmp_path):
    bb = Blackboard()
    sr = 22050
    duration = 2.0
    audio = np.zeros(int(duration * sr), dtype=np.float32)

    # Create a sharp transient spike at exactly sample index 11025 (t = 0.5s)
    spike_idx = 11025
    audio[spike_idx] = 1.0

    drums_path = os.path.join(tmp_path, "drums.wav")
    sf.write(drums_path, audio, sr)

    # Approximated beat at t = 0.515s (15ms offset)
    beats = np.array([[0.515, 1]])
    bb.set_val("beats", beats)
    bb.set_val("stems", {"drums": drums_path})
    bb.set_val("sr", sr)

    node = MicroTimingTransientSnapNode(search_window_ms=35.0)
    res = node.execute(bb)

    assert res == NodeStatus.SUCCESS
    refined_beats = bb.get_val("refined_beats")
    assert refined_beats is not None
    # Snapped to t = 0.500s
    assert abs(refined_beats[0, 0] - 0.500) < 0.001

def test_build_beat_tracking_tree_contains_pass103_nodes():
    tree = build_beat_tracking_tree()
    node_names = [child.name for child in tree.children]
    assert "MultiModelBeatEnsembleNode" in node_names
    assert "MicroTimingTransientSnapNode" in node_names
