"""
Unit tests for SDD Pass 19: Non-Instrumental & Speech Events BT Architecture Integration
"""

import os
import tempfile
import numpy as np
import scipy.io.wavfile as wavfile
import pytest

from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.audio_quality_bt import (
    DeHumFilterNode,
    SeparateCrowdNode,
    DeReverbFilterNode,
    build_audio_quality_tree
)
from pgm_craft.workflow.stem_separation_bt import (
    ExtractCountInVoiceNode,
    ExtractClapSnapEventsNode,
    build_stem_separation_tree
)
from pgm_craft.separator import CascadedStemSeparator


def _make_dummy_wav(path, duration=1.0, sr=22050):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sig = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    wavfile.write(path, sr, sig)
    return path


class MockSeparator(CascadedStemSeparator):
    def separate_crowd(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        c = os.path.join(output_dir, "crowd_cheering.wav")
        nc = os.path.join(output_dir, "no_crowd.wav")
        _make_dummy_wav(c)
        _make_dummy_wav(nc)
        return c, nc

    def process_dereverb(self, audio_path, output_dir, is_already_single_stem=False):
        os.makedirs(output_dir, exist_ok=True)
        d = os.path.join(output_dir, "dereverb_dry.wav")
        r = os.path.join(output_dir, "reverb_room.wav")
        _make_dummy_wav(d)
        _make_dummy_wav(r)
        return d, r

    def extract_count_in(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        ci = os.path.join(output_dir, "count_in_voice.wav")
        _make_dummy_wav(ci)
        return ci

    def extract_claps_snaps(self, audio_path, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        cs = os.path.join(output_dir, "claps_snaps.wav")
        _make_dummy_wav(cs)
        return cs


def test_dehum_filter_node():
    bb = Blackboard()
    sr = 22050
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # Add 50Hz hum noise
    y = np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 50 * t)
    bb.set_val("y", y)
    bb.set_val("sr", sr)

    node = DeHumFilterNode()
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert bb.get_val("y") is not None


def test_separate_crowd_node(tmp_path):
    audio_path = _make_dummy_wav(str(tmp_path / "test.wav"))
    bb = Blackboard()
    bb.set_val("audio_path", audio_path)
    bb.set_val("output_dir", str(tmp_path))

    node = SeparateCrowdNode(MockSeparator())
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert os.path.exists(bb.get_val("crowd_path"))


def test_dereverb_filter_node(tmp_path):
    audio_path = _make_dummy_wav(str(tmp_path / "test.wav"))
    bb = Blackboard()
    bb.set_val("audio_path", audio_path)
    bb.set_val("output_dir", str(tmp_path))

    node = DeReverbFilterNode(MockSeparator())
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert os.path.exists(bb.get_val("dereverb_dry_path"))


def test_extract_count_in_voice_node(tmp_path):
    audio_path = _make_dummy_wav(str(tmp_path / "test.wav"))
    stems_dir = tmp_path / "stems"
    os.makedirs(stems_dir)

    bb = Blackboard()
    bb.set_val("audio_path", audio_path)
    bb.set_val("stems_dir", str(stems_dir))

    node = ExtractCountInVoiceNode(MockSeparator())
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert os.path.exists(bb.get_val("count_in_path"))


def test_extract_clap_snap_events_node(tmp_path):
    inst_path = _make_dummy_wav(str(tmp_path / "instrumental.wav"))
    stems_dir = tmp_path / "stems"
    os.makedirs(stems_dir)

    bb = Blackboard()
    bb.set_val("instrumental_path", inst_path)
    bb.set_val("stems_dir", str(stems_dir))

    node = ExtractClapSnapEventsNode(MockSeparator())
    status = node.run(bb)
    assert status == NodeStatus.SUCCESS
    assert os.path.exists(bb.get_val("claps_path"))
