"""
Unit tests for HybridPitchNode dual-pitch fusion MIDI node.
"""

import os
import tempfile
import pytest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import HybridPitchNode


def test_hybrid_pitch_node_missing_keys():
    bb = Blackboard()
    node = HybridPitchNode()
    missing = bb.validate_strict(node)
    assert "audio_path" in missing


def test_hybrid_pitch_node_execution():
    bb = Blackboard()
    with tempfile.TemporaryDirectory() as temp_dir:
        sample_audio = os.path.join(temp_dir, "test_hybrid.wav")
        sr = 22050
        y = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr))
        sf.write(sample_audio, y, sr)

        bb.set_val("audio_path", sample_audio)
        bb.set_val("output_dir", temp_dir)
        bb.set_val("beats", np.array([0.0, 0.5, 1.0]))

        node = HybridPitchNode()
        status = node.run(bb)

        assert status == NodeStatus.SUCCESS
        assert "vocal_lead_quantized_midi" in bb

        midi_path = bb["vocal_lead_quantized_midi"]
        assert os.path.exists(midi_path)
