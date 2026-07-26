"""
Unit tests for SDD Pass 20: 3-Tier Peer Competition & Dynamic Peel-and-Subtract BT Integration
"""

import os
import numpy as np
import scipy.io.wavfile as wavfile
import pytest

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.stem_separation_bt import (
    PeelTier2HighConfidenceNode,
    PeelTier3MediumConfidenceNode,
    build_stem_separation_tree
)
from pgm_craft.separator import PeelCoreTrioStemSeparator


def _make_dummy_wav(path, duration=1.0, sr=22050):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    wavfile.write(path, sr, sig)
    return path


class MockPeelEngine(PeelCoreTrioStemSeparator):
    def probe_tier2_scores(self, audio_path):
        return {"organ": 0.88, "sub_bass_808": 0.20, "glockenspiel": 0.05}

    def run_peel_tier2_loop(self, input_residual_path, output_dir="stems", min_threshold=0.15):
        os.makedirs(output_dir, exist_ok=True)
        organ = os.path.join(output_dir, "organ.wav")
        res = os.path.join(output_dir, "residual_tier2.wav")
        _make_dummy_wav(organ)
        _make_dummy_wav(res)
        return {"organ": organ, "tier2_residual": res}

    def probe_tier3_scores(self, audio_path):
        return {"synth_pads": 0.75, "brass": 0.10, "saxophone": 0.05, "accordion": 0.02}

    def run_peel_tier3_loop(self, input_residual_path, output_dir="stems", min_threshold=0.25):
        os.makedirs(output_dir, exist_ok=True)
        synth = os.path.join(output_dir, "synth_pads.wav")
        final_res = os.path.join(output_dir, "instrumental.wav")
        _make_dummy_wav(synth)
        _make_dummy_wav(final_res)
        return {"synth_pads": synth, "final_residual": final_res}


def test_peel_tier2_high_confidence_node(tmp_path):
    res_in = _make_dummy_wav(str(tmp_path / "residual_tier1.wav"))
    stems_dir = tmp_path / "stems"
    os.makedirs(stems_dir)

    bb = Blackboard()
    bb.set_val("trio_residual_path", res_in)
    bb.set_val("stems_dir", str(stems_dir))

    node = PeelTier2HighConfidenceNode(MockPeelEngine())
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert "organ" in bb.get_val("stems", {})
    assert os.path.exists(bb.get_val("tier2_residual_path"))


def test_peel_tier3_medium_confidence_node(tmp_path):
    res_in = _make_dummy_wav(str(tmp_path / "residual_tier2.wav"))
    stems_dir = tmp_path / "stems"
    os.makedirs(stems_dir)

    bb = Blackboard()
    bb.set_val("tier2_residual_path", res_in)
    bb.set_val("stems_dir", str(stems_dir))

    node = PeelTier3MediumConfidenceNode(MockPeelEngine())
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert "synth_pads" in bb.get_val("stems", {})
    assert os.path.exists(bb.get_val("final_residual_path"))
