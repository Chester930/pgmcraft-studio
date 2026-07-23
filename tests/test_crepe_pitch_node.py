"""
Unit tests for CREPEPitchNode pitch tracking node.
"""

import os
import tempfile
import pytest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import CREPEPitchNode


def test_crepe_pitch_node_missing_keys():
    bb = Blackboard()
    node = CREPEPitchNode()
    missing = bb.validate_strict(node)
    assert "audio_path" in missing


def test_crepe_pitch_node_execution():
    bb = Blackboard()
    with tempfile.TemporaryDirectory() as temp_dir:
        sample_audio = os.path.join(temp_dir, "test.wav")
        sr = 22050
        y = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr))
        sf.write(sample_audio, y, sr)

        bb.set_val("audio_path", sample_audio)
        bb.set_val("output_dir", temp_dir)

        node = CREPEPitchNode()
        status = node.run(bb)

        assert status == NodeStatus.SUCCESS
        assert "vocal_pitch_midi" in bb
        assert "pitch_contour_json" in bb
        assert os.path.exists(bb["vocal_pitch_midi"])
        assert os.path.exists(bb["pitch_contour_json"])
