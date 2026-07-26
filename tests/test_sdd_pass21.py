"""
Unit tests for SDD Pass 21: CLAP Semantic Probe & Formant Safety Guard BT Integration
"""

import os
import numpy as np
import scipy.io.wavfile as wavfile
import pytest

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.stem_separation_bt import (
    CLAPSemanticProbeConditionNode,
    FormantSafetyGuardNode,
    build_stem_separation_tree
)
from pgm_craft.separator import PeelCoreTrioStemSeparator


def _make_dummy_wav(path, duration=1.0, sr=22050):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    wavfile.write(path, sr, sig)
    return path


class MockClapEngine(PeelCoreTrioStemSeparator):
    def probe_clap_semantic_similarity(self, audio_path, prompts=None):
        if "high_sim" in audio_path:
            return 0.85
        return 0.10

    def check_formant_distortion(self, orig_path, residual_path):
        if "high_dist" in residual_path:
            return 0.75
        return 0.05


def test_clap_semantic_probe_pass(tmp_path):
    wav = _make_dummy_wav(str(tmp_path / "high_sim.wav"))
    bb = Blackboard()
    bb.set_val("tier2_residual_path", wav)
    bb.set_val("stems_dir", str(tmp_path))

    node = CLAPSemanticProbeConditionNode(MockClapEngine(), min_similarity=0.35)
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert bb.get_val("clap_similarity_score") == 0.85


def test_clap_semantic_probe_skip(tmp_path):
    wav = _make_dummy_wav(str(tmp_path / "low_sim.wav"))
    bb = Blackboard()
    bb.set_val("tier2_residual_path", wav)
    bb.set_val("stems_dir", str(tmp_path))

    node = CLAPSemanticProbeConditionNode(MockClapEngine(), min_similarity=0.35)
    status = node.run(bb)
    assert status == NodeStatus.FAILURE
    assert bb.get_val("clap_similarity_score") == 0.10


def test_formant_safety_guard_rollback(tmp_path):
    orig = _make_dummy_wav(str(tmp_path / "orig.wav"))
    high_dist = _make_dummy_wav(str(tmp_path / "high_dist.wav"))

    bb = Blackboard()
    bb.set_val("tier2_residual_path", orig)
    bb.set_val("final_residual_path", high_dist)
    bb.set_val("stems_dir", str(tmp_path))
    bb.set_val("stems", {"synth_pads": high_dist, "vocals": "vocals.wav"})

    node = FormantSafetyGuardNode(MockClapEngine(), max_distortion=0.40)
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert bb.get_val("formant_guard_status") == "ROLLBACK_EXECUTED"
    assert bb.get_val("final_residual_path") == orig
    assert "synth_pads" not in bb.get_val("stems")
