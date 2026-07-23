"""
Unit tests for InstrumentPresenceNode instrument presence & matrix analyzer.
"""

import os
import json
import tempfile
import pytest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import InstrumentPresenceNode


def test_instrument_presence_node_missing_keys():
    bb = Blackboard()
    node = InstrumentPresenceNode()
    missing = bb.validate_strict(node)
    assert "measure_map" in missing


def test_instrument_presence_node_execution():
    bb = Blackboard()
    with tempfile.TemporaryDirectory() as temp_dir:
        sample_audio = os.path.join(temp_dir, "test_presence.wav")
        sr = 22050
        y = np.sin(2 * np.pi * 200 * np.linspace(0, 4.0, sr * 4))
        sf.write(sample_audio, y, sr)

        bb.set_val("audio_path", sample_audio)
        bb.set_val("output_dir", temp_dir)
        bb.set_val("measure_map", [
            {"measure": 1, "start_time": 0.0, "end_time": 2.0},
            {"measure": 2, "start_time": 2.0, "end_time": 4.0},
        ])

        node = InstrumentPresenceNode()
        status = node.run(bb)

        assert status == NodeStatus.SUCCESS
        assert "instrument_matrix" in bb
        assert "instrument_presence_json" in bb

        json_path = bb["instrument_presence_json"]
        assert os.path.exists(json_path)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "instrument_presence" in data
        assert len(data["instrument_presence"]) == 2
