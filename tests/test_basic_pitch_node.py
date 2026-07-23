"""
Unit tests for BasicPitchNode AI melody transcription node.
"""

import os
import tempfile
import pytest
import numpy as np
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import BasicPitchNode


def test_basic_pitch_node_contract_missing_keys():
    bb = Blackboard()
    node = BasicPitchNode()
    missing = bb.validate_strict(node)

    assert "audio_path" in missing
    assert "beats" in missing


def test_basic_pitch_node_execution():
    bb = Blackboard()
    with tempfile.TemporaryDirectory() as temp_dir:
        # 準備測試檔案與節拍
        sample_audio = os.path.join(temp_dir, "test.wav")
        import soundfile as sf
        sr = 22050
        y = np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr))
        sf.write(sample_audio, y, sr)

        bb.set_val("audio_path", sample_audio)
        bb.set_val("beats", [(0.0, 1), (0.5, 2), (1.0, 1)])
        bb.set_val("output_dir", temp_dir)

        node = BasicPitchNode()
        status = node.run(bb)

        assert status == NodeStatus.SUCCESS
        assert "melody_lead_midi" in bb
        assert os.path.exists(bb["melody_lead_midi"])
