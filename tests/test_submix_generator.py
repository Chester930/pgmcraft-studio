"""
Unit tests for SubMixGeneratorNode (Targeted Sub-Mix Synthesis)
"""

import os
import pytest
import numpy as np
import scipy.io.wavfile as wavfile
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_nodes import SubMixGeneratorNode


@pytest.fixture
def dummy_stems(tmp_path):
    sr = 22050
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)

    stems = {}
    for name in ["drums", "bass", "guitar", "piano", "vocals", "other"]:
        p = tmp_path / f"{name}.wav"
        wavfile.write(str(p), sr, audio)
        stems[name] = str(p)

    return stems, str(tmp_path / "audio.wav")


def test_submix_generator_node(dummy_stems, tmp_path):
    stems, audio_path = dummy_stems
    node = SubMixGeneratorNode()

    blackboard = Blackboard()
    blackboard.set_val("audio_path", audio_path)
    blackboard.set_val("stems", stems)
    blackboard.set_val("output_dir", str(tmp_path))

    status = node.execute(blackboard)
    assert status == NodeStatus.SUCCESS

    rhythm_submix = blackboard.get_val("rhythm_submix")
    harmonic_submix = blackboard.get_val("harmonic_submix")
    structure_submix = blackboard.get_val("structure_submix")

    assert os.path.exists(rhythm_submix)
    assert os.path.exists(harmonic_submix)
    assert os.path.exists(structure_submix)
